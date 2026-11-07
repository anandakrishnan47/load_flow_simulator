
import numpy as np
import pytest
from scipy.sparse import csr_matrix

from loadflow.models import (
    Network, Bus, Line, Transformer, Shunt
)
from loadflow.ybus import (
    build_ybus, branch_admittances
)


def two_bus():
    net = Network(base_mva=100.0)
    net.add_bus(Bus(1, "Bus 1", 132.0))
    net.add_bus(Bus(2, "Bus 2", 132.0))
    return net


def test_sparse_ybus():
    net = two_bus()
    net.add_line(Line(1, 2, 0.02, 0.06))

    ybus, mapping = build_ybus(net)

    assert isinstance(ybus, csr_matrix)
    assert ybus.shape == (2, 2)
    assert mapping == {1: 0, 2: 1}


def test_line_admittance():
    net = two_bus()
    net.add_line(Line(1, 2, 0.02, 0.06))

    ybus, _ = build_ybus(net)

    y = 1 / complex(0.02, 0.06)

    expected = np.array([
        [y, -y],
        [-y, y]
    ])

    np.testing.assert_allclose(
        ybus.toarray(), expected
    )


def test_line_charging():
    net = two_bus()
    net.add_line(
        Line(1, 2, 0.02, 0.06, b=0.04)
    )

    ybus, _ = build_ybus(net)
    y = 1 / complex(0.02, 0.06)

    assert ybus[0, 0] == pytest.approx(
        y + 0.02j
    )


def test_transformer_tap():
    net = two_bus()

    net.add_transformer(
        Transformer(
            1, 2, 0.01, 0.05,
            rating_mva=100.0,
            tap_ratio=1.1
        )
    )

    ybus, _ = build_ybus(net)

    y = 1 / complex(0.01, 0.05)

    assert ybus[0, 0] == pytest.approx(
        y / 1.1**2
    )


def test_phase_shift():
    values = branch_admittances(
        0.01, 0.05,
        phase_shift=20.0
    )

    assert not np.isclose(
        values[1], values[2]
    )


def test_bus_shunt():
    net = two_bus()
    net.add_shunt(
        Shunt(bus=1, gs=10.0, bs=20.0)
    )

    ybus, _ = build_ybus(net)

    assert ybus[0, 0] == pytest.approx(
        0.1 + 0.2j
    )


def test_out_of_service_line():
    net = two_bus()

    net.add_line(
        Line(
            1, 2, 0.02, 0.06,
            in_service=False
        )
    )

    ybus, _ = build_ybus(net)

    assert ybus.nnz == 0


def test_nonsequential_buses():
    net = Network()
    net.add_bus(Bus(10, "Bus 10", 132.0))
    net.add_bus(Bus(30, "Bus 30", 132.0))

    net.add_line(
        Line(10, 30, 0.02, 0.06)
    )

    ybus, mapping = build_ybus(net)

    assert ybus.shape == (2, 2)
    assert mapping == {10: 0, 30: 1}


def test_zero_impedance():
    net = two_bus()

    with pytest.raises(
        ValueError,
        match="Line impedance cannot be zero"
    ):
        net.add_line(
            Line(1, 2, 0.0, 0.0)
        )


def test_to_side_tap():
    values = branch_admittances(
        0.01, 0.05,
        tap_ratio=1.1,
        tap_side="to"
    )

    y = 1 / complex(0.01, 0.05)

    assert values[0] == pytest.approx(y)
    assert values[3] == pytest.approx(
        y / 1.1**2
    )
