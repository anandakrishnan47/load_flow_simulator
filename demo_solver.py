
"""
Module 5 demonstration:
Newton-Raphson AC load flow for a 3-bus system.
"""

import numpy as np

from main import create_sample_network
from loadflow.solver import solve_load_flow


def main():
    network = create_sample_network()

    print("=" * 65)
    print("E4234 APSA LOAD FLOW SIMULATOR")
    print("MODULE 5: NEWTON-RAPHSON LOAD FLOW")
    print("=" * 65)

    result = solve_load_flow(
        network,
        tolerance=1e-8,
        max_iterations=30,
        verbose=True,
    )

    print("\n" + "=" * 65)
    print("LOAD FLOW RESULTS")
    print("=" * 65)

    print("Converged:", result.converged)
    print("Message:", result.message)
    print("Iterations:", result.iterations)
    print(
        "Final maximum mismatch:",
        f"{result.mismatch:.10e} pu"
    )

    print("\nBus voltage results:")
    print("-" * 65)

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

    print("\nCalculated net bus injections:")
    print("-" * 65)

    print(
        f"{'Bus':<8}"
        f"{'P (MW)':<16}"
        f"{'Q (MVAr)':<16}"
    )

    for bus in network.buses:
        if not bus.in_service:
            continue

        i = result.bus_index[bus.number]

        p_mw = (
            result.p_calc[i] * network.base_mva
        )
        q_mvar = (
            result.q_calc[i] * network.base_mva
        )

        print(
            f"{bus.number:<8}"
            f"{p_mw:<16.6f}"
            f"{q_mvar:<16.6f}"
        )

    print("\nMismatch history:")
    print("-" * 65)

    for iteration, error in enumerate(
        result.mismatch_history
    ):
        print(
            f"Iteration {iteration:2d}: "
            f"{error:.10e} pu"
        )

    if result.converged:
        print("\nLoad flow converged successfully.")
    else:
        print("\nLoad flow did not converge.")

    print("\nModule 5 demonstration completed.")


if __name__ == "__main__":
    main()
