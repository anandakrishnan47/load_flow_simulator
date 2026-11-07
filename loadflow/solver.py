
"""
Module 5: Newton-Raphson AC load-flow solver.

Uses:
    Module 1 - Network data models
    Module 2 - Sparse Ybus
    Module 3 - Power mismatches
    Module 4 - Analytical sparse Jacobian

Conventions:
    Power: per unit
    Voltage magnitude: per unit
    Internal voltage angle: radians
    Result voltage angle: degrees

This version supports:
    One slack bus
    PV and PQ buses
    Constant-power loads
    Fixed generator voltage set points
    Sparse Newton-Raphson iterations

Generator Q-limit switching is Module 6.
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
    Prepare initial voltage magnitudes and angles.

    Returns voltage arrays in Ybus ordering.
    """
    n = len(bus_index)

    vm = np.ones(n, dtype=float)
    va = np.zeros(n, dtype=float)

    # Read initial values from the bus models.
    for bus in network.buses:
        if not bus.in_service:
            continue

        i = bus_index[bus.number]

        vm[i] = bus.vm
        va[i] = np.deg2rad(bus.va)

    # Apply PV generator voltage set points.
    for gen in network.generators:
        if not gen.in_service:
            continue

        if gen.bus not in bus_index:
            raise ValueError(
                f"Generator bus {gen.bus} is inactive"
            )

        i = bus_index[gen.bus]

        bus = next(
            b for b in network.buses
            if b.number == gen.bus
        )

        if bus.bus_type == "PV":
            vm[i] = gen.vg

    # Apply slack voltage reference.
    for grid in network.external_grids:
        if not grid.in_service:
            continue

        if grid.bus not in bus_index:
            raise ValueError(
                f"External grid bus {grid.bus} is inactive"
            )

        i = bus_index[grid.bus]

        bus = next(
            b for b in network.buses
            if b.number == grid.bus
        )

        if bus.bus_type != "Slack":
            raise ValueError(
                "External grid must be on slack bus"
            )

        vm[i] = grid.vm
        va[i] = np.deg2rad(grid.va)

    return vm, va


def solve_load_flow(
    network: Network,
    tolerance=1e-8,
    max_iterations=30,
    verbose=False,
):
    """
    Solve the AC power-flow equations using
    Newton-Raphson iterations.

    Parameters
    ----------
    network : Network
        Electrical network from Module 1.
    tolerance : float
        Maximum acceptable power mismatch in pu.
    max_iterations : int
        Maximum number of Newton corrections.
    verbose : bool
        Print iteration information.

    Returns
    -------
    LoadFlowResult
        Convergence status, bus voltages, calculated
        injections, iteration count, and diagnostics.

    Notes
    -----
    The Jacobian is the derivative of calculated
    power injections.

    Therefore:
        J * correction = specified - calculated
        state_new = state_old + correction
    """

    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError(
            "Tolerance must be positive and finite"
        )

    if (
        isinstance(max_iterations, bool)
        or not isinstance(
            max_iterations, (int, np.integer)
        )
        or max_iterations < 0
    ):
        raise ValueError(
            "max_iterations must be a nonnegative integer"
        )

    # Module 2: Build sparse Ybus.
    ybus, bus_index = build_ybus(network)

    if not bus_index:
        raise ValueError(
            "Network has no active buses"
        )

    # Module 3: Determine bus classifications.
    slack, pv, pq = get_bus_types(
        network, bus_index
    )

    # Validate that the reduced system is connected
    # to the slack reference through the Ybus graph.
    nbus = len(bus_index)
    adjacency = [set() for _ in range(nbus)]

    y_coo = ybus.tocoo()

    for i, j, value in zip(
        y_coo.row, y_coo.col, y_coo.data
    ):
        if i != j and abs(value) > 0:
            adjacency[i].add(j)
            adjacency[j].add(i)

    visited = {int(slack[0])}
    stack = [int(slack[0])]

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

    # Prepare specified net injections.
    p_spec, q_spec = specified_power(
        network, bus_index
    )

    # Initial voltage conditions.
    vm, va = _initial_voltages(
        network, bus_index
    )

    if (
        not np.all(np.isfinite(vm))
        or not np.all(np.isfinite(va))
        or np.any(vm <= 0)
    ):
        raise ValueError(
            "Invalid initial bus voltages"
        )

    # Unknown angle indices: PV followed by PQ.
    angle_buses = np.concatenate((pv, pq))

    n_angle = len(angle_buses)

    history = []
    converged = False
    message = "Maximum iterations reached"

    iterations = 0

    for iteration in range(max_iterations + 1):

        # Module 3: Calculate power mismatch.
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

        error = maximum_mismatch(mismatch)
        history.append(error)

        if verbose:
            print(
                f"Iteration {iteration:2d}: "
                f"maximum mismatch = {error:.10e} pu"
            )

        # Stop if the solution has converged.
        if error < tolerance:
            converged = True
            message = "Load flow converged"
            break

        # No more Newton corrections allowed.
        if iteration == max_iterations:
            break

        # Module 4: Analytical Jacobian.
        jacobian = build_jacobian(
            ybus, vm, va, pv, pq
        )

        # Solve sparse linear correction system.
        try:
            with warnings.catch_warnings():
                warnings.simplefilter(
                    "error", MatrixRankWarning
                )

                correction = spsolve(
                    jacobian, mismatch
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
            np.asarray(correction, dtype=float)
        )

        if not np.all(np.isfinite(correction)):
            message = (
                "Newton correction contains "
                "non-finite values"
            )
            break

        # Backtracking line search:
        # Accept a trial only when it reduces
        # the maximum power mismatch.
        step = 1.0
        accepted = False

        for _ in range(20):
            trial_vm = vm.copy()
            trial_va = va.copy()

            trial_va[angle_buses] += (
                step * correction[:n_angle]
            )

            trial_vm[pq] += (
                step * correction[n_angle:]
            )

            # Reject nonphysical voltages.
            if np.any(trial_vm <= 0):
                step *= 0.5
                continue

            trial_mismatch, _, _ = (
                calculate_mismatch(
                    ybus,
                    trial_vm,
                    trial_va,
                    p_spec,
                    q_spec,
                    pv,
                    pq,
                )
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

    # Recalculate injections at final voltages.
    p_calc, q_calc = calculate_power(
        ybus, vm, va
    )

    final_mismatch, _, _ = calculate_mismatch(
        ybus,
        vm,
        va,
        p_spec,
        q_spec,
        pv,
        pq,
    )

    final_error = maximum_mismatch(
        final_mismatch
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
