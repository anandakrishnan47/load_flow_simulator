
"""
Module 2: Sparse Ybus matrix formation.

Supports:
- Transmission line pi-model
- Transformer tap ratios and phase shifts
- Bus shunts
- Out-of-service elements
- Arbitrary bus numbering
"""

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from loadflow.models import Network


def series_admittance(r: float, x: float) -> complex:
    """Return admittance from per-unit series impedance."""
    z = complex(r, x)

    if abs(z) < 1e-15:
        raise ValueError("Branch impedance cannot be zero")

    return 1.0 / z


def branch_admittances(
    r: float,
    x: float,
    b: float = 0.0,
    tap_ratio: float = 1.0,
    phase_shift: float = 0.0,
    tap_side: str = "from",
):
    """
    Calculate four branch admittance coefficients.

    phase_shift is in degrees.
    b is total charging susceptance in pu.

    Returns Yff, Yft, Ytf, Ytt.
    """
    if tap_ratio <= 0:
        raise ValueError("Tap ratio must be positive")

    if tap_side not in ("from", "to"):
        raise ValueError("Tap side must be 'from' or 'to'")

    y = series_admittance(r, x)
    charging = 1j * b / 2.0

    angle = np.deg2rad(phase_shift)
    tap = tap_ratio * np.exp(1j * angle)

    # Standard MATPOWER-style from-side tap convention.
    yff = (y + charging) / (abs(tap) ** 2)
    yft = -y / np.conj(tap)
    ytf = -y / tap
    ytt = y + charging

    if tap_side == "to":
        # Reorient the transformer so the tap is on the
        # opposite physical terminal.
        return ytt, ytf, yft, yff

    return yff, yft, ytf, ytt


def build_ybus(network: Network):
    """
    Construct sparse bus admittance matrix.

    Returns
    -------
    ybus : scipy.sparse.csr_matrix
        Complex bus admittance matrix in pu.
    bus_index : dict
        Mapping of bus number to matrix index.
    """
    if network.base_mva <= 0:
        raise ValueError("System base MVA must be positive")

    active_buses = [
        bus for bus in network.buses if bus.in_service
    ]

    bus_index = {
        bus.number: index
        for index, bus in enumerate(active_buses)
    }

    nbus = len(active_buses)

    rows = []
    cols = []
    values = []

    def add_entry(i, j, value):
        rows.append(i)
        cols.append(j)
        values.append(value)

    def add_branch(from_bus, to_bus, admittances):
        if from_bus not in bus_index:
            raise ValueError(
                f"Branch references inactive bus {from_bus}"
            )

        if to_bus not in bus_index:
            raise ValueError(
                f"Branch references inactive bus {to_bus}"
            )

        i = bus_index[from_bus]
        j = bus_index[to_bus]

        yff, yft, ytf, ytt = admittances

        add_entry(i, i, yff)
        add_entry(i, j, yft)
        add_entry(j, i, ytf)
        add_entry(j, j, ytt)

    # 1. Transmission lines
    for line in network.lines:
        if not line.in_service:
            continue

        admittances = branch_admittances(
            r=line.r,
            x=line.x,
            b=line.b,
        )

        add_branch(
            line.from_bus,
            line.to_bus,
            admittances,
        )

    # 2. Transformers
    for transformer in network.transformers:
        if not transformer.in_service:
            continue

        admittances = branch_admittances(
            r=transformer.r,
            x=transformer.x,
            tap_ratio=transformer.tap_ratio,
            phase_shift=transformer.phase_shift,
            tap_side=transformer.tap_side,
        )

        add_branch(
            transformer.from_bus,
            transformer.to_bus,
            admittances,
        )

    # 3. Bus shunts
    for shunt in network.shunts:
        if not shunt.in_service:
            continue

        if shunt.bus not in bus_index:
            raise ValueError(
                f"Shunt references inactive bus {shunt.bus}"
            )

        i = bus_index[shunt.bus]

        ysh = complex(
            shunt.gs,
            shunt.bs,
        ) / network.base_mva

        add_entry(i, i, ysh)

    # 4. Assemble sparse matrix
    ybus = coo_matrix(
        (
            np.asarray(values, dtype=complex),
            (rows, cols),
        ),
        shape=(nbus, nbus),
        dtype=complex,
    ).tocsr()

    ybus.sum_duplicates()
    ybus.eliminate_zeros()

    return ybus, bus_index


def print_ybus(ybus: csr_matrix, bus_index: dict):
    """Display Ybus for small test networks."""
    print("\nBus Index Mapping:")
    for bus_number, index in bus_index.items():
        print(f"Bus {bus_number} -> Index {index}")

    print("\nYbus Matrix (pu):")
    print(np.array2string(
        ybus.toarray(),
        precision=4,
        suppress_small=True,
    ))
