
"""Module 10: Interactive SLD editor tests."""

import json

import pytest

from PySide6.QtCore import QPointF

from gui.controller import (
    load_network,
    run_study,
)
from gui.diagram_scene import DiagramScene
from gui.diagram_editor import DiagramEditor
from gui.main_window import MainWindow


@pytest.fixture
def scene(qtbot):
    network = load_network("3-Bus Example")
    return DiagramScene(network)


def test_initial_bus_count(scene):
    assert len(scene.bus_items) == 3


def test_initial_branch_count(scene):
    assert len(scene.branch_items) == 3


def test_bus_movement_updates_branch(scene):
    bus = scene.bus_items[1]
    branch = bus.branches[0]

    old_line = branch.line()

    bus.setPos(
        bus.pos() + QPointF(80, 40)
    )

    new_line = branch.line()

    assert old_line != new_line


def test_add_bus(scene):
    scene.add_bus(
        4,
        bus_type="PQ",
        x=500,
        y=300,
    )

    assert len(scene.network.buses) == 4
    assert 4 in scene.bus_items


def test_duplicate_bus_rejected(scene):
    with pytest.raises(ValueError):
        scene.add_bus(1)


def test_second_slack_rejected(scene):
    with pytest.raises(ValueError):
        scene.add_bus(
            4, bus_type="Slack"
        )


def test_add_line(scene):
    scene.add_bus(4)

    scene.add_line(
        3, 4,
        r=0.02,
        x=0.08,
    )

    assert len(scene.network.lines) == 4
    assert len(scene.branch_items) == 4


def test_add_transformer(scene):
    scene.add_bus(4)

    scene.add_transformer(
        2, 4,
        r=0.01,
        x=0.05,
        tap_ratio=1.05,
    )

    assert len(scene.network.transformers) == 1

    assert any(
        item.kind == "Transformer"
        for item in scene.branch_items
    )


def test_remove_bus_and_connected_branches(scene):
    scene.remove_bus(3)

    assert 3 not in scene.bus_items

    assert all(
        3 not in (line.from_bus, line.to_bus)
        for line in scene.network.lines
    )

    assert all(
        load.bus != 3
        for load in scene.network.loads
    )


def test_slack_bus_protected(scene):
    with pytest.raises(ValueError):
        scene.remove_bus(1)


def test_remove_branch(scene):
    branch = scene.network.lines[0]

    scene.remove_branch(branch)

    assert len(scene.network.lines) == 2
    assert len(scene.branch_items) == 2


def test_layout_save_and_load(scene, tmp_path):
    path = tmp_path / "layout.json"

    scene.bus_items[1].setPos(350, 220)
    scene.save_layout(path)

    scene.bus_items[1].setPos(100, 100)

    scene.load_layout(path)

    assert scene.bus_items[1].pos().x() == 350
    assert scene.bus_items[1].pos().y() == 220

    data = json.loads(path.read_text())

    assert data["version"] == 1


def test_invalid_layout_version(scene, tmp_path):
    path = tmp_path / "invalid.json"

    path.write_text(
        json.dumps({
            "version": 999,
            "positions": {},
        })
    )

    with pytest.raises(ValueError):
        scene.load_layout(path)


def test_apply_solution(scene):
    network = load_network("3-Bus Example")

    study = run_study(network)

    scene.apply_solution(study.solution)

    assert all(
        item.voltage is not None
        for item in scene.bus_items.values()
    )


def test_editor_creation(qtbot):
    network = load_network("3-Bus Example")

    editor = DiagramEditor(network)
    qtbot.addWidget(editor)

    assert len(editor.scene.bus_items) == 3
    assert len(editor.scene.branch_items) == 3


def test_editor_network_copy(qtbot):
    network = load_network("3-Bus Example")

    editor = DiagramEditor(network)
    qtbot.addWidget(editor)

    editor.scene.add_bus(4)

    exported = editor.get_network()

    assert len(exported.buses) == 4
    assert len(network.buses) == 3


def test_edit_line_parameters(qtbot, monkeypatch):
    network = load_network("3-Bus Example")

    editor = DiagramEditor(network)
    qtbot.addWidget(editor)

    item = editor.scene.branch_items[0]

    monkeypatch.setattr(
        editor,
        "parameter_dialog",
        lambda title, fields: [
            0.04, 0.12, 150.0, 0.03
        ],
    )

    editor.edit_branch(item)

    line = editor.scene.network.lines[0]

    assert line.r == pytest.approx(0.04)
    assert line.x == pytest.approx(0.12)
    assert line.rating_mva == pytest.approx(150.0)
    assert line.b == pytest.approx(0.03)


def test_edit_bus_parameters(qtbot, monkeypatch):
    network = load_network("3-Bus Example")

    editor = DiagramEditor(network)
    qtbot.addWidget(editor)

    item = editor.scene.bus_items[3]

    monkeypatch.setattr(
        editor,
        "parameter_dialog",
        lambda title, fields: [
            132.0, 1.0, 0.90, 1.10
        ],
    )

    editor.edit_bus(item)

    bus = next(
        b for b in editor.scene.network.buses
        if b.number == 3
    )

    assert bus.vmin == pytest.approx(0.90)
    assert bus.vmax == pytest.approx(1.10)


def test_main_window_diagram_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert len(
        window.diagram_editor.scene.bus_items
    ) == 3

    titles = [
        window.tabs.tabText(i)
        for i in range(window.tabs.count())
    ]

    assert "Single-Line Diagram" in titles


def test_main_window_diagram_sync(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.diagram_editor.scene.add_bus(4)

    window.sync_diagram_to_network()

    assert len(window.network.buses) == 4
    assert window.load_table.rowCount() == 4
