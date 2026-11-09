
import pytest

from PySide6.QtWidgets import QApplication

from loadflow.models import Network, Bus, Load
from gui.diagram_scene import DiagramScene


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()

    if app is None:
        app = QApplication([])

    return app


@pytest.fixture
def scene(qapp):
    network = Network(base_mva=100.0)

    network.add_bus(
        Bus(
            number=1,
            name="Slack",
            base_kv=230.0,
            bus_type="Slack",
        )
    )

    network.add_bus(
        Bus(
            number=2,
            name="Load Bus",
            base_kv=230.0,
            bus_type="PQ",
        )
    )

    network.add_load(
        Load(
            bus=2,
            pd=50.0,
            qd=20.0,
        )
    )

    return DiagramScene(network)


def test_equipment_symbol(scene):
    bus = scene.bus_items[2]

    assert len(bus.equipment_symbols) == 1
    assert bus.equipment_symbols[0].kind == "Load"


def test_project_roundtrip(scene, tmp_path):
    scene.add_line(1, 2)

    scene.bus_items[2].setPos(400, 250)

    path = tmp_path / "project.json"

    scene.save_project(path)

    restored = DiagramScene()
    restored.load_project(path)

    assert restored.bus_count() == 2
    assert restored.branch_count() == 1

    assert restored.positions()[2] == (
        400.0,
        250.0,
    )

    assert len(restored.network.loads) == 1
    assert restored.network.loads[0].pd == 50.0


def test_project_load_resets_history(scene, tmp_path):
    scene.add_bus(3)

    assert scene.can_undo()

    path = tmp_path / "project.json"
    scene.save_project(path)

    scene.load_project(path)

    assert not scene.can_undo()
    assert not scene.can_redo()


def test_invalid_project_preserves_network(scene, tmp_path):
    path = tmp_path / "invalid.json"

    path.write_text(
        '{"format":"INVALID","version":2}',
        encoding="utf-8",
    )

    original_numbers = [
        bus.number for bus in scene.network.buses
    ]

    with pytest.raises(ValueError):
        scene.load_project(path)

    assert [
        bus.number for bus in scene.network.buses
    ] == original_numbers


def test_undo_after_branch_addition(scene):
    scene.add_line(1, 2)

    assert scene.branch_count() == 1

    scene.undo()

    assert scene.branch_count() == 0

    scene.redo()

    assert scene.branch_count() == 1
