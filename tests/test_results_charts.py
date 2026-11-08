
"""Module 11: Chart and export panel GUI tests."""

import pytest

from gui.controller import (
    load_network,
    run_study,
)
from gui.results_charts import ResultsCharts
from gui.export_dialog import ExportPanel
from gui.main_window import MainWindow


@pytest.fixture(scope="module")
def study():
    return run_study(
        load_network("3-Bus Example")
    )


def test_charts_widget_creation(qtbot):
    widget = ResultsCharts()
    qtbot.addWidget(widget)

    assert widget.chart_combo.count() == 4


def test_charts_accept_study(qtbot, study):
    widget = ResultsCharts()
    qtbot.addWidget(widget)

    widget.set_study(study)

    assert widget.study is study


@pytest.mark.parametrize(
    "chart_name",
    [
        "Voltage Magnitude",
        "Voltage Angle",
        "Convergence",
        "Branch Loading",
    ],
)
def test_all_chart_types(qtbot, study, chart_name):
    widget = ResultsCharts()
    qtbot.addWidget(widget)

    widget.set_study(study)
    widget.chart_combo.setCurrentText(
        chart_name
    )

    widget.refresh()

    assert len(widget.figure.axes) == 1


def test_save_chart_png(qtbot, study, tmp_path):
    widget = ResultsCharts()
    qtbot.addWidget(widget)

    widget.set_study(study)

    path = tmp_path / "voltage.png"
    widget.save_png(path)

    assert path.exists()
    assert path.stat().st_size > 1000


def test_save_without_study_rejected(qtbot, tmp_path):
    widget = ResultsCharts()
    qtbot.addWidget(widget)

    with pytest.raises(ValueError):
        widget.save_png(
            tmp_path / "invalid.png"
        )


def test_export_panel_initially_disabled(qtbot):
    panel = ExportPanel()
    qtbot.addWidget(panel)

    assert not panel.csv_button.isEnabled()
    assert not panel.excel_button.isEnabled()
    assert not panel.pdf_button.isEnabled()


def test_export_panel_enabled(qtbot, study):
    panel = ExportPanel()
    qtbot.addWidget(panel)

    panel.set_study(study)

    assert panel.csv_button.isEnabled()
    assert panel.excel_button.isEnabled()
    assert panel.pdf_button.isEnabled()


def test_export_panel_clear(qtbot, study):
    panel = ExportPanel()
    qtbot.addWidget(panel)

    panel.set_study(study)
    panel.set_study(None)

    assert not panel.csv_button.isEnabled()


def test_main_window_charts_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    titles = [
        window.tabs.tabText(i)
        for i in range(window.tabs.count())
    ]

    assert "Charts" in titles


def test_main_window_export_panel(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.export_panel is not None
    assert not window.export_panel.csv_button.isEnabled()


def test_main_window_results_integration(qtbot, study):
    window = MainWindow()
    qtbot.addWidget(window)

    window.on_completed(study)

    assert window.results_charts.study is study
    assert window.export_panel.study is study

    window.clear_results()

    assert window.results_charts.study is None
    assert window.export_panel.study is None
