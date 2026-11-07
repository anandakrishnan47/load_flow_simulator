
"""
Module 6: Generator reactive power limit enforcement.

Method:
    1. Solve the AC load flow.
    2. Calculate reactive generation at PV buses.
    3. Check generator Qmin and Qmax.
    4. Switch violating PV buses to PQ.
    5. Fix generator Q at the violated limit.
    6. Solve again until no new violations occur.

This version uses one-way PV-to-PQ switching.

Limitations:
    - One generator per PV bus
    - Constant-power loads
    - Slack generator limits are not enforced
    - No PQ-to-PV restoration
"""

from copy import deepcopy
from dataclasses import dataclass, field

import numpy as np

from loadflow.models import Network
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


def calculate_generator_q(
    network: Network,
    result: LoadFlowResult,
):
    """
    Calculate generator reactive output in MVAr.

    Qgen = Qbus * base_mva + Qload

    Returns a dictionary indexed by bus number.

    Only in-service generators at PV buses are
    included. Multiple generators on the same
    PV bus are not supported.
    """
    generator_q = {}

    for bus in network.buses:
        if not bus.in_service:
            continue

        if bus.bus_type != "PV":
            continue

        generators = [
            gen for gen in network.generators
            if gen.in_service and gen.bus == bus.number
        ]

        if len(generators) != 1:
            raise ValueError(
                f"PV bus {bus.number} must have "
                "exactly one in-service generator"
            )

        if bus.number not in result.bus_index:
            raise ValueError(
                f"Bus {bus.number} not in load-flow result"
            )

        i = result.bus_index[bus.number]

        q_load = sum(
            load.qd
            for load in network.loads
            if load.in_service and load.bus == bus.number
        )

        q_injection = (
            result.q_calc[i] * network.base_mva
        )

        generator_q[bus.number] = (
            q_injection + q_load
        )

    return generator_q


def solve_with_q_limits(
    network: Network,
    tolerance=1e-8,
    max_iterations=30,
    q_tolerance=1e-5,
    max_outer_iterations=10,
    verbose=False,
):
    """
    Solve AC load flow with generator Q-limit enforcement.

    Parameters
    ----------
    network : Network
        Original network. Not modified.
    tolerance : float
        Inner Newton-Raphson mismatch tolerance, pu.
    max_iterations : int
        Maximum Newton corrections per load-flow solve.
    q_tolerance : float
        Reactive limit comparison tolerance, MVAr.
    max_outer_iterations : int
        Maximum allowed outer limit-enforcement passes.
    verbose : bool
        Print diagnostic information.

    Returns
    -------
    QLimitResult
        Final load flow, bus classifications,
        reactive outputs, and switching history.
    """

    if not np.isfinite(q_tolerance) or q_tolerance < 0:
        raise ValueError(
            "q_tolerance must be nonnegative and finite"
        )

    if (
        isinstance(max_outer_iterations, bool)
        or not isinstance(max_outer_iterations, int)
        or max_outer_iterations < 1
    ):
        raise ValueError(
            "max_outer_iterations must be a positive integer"
        )

    # Work on a copy so original data is unchanged.
    working = deepcopy(network)

    switched = []
    passes = 0

    # Validate generator configuration at PV buses.
    for bus in working.buses:
        if not bus.in_service or bus.bus_type != "PV":
            continue

        generators = [
            gen for gen in working.generators
            if gen.in_service and gen.bus == bus.number
        ]

        if len(generators) != 1:
            raise ValueError(
                f"PV bus {bus.number} must have "
                "exactly one in-service generator"
            )

        gen = generators[0]

        if gen.qmin > gen.qmax:
            raise ValueError(
                f"Invalid reactive limits at bus {bus.number}"
            )

    # The final pass must solve the final bus types.
    for outer in range(1, max_outer_iterations + 1):
        passes = outer

        if verbose:
            print(
                f"\nQ-limit outer iteration {outer}"
            )

        # Module 5: Solve the current network.
        result = solve_load_flow(
            working,
            tolerance=tolerance,
            max_iterations=max_iterations,
            verbose=verbose,
        )

        if not result.converged:
            return QLimitResult(
                converged=False,
                load_flow=result,
                bus_types={
                    bus.number: bus.bus_type
                    for bus in working.buses
                    if bus.in_service
                },
                generator_q={},
                switched_buses=switched,
                outer_iterations=passes,
                message=(
                    "Inner Newton-Raphson solver failed: "
                    + result.message
                ),
            )

        # Calculate Q generation at remaining PV buses.
        generator_q = calculate_generator_q(
            working, result
        )

        violations = []

        for bus_number, qg in generator_q.items():
            gen = next(
                gen for gen in working.generators
                if gen.in_service and gen.bus == bus_number
            )

            if qg > gen.qmax + q_tolerance:
                violations.append(
                    (bus_number, gen.qmax, "Qmax")
                )

            elif qg < gen.qmin - q_tolerance:
                violations.append(
                    (bus_number, gen.qmin, "Qmin")
                )

        # No violations: final solution is acceptable.
        if not violations:
            # Include Q for generators already limited.
            for gen in working.generators:
                if (
                    gen.in_service
                    and gen.bus in switched
                ):
                    generator_q[gen.bus] = gen.qg

            return QLimitResult(
                converged=True,
                load_flow=result,
                bus_types={
                    bus.number: bus.bus_type
                    for bus in working.buses
                    if bus.in_service
                },
                generator_q=generator_q,
                switched_buses=switched,
                outer_iterations=passes,
                message=(
                    "Load flow converged with "
                    "reactive limits enforced"
                ),
            )

        # There must be another pass to solve the
        # modified bus classifications.
        if outer == max_outer_iterations:
            return QLimitResult(
                converged=False,
                load_flow=result,
                bus_types={
                    bus.number: bus.bus_type
                    for bus in working.buses
                    if bus.in_service
                },
                generator_q=generator_q,
                switched_buses=switched,
                outer_iterations=passes,
                message=(
                    "Maximum Q-limit outer iterations "
                    "reached before enforcing all limits"
                ),
            )

        # Warm-start the next Newton solve.
        for bus in working.buses:
            if not bus.in_service:
                continue

            i = result.bus_index[bus.number]

            bus.vm = float(result.vm[i])
            bus.va = float(result.va[i])

        # Switch all violating PV buses to PQ.
        for bus_number, q_limit, limit_name in violations:
            bus = next(
                bus for bus in working.buses
                if bus.number == bus_number
            )

            gen = next(
                gen for gen in working.generators
                if gen.in_service and gen.bus == bus_number
            )

            bus.bus_type = "PQ"
            gen.qg = float(q_limit)

            switched.append(bus_number)

            if verbose:
                print(
                    f"Bus {bus_number}: PV -> PQ, "
                    f"{limit_name} = {q_limit:.4f} MVAr"
                )

    raise RuntimeError("Unexpected Q-limit loop termination")
