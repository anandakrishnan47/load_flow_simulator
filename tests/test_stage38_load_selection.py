"""Regression tests for selecting load and generator graphics."""
from types import SimpleNamespace
from PySide6.QtCore import Qt
from gui.diagram_items import BusItem, EquipmentSymbol


def test_load_symbol_is_selectable(qtbot):
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
    scene = QGraphicsScene()
    bus = BusItem(SimpleNamespace(number=1, bus_type="PQ", base_kv=132.0))
    scene.addItem(bus)
    load = SimpleNamespace(bus=1, pd=20.0, qd=10.0, in_service=True)
    bus.set_equipment(loads=[load])
    symbol = bus.equipment_symbols[0]
    assert isinstance(symbol, EquipmentSymbol)
    assert symbol.flags() & symbol.GraphicsItemFlag.ItemIsSelectable
    assert symbol.acceptedMouseButtons() & Qt.MouseButton.LeftButton
    symbol.setSelected(True)
    assert symbol in scene.selectedItems()
    assert symbol.component is load


def test_generator_symbol_is_selectable(qtbot):
    from PySide6.QtWidgets import QGraphicsScene
    scene = QGraphicsScene()
    bus = BusItem(SimpleNamespace(number=2, bus_type="PV", base_kv=132.0))
    scene.addItem(bus)
    gen = SimpleNamespace(bus=2, in_service=True)
    bus.set_equipment(generators=[gen])
    symbol = bus.equipment_symbols[0]
    symbol.setSelected(True)
    assert symbol in scene.selectedItems()
    assert symbol.kind == "Generator"
