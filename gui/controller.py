
"""
Module 9: GUI controller for the APSA simulator.

Keeps the Qt interface separate from the numerical engine.
"""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from main import create_sample_network
from loadflow.ieee_validation import (
    read_matpower_case,
    convert_to_network,
)
from loadflow.solver import solve_load_flow
from loadflow.qlimits import solve_with_q_limits
from loadflow.branch_flows import calculate_branch_flows


ROOT = Path(__file__).resolve().parents[1]

NETWORKS = {
    "3-Bus Example": None,
    "IEEE 14-Bus": "case14.m",
    "IEEE 30-Bus": "case30.m",
    "IEEE 57-Bus": "case57.m",
    "IEEE 118-Bus": "case118.m",
}


@dataclass
class StudyResult:
    network: object
    solution: object
    flows: object
    q_limits: object = None


def load_network(name):
    """Load a fresh copy of a selected network."""

    if name not in NETWORKS:
        raise ValueError(f"Unknown network: {name}")

    filename = NETWORKS[name]

    if filename is None:
        return create_sample_network()

    path = ROOT / "data" / "ieee" / filename

    if not path.is_file():
        raise FileNotFoundError(
            f"Missing benchmark file: {path}\n"
            "Run: python download_ieee_cases.py"
        )

    return convert_to_network(
        read_matpower_case(path)
    )


def update_loads(network, values):
    """
    Update aggregate bus loads.

    values: mapping of bus number to (Pd, Qd), in MW/MVAr.

    Multiple loads at the same bus are replaced with
    one equivalent constant-power load.
    """
    from loadflow.models import Load

    working = deepcopy(network)

    active_numbers = {
        bus.number
        for bus in working.buses
        if bus.in_service
    }

    for number, (pd, qd) in values.items():
        if number not in active_numbers:
            raise ValueError(f"Invalid bus {number}")

        import math

        if not math.isfinite(pd) or not math.isfinite(qd):
            raise ValueError("Load values must be finite")

        # Remove the previous active loads at this bus.
        working.loads = [
            load for load in working.loads
            if not (
                load.bus == number
                and load.in_service
            )
        ]

        if pd != 0 or qd != 0:
            working.add_load(
                Load(bus=number, pd=pd, qd=qd)
            )

    return working


def run_study(
    network,
    tolerance=1e-8,
    max_iterations=40,
    enforce_q_limits=False,
):
    """
    Solve a network and calculate branch flows.

    Does not modify the supplied network.
    """
    working = deepcopy(network)

    if enforce_q_limits:
        limited = solve_with_q_limits(
            working,
            tolerance=tolerance,
            max_iterations=max_iterations,
            max_outer_iterations=20,
        )
        solution = limited.load_flow

        if not limited.converged:
            raise RuntimeError(limited.message)

    else:
        limited = None

        solution = solve_load_flow(
            working,
            tolerance=tolerance,
            max_iterations=max_iterations,
        )

        if not solution.converged:
            raise RuntimeError(solution.message)

    flows = calculate_branch_flows(
        working,
        solution,
    )

    return StudyResult(
        network=working,
        solution=solution,
        flows=flows,
        q_limits=limited,
    )
