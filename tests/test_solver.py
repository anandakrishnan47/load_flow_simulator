
"""Module 5: Newton-Raphson solver tests."""

import numpy as np
import pytest

from loadflow.models import (
    Network, Bus, Line, Generator,
    Load, ExternalGrid
)
from loadflow.ybus import build_ybus
from loadflow.power import (
    calculate_power, specified_power,
    get_bus_types, calculate_mismatch
)
from loadflow.solver import solve_load_flow
from main import create_sample_network


def make_two_bus_network():
    """
    Create a two-bus system with a known
    reference solution.

    The load is calculated from a chosen
    voltage solution, independently of
    the Newton-Raphson solver.
    """
    net = Network(base_mva=100.0)

    net.add_bus(
        Bus(1, "Slack", 132.0, "Slack")
    )
    net.add_bus(
        Bus(2, "Load", 132.0, "PQ")
    )

    net.add_line(
        Line(1, 2, 0.02, 0.06)
    )

    net.add_external_grid(
        ExternalGrid(bus=1, vm=1.0, va=0.0)
    )

    ybus, _ = build_ybus(net)

    target_vm = np.array([1.0, 0.98])
    target_va = np.array([0.0, -0.04])

    p, q = calculate_power(
        ybus, target_vm, target_va
    )

    # A negative injection represents load.
    net.add_load(
        Load(
            bus=2,
            pd=-p[1] * net.base_mva,
            qd=-q[1] * net.base_mva,
        )
    )

    return net, target_vm, target_va


def test_two_bus_convergence():
    net, target_vm, target_va = (
        make_two_bus_network()
    )

    result = solve_load_flow(
        net,
        tolerance=1e-10,
        max_iterations=30,
    )

    assert result.converged
    assert result.mismatch < 1e-10

    np.testing.assert_allclose(
        result.vm,
        target_vm,
        atol=1e-7,
    )

    np.testing.assert_allclose(
        np.deg2rad(result.va),
        target_va,
        atol=1e-7,
    )


def test_three_bus_convergence():
    net = create_sample_network()

    result = solve_load_flow(
        net,
        tolerance=1e-8,
        max_iterations=30,
    )

    assert result.converged
    assert result.mismatch < 1e-8
    assert result.iterations > 0
    assert result.vm.shape == (3,)
    assert result.va.shape == (3,)


def test_slack_voltage_fixed():
    net = create_sample_network()

    result = solve_load_flow(net)

    assert result.converged

    i = result.bus_index[1]

    assert result.vm[i] == pytest.approx(1.0)
    assert result.va[i] == pytest.approx(0.0)


def test_pv_voltage_fixed():
    net = create_sample_network()

    result = solve_load_flow(net)

    assert result.converged

    i = result.bus_index[2]

    assert result.vm[i] == pytest.approx(1.02)


def test_power_balance():
    net = create_sample_network()

    result = solve_load_flow(
        net, tolerance=1e-10
    )

    assert result.converged

    ybus, mapping = build_ybus(net)

    p_spec, q_spec = specified_power(
        net, mapping
    )

    _, pv, pq = get_bus_types(net, mapping)

    mismatch, _, _ = calculate_mismatch(
        ybus,
        result.vm,
        np.deg2rad(result.va),
        p_spec,
        q_spec,
        pv,
        pq,
    )

    assert np.max(np.abs(mismatch)) < 1e-10


def test_iteration_limit():
    net = create_sample_network()

    result = solve_load_flow(
        net,
        tolerance=1e-12,
        max_iterations=0,
    )

    assert not result.converged
    assert result.iterations == 0
    assert result.message == "Maximum iterations reached"


def test_invalid_tolerance():
    net = create_sample_network()

    with pytest.raises(ValueError):
        solve_load_flow(net, tolerance=0.0)


def test_invalid_iteration_count():
    net = create_sample_network()

    with pytest.raises(ValueError):
        solve_load_flow(
            net, max_iterations=-1
        )


def test_disconnected_network():
    net = Network()

    net.add_bus(
        Bus(1, "Slack", 132.0, "Slack")
    )
    net.add_bus(
        Bus(2, "PQ", 132.0, "PQ")
    )

    with pytest.raises(
        ValueError, match="disconnected"
    ):
        solve_load_flow(net)


def test_missing_slack_bus():
    net = Network()

    net.add_bus(
        Bus(1, "PQ", 132.0, "PQ")
    )

    with pytest.raises(
        ValueError, match="slack"
    ):
        solve_load_flow(net)


def test_result_history():
    net = create_sample_network()

    result = solve_load_flow(net)

    assert result.converged

    assert len(result.mismatch_history) == (
        result.iterations + 1
    )

    assert result.mismatch_history[-1] < (
        result.mismatch_history[0]
    )


def test_out_of_service_line():
    net = create_sample_network()

    for line in net.lines:
        line.in_service = False

    with pytest.raises(
        ValueError, match="disconnected"
    ):
        solve_load_flow(net)
