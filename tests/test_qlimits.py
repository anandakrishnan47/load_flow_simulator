
"""Module 6: Generator Q-limit tests."""

import numpy as np
import pytest

from loadflow.models import (
    Network, Bus, Line, Generator,
    Load, ExternalGrid
)
from loadflow.solver import solve_load_flow
from loadflow.qlimits import (
    calculate_generator_q,
    solve_with_q_limits,
)


def make_network(
    qd=30.0,
    qmin=-50.0,
    qmax=50.0,
):
    """
    Two-bus system:
        Bus 1: Slack, 1.0 pu
        Bus 2: PV generator, 1.0 pu
        Line: X = 0.1 pu
        Pgen = 0 MW

    The reactive load is connected to bus 2.
    """
    net = Network(base_mva=100.0)

    net.add_bus(
        Bus(1, "Slack", 132.0, "Slack")
    )

    net.add_bus(
        Bus(2, "Generator", 132.0, "PV")
    )

    net.add_line(
        Line(1, 2, 0.0, 0.1)
    )

    net.add_external_grid(
        ExternalGrid(
            bus=1, vm=1.0, va=0.0
        )
    )

    net.add_generator(
        Generator(
            bus=2,
            pg=0.0,
            vg=1.0,
            qmin=qmin,
            qmax=qmax,
        )
    )

    net.add_load(
        Load(bus=2, pd=0.0, qd=qd)
    )

    return net


def test_calculate_generator_q():
    net = make_network()

    result = solve_load_flow(net)

    assert result.converged

    qgen = calculate_generator_q(
        net, result
    )

    assert qgen[2] == pytest.approx(
        30.0, abs=1e-6
    )


def test_no_limit_violation():
    net = make_network(
        qmin=-50.0,
        qmax=50.0,
    )

    result = solve_with_q_limits(net)

    assert result.converged
    assert result.bus_types[2] == "PV"
    assert result.switched_buses == []
    assert result.outer_iterations == 1

    assert result.generator_q[2] == pytest.approx(
        30.0, abs=1e-6
    )


def test_upper_q_limit():
    net = make_network(
        qmin=-50.0,
        qmax=10.0,
    )

    result = solve_with_q_limits(net)

    assert result.converged
    assert result.bus_types[2] == "PQ"
    assert result.switched_buses == [2]

    assert result.generator_q[2] == pytest.approx(
        10.0
    )

    # Upper Q limit means insufficient reactive
    # generation, so the bus voltage decreases.
    i = result.load_flow.bus_index[2]

    assert result.load_flow.vm[i] < 1.0


def test_upper_limit_analytical_voltage():
    net = make_network(
        qmin=-50.0,
        qmax=10.0,
    )

    result = solve_with_q_limits(net)

    assert result.converged

    # Qnet = (10 - 30) / 100 = -0.2 pu.
    # For X=0.1, V1=1:
    # Qnet = V2 * (V2 - 1) / X
    # V2^2 - V2 + 0.02 = 0
    expected = (
        1.0 + np.sqrt(1.0 - 0.08)
    ) / 2.0

    i = result.load_flow.bus_index[2]

    assert result.load_flow.vm[i] == pytest.approx(
        expected, abs=1e-6
    )


def test_lower_q_limit():
    # Negative Qd represents capacitive demand.
    # The generator must absorb 30 MVAr at V=1 pu.
    net = make_network(
        qd=-30.0,
        qmin=-10.0,
        qmax=50.0,
    )

    result = solve_with_q_limits(net)

    assert result.converged
    assert result.bus_types[2] == "PQ"
    assert result.switched_buses == [2]

    assert result.generator_q[2] == pytest.approx(
        -10.0
    )

    # Insufficient reactive absorption causes
    # the bus voltage to increase.
    i = result.load_flow.bus_index[2]

    assert result.load_flow.vm[i] > 1.0


def test_lower_limit_analytical_voltage():
    net = make_network(
        qd=-30.0,
        qmin=-10.0,
        qmax=50.0,
    )

    result = solve_with_q_limits(net)

    assert result.converged

    # Qnet = (-10 - (-30)) / 100 = 0.2 pu
    # V2^2 - V2 - 0.02 = 0
    expected = (
        1.0 + np.sqrt(1.0 + 0.08)
    ) / 2.0

    i = result.load_flow.bus_index[2]

    assert result.load_flow.vm[i] == pytest.approx(
        expected, abs=1e-6
    )


def test_original_network_unchanged():
    net = make_network(qmax=10.0)

    result = solve_with_q_limits(net)

    assert result.converged

    # The original model must not be modified.
    assert net.buses[1].bus_type == "PV"
    assert net.generators[0].qg == 0.0


def test_outer_iteration_count():
    net = make_network(qmax=10.0)

    result = solve_with_q_limits(net)

    assert result.converged
    assert result.outer_iterations == 2


def test_insufficient_outer_iterations():
    net = make_network(qmax=10.0)

    result = solve_with_q_limits(
        net,
        max_outer_iterations=1,
    )

    assert not result.converged
    assert "Maximum Q-limit" in result.message


def test_invalid_q_tolerance():
    net = make_network()

    with pytest.raises(ValueError):
        solve_with_q_limits(
            net, q_tolerance=-1.0
        )


def test_invalid_outer_iterations():
    net = make_network()

    with pytest.raises(ValueError):
        solve_with_q_limits(
            net, max_outer_iterations=0
        )


def test_multiple_generators_rejected():
    net = make_network()

    net.add_generator(
        Generator(
            bus=2,
            pg=0.0,
            vg=1.0,
            qmin=-10.0,
            qmax=10.0,
        )
    )

    with pytest.raises(
        ValueError,
        match="exactly one",
    ):
        solve_with_q_limits(net)


def test_inner_solver_failure():
    net = make_network(qmax=10.0)

    result = solve_with_q_limits(
        net,
        tolerance=1e-12,
        max_iterations=0,
    )

    # This particular flat-start PV system has
    # zero mismatch initially, so it can converge
    # without Newton corrections. The Q limit
    # still requires a second solve, which fails.
    assert not result.converged
    assert "Inner Newton-Raphson" in result.message


def test_three_bus_integration():
    from main import create_sample_network

    net = create_sample_network()

    # Apply a restrictive Q limit to the
    # generator at bus 2.
    net.generators[0].qmin = -5.0
    net.generators[0].qmax = 5.0

    result = solve_with_q_limits(net)

    assert result.converged

    qg = result.generator_q[2]

    assert -5.0 - 1e-5 <= qg <= 5.0 + 1e-5

    assert result.load_flow.mismatch < 1e-8
