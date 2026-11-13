"""
Module 7: Branch power flows and network losses.

Calculates:
    - Sending and receiving terminal powers
    - Line and transformer net P/Q losses
    - MVA loading at each end
    - Total branch losses
    - System power-balance residual

Power sign convention:
    Positive terminal power flows from bus into branch.
    Branch loss = from-end power + to-end power.

P: MW
Q: MVAr
S: MVA
Voltages: pu, angles in degrees in LoadFlowResult
"""

from dataclasses import dataclass
import numpy as np

from loadflow.models import Network
from loadflow.solver import LoadFlowResult
from loadflow.ybus import branch_admittances


@dataclass
class BranchFlow:
    kind: str
    from_bus: int
    to_bus: int
    p_from: float
    q_from: float
    p_to: float
    q_to: float
    p_loss: float
    q_net: float
    s_from: float
    s_to: float
    rating_mva: float
    loading_percent: float


@dataclass
class BranchFlowResult:
    branches: list[BranchFlow]
    total_p_loss: float
    total_q_net: float
    max_loading_percent: float
    bus_p_balance_error: float
    bus_q_balance_error: float


def calculate_branch_flows(
    network: Network,
    result: LoadFlowResult,
):
    """
    Calculate branch terminal flows from a
    converged load-flow result.

    Uses exactly the same branch admittance
    convention as Module 2.

    Notes
    -----
    - Out-of-service branches are excluded.
    - Bus shunts are excluded from branch totals.
    - Network base MVA is used for conversion.
    - Result bus indices must match the network.
    """

    if not result.converged:
        raise ValueError(
            "Branch flows require a converged load flow"
        )

    if network.base_mva <= 0:
        raise ValueError("Base MVA must be positive")

    mapping = result.bus_index
    n = len(mapping)

    vm = np.asarray(result.vm, dtype=float)
    va = np.asarray(result.va, dtype=float)

    if vm.shape != (n,) or va.shape != (n,):
        raise ValueError("Invalid result voltage dimensions")

    if (
        not np.all(np.isfinite(vm))
        or not np.all(np.isfinite(va))
        or np.any(vm <= 0)
    ):
        raise ValueError("Invalid solved bus voltages")

    active = {
        bus.number
        for bus in network.buses
        if bus.in_service
    }

    if (
        len(mapping) != len(active)
        or set(mapping) != active
        or set(mapping.values()) != set(range(n))
    ):
        raise ValueError(
            "Result bus mapping does not match network"
        )

    # Module 5 returns voltage angles in degrees.
    voltage = vm * np.exp(1j * np.deg2rad(va))

    branches = []

    def process_branch(
        kind, from_bus, to_bus,
        r, x, b, rating,
        tap_ratio=1.0,
        phase_shift=0.0,
        tap_side="from",
    ):
        if rating <= 0:
            raise ValueError(
                "Branch MVA rating must be positive"
            )

        if from_bus not in mapping or to_bus not in mapping:
            raise ValueError(
                "Branch connects to an inactive bus"
            )

        i = mapping[from_bus]
        j = mapping[to_bus]

        vf = voltage[i]
        vt = voltage[j]

        # Reuse the Module 2 branch model.
        yff, yft, ytf, ytt = branch_admittances(
            r, x,
            b=b,
            tap_ratio=tap_ratio,
            phase_shift=phase_shift,
            tap_side=tap_side,
        )

        # Terminal currents into the branch.
        i_from = yff * vf + yft * vt
        i_to = ytf * vf + ytt * vt

        # Terminal complex powers, in MVA.
        s_from = (
            vf * np.conj(i_from) * network.base_mva
        )
        s_to = (
            vt * np.conj(i_to) * network.base_mva
        )

        s_loss = s_from + s_to

        from_mva = abs(s_from)
        to_mva = abs(s_to)

        loading = (
            max(from_mva, to_mva)
            / rating * 100.0
        )

        branches.append(
            BranchFlow(
                kind=kind,
                from_bus=from_bus,
                to_bus=to_bus,
                p_from=float(s_from.real),
                q_from=float(s_from.imag),
                p_to=float(s_to.real),
                q_to=float(s_to.imag),
                p_loss=float(s_loss.real),
                q_net=float(s_loss.imag),
                s_from=float(from_mva),
                s_to=float(to_mva),
                rating_mva=float(rating),
                loading_percent=float(loading),
            )
        )

    # Transmission lines.
    for line in network.lines:
        if not line.in_service:
            continue

        process_branch(
            kind="Line",
            from_bus=line.from_bus,
            to_bus=line.to_bus,
            r=line.r,
            x=line.x,
            b=line.b,
            rating=line.rating_mva,
        )

    # Transformers.
    for transformer in network.transformers:
        if not transformer.in_service:
            continue

        process_branch(
            kind="Transformer",
            from_bus=transformer.from_bus,
            to_bus=transformer.to_bus,
            r=transformer.r,
            x=transformer.x,
            b=0.0,
            rating=transformer.rating_mva,
            tap_ratio=transformer.tap_ratio,
            phase_shift=transformer.phase_shift,
            tap_side=transformer.tap_side,
        )

    total_p_loss = sum(
        branch.p_loss for branch in branches
    )

    total_q_net = sum(
        branch.q_net for branch in branches
    )

    max_loading = max(
        (branch.loading_percent for branch in branches),
        default=0.0,
    )

    # Calculate complex power absorbed by explicit
    # bus shunts. Module 2 uses gs/bs in MW/MVAr
    # at 1 pu voltage on the network base.
    shunt_power = 0.0 + 0.0j

    for shunt in network.shunts:
        if not shunt.in_service:
            continue

        if shunt.bus not in mapping:
            raise ValueError("Shunt bus is inactive")

        i = mapping[shunt.bus]

        shunt_power += (
            vm[i] ** 2
            * complex(shunt.gs, -shunt.bs)
        )

    # Sum of all calculated bus injections
    # should equal branch terminal sums plus
    # explicit shunt consumption/injection.
    p_injected = (
        np.sum(result.p_calc) * network.base_mva
    )
    q_injected = (
        np.sum(result.q_calc) * network.base_mva
    )

    p_balance_error = (
        p_injected
        - total_p_loss
        - shunt_power.real
    )

    q_balance_error = (
        q_injected
        - total_q_net
        - shunt_power.imag
    )

    return BranchFlowResult(
        branches=branches,
        total_p_loss=float(total_p_loss),
        total_q_net=float(total_q_net),
        max_loading_percent=float(max_loading),
        bus_p_balance_error=float(p_balance_error),
        bus_q_balance_error=float(q_balance_error),
    )
