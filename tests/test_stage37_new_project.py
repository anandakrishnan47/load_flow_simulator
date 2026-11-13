"""Stage 3.7 regression tests for the blank project workflow."""

from PySide6.QtWidgets import QMessageBox
from gui.main_window import MainWindow


def test_new_project_starts_empty(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project()
    network = window.diagram_editor.get_network()
    assert len(network.buses) == 0
    assert len(network.lines) == 0
    assert len(network.transformers) == 0
    assert window.project_path is None
    assert window.tabs.currentWidget() is window.diagram_editor


def test_new_project_allows_first_slack_bus(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_project()
    window.diagram_editor.scene.add_bus(1, bus_type="Slack", x=100, y=100)
    assert window.diagram_editor.scene.bus_count() == 1
    assert window.diagram_editor.scene.can_undo()


def test_new_project_can_be_cancelled(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.diagram_editor.scene.add_bus(99, bus_type="PQ")
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )
    window.new_project()
    assert 99 in window.diagram_editor.scene.bus_items
