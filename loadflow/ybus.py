
"""Module 2: Sparse bus admittance matrix."""


import numpy as np
from scipy.sparse import coo_matrix

from loadflow.models import Network


def branch_admittances(
    r, x, b=0.0, tap_ratio=1.0,
    phase_shift=0.0, tap_side="from"
):
    """
    Return Yff, Yft, Ytf, Ytt.

    Impedance and charging are in pu.
    Phase shift is in degrees.
    """
    if r == 0 and x == 0:
        raise ValueError(
            "Branch impedance cannot be zero"
        )

    if tap_ratio <= 0:
        raise ValueError("Invalid tap ratio")

    if tap_side not in ("from", "to"):
        raise ValueError("Invalid tap side")

    y = 1.0 / complex(r, x)
    charging = 1j * b / 2.0

    tap = tap_ratio * np.exp(
        1j * np.deg2rad(phase_shift)
    )

    yff = (y + charging) / abs(tap)**2
    yft = -y / np.conj(tap)
    ytf = -y / tap
    ytt = y + charging

    if tap_side == "to":
        return ytt, ytf, yft, yff

    return yff, yft, ytf, ytt


def build_ybus(network: Network):
    """Return sparse Ybus and bus index mapping."""

    if network.base_mva <= 0:
        raise ValueError("Invalid base MVA")

    active_buses = [
        bus for bus in network.buses
        if bus.in_service
    ]

    bus_index = {
        bus.number: i
        for i, bus in enumerate(active_buses)
    }

    rows = []
    cols = []
    data = []

    def add(i, j, value):
        rows.append(i)
        cols.append(j)
        data.append(value)

    def stamp(from_bus, to_bus, coefficients):
        if from_bus not in bus_index:
            raise ValueError("Invalid from bus")

        if to_bus not in bus_index:
            raise ValueError("Invalid to bus")

        i = bus_index[from_bus]
        j = bus_index[to_bus]

        yff, yft, ytf, ytt = coefficients

        add(i, i, yff)
        add(i, j, yft)
        add(j, i, ytf)
        add(j, j, ytt)

    # Transmission line pi-model
    for line in network.lines:
        if not line.in_service:
            continue

        coefficients = branch_admittances(
            line.r, line.x, b=line.b
        )

        stamp(
            line.from_bus,
            line.to_bus,
            coefficients
        )

    # Off-nominal transformers
    for transformer in network.transformers:
        if not transformer.in_service:
            continue

        coefficients = branch_admittances(
            transformer.r,
            transformer.x,
            tap_ratio=transformer.tap_ratio,
            phase_shift=transformer.phase_shift,
            tap_side=transformer.tap_side
        )

        stamp(
            transformer.from_bus,
            transformer.to_bus,
            coefficients
        )

    # Fixed bus shunts
    for shunt in network.shunts:
        if not shunt.in_service:
            continue

        if shunt.bus not in bus_index:
            raise ValueError("Invalid shunt bus")

        i = bus_index[shunt.bus]

        ysh = complex(
            shunt.gs, shunt.bs
        ) / network.base_mva

        add(i, i, ysh)

    n = len(active_buses)

    ybus = coo_matrix(
        (
            np.asarray(data, dtype=complex),
            (rows, cols)
        ),
        shape=(n, n),
        dtype=complex
    ).tocsr()

    ybus.sum_duplicates()
    ybus.eliminate_zeros()

    return ybus, bus_index
