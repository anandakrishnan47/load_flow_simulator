
"""
Demonstration of Module 3 power calculations.
"""

import numpy as np

from main import create_sample_network
from loadflow.ybus import build_ybus
from loadflow.power import (
    calculate_power,
    specified_power,
    get_bus_types,
    calculate_mismatch,
    maximum_mismatch,
)


def main():
    # Create the sample network.
    network = create_sample_network()

    # Build the bus admittance matrix.
    ybus, bus_index = build_ybus(network)

    # Obtain buses in Ybus matrix order.
    buses = [
        bus for bus in network.buses
        if bus.in_service
    ]

    # Initial voltage magnitudes.
    vm = np.array(
        [bus.vm for bus in buses],
        dtype=float
    )

    # Convert angles from degrees to radians.
    va = np.deg2rad(
        [bus.va for bus in buses]
    )

    # Apply the generator voltage set point.
    for gen in network.generators:
        if gen.in_service:
            vm[bus_index[gen.bus]] = gen.vg

    # Apply the external grid voltage reference.
    for grid in network.external_grids:
        if grid.in_service:
            i = bus_index[grid.bus]
            vm[i] = grid.vm
            va[i] = np.deg2rad(grid.va)

    # Calculate bus power injections.
    p_calc, q_calc = calculate_power(
        ybus, vm, va
    )

    # Calculate specified powers.
    p_spec, q_spec = specified_power(
        network, bus_index
    )

    # Identify bus types.
    slack, pv, pq = get_bus_types(
        network, bus_index
    )

    # Construct mismatch vector.
    mismatch, _, _ = calculate_mismatch(
        ybus, vm, va,
        p_spec, q_spec,
        pv, pq
    )

    print("=" * 55)
    print("E4234 APSA LOAD FLOW SIMULATOR")
    print("MODULE 3: POWER INJECTION CALCULATIONS")
    print("=" * 55)

    print("\nBus power calculations:")
    print(
        f"{'Bus':<8}{'Vm':<10}"
        f"{'Pcalc':<14}{'Qcalc':<14}"
    )

    for bus in buses:
        i = bus_index[bus.number]

        print(
            f"{bus.number:<8}"
            f"{vm[i]:<10.4f}"
            f"{p_calc[i]:<14.6f}"
            f"{q_calc[i]:<14.6f}"
        )

    print("\nSpecified powers (pu):")
    print("P specified:", p_spec)
    print("Q specified:", q_spec)

    print("\nBus classifications:")
    print("Slack indices:", slack)
    print("PV indices:", pv)
    print("PQ indices:", pq)

    print("\nMismatch vector (pu):")
    print(mismatch)

    print(
        "\nMaximum mismatch:",
        f"{maximum_mismatch(mismatch):.6f}",
        "pu"
    )

    print("\nModule 3 calculations completed.")


if __name__ == "__main__":
    main()
