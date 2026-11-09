"""Stage 3 smoke tests. Requires pytest-qt and PySide6."""
from loadflow.models import Network, Bus, Load
from gui.diagram_editor import DiagramEditor
from gui.diagram_scene import DiagramScene


def sample_network():
    network = Network(base_mva=100.0)
    network.add_bus(Bus(number=1, name='Slack', base_kv=230, bus_type='Slack'))
    network.add_bus(Bus(number=2, name='PQ', base_kv=230, bus_type='PQ'))
    network.add_load(Load(bus=2, pd=20, qd=10))
    return network


def test_editor_accepts_network(qtbot):
    editor = DiagramEditor(sample_network())
    qtbot.addWidget(editor)
    assert editor.scene.bus_count() == 2


def test_undo_redo(qtbot):
    scene = DiagramScene(sample_network())
    scene.add_bus(3)
    assert scene.bus_count() == 3
    scene.undo()
    assert scene.bus_count() == 2
    scene.redo()
    assert scene.bus_count() == 3


def test_project_roundtrip(qtbot, tmp_path):
    scene = DiagramScene(sample_network())
    scene.add_line(1, 2)
    path = tmp_path / 'project.json'
    scene.save_project(path)
    other = DiagramScene()
    other.load_project(path)
    assert other.bus_count() == 2
    assert other.branch_count() == 1
    assert len(other.bus_items[2].equipment_symbols) == 1
