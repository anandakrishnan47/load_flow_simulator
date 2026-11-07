
"""Module 7: Branch power-flow and loss tests."""

import numpy as np
import pytest

from main import create_sample_network

from loadflow.models import (
    Network, Bus, Line, Transformer,
    Load, ExternalGrid, Shunt,
)
from loadflow.solver import solve_load_flow
from loadflow.branch_flows import (
    calculate_branch_flows,
)


def make_two_bus(
    r=0.02, x=0.06, b=0.0,
    rating=100.0,
):
    net = Network(base_mva=100.0)

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "Load", 132.0, "PQ"))

    net.add_line(
        Line(
            1, 2, r, x,
            b=b,
            rating_mva=rating,
        )
    )

    net.add_external_grid(
        ExternalGrid(bus=1, vm=1.0, va=0.0)
    )

    net.add_load(
        Load(bus=2, pd=30.0, qd=15.0)
    )

    return net


def test_two_bus_convergence_and_flows():
    net = make_two_bus()

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    assert len(flows.branches) == 1
    assert flows.branches[0].kind == "Line"
    assert flows.branches[0].from_bus == 1
    assert flows.branches[0].to_bus == 2

    assert flows.total_p_loss > 0.0


def test_analytical_resistive_loss():
    net = make_two_bus()

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    v1 = result.vm[result.bus_index[1]] * np.exp(
        1j * np.deg2rad(
            result.va[result.bus_index[1]]
        )
    )

    v2 = result.vm[result.bus_index[2]] * np.exp(
        1j * np.deg2rad(
            result.va[result.bus_index[2]]
        )
    )

    line = net.lines[0]

    current = (
        (v1 - v2)
        / complex(line.r, line.x)
    )

    expected_p_loss = (
        abs(current) ** 2
        * line.r
        * net.base_mva
    )

    assert flows.total_p_loss == pytest.approx(
        expected_p_loss, abs=1e-8
    )


def test_analytical_reactive_series_loss():
    net = make_two_bus()

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    i1 = result.bus_index[1]
    i2 = result.bus_index[2]

    v1 = result.vm[i1] * np.exp(
        1j * np.deg2rad(result.va[i1])
    )
    v2 = result.vm[i2] * np.exp(
        1j * np.deg2rad(result.va[i2])
    )

    line = net.lines[0]
    current = (v1 - v2) / complex(line.r, line.x)

    expected_q = (
        abs(current) ** 2
        * line.x
        * net.base_mva
    )

    assert flows.total_q_net == pytest.approx(
        expected_q, abs=1e-8
    )


def test_terminal_power_balance():
    net = make_two_bus()

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    branch = flows.branches[0]

    assert branch.p_loss == pytest.approx(
        branch.p_from + branch.p_to
    )

    assert branch.q_net == pytest.approx(
        branch.q_from + branch.q_to
    )


def test_loading_percentage():
    net = make_two_bus(rating=50.0)

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    branch = flows.branches[0]

    expected = (
        max(branch.s_from, branch.s_to)
        / 50.0 * 100.0
    )

    assert branch.loading_percent == pytest.approx(
        expected
    )


def test_three_bus_power_balance():
    net = create_sample_network()

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    assert len(flows.branches) == 3

    assert abs(flows.bus_p_balance_error) < 1e-7
    assert abs(flows.bus_q_balance_error) < 1e-7


def test_line_charging():
    net = make_two_bus(b=0.04)

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    i1 = result.bus_index[1]
    i2 = result.bus_index[2]

    v1 = result.vm[i1] * np.exp(
        1j * np.deg2rad(result.va[i1])
    )
    v2 = result.vm[i2] * np.exp(
        1j * np.deg2rad(result.va[i2])
    )

    line = net.lines[0]
    current = (
        (v1 - v2)
        / complex(line.r, line.x)
    )

    expected_q = net.base_mva * (
        abs(current) ** 2 * line.x
        - line.b / 2.0
        * (abs(v1) ** 2 + abs(v2) ** 2)
    )

    assert flows.total_q_net == pytest.approx(
        expected_q, abs=1e-8
    )


def test_transformer_tap():
    net = Network(base_mva=100.0)

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "PQ", 132.0, "PQ"))

    net.add_external_grid(
        ExternalGrid(bus=1)
    )

    net.add_transformer(
        Transformer(
            1, 2,
            r=0.01,
            x=0.05,
            rating_mva=100.0,
            tap_ratio=1.05,
        )
    )

    net.add_load(
        Load(bus=2, pd=20.0, qd=10.0)
    )

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    assert len(flows.branches) == 1
    assert flows.branches[0].kind == "Transformer"
    assert flows.total_p_loss >= -1e-8

    assert abs(flows.bus_p_balance_error) < 1e-7
    assert abs(flows.bus_q_balance_error) < 1e-7


def test_phase_shifting_transformer():
    net = Network(base_mva=100.0)

    net.add_bus(Bus(1, "Slack", 132.0, "Slack"))
    net.add_bus(Bus(2, "PQ", 132.0, "PQ"))

    net.add_external_grid(
        ExternalGrid(bus=1)
    )

    net.add_transformer(
        Transformer(
            1, 2,
            r=0.01,
            x=0.05,
            rating_mva=100.0,
            tap_ratio=1.0,
            phase_shift=5.0,
        )
    )

    net.add_load(
        Load(bus=2, pd=20.0, qd=10.0)
    )

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    assert abs(flows.bus_p_balance_error) < 1e-7
    assert abs(flows.bus_q_balance_error) < 1e-7


def test_explicit_bus_shunt_balance():
    net = make_two_bus()

    net.add_shunt(
        Shunt(bus=2, gs=2.0, bs=5.0)
    )

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    assert abs(flows.bus_p_balance_error) < 1e-7
    assert abs(flows.bus_q_balance_error) < 1e-7


def test_out_of_service_branch_excluded():
    net = make_two_bus()

    result = solve_load_flow(net)
    assert result.converged

    # Exclude the line in a reporting-only copy.
    # The original solved network remains intact.
    from copy import deepcopy

    report_net = deepcopy(net)
    report_net.lines[0].in_service = False

    flows = calculate_branch_flows(
        report_net, result
    )

    assert len(flows.branches) == 0
    assert flows.total_p_loss == 0.0


def test_reject_nonconverged_result():
    net = make_two_bus()

    result = solve_load_flow(
        net, max_iterations=0
    )

    assert not result.converged

    with pytest.raises(
        ValueError, match="converged"
    ):
        calculate_branch_flows(net, result)


def test_invalid_rating():
    net = make_two_bus()

    result = solve_load_flow(net)
    assert result.converged

    net.lines[0].rating_mva = 0.0

    with pytest.raises(
        ValueError, match="rating"
    ):
        calculate_branch_flows(net, result)


def test_total_losses_equal_sum():
    net = create_sample_network()

    result = solve_load_flow(net)
    assert result.converged

    flows = calculate_branch_flows(net, result)

    expected_p = sum(
        branch.p_loss for branch in flows.branches
    )
    expected_q = sum(
        branch.q_net for branch in flows.branches
    )

    assert flows.total_p_loss == pytest.approx(
        expected_p
    )
    assert flows.total_q_net == pytest.approx(
        expected_q
    )
