
"""
Module 6: Generator reactive-power limit enforcement.

Features:
    - PV-to-PQ switching at generator Q limits
    - Optional PQ-to-PV restoration
    - ZIP load compatibility
    - Warm-started Newton-Raphson solutions
    - Switching event history
    - Original network remains unchanged

Assumptions:
    - Exactly one in-service generator per PV bus
    - Slack generator Q limits are not enforced
    - Generator Q limits are expressed in MVAr
    - Voltage angles in LoadFlowResult are degrees

The restoration logic is based on the voltage
at a Q-limited PQ bus:

    At Qmax:
        Restore PV if Vbus > Vset + tolerance

    At Qmin:
        Restore PV if Vbus < Vset - tolerance

This corresponds to a generator whose reactive
output increases when its terminal voltage
falls below the voltage setpoint.

Restoration is disabled by default to preserve
the original one-way switching behavior.
"""

from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np

from loadflow.models import Network

from loadflow.power import calculate_load_power

from loadflow.solver import (
    LoadFlowResult,
    solve_load_flow,
)


@dataclass
class QLimitResult:
    """Result of load flow with Q-limit enforcement."""

    converged: bool
    load_flow: LoadFlowResult
    bus_types: dict
    generator_q: dict
    switched_buses: list = field(default_factory=list)
    outer_iterations: int = 0
    message: str = ""
    switching_events: list = field(default_factory=list)


def _active_bus_map(network):
    """Return active bus objects indexed by number."""

    return {
        bus.number: bus
        for bus in network.buses
        if bus.in_service
    }


def _pv_generators(network):
    """
    Return one generator per active PV bus.

    Multiple generators on one PV bus are
    not supported by this implementation.
    """

    generators = {}

    for bus in network.buses:

        if not bus.in_service:
            continue

        if bus.bus_type != "PV":
            continue

        matches = [
            gen
            for gen in network.generators
            if gen.in_service
            and gen.bus == bus.number
        ]

        if len(matches) != 1:
            raise ValueError(
                f"PV bus {bus.number} must have "
                "exactly one in-service generator"
            )

        gen = matches[0]

        if gen.qmin > gen.qmax:
            raise ValueError(
                f"Invalid reactive limits "
                f"at bus {bus.number}"
            )

        generators[bus.number] = gen

    return generators


def calculate_generator_q(
    network: Network,
    result: LoadFlowResult,
):
    """
    Calculate generator reactive output in MVAr.

    Qgen = Qbus * base_mva + Qload(V)

    Returns a dictionary indexed by PV bus number.

    Voltage-dependent loads are evaluated at
    the solved bus voltage magnitudes.
    """

    generator_q = {}

    pv_generators = _pv_generators(
        network
    )

    (
        _,
        q_load,
        _,
        _,
    ) = calculate_load_power(
        network,
        result.bus_index,
        result.vm,
    )

    for bus_number in pv_generators:

        if bus_number not in result.bus_index:
            raise ValueError(
                f"Bus {bus_number} not in "
                "load-flow result"
            )

        i = result.bus_index[bus_number]

        q_injection = (
            result.q_calc[i]
            * network.base_mva
        )

        generator_q[bus_number] = (
            q_injection
            + q_load[i] * network.base_mva
        )

    return generator_q


def _bus_types(network):
    """Return active bus classifications."""

    return {
        bus.number: bus.bus_type
        for bus in network.buses
        if bus.in_service
    }


def _store_solution_as_initial(network, result):
    """
    Copy solved voltages to bus initial values.

    Result voltage angles are in degrees.
    """

    for bus in network.buses:

        if not bus.in_service:
            continue

        i = result.bus_index[bus.number]

        bus.vm = float(result.vm[i])
        bus.va = float(result.va[i])


def _event(
    outer,
    bus_number,
    old_type,
    new_type,
    reason,
    q_value,
    voltage,
):
    """Create a structured switching event."""

    return {
        "outer_iteration": outer,
        "bus": bus_number,
        "from_type": old_type,
        "to_type": new_type,
        "reason": reason,
        "q_mvar": float(q_value),
        "vm_pu": float(voltage),
    }


def solve_with_q_limits(
    network: Network,
    tolerance=1e-8,
    max_iterations=30,
    q_tolerance=1e-5,
    max_outer_iterations=10,
    verbose=False,
    allow_restoration=False,
    voltage_tolerance=1e-4,
):
    """
    Solve AC load flow with generator Q limits.

    Parameters
    ----------
    network : Network
        Original network; not modified.

    tolerance : float
        Inner Newton-Raphson tolerance in pu.

    max_iterations : int
        Maximum Newton corrections per solve.

    q_tolerance : float
        Reactive limit comparison tolerance
        in MVAr.

    max_outer_iterations : int
        Maximum outer enforcement passes.

    verbose : bool
        Print diagnostic messages.

    allow_restoration : bool
        Enable PQ-to-PV restoration.

    voltage_tolerance : float
        Voltage deadband for restoration in pu.

    Returns
    -------
    QLimitResult
    """

    if not np.isfinite(q_tolerance) or q_tolerance < 0:
        raise ValueError(
            "q_tolerance must be nonnegative "
            "and finite"
        )

    if (
        isinstance(max_outer_iterations, bool)
        or not isinstance(max_outer_iterations, int)
        or max_outer_iterations < 1
    ):
        raise ValueError(
            "max_outer_iterations must be "
            "a positive integer"
        )

    if (
        not np.isfinite(voltage_tolerance)
        or voltage_tolerance < 0
    ):
        raise ValueError(
            "voltage_tolerance must be "
            "nonnegative and finite"
        )

    working = deepcopy(network)

    original_pv = _pv_generators(working)

    switched = []
    events = []

    # Tracks buses currently fixed at a Q limit.
    limited = {}

    previous_result = None

    for outer in range(
        1,
        max_outer_iterations + 1,
    ):

        if verbose:
            print(
                f"\nQ-limit outer iteration {outer}"
            )

        # Warm start after the first pass.
        if previous_result is None:

            result = solve_load_flow(
                working,
                tolerance=tolerance,
                max_iterations=max_iterations,
                verbose=verbose,
            )

        else:

            result = solve_load_flow(
                working,
                tolerance=tolerance,
                max_iterations=max_iterations,
                verbose=verbose,
                initialization="previous",
                previous_result=previous_result,
            )

        if not result.converged:

            return QLimitResult(
                converged=False,
                load_flow=result,
                bus_types=_bus_types(working),
                generator_q={},
                switched_buses=switched,
                outer_iterations=outer,
                message=(
                    "Inner Newton-Raphson solver failed: "
                    + result.message
                ),
                switching_events=events,
            )

        generator_q = calculate_generator_q(
            working,
            result,
        )

        violations = []

        # Detect new PV-to-PQ transitions.
        for bus_number, qg in generator_q.items():

            gen = original_pv[bus_number]

            if qg > gen.qmax + q_tolerance:

                violations.append(
                    (
                        bus_number,
                        gen.qmax,
                        "Qmax",
                    )
                )

            elif qg < gen.qmin - q_tolerance:

                violations.append(
                    (
                        bus_number,
                        gen.qmin,
                        "Qmin",
                    )
                )

        restorations = []

        if allow_restoration:

            for bus_number, limit_name in limited.items():

                gen = original_pv[bus_number]

                i = result.bus_index[bus_number]

                voltage = float(result.vm[i])

                if (
                    limit_name == "Qmax"
                    and voltage
                    > gen.vg + voltage_tolerance
                ):

                    restorations.append(
                        bus_number
                    )

                elif (
                    limit_name == "Qmin"
                    and voltage
                    < gen.vg - voltage_tolerance
                ):

                    restorations.append(
                        bus_number
                    )

        # Return when no classifications change.
        if not violations and not restorations:

            for bus_number in limited:
                generator_q[bus_number] = (
                    original_pv[bus_number].qg
                )

            return QLimitResult(
                converged=True,
                load_flow=result,
                bus_types=_bus_types(working),
                generator_q=generator_q,
                switched_buses=switched,
                outer_iterations=outer,
                message=(
                    "Load flow converged with "
                    "reactive limits enforced"
                ),
                switching_events=events,
            )

        # Need another solve after changes.
        if outer == max_outer_iterations:

            return QLimitResult(
                converged=False,
                load_flow=result,
                bus_types=_bus_types(working),
                generator_q=generator_q,
                switched_buses=switched,
                outer_iterations=outer,
                message=(
                    "Maximum Q-limit outer iterations "
                    "reached before enforcing all limits"
                ),
                switching_events=events,
            )

        _store_solution_as_initial(
            working,
            result,
        )

        previous_result = result

        bus_lookup = _active_bus_map(
            working
        )

        # Apply PV-to-PQ switching.
        for (
            bus_number,
            q_limit,
            limit_name,
        ) in violations:

            bus = bus_lookup[bus_number]
            gen = original_pv[bus_number]

            i = result.bus_index[bus_number]

            bus.bus_type = "PQ"
            gen.qg = float(q_limit)

            limited[bus_number] = limit_name

            if bus_number not in switched:
                switched.append(bus_number)

            event = _event(
                outer,
                bus_number,
                "PV",
                "PQ",
                limit_name,
                q_limit,
                result.vm[i],
            )

            events.append(event)

            if verbose:
                print(
                    f"Bus {bus_number}: PV -> PQ, "
                    f"{limit_name} = "
                    f"{q_limit:.4f} MVAr"
                )

        # Apply PQ-to-PV restoration.
        for bus_number in restorations:

            bus = bus_lookup[bus_number]
            gen = original_pv[bus_number]

            i = result.bus_index[bus_number]

            old_q = gen.qg

            bus.bus_type = "PV"

            del limited[bus_number]

            event = _event(
                outer,
                bus_number,
                "PQ",
                "PV",
                "Voltage-control restoration",
                old_q,
                result.vm[i],
            )

            events.append(event)

            if verbose:
                print(
                    f"Bus {bus_number}: PQ -> PV, "
                    f"voltage control restored"
                )

    raise RuntimeError(
        "Unexpected Q-limit loop termination"
    )
