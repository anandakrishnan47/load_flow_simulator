
"""
Module 7 demonstration:
Branch power flows and transmission losses.
"""

from main import create_sample_network

from loadflow.solver import solve_load_flow
from loadflow.branch_flows import (
    calculate_branch_flows,
)


def main():
    network = create_sample_network()

    print("=" * 85)
    print("E4234 APSA LOAD FLOW SIMULATOR")
    print("MODULE 7: BRANCH FLOWS AND LOSSES")
    print("=" * 85)

    # Step 1: Solve the network.
    result = solve_load_flow(
        network,
        tolerance=1e-10,
        max_iterations=30,
        verbose=True,
    )

    if not result.converged:
        print("Load flow did not converge.")
        print(result.message)
        return

    # Step 2: Calculate branch powers.
    flows = calculate_branch_flows(
        network, result
    )

    print("\nLOAD FLOW SUMMARY")
    print("-" * 85)
    print("Converged:", result.converged)
    print("Iterations:", result.iterations)
    print(
        "Maximum mismatch:",
        f"{result.mismatch:.10e} pu"
    )

    print("\nBUS VOLTAGE RESULTS")
    print("-" * 85)

    print(
        f"{'Bus':<8}"
        f"{'Type':<10}"
        f"{'Vm (pu)':<14}"
        f"{'Angle (deg)':<16}"
    )

    for bus in network.buses:
        if not bus.in_service:
            continue

        i = result.bus_index[bus.number]

        print(
            f"{bus.number:<8}"
            f"{bus.bus_type:<10}"
            f"{result.vm[i]:<14.6f}"
            f"{result.va[i]:<16.6f}"
        )

    print("\nBRANCH ACTIVE POWER FLOWS")
    print("-" * 85)

    print(
        f"{'Type':<14}"
        f"{'From':<7}"
        f"{'To':<7}"
        f"{'Pfrom MW':<14}"
        f"{'Pto MW':<14}"
        f"{'Ploss MW':<14}"
    )

    for branch in flows.branches:
        print(
            f"{branch.kind:<14}"
            f"{branch.from_bus:<7}"
            f"{branch.to_bus:<7}"
            f"{branch.p_from:<14.5f}"
            f"{branch.p_to:<14.5f}"
            f"{branch.p_loss:<14.5f}"
        )

    print("\nBRANCH REACTIVE POWER FLOWS")
    print("-" * 85)

    print(
        f"{'From':<8}"
        f"{'To':<8}"
        f"{'Qfrom MVAr':<16}"
        f"{'Qto MVAr':<16}"
        f"{'Qnet MVAr':<16}"
    )

    for branch in flows.branches:
        print(
            f"{branch.from_bus:<8}"
            f"{branch.to_bus:<8}"
            f"{branch.q_from:<16.5f}"
            f"{branch.q_to:<16.5f}"
            f"{branch.q_net:<16.5f}"
        )

    print("\nBRANCH LOADING")
    print("-" * 85)

    print(
        f"{'From':<8}"
        f"{'To':<8}"
        f"{'Rating MVA':<16}"
        f"{'Loading %':<16}"
        f"{'Status':<12}"
    )

    for branch in flows.branches:
        status = (
            "OVERLOADED"
            if branch.loading_percent > 100.0
            else "OK"
        )

        print(
            f"{branch.from_bus:<8}"
            f"{branch.to_bus:<8}"
            f"{branch.rating_mva:<16.3f}"
            f"{branch.loading_percent:<16.3f}"
            f"{status:<12}"
        )

    print("\nSYSTEM LOSS SUMMARY")
    print("-" * 85)

    print(
        "Total active loss:",
        f"{flows.total_p_loss:.6f} MW"
    )

    print(
        "Total net branch reactive absorption:",
        f"{flows.total_q_net:.6f} MVAr"
    )

    print(
        "Maximum branch loading:",
        f"{flows.max_loading_percent:.3f} %"
    )

    print(
        "Active power balance residual:",
        f"{flows.bus_p_balance_error:.10e} MW"
    )

    print(
        "Reactive power balance residual:",
        f"{flows.bus_q_balance_error:.10e} MVAr"
    )

    print("\nModule 7 demonstration completed.")


if __name__ == "__main__":
    main()
