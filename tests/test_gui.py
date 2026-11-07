
"""Module 9: GUI and controller tests."""

import pytest

from gui.controller import (
    NETWORKS,
    load_network,
    update_loads,
    run_study,
)
from gui.main_window import MainWindow


def test_network_options():
    assert len(NETWORKS) == 5
    assert "IEEE 118-Bus" in NETWORKS


def test_load_sample_network():
    net = load_network("3-Bus Example")

    assert len(net.buses) == 3
    assert len(net.lines) == 3


@pytest.mark.parametrize(
    "name,count",
    [
        ("IEEE 14-Bus", 14),
        ("IEEE 30-Bus", 30),
        ("IEEE 57-Bus", 57),
        ("IEEE 118-Bus", 118),
    ],
)
def test_load_ieee_network(name, count):
    net = load_network(name)
    assert len(net.buses) == count


def test_invalid_network_name():
    with pytest.raises(ValueError):
        load_network("Unknown Network")


def test_update_loads():
    net = load_network("3-Bus Example")

    edited = update_loads(
        net,
        {3: (75.0, 35.0)},
    )

    load = next(
        load for load in edited.loads
        if load.bus == 3
    )

    assert load.pd == 75.0
    assert load.qd == 35.0


def test_original_network_unchanged():
    net = load_network("3-Bus Example")

    update_loads(
        net,
        {3: (80.0, 40.0)},
    )

    original = next(
        load for load in net.loads
        if load.bus == 3
    )

    assert original.pd == 60.0
    assert original.qd == 30.0


def test_invalid_load_bus():
    net = load_network("3-Bus Example")

    with pytest.raises(ValueError):
        update_loads(
            net, {999: (10.0, 5.0)}
        )


def test_nonfinite_load_rejected():
    net = load_network("3-Bus Example")

    with pytest.raises(ValueError):
        update_loads(
            net, {3: (float("nan"), 10.0)}
        )


def test_controller_solver():
    net = load_network("3-Bus Example")

    study = run_study(net)

    assert study.solution.converged
    assert study.solution.mismatch < 1e-8
    assert len(study.flows.branches) == 3


def test_controller_q_limits():
    net = load_network("3-Bus Example")

    study = run_study(
        net,
        enforce_q_limits=True,
    )

    assert study.solution.converged
    assert study.q_limits is not None


def test_main_window_creation(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert "APSA" in window.windowTitle()
    assert window.load_table.rowCount() == 3


def test_network_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.network_combo.setCurrentText(
        "IEEE 14-Bus"
    )

    window.load_selected_network()

    assert window.load_table.rowCount() == 14


def test_editable_load_table(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    # Sample network order: buses 1, 2, 3.
    window.load_table.item(2, 2).setText(
        "70.0"
    )

    values = window.read_load_table()

    assert values[3][0] == 70.0


def test_populate_results(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    study = run_study(window.network)

    window.populate_results(study)

    assert window.bus_table.rowCount() == 3
    assert window.branch_table.rowCount() == 3

    assert "Total active loss" in (
        window.summary_text.toPlainText()
    )


def test_convergence_history(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    study = run_study(window.network)

    window.populate_results(study)

    text = window.history_text.toPlainText()

    assert "Iteration" in text
    assert "mismatch" in text.lower()


def test_background_worker(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    with qtbot.waitSignal(
        window.run_button.clicked,
        timeout=3000,
    ):
        window.run_button.click()

    # Wait for the background calculation to finish.
    qtbot.waitUntil(
        lambda: window.worker is None,
        timeout=30000,
    )

    assert window.study is not None
    assert window.study.solution.converged
    assert window.bus_table.rowCount() == 3
