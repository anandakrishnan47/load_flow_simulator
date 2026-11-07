
import pytest

from loadflow.models import (
    Bus,
    Line,
    Generator,
    Load,
    Network,
)


def test_add_bus():
    net = Network()
    net.add_bus(Bus(1, "Bus 1", 132.0))

    assert len(net.buses) == 1


def test_duplicate_bus():
    net = Network()
    net.add_bus(Bus(1, "Bus 1", 132.0))

    with pytest.raises(ValueError):
        net.add_bus(Bus(1, "Duplicate", 132.0))


def test_add_line():
    net = Network()
    net.add_bus(Bus(1, "Bus 1", 132.0))
    net.add_bus(Bus(2, "Bus 2", 132.0))

    net.add_line(Line(1, 2, 0.02, 0.06))

    assert len(net.lines) == 1


def test_invalid_line():
    net = Network()
    net.add_bus(Bus(1, "Bus 1", 132.0))

    with pytest.raises(ValueError):
        net.add_line(Line(1, 3, 0.02, 0.06))


def test_add_generator():
    net = Network()
    net.add_bus(Bus(1, "Bus 1", 132.0))

    net.add_generator(Generator(1, 100.0))

    assert len(net.generators) == 1


def test_add_load():
    net = Network()
    net.add_bus(Bus(2, "Bus 2", 132.0))

    net.add_load(Load(2, 50.0, 30.0))

    assert net.loads[0].pd == 50.0


def test_invalid_zero_impedance():
    net = make_two_bus_network()

    with pytest.raises(ValueError):
        net.add_line(Line(1, 2, 0.0, 0.0))

