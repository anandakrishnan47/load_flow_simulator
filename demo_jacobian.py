
"""
Module 4 demonstration:
Analytical Jacobian for a three-bus system.
"""

import numpy as np

from main import create_sample_network
from loadflow.ybus import build_ybus
from loadflow.power import (
    calculate_power,
    get_bus_types,
)
from loadflow.jacobian import (
    build_jacobian,
    split_jacobian,
)


def main():
    # Create the three-bus network.
    network = create_sample_network()

    # Build Ybus using Module 2.
    ybus, bus_index = build_ybus(network)

    # Obtain active buses in Ybus order.
    buses = [
        bus for bus in network.buses
        if bus.in_service
    ]

    # Initial voltage magnitudes and angles.
    vm = np.array(
        [bus.vm for bus in buses],
        dtype=float
    )

    va = np.deg2rad(
        [bus.va for bus in buses]
    )

    # Apply generator voltage set points.
    for gen in network.generators:
        if gen.in_service:
            vm[bus_index[gen.bus]] = gen.vg

    # Apply slack-bus voltage reference.
    for grid in network.external_grids:
        if grid.in_service:
            i = bus_index[grid.bus]
            vm[i] = grid.vm
            va[i] = np.deg2rad(grid.va)

    # Identify bus types.
    slack, pv, pq = get_bus_types(
        network, bus_index
    )

    # Calculate power injections.
    p, q = calculate_power(
        ybus, vm, va
    )

    # Construct analytical Jacobian.
    jac = build_jacobian(
        ybus, vm, va, pv, pq
    )

    # Extract Jacobian submatrices.
    h, n, m, l = split_jacobian(
        jac,
        n_pv=len(pv),
        n_pq=len(pq),
    )

    np.set_printoptions(
        precision=5,
        suppress=True,
    )

    print("=" * 55)
    print("E4234 APSA LOAD FLOW SIMULATOR")
    print("MODULE 4: ANALYTICAL JACOBIAN")
    print("=" * 55)

    print("\nVoltage magnitudes (pu):")
    print(vm)

    print("\nVoltage angles (radians):")
    print(va)

    print("\nCalculated active power (pu):")
    print(p)

    print("\nCalculated reactive power (pu):")
    print(q)

    print("\nJacobian H = dP/dAngle:")
    print(h.toarray())

    print("\nJacobian N = dP/dVoltage:")
    print(n.toarray())

    print("\nJacobian M = dQ/dAngle:")
    print(m.toarray())

    print("\nJacobian L = dQ/dVoltage:")
    print(l.toarray())

    print("\nComplete Jacobian:")
    print(jac.toarray())

    print("\nJacobian dimensions:", jac.shape)
    print("Nonzero entries:", jac.nnz)

    print("\nModule 4 demonstration completed.")


if __name__ == "__main__":
    main()
