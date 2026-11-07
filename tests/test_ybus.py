
import numpy as np
import pytest
from scipy.sparse import csr_matrix

from loadflow.models import (
    Bus,
    Line,
    Transformer,
    Shunt,
    Network,
)
from loadflow.ybus import (
    build_ybus,
    branch_admittances,
)


def make_two_bus_network():
    net = Network(base_mva=100.0)
    net.add_bus(Bus(1, "Bus 1", 132.0))
    net.add_bus(Bus(2, "Bus 2", 132.0))
    return net


def test_sparse_matrix():
    net = make_two_bus_network()
    net.add_line(Line(1, 2, 0.02, 0.06))

    ybus, index = build_ybus(net)

    assert isinstance(ybus, csr_matrix)
    assert ybus.shape == (2, 2)
    assert index == {1: 0, 2: 1}


def test_simple_line():
    net = make_two_bus_network()
    net.add_line(Line(1, 2, 0.02, 0.06))

    ybus, _ = build_ybus(net)

    y = 1 / complex(0.02, 0.06)

    expected = np.array([
        [y, -y],
        [-y, y],
    ])

    np.testing.assert_allclose(
        ybus.toarray(), expected, atol=1e-12
    )


def test_line_charging():
    net = make_two_bus_network()
    net.add_line(
        Line(1, 2, 0.02, 0.06, b=0.04)
    )

    ybus, _ = build_ybus(net)
    y = 1 / complex(0.02, 0.06)

    assert ybus[0, 0] == pytest.approx(
        y + 0.02j
    )
    assert ybus[1, 1] == pytest.approx(
        y + 0.02j
    )


def test_off_nominal_tap():
    net = make_two_bus_network()
    net.add_transformer(
        Transformer(
            1, 2, r=0.01, x=0.05,
            rating_mva=100.0,
            tap_ratio=1.1,
        )
    )

    ybus, _ = build_ybus(net)
    y = 1 / complex(0.01, 0.05)

    assert ybus[0, 0] == pytest.approx(
        y / 1.1**2
    )
    assert ybus[0, 1] == pytest.approx(
        -y / 1.1
    )


def test_phase_shifter_asymmetry():
    net = make_two_bus_network()
    net.add_transformer(
        Transformer(
            1, 2, r=0.01, x=0.05,
            rating_mva=100.0,
            phase_shift=15.0,
        )
    )

    ybus, _ = build_ybus(net)

    assert not np.isclose(
        ybus[0, 1], ybus[1, 0]
    )


def test_shunt():
    net = make_two_bus_network()
    net.add_shunt(
        Shunt(bus=1, gs=10.0, bs=20.0)
    )

    ybus, _ = build_ybus(net)

    assert ybus[0, 0] == pytest.approx(
        0.1 + 0.2j
    )
    assert ybus[1, 1] == 0


def test_out_of_service_line():
    net = make_two_bus_network()
    net.add_line(
        Line(
            1, 2, 0.02, 0.06,
            in_service=False,
        )
    )

    ybus, _ = build_ybus(net)

    np.testing.assert_allclose(
        ybus.toarray(), np.zeros((2, 2))
    )


def test_nonsequential_bus_numbers():
    net = Network()
    net.add_bus(Bus(10, "Bus 10", 132.0))
    net.add_bus(Bus(30, "Bus 30", 132.0))
    net.add_line(Line(10, 30, 0.02, 0.06))

    ybus, index = build_ybus(net)

    assert ybus.shape == (2, 2)
    assert index == {10: 0, 30: 1}


def test_to_side_tap():
    result = branch_admittances(
        0.01, 0.05,
        tap_ratio=1.1,
        tap_side="to",
    )

    y = 1 / complex(0.01, 0.05)

    assert result[0] == pytest.approx(y)
    assert result[3] == pytest.approx(
        y / 1.1**2
    )


def test_invalid_zero_impedance():
    net = make_two_bus_network()
    net.add_line(Line(1, 2, 0.0, 0.0))

    with pytest.raises(ValueError):
        build_ybus(net)


def test_invalid_zero_impedance():
    net = make_two_bus_network()

    with pytest.raises(ValueError):
        net.add_line(Line(1, 2, 0.0, 0.0))
