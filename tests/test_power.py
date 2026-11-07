
"""Unit tests for Module 3 power calculations."""

import numpy as np
import pytest

from loadflow.models import (
    Network, Bus, Line, Generator, Load
)
from loadflow.ybus import build_ybus
from loadflow.power import (
    calculate_power,
    specified_power,
    get_bus_types,
    calculate_mismatch,
    maximum_mismatch,
)


def make_network():
    """Create a simple three-bus test network."""
    net = Network(base_mva=100.0)

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "Generator", 132.0, "PV"))
    net.add_bus(Bus(3, "Load", 132.0, "PQ"))

    net.add_line(Line(1, 2, 0.02, 0.06))
    net.add_line(Line(1, 3, 0.08, 0.24))
    net.add_line(Line(2, 3, 0.06, 0.18))

    net.add_generator(
        Generator(bus=2, pg=40.0, vg=1.02)
    )

    net.add_load(
        Load(bus=3, pd=60.0, qd=30.0)
    )

    return net


def test_flat_start_power():
    """No line charging: flat voltage gives zero P,Q."""
    net = make_network()
    ybus, _ = build_ybus(net)

    vm = np.ones(3)
    va = np.zeros(3)

    p, q = calculate_power(ybus, vm, va)

    np.testing.assert_allclose(
        p, np.zeros(3), atol=1e-12
    )
    np.testing.assert_allclose(
        q, np.zeros(3), atol=1e-12
    )


def test_two_bus_analytical_power():
    """Compare against an independent two-bus calculation."""
    net = Network()

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "PQ", 132.0, "PQ"))

    net.add_line(Line(1, 2, 0.0, 0.1))

    ybus, _ = build_ybus(net)

    vm = np.array([1.0, 1.0])
    va = np.deg2rad([0.0, -30.0])

    p, q = calculate_power(ybus, vm, va)

    np.testing.assert_allclose(
        p, [5.0, -5.0], atol=1e-10
    )

    expected_q = 10 * (
        1 - np.cos(np.deg2rad(30))
    )

    np.testing.assert_allclose(
        q, [expected_q, expected_q],
        atol=1e-10
    )


def test_specified_power():
    net = make_network()
    _, mapping = build_ybus(net)

    p_spec, q_spec = specified_power(
        net, mapping
    )

    np.testing.assert_allclose(
        p_spec, [0.0, 0.4, -0.6]
    )

    np.testing.assert_allclose(
        q_spec, [0.0, 0.0, -0.3]
    )


def test_multiple_generators():
    net = make_network()

    net.add_generator(
        Generator(bus=2, pg=20.0)
    )

    _, mapping = build_ybus(net)

    p_spec, _ = specified_power(net, mapping)

    assert p_spec[1] == pytest.approx(0.6)


def test_out_of_service_generator():
    net = make_network()

    net.generators[0].in_service = False

    _, mapping = build_ybus(net)

    p_spec, _ = specified_power(net, mapping)

    assert p_spec[1] == pytest.approx(0.0)


def test_bus_types():
    net = make_network()
    _, mapping = build_ybus(net)

    slack, pv, pq = get_bus_types(
        net, mapping
    )

    np.testing.assert_array_equal(slack, [0])
    np.testing.assert_array_equal(pv, [1])
    np.testing.assert_array_equal(pq, [2])


def test_mismatch_vector():
    net = make_network()

    ybus, mapping = build_ybus(net)

    p_spec, q_spec = specified_power(
        net, mapping
    )

    _, pv, pq = get_bus_types(net, mapping)

    vm = np.ones(3)
    va = np.zeros(3)

    mismatch, _, _ = calculate_mismatch(
        ybus, vm, va,
        p_spec, q_spec,
        pv, pq
    )

    np.testing.assert_allclose(
        mismatch, [0.4, -0.6, -0.3],
        atol=1e-12
    )


def test_maximum_mismatch():
    mismatch = np.array([
        0.4, -0.6, -0.3
    ])

    assert maximum_mismatch(
        mismatch
    ) == pytest.approx(0.6)


def test_invalid_voltage():
    net = make_network()
    ybus, _ = build_ybus(net)

    vm = np.array([1.0, 0.0, 1.0])
    va = np.zeros(3)

    with pytest.raises(ValueError):
        calculate_power(ybus, vm, va)


def test_zip_not_implemented():
    net = make_network()
    net.loads[0].model = "ZIP"

    _, mapping = build_ybus(net)

    with pytest.raises(NotImplementedError):
        specified_power(net, mapping)


def test_voltage_angle_dimensions():
    net = make_network()
    ybus, _ = build_ybus(net)

    vm = np.ones(3)
    va = np.zeros(2)

    with pytest.raises(ValueError):
        calculate_power(ybus, vm, va)
