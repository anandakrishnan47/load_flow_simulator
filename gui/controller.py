"""Stage 3.5 APSA GUI controller: data management and numerical studies."""

from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path

from main import create_sample_network
from loadflow.ieee_validation import read_matpower_case, convert_to_network
from loadflow.solver import solve_load_flow
from loadflow.qlimits import solve_with_q_limits
from loadflow.branch_flows import calculate_branch_flows
from loadflow.models import Load

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
    """Return a fresh network, not a shared mutable instance."""
    if name not in NETWORKS:
        raise ValueError(f"Unknown network: {name}")
    filename = NETWORKS[name]
    if filename is None:
        return create_sample_network()
    path = ROOT / "data" / "ieee" / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing benchmark file: {path}\nRun: python download_ieee_cases.py"
        )
    return convert_to_network(read_matpower_case(path))


def update_loads(network, values):
    """Update aggregate bus Pd/Qd while preserving unchanged ZIP load models.

    For a changed bus with existing active loads, scale their P and Q
    ratings independently, preserving each load's ZIP coefficients.
    When a previous aggregate is zero and the new aggregate is nonzero,
    add one constant-power load for that component.
    """
    working = deepcopy(network)
    active = {bus.number for bus in working.buses if bus.in_service}
    for number, pair in values.items():
        if number not in active:
            raise ValueError(f"Invalid bus {number}")
        if len(pair) != 2:
            raise ValueError(f"Invalid load tuple for bus {number}")
        pd, qd = map(float, pair)
        if not math.isfinite(pd) or not math.isfinite(qd):
            raise ValueError("Load values must be finite")
        loads = [load for load in working.loads if load.in_service and load.bus == number]
        old_p = sum(load.pd for load in loads)
        old_q = sum(load.qd for load in loads)
        if math.isclose(pd, old_p, rel_tol=0, abs_tol=1e-9) and math.isclose(qd, old_q, rel_tol=0, abs_tol=1e-9):
            continue
        for field, target, previous in (("pd", pd, old_p), ("qd", qd, old_q)):
            if not math.isclose(previous, 0.0, abs_tol=1e-12):
                factor = target / previous
                for load in loads:
                    setattr(load, field, getattr(load, field) * factor)
            elif not math.isclose(target, 0.0, abs_tol=1e-12):
                working.add_load(Load(
                    bus=number,
                    pd=target if field == "pd" else 0.0,
                    qd=target if field == "qd" else 0.0,
                ))
    return working


def validate_network(network):
    """Validate basic topology and finite electrical inputs before solving."""
    active = {bus.number: bus for bus in network.buses if bus.in_service}
    if not active:
        raise ValueError("Network contains no active buses")
    slack = [bus for bus in active.values() if bus.bus_type == "Slack"]
    if len(slack) != 1:
        raise ValueError(f"Expected exactly one active slack bus, found {len(slack)}")
    if not math.isfinite(network.base_mva) or network.base_mva <= 0:
        raise ValueError("Network base MVA must be positive and finite")
    for bus in active.values():
        if not math.isfinite(bus.base_kv) or bus.base_kv <= 0:
            raise ValueError(f"Bus {bus.number}: invalid base kV")
        if not math.isfinite(bus.vm) or bus.vm <= 0:
            raise ValueError(f"Bus {bus.number}: invalid voltage")
    adjacency = {number: set() for number in active}
    for branch in network.lines + network.transformers:
        if not branch.in_service:
            continue
        if branch.from_bus not in active or branch.to_bus not in active:
            raise ValueError("Active branch references an inactive/missing bus")
        if not all(math.isfinite(v) for v in (branch.r, branch.x)) or (branch.r == 0 and branch.x == 0):
            raise ValueError(f"Branch {branch.from_bus}-{branch.to_bus}: invalid impedance")
        if not math.isfinite(branch.rating_mva) or branch.rating_mva <= 0:
            raise ValueError("Branch rating must be positive")
        if hasattr(branch, "tap_ratio") and (not math.isfinite(branch.tap_ratio) or branch.tap_ratio <= 0):
            raise ValueError("Transformer tap ratio must be positive")
        adjacency[branch.from_bus].add(branch.to_bus)
        adjacency[branch.to_bus].add(branch.from_bus)
    visited = set()
    pending = [slack[0].number]
    while pending:
        node = pending.pop()
        if node in visited:
            continue
        visited.add(node)
        pending.extend(adjacency[node] - visited)
    missing = sorted(set(active) - visited)
    if missing:
        raise ValueError(f"Buses disconnected from slack bus: {missing}")
    for collection in (network.loads, network.generators, network.shunts, network.external_grids):
        for component in collection:
            if component.in_service and component.bus not in active:
                raise ValueError(f"Active component references missing/inactive bus {component.bus}")
    return True


def run_study(network, tolerance=1e-8, max_iterations=40, enforce_q_limits=False):
    """Solve a deep copy of the model and return branch flows."""
    working = deepcopy(network)
    validate_network(working)
    if enforce_q_limits:
        limited = solve_with_q_limits(
            working, tolerance=tolerance, max_iterations=max_iterations,
            max_outer_iterations=20,
        )
        solution = limited.load_flow
        if not limited.converged:
            raise RuntimeError(limited.message)
    else:
        limited = None
        solution = solve_load_flow(
            working, tolerance=tolerance, max_iterations=max_iterations,
        )
        if not solution.converged:
            raise RuntimeError(solution.message)
    flows = calculate_branch_flows(working, solution)
    return StudyResult(network=working, solution=solution, flows=flows, q_limits=limited)
