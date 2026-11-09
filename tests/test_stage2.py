
"""
Stage 2 numerical engine tests.

Tests:
    1. ZIP load power and derivatives
    2. Analytical ZIP Jacobian
    3. Flat-start Newton-Raphson
    4. Warm-start Newton-Raphson
    5. Generator Q-limit switching
    6. Switching event logging
"""

import numpy as np
import pytest

from loadflow.models import (
    Network,
    Bus,
    Line,
    Generator,
    Load,
    ExternalGrid,
)

from loadflow.power import (
    calculate_load_power,
    specified_power,
)

from loadflow.jacobian import build_jacobian

from loadflow.ybus import build_ybus

from loadflow.solver import solve_load_flow

from loadflow.qlimits import solve_with_q_limits


def make_network():
    """Create a simple three-bus network."""

    network = Network(base_mva=100.0)

    network.buses.extend([
        Bus(
            number=1,
            name="Slack",
            base_kv=230,
            bus_type="Slack",
            vm=1.04,
        ),
        Bus(
            number=2,
            name="Generator",
            base_kv=230,
            bus_type="PV",
            vm=1.01,
        ),
        Bus(
            number=3,
            name="Load",
            base_kv=230,
            bus_type="PQ",
        ),
    ])

    network.lines.extend([
        Line(
            from_bus=1,
            to_bus=2,
            r=0.02,
            x=0.06,
        ),
        Line(
            from_bus=1,
            to_bus=3,
            r=0.08,
            x=0.24,
        ),
        Line(
            from_bus=2,
            to_bus=3,
            r=0.06,
            x=0.18,
        ),
    ])

    network.external_grids.append(
        ExternalGrid(
            bus=1,
            vm=1.04,
            va=0.0,
        )
    )

    network.generators.append(
        Generator(
            bus=2,
            pg=40.0,
            qg=0.0,
            vg=1.01,
            qmin=-100.0,
            qmax=100.0,
        )
    )

    network.loads.append(
        Load(
            bus=3,
            pd=60.0,
            qd=30.0,
            model="ZIP",
            zip_p=(0.3, 0.2, 0.5),
            zip_q=(0.2, 0.3, 0.5),
        )
    )

    return network


def test_zip_load_power_and_derivatives():
    network = make_network()

    bus_index = {
        1: 0,
        2: 1,
        3: 2,
    }

    vm = np.array([
        1.04,
        1.01,
        0.95,
    ])

    p, q, dp, dq = calculate_load_power(
        network,
        bus_index,
        vm,
    )

    expected_p = (
        0.6
        * (
            0.3 * 0.95**2
            + 0.2 * 0.95
            + 0.5
        )
    )

    expected_q = (
        0.3
        * (
            0.2 * 0.95**2
            + 0.3 * 0.95
            + 0.5
        )
    )

    expected_dp = (
        0.6
        * (
            2 * 0.3 * 0.95
            + 0.2
        )
    )

    expected_dq = (
        0.3
        * (
            2 * 0.2 * 0.95
            + 0.3
        )
    )

    assert p[2] == pytest.approx(expected_p)
    assert q[2] == pytest.approx(expected_q)

    assert dp[2] == pytest.approx(expected_dp)
    assert dq[2] == pytest.approx(expected_dq)


def test_zip_specified_power():
    network = make_network()

    bus_index = {
        1: 0,
        2: 1,
        3: 2,
    }

    vm = np.array([
        1.04,
        1.01,
        0.95,
    ])

    p_spec, q_spec = specified_power(
        network,
        bus_index,
        vm=vm,
    )

    p_load, q_load, _, _ = calculate_load_power(
        network,
        bus_index,
        vm,
    )

    assert p_spec[2] == pytest.approx(-p_load[2])
    assert q_spec[2] == pytest.approx(-q_load[2])

    assert p_spec[1] == pytest.approx(0.4)


def test_zip_jacobian_derivatives():
    network = make_network()

    ybus, bus_index = build_ybus(network)

    vm = np.array([
        1.04,
        1.01,
        0.95,
    ])

    va = np.array([
        0.0,
        -0.02,
        -0.05,
    ])

    pv = np.array([
        bus_index[2],
    ])

    pq = np.array([
        bus_index[3],
    ])

    _, _, dp, dq = calculate_load_power(
        network,
        bus_index,
        vm,
    )

    j_base = build_jacobian(
        ybus,
        vm,
        va,
        pv,
        pq,
    )

    j_zip = build_jacobian(
        ybus,
        vm,
        va,
        pv,
        pq,
        dp_load_dv=dp,
        dq_load_dv=dq,
    )

    difference = (
        j_zip - j_base
    ).toarray()

    # State order:
    # delta_PV, delta_PQ, V_PQ

    assert difference[1, 2] == pytest.approx(dp[2])
    assert difference[2, 2] == pytest.approx(dq[2])

    # ZIP derivatives must not alter H or M.
    assert np.allclose(
        difference[:, :2],
        0.0,
    )


def test_flat_start():
    network = make_network()

    result = solve_load_flow(
        network,
        initialization="flat",
    )

    assert result.converged
    assert result.mismatch < 1e-8

    assert result.vm[
        result.bus_index[1]
    ] == pytest.approx(1.04)

    assert result.vm[
        result.bus_index[2]
    ] == pytest.approx(1.01)


def test_warm_start():
    network = make_network()

    first = solve_load_flow(
        network,
        initialization="flat",
    )

    assert first.converged

    second = solve_load_flow(
        network,
        initialization="previous",
        previous_result=first,
    )

    assert second.converged
    assert second.iterations == 0

    assert np.allclose(
        first.vm,
        second.vm,
        atol=1e-10,
    )

    assert np.allclose(
        first.va,
        second.va,
        atol=1e-10,
    )


def test_q_limit_switching():
    network = make_network()

    gen = network.generators[0]

    # Deliberately restrictive Q limits.
    gen.qmin = -1.0
    gen.qmax = 1.0

    result = solve_with_q_limits(
        network,
        max_outer_iterations=10,
    )

    assert result.converged

    assert result.bus_types[2] == "PQ"

    assert 2 in result.switched_buses

    assert result.generator_q[2] == pytest.approx(
        gen.qmax,
        abs=1e-5,
    ) or result.generator_q[2] == pytest.approx(
        gen.qmin,
        abs=1e-5,
    )


def test_q_limit_event_logging():
    network = make_network()

    network.generators[0].qmin = -1.0
    network.generators[0].qmax = 1.0

    result = solve_with_q_limits(
        network,
        max_outer_iterations=10,
    )

    assert result.converged

    assert len(result.switching_events) >= 1

    event = result.switching_events[0]

    assert event["bus"] == 2
    assert event["from_type"] == "PV"
    assert event["to_type"] == "PQ"
