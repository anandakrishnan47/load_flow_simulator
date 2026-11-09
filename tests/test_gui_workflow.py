
"""
Module 12: End-to-end PySide6 GUI workflow tests.
"""

import pytest

from PySide6.QtCore import Qt

from gui.main_window import MainWindow


@pytest.fixture
def window(qtbot):
    main_window = MainWindow()
    qtbot.addWidget(main_window)

    return main_window


def test_application_starts(window):
    assert window.network is not None
    assert window.worker is None


def test_all_required_tabs_exist(window):
    titles = {
        window.tabs.tabText(i)
        for i in range(window.tabs.count())
    }

    expected = {
        "Single-Line Diagram",
        "Charts",
        "Bus Results",
        "Branch Flows",
        "Summary",
        "Convergence",
    }

    assert expected.issubset(titles)


def test_network_selection(window):
    window.network_combo.setCurrentText(
        "IEEE 14-Bus"
    )

    window.load_selected_network()

    assert len(window.network.buses) == 14
    assert window.load_table.rowCount() == 14
    assert len(
        window.diagram_editor.scene.bus_items
    ) == 14


def test_diagram_changes_synchronize(window):
    window.diagram_editor.scene.add_bus(
        4,
        bus_type="PQ",
        x=400,
        y=300,
    )

    window.sync_diagram_to_network()

    assert len(window.network.buses) == 4
    assert window.load_table.rowCount() == 4


def test_invalid_load_rejected(window):
    window.load_table.item(2, 2).setText(
        "invalid"
    )

    with pytest.raises(ValueError):
        window.read_load_table()


def test_complete_gui_load_flow(qtbot, window):
    """
    Start a real background calculation.

    qtbot.waitUntil processes the Qt event loop
    until the worker finishes or timeout expires.
    """
    window.run_load_flow()

    qtbot.waitUntil(
        lambda: window.worker is None,
        timeout=20000,
    )

    assert window.study is not None
    assert window.study.solution.converged

    assert window.bus_table.rowCount() == 3
    assert window.branch_table.rowCount() == 3

    assert window.results_charts.study is window.study
    assert window.export_panel.study is window.study

    assert window.export_panel.csv_button.isEnabled()
    assert window.export_panel.excel_button.isEnabled()
    assert window.export_panel.pdf_button.isEnabled()


def test_clear_results_disables_export(window):
    from gui.controller import (
        load_network,
        run_study,
    )

    study = run_study(
        load_network("3-Bus Example")
    )

    window.on_completed(study)

    assert window.export_panel.study is study

    window.clear_results()

    assert window.study is None
    assert window.export_panel.study is None

    assert not window.export_panel.csv_button.isEnabled()


def test_switching_network_clears_old_results(window):
    from gui.controller import (
        load_network,
        run_study,
    )

    study = run_study(
        load_network("3-Bus Example")
    )

    window.on_completed(study)

    window.network_combo.setCurrentText(
        "IEEE 14-Bus"
    )

    window.load_selected_network()

    assert window.study is None
    assert window.export_panel.study is None
    assert window.bus_table.rowCount() == 0


def test_voltage_coloring_after_solution(window):
    from gui.controller import (
        load_network,
        run_study,
    )

    study = run_study(
        load_network("3-Bus Example")
    )

    window.on_completed(study)

    for item in window.diagram_editor.scene.bus_items.values():
        assert item.voltage is not None
