"""Stage 3.8 GUI regression tests. Requires pytest-qt and PySide6."""
import pytest
from gui.diagram_editor import DiagramEditor
from gui.diagram_items import EquipmentSymbol, BranchItem


def make_editor(qtbot):
    editor = DiagramEditor()
    qtbot.addWidget(editor)
    editor.scene.add_bus(1, bus_type='Slack')
    editor.scene.add_bus(2, bus_type='PQ')
    return editor


def test_change_bus_type_undo(qtbot):
    editor = make_editor(qtbot)
    editor.scene.change_bus_type(2, 'PV')
    assert editor.scene.network.buses[1].bus_type == 'PV'
    editor.scene.undo()
    assert editor.scene.network.buses[1].bus_type == 'PQ'


def test_reject_duplicate_slack(qtbot):
    editor = make_editor(qtbot)
    with pytest.raises(ValueError, match='Slack'):
        editor.scene.change_bus_type(2, 'Slack')


def test_generator_select_and_edit_undo(qtbot):
    editor = make_editor(qtbot)
    editor.scene.add_generator(2, pg=25.0)
    symbol = editor.scene.bus_items[2].equipment_symbols[0]
    assert isinstance(symbol, EquipmentSymbol)
    assert symbol.flags() & symbol.GraphicsItemFlag.ItemIsSelectable
    symbol.setSelected(True)
    assert editor.selected_component() is symbol
    editor.scene.edit_component(symbol.component, {'pg': 75.0, 'vg': 1.02})
    assert editor.scene.network.generators[0].pg == 75.0
    editor.scene.undo()
    assert editor.scene.network.generators[0].pg == 25.0


def test_transformer_add_and_edit(qtbot):
    editor = make_editor(qtbot)
    editor.scene.add_transformer(1, 2)
    branch = editor.scene.branch_items[0]
    assert isinstance(branch, BranchItem)
    assert branch.kind == 'Transformer'
    editor.scene.edit_component(branch.branch, {'tap_ratio': 1.05, 'phase_shift': 5.0})
    assert editor.scene.network.transformers[0].tap_ratio == 1.05
    editor.scene.undo()
    assert editor.scene.network.transformers[0].tap_ratio == 1.0


def test_remove_generator_undo(qtbot):
    editor = make_editor(qtbot)
    generator = editor.scene.add_generator(2)
    editor.scene.remove_equipment(editor.scene.network.generators[0])
    assert len(editor.scene.network.generators) == 0
    editor.scene.undo()
    assert len(editor.scene.network.generators) == 1
