
"""
Module 5: Newton-Raphson AC load-flow solver.

Features:
    - Slack, PV and PQ buses
    - Constant PQ, Z, I and ZIP loads
    - Analytical sparse Jacobian
    - Sparse LU linear solving
    - Flat-start initialization
    - Model-based initialization (default)
    - Warm start from a previous solution
    - Generator voltage setpoints
    - Backtracking line search
    - Convergence history
    - Network connectivity validation

Conventions:
    Power: per unit
    Voltage magnitude: per unit
    Internal voltage angles: radians
    Result voltage angles: degrees

Generator reactive-power limit enforcement is
handled separately by Module 6.
"""

from dataclasses import dataclass, field
import warnings

import numpy as np

from scipy.sparse.linalg import (
    MatrixRankWarning,
    spsolve,
)

from loadflow.models import Network
from loadflow.ybus import build_ybus

from loadflow.power import (
    calculate_power,
    calculate_load_power,
    specified_power,
    get_bus_types,
    calculate_mismatch,
    maximum_mismatch,
)

from loadflow.jacobian import build_jacobian


@dataclass
class LoadFlowResult:
    """Container for load-flow solution results."""

    converged: bool
    iterations: int
    vm: np.ndarray
    va: np.ndarray
    p_calc: np.ndarray
    q_calc: np.ndarray
    mismatch: float
    bus_index: dict
    message: str
    mismatch_history: list = field(
        default_factory=list
    )


def _initial_voltages(network, bus_index):
    """
    Prepare initial voltages using network data.

    Returns
    -------
    vm : numpy.ndarray
        Voltage magnitudes in pu.

    va : numpy.ndarray
        Voltage angles in radians.
    """

    n = len(bus_index)

    vm = np.ones(n, dtype=float)
    va = np.zeros(n, dtype=float)

    bus_lookup = {
        bus.number: bus
        for bus in network.buses
        if bus.in_service
    }

    for number, i in bus_index.items():
        bus = bus_lookup[number]

        vm[i] = bus.vm
        va[i] = np.deg2rad(bus.va)

    # Apply PV generator voltage setpoints.
    for gen in network.generators:

        if not gen.in_service:
            continue

        if gen.bus not in bus_index:
            raise ValueError(
                f"Generator bus {gen.bus} is inactive"
            )

        bus = bus_lookup[gen.bus]

        if bus.bus_type == "PV":
            vm[bus_index[gen.bus]] = gen.vg

    # Apply slack voltage reference.
    for grid in network.external_grids:

        if not grid.in_service:
            continue

        if grid.bus not in bus_index:
            raise ValueError(
                f"External grid bus {grid.bus} is inactive"
            )

        bus = bus_lookup[grid.bus]

        if bus.bus_type != "Slack":
            raise ValueError(
                "External grid must be on slack bus"
            )

        i = bus_index[grid.bus]

        vm[i] = grid.vm
        va[i] = np.deg2rad(grid.va)

    return vm, va


def _flat_start_voltages(network, bus_index):
    """
    Initialize non-reference angles to zero
    and PQ voltage magnitudes to 1 pu.

    Preserve PV and slack voltage setpoints.
    """

    vm, va = _initial_voltages(
        network,
        bus_index,
    )

    slack, pv, pq = get_bus_types(
        network,
        bus_index,
    )

    va[pv] = 0.0
    va[pq] = 0.0

    vm[pq] = 1.0

    return vm, va


def _previous_solution_voltages(
    network,
    bus_index,
    previous_result,
):
    """
    Initialize from a previous LoadFlowResult.

    Bus voltages are mapped by bus number,
    not by array position.

    Previous result angles are in degrees.
    """

    if previous_result is None:
        raise ValueError(
            "Previous result is required "
            "for warm-start initialization"
        )

    if not previous_result.converged:
        raise ValueError(
            "Previous load-flow result "
            "must have converged"
        )

    vm, va = _initial_voltages(
        network,
        bus_index,
    )

    previous_index = previous_result.bus_index

    for number, i in bus_index.items():

        if number not in previous_index:
            raise ValueError(
                f"Bus {number} is missing "
                "from previous solution"
            )

        j = previous_index[number]

        vm[i] = previous_result.vm[j]
        va[i] = np.deg2rad(
            previous_result.va[j]
        )

    # Restore fixed PV/slack voltage references
    # for the current network.
    reference_vm, reference_va = (
        _initial_voltages(
            network,
            bus_index,
        )
    )

    slack, pv, pq = get_bus_types(
        network,
        bus_index,
    )

    vm[pv] = reference_vm[pv]

    vm[slack] = reference_vm[slack]
    va[slack] = reference_va[slack]

    return vm, va


def _validate_initial_voltages(vm, va):
    """Validate initial voltage state."""

    if vm.ndim != 1 or va.ndim != 1:
        raise ValueError(
            "Initial voltage arrays must be 1D"
        )

    if vm.shape != va.shape:
        raise ValueError(
            "Initial voltage dimensions do not match"
        )

    if not np.all(np.isfinite(vm)):
        raise ValueError(
            "Invalid initial voltage magnitude"
        )

    if not np.all(np.isfinite(va)):
        raise ValueError(
            "Invalid initial voltage angle"
        )

    if np.any(vm <= 0):
        raise ValueError(
            "Initial voltage magnitudes "
            "must be positive"
        )


def _validate_connectivity(ybus, slack):
    """
    Verify every active bus is connected
    to the slack bus through the Ybus graph.
    """

    nbus = ybus.shape[0]

    adjacency = [
        set()
        for _ in range(nbus)
    ]

    y_coo = ybus.tocoo()

    for i, j, value in zip(
        y_coo.row,
        y_coo.col,
        y_coo.data,
    ):

        if i != j and abs(value) > 0:
            adjacency[i].add(j)
            adjacency[j].add(i)

    visited = {
        int(slack[0])
    }

    stack = [
        int(slack[0])
    ]

    while stack:

        i = stack.pop()

        for j in adjacency[i]:

            if j not in visited:
                visited.add(j)
                stack.append(j)

    if len(visited) != nbus:
        raise ValueError(
            "Network has buses disconnected "
            "from the slack bus"
        )


def _power_state(
    network,
    bus_index,
    ybus,
    vm,
    va,
    pv,
    pq,
):
    """
    Evaluate voltage-dependent specified
    injections and NR mismatches.

    Returns
    -------
    mismatch, p_calc, q_calc, dp_load_dv,
    dq_load_dv
    """

    p_spec, q_spec = specified_power(
        network,
        bus_index,
        vm=vm,
    )

    mismatch, p_calc, q_calc = (
        calculate_mismatch(
            ybus,
            vm,
            va,
            p_spec,
            q_spec,
            pv,
            pq,
        )
    )

    (
        _,
        _,
        dp_load_dv,
        dq_load_dv,
    ) = calculate_load_power(
        network,
        bus_index,
        vm,
    )

    return (
        mismatch,
        p_calc,
        q_calc,
        dp_load_dv,
        dq_load_dv,
    )


def solve_load_flow(
    network: Network,
    tolerance=1e-8,
    max_iterations=30,
    verbose=False,
    initialization="model",
    previous_result=None,
):
    """
    Solve AC power flow using Newton-Raphson.

    Parameters
    ----------
    network : Network
        Electrical network.

    tolerance : float
        Maximum power mismatch in pu.

    max_iterations : int
        Maximum Newton corrections.

    verbose : bool
        Print convergence information.

    initialization : str
        "model"    - use bus initial values.
        "flat"     - flat start.
        "previous" - use previous solution.

    previous_result : LoadFlowResult, optional
        Required for initialization="previous".

    Returns
    -------
    LoadFlowResult
    """

    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError(
            "Tolerance must be positive and finite"
        )

    if (
        isinstance(max_iterations, bool)
        or not isinstance(
            max_iterations,
            (int, np.integer),
        )
        or max_iterations < 0
    ):
        raise ValueError(
            "max_iterations must be "
            "a nonnegative integer"
        )

    if initialization not in (
        "model",
        "flat",
        "previous",
    ):
        raise ValueError(
            "initialization must be "
            "'model', 'flat', or 'previous'"
        )

    # Build sparse bus admittance matrix.
    ybus, bus_index = build_ybus(network)

    if not bus_index:
        raise ValueError(
            "Network has no active buses"
        )

    slack, pv, pq = get_bus_types(
        network,
        bus_index,
    )

    _validate_connectivity(
        ybus,
        slack,
    )

    # Initialize bus voltages.
    if initialization == "model":

        vm, va = _initial_voltages(
            network,
            bus_index,
        )

    elif initialization == "flat":

        vm, va = _flat_start_voltages(
            network,
            bus_index,
        )

    else:

        vm, va = _previous_solution_voltages(
            network,
            bus_index,
            previous_result,
        )

    _validate_initial_voltages(vm, va)

    angle_buses = np.concatenate(
        (pv, pq)
    )

    n_angle = len(angle_buses)

    history = []
    converged = False
    message = "Maximum iterations reached"

    iterations = 0

    for iteration in range(
        max_iterations + 1
    ):

        (
            mismatch,
            p_calc,
            q_calc,
            dp_load_dv,
            dq_load_dv,
        ) = _power_state(
            network,
            bus_index,
            ybus,
            vm,
            va,
            pv,
            pq,
        )

        error = maximum_mismatch(
            mismatch
        )

        history.append(error)

        if verbose:
            print(
                f"Iteration {iteration:2d}: "
                f"maximum mismatch = "
                f"{error:.10e} pu"
            )

        if error < tolerance:
            converged = True
            message = "Load flow converged"
            break

        if iteration == max_iterations:
            break

        # Analytical sparse Jacobian,
        # including ZIP derivatives.
        jacobian = build_jacobian(
            ybus,
            vm,
            va,
            pv,
            pq,
            dp_load_dv=dp_load_dv,
            dq_load_dv=dq_load_dv,
        )

        # Sparse linear system.
        try:

            with warnings.catch_warnings():

                warnings.simplefilter(
                    "error",
                    MatrixRankWarning,
                )

                correction = spsolve(
                    jacobian,
                    mismatch,
                )

        except (
            MatrixRankWarning,
            ValueError,
            RuntimeError,
        ):

            message = (
                "Jacobian is singular or "
                "the linear solve failed"
            )

            break

        correction = np.atleast_1d(
            np.asarray(
                correction,
                dtype=float,
            )
        )

        if not np.all(
            np.isfinite(correction)
        ):

            message = (
                "Newton correction contains "
                "non-finite values"
            )

            break

        # Backtracking line search.
        step = 1.0
        accepted = False

        for _ in range(20):

            trial_vm = vm.copy()
            trial_va = va.copy()

            trial_va[angle_buses] += (
                step
                * correction[:n_angle]
            )

            trial_vm[pq] += (
                step
                * correction[n_angle:]
            )

            if np.any(trial_vm <= 0):
                step *= 0.5
                continue

            (
                trial_mismatch,
                _,
                _,
                _,
                _,
            ) = _power_state(
                network,
                bus_index,
                ybus,
                trial_vm,
                trial_va,
                pv,
                pq,
            )

            trial_error = maximum_mismatch(
                trial_mismatch
            )

            if (
                np.isfinite(trial_error)
                and trial_error < error
            ):

                vm = trial_vm
                va = trial_va

                accepted = True
                iterations += 1
                break

            step *= 0.5

        if not accepted:

            message = (
                "Newton step failed to reduce "
                "the mismatch"
            )

            break

    # Final network injections.
    p_calc, q_calc = calculate_power(
        ybus,
        vm,
        va,
    )

    final_state = _power_state(
        network,
        bus_index,
        ybus,
        vm,
        va,
        pv,
        pq,
    )

    final_error = maximum_mismatch(
        final_state[0]
    )

    return LoadFlowResult(
        converged=converged,
        iterations=iterations,
        vm=vm.copy(),
        va=np.rad2deg(va),
        p_calc=p_calc,
        q_calc=q_calc,
        mismatch=final_error,
        bus_index=bus_index.copy(),
        message=message,
        mismatch_history=history,
    )
