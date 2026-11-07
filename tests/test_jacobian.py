
"""Tests for Module 4 analytical Jacobian."""

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from loadflow.models import (
    Network, Bus, Line, Transformer
)
from loadflow.ybus import build_ybus
from loadflow.power import calculate_power
from loadflow.jacobian import (
    build_jacobian,
    split_jacobian,
)


def make_network():
    """Three-bus network with one PV and one PQ bus."""
    net = Network(base_mva=100.0)

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "PV", 132.0, "PV"))
    net.add_bus(Bus(3, "PQ", 132.0, "PQ"))

    net.add_line(Line(1, 2, 0.02, 0.06, 0.03))
    net.add_line(Line(1, 3, 0.08, 0.24, 0.025))
    net.add_line(Line(2, 3, 0.06, 0.18, 0.02))

    return net


def numerical_jacobian(ybus, vm, va, pv, pq):
    """
    Independent central finite-difference Jacobian.

    The state is:
        angles at PV and PQ buses
        magnitudes at PQ buses
    """
    p_buses = np.concatenate((pv, pq))
    n_angle = len(p_buses)

    x = np.concatenate((
        va[p_buses],
        vm[pq],
    ))

    def equations(state):
        vm_test = vm.copy()
        va_test = va.copy()

        va_test[p_buses] = state[:n_angle]
        vm_test[pq] = state[n_angle:]

        p, q = calculate_power(
            ybus, vm_test, va_test
        )

        return np.concatenate((
            p[p_buses],
            q[pq],
        ))

    h = 1e-6
    jac = np.zeros((len(x), len(x)))

    for k in range(len(x)):
        x_plus = x.copy()
        x_minus = x.copy()

        x_plus[k] += h
        x_minus[k] -= h

        jac[:, k] = (
            equations(x_plus)
            - equations(x_minus)
        ) / (2.0 * h)

    return jac


def test_jacobian_shape():
    net = make_network()
    ybus, _ = build_ybus(net)

    vm = np.array([1.0, 1.02, 0.98])
    va = np.deg2rad([0.0, 2.0, -3.0])

    pv = np.array([1])
    pq = np.array([2])

    jac = build_jacobian(
        ybus, vm, va, pv, pq
    )

    assert isinstance(jac, csr_matrix)
    assert jac.shape == (3, 3)


def test_analytical_vs_numerical():
    net = make_network()
    ybus, _ = build_ybus(net)

    vm = np.array([1.0, 1.02, 0.98])
    va = np.deg2rad([0.0, 2.0, -3.0])

    pv = np.array([1])
    pq = np.array([2])

    analytical = build_jacobian(
        ybus, vm, va, pv, pq
    ).toarray()

    numerical = numerical_jacobian(
        ybus, vm, va, pv, pq
    )

    np.testing.assert_allclose(
        analytical,
        numerical,
        rtol=1e-6,
        atol=1e-6,
    )


def test_flat_start_jacobian():
    net = make_network()
    ybus, _ = build_ybus(net)

    vm = np.ones(3)
    va = np.zeros(3)

    pv = np.array([1])
    pq = np.array([2])

    analytical = build_jacobian(
        ybus, vm, va, pv, pq
    ).toarray()

    numerical = numerical_jacobian(
        ybus, vm, va, pv, pq
    )

    np.testing.assert_allclose(
        analytical,
        numerical,
        rtol=1e-6,
        atol=1e-6,
    )


def test_split_jacobian():
    net = make_network()
    ybus, _ = build_ybus(net)

    jac = build_jacobian(
        ybus,
        np.ones(3),
        np.zeros(3),
        np.array([1]),
        np.array([2]),
    )

    h, n, m, l = split_jacobian(
        jac, n_pv=1, n_pq=1
    )

    assert h.shape == (2, 2)
    assert n.shape == (2, 1)
    assert m.shape == (1, 2)
    assert l.shape == (1, 1)


def test_pq_only_system():
    net = Network()

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "PQ", 132.0, "PQ"))

    net.add_line(Line(1, 2, 0.02, 0.06))

    ybus, _ = build_ybus(net)

    vm = np.array([1.0, 0.97])
    va = np.deg2rad([0.0, -4.0])

    pv = np.array([], dtype=int)
    pq = np.array([1])

    analytical = build_jacobian(
        ybus, vm, va, pv, pq
    ).toarray()

    numerical = numerical_jacobian(
        ybus, vm, va, pv, pq
    )

    assert analytical.shape == (2, 2)

    np.testing.assert_allclose(
        analytical,
        numerical,
        atol=1e-6,
        rtol=1e-6,
    )


def test_transformer_phase_shift():
    net = Network()

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "PQ", 132.0, "PQ"))

    net.add_transformer(
        Transformer(
            1, 2,
            r=0.01,
            x=0.05,
            rating_mva=100.0,
            tap_ratio=1.05,
            phase_shift=10.0,
        )
    )

    ybus, _ = build_ybus(net)

    vm = np.array([1.0, 0.99])
    va = np.deg2rad([0.0, -2.0])

    pv = np.array([], dtype=int)
    pq = np.array([1])

    analytical = build_jacobian(
        ybus, vm, va, pv, pq
    ).toarray()

    numerical = numerical_jacobian(
        ybus, vm, va, pv, pq
    )

    np.testing.assert_allclose(
        analytical,
        numerical,
        atol=1e-6,
        rtol=1e-6,
    )


def test_invalid_voltage():
    net = make_network()
    ybus, _ = build_ybus(net)

    with pytest.raises(ValueError):
        build_jacobian(
            ybus,
            np.array([1.0, 0.0, 1.0]),
            np.zeros(3),
            np.array([1]),
            np.array([2]),
        )


def test_duplicate_indices():
    net = make_network()
    ybus, _ = build_ybus(net)

    with pytest.raises(ValueError):
        build_jacobian(
            ybus,
            np.ones(3),
            np.zeros(3),
            np.array([1]),
            np.array([1, 2]),
        )


def test_invalid_ybus_dimensions():
    with pytest.raises(ValueError):
        build_jacobian(
            np.eye(2),
            np.ones(3),
            np.zeros(3),
            np.array([1]),
            np.array([2]),
        )


def test_invalid_split_dimensions():
    jac = csr_matrix(np.eye(3))

    with pytest.raises(ValueError):
        split_jacobian(
            jac, n_pv=2, n_pq=1
        )
