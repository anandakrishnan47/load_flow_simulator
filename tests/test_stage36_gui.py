"""Stage 3.6 regression tests. Requires pytest-qt and PySide6."""
import pytest
from PySide6.QtCore import QPointF
from loadflow.models import Network, Bus
from gui.diagram_editor import DiagramEditor, DiagramView, ComponentPalette

@pytest.fixture
def editor(qtbot):
    network = Network()
    network.add_bus(Bus(number=1, name='Slack', base_kv=132, bus_type='Slack'))
    network.add_bus(Bus(number=2, name='PQ', base_kv=132, bus_type='PQ'))
    widget = DiagramEditor(network)
    qtbot.addWidget(widget)
    return widget

def test_palette_and_canvas(editor):
    assert isinstance(editor.palette, ComponentPalette)
    assert isinstance(editor.view, DiagramView)
    assert editor.palette.count() == 5

def test_placement_undo_redo(editor):
    editor.scene.add_bus(3, x=321, y=222)
    assert editor.scene.positions()[3] == (321, 222)
    editor.undo()
    assert 3 not in editor.scene.bus_items
    editor.redo()
    assert 3 in editor.scene.bus_items

def test_equipment_undo_redo(editor):
    editor.scene.add_load(2, 12.0, 5.0)
    assert any(l.bus == 2 and l.pd == 12 for l in editor.scene.network.loads)
    editor.undo()
    assert not editor.scene.network.loads
    editor.redo()
    assert len(editor.scene.network.loads) == 1

def test_interactive_line_connection(editor):
    editor.start_connection('Line')
    editor.handle_connection_click(1)
    editor.handle_connection_click(2)
    assert len(editor.scene.network.lines) == 1
    assert editor.view.connection_mode is None
    editor.undo()
    assert not editor.scene.network.lines

def test_project_roundtrip(editor, tmp_path):
    editor.scene.add_generator(1, pg=20)
    editor.scene.add_load(2, pd=10, qd=4)
    path = tmp_path / 'project.json'
    editor.scene.save_project(path)
    editor.scene.load_project(path)
    assert len(editor.scene.network.generators) == 1
    assert len(editor.scene.network.loads) == 1
