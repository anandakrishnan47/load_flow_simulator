
import pytest

from loadflow.models import Network, Bus
from gui.diagram_scene import DiagramScene


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
            name="Load",
            base_kv=230.0,
            bus_type="PQ",
        )
    )

    return DiagramScene(network)


def test_initial_network(scene):
    assert scene.bus_count() == 2
    assert scene.branch_count() == 0


def test_add_bus_undo_redo(scene):
    scene.add_bus(
        number=3,
        x=200,
        y=300,
    )

    assert scene.bus_count() == 3
    assert scene.can_undo()

    scene.undo()

    assert scene.bus_count() == 2

    scene.redo()

    assert scene.bus_count() == 3
    assert scene.positions()[3] == (200.0, 300.0)


def test_add_line_undo_redo(scene):
    scene.add_line(
        1,
        2,
        r=0.02,
        x=0.06,
    )

    assert scene.branch_count() == 1

    scene.undo()

    assert scene.branch_count() == 0

    scene.redo()

    assert scene.branch_count() == 1


def test_remove_bus_undo(scene):
    scene.add_line(1, 2)

    scene.remove_bus(2)

    assert scene.bus_count() == 1
    assert scene.branch_count() == 0

    scene.undo()

    assert scene.bus_count() == 2
    assert scene.branch_count() == 1


def test_remove_parallel_branch(scene):
    scene.add_line(1, 2)
    scene.add_line(1, 2)

    assert scene.branch_count() == 2

    branch = scene.branch_items[0].branch

    scene.remove_branch(branch)

    assert scene.branch_count() == 1

    scene.undo()

    assert scene.branch_count() == 2


def test_save_load_layout(scene, tmp_path):
    path = tmp_path / "layout.json"

    scene.bus_items[2].setPos(250, 350)

    scene.save_layout(path)

    scene.bus_items[2].setPos(100, 100)

    scene.load_layout(path)

    assert scene.positions()[2] == (
        250.0,
        350.0,
    )

    scene.undo()

    assert scene.positions()[2] == (
        100.0,
        100.0,
    )


def test_set_network_clears_history(scene):
    scene.add_bus(3)

    assert scene.can_undo()

    replacement = Network(base_mva=100.0)

    replacement.add_bus(
        Bus(
            number=10,
            name="New Slack",
            base_kv=132.0,
            bus_type="Slack",
        )
    )

    scene.set_network(replacement)

    assert scene.bus_count() == 1
    assert not scene.can_undo()
