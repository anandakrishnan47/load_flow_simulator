
import pytest

from loadflow.models import (
    Network, Bus, Line, Transformer,
    Generator, Load, Shunt, ExternalGrid
)


def sample_network():
    net = Network()
    net.add_bus(Bus(1, "Bus 1", 132.0))
    net.add_bus(Bus(2, "Bus 2", 132.0))
    return net


def test_bus_creation():
    net = sample_network()
    assert len(net.buses) == 2


def test_duplicate_bus():
    net = sample_network()

    with pytest.raises(ValueError):
        net.add_bus(Bus(1, "Duplicate", 132.0))


def test_line_creation():
    net = sample_network()
    net.add_line(Line(1, 2, 0.02, 0.06))
    assert len(net.lines) == 1


def test_zero_impedance():
    net = sample_network()

    with pytest.raises(
        ValueError,
        match="Line impedance cannot be zero"
    ):
        net.add_line(Line(1, 2, 0.0, 0.0))


def test_transformer_creation():
    net = sample_network()
    net.add_transformer(
        Transformer(1, 2, 0.01, 0.05, 100.0)
    )
    assert len(net.transformers) == 1


def test_generator_creation():
    net = sample_network()
    net.add_generator(Generator(1, 40.0))
    assert len(net.generators) == 1


def test_load_creation():
    net = sample_network()
    net.add_load(Load(2, 60.0, 30.0))
    assert len(net.loads) == 1


def test_shunt_creation():
    net = sample_network()
    net.add_shunt(Shunt(2, 10.0, 20.0))
    assert len(net.shunts) == 1


def test_external_grid():
    net = sample_network()
    net.add_external_grid(ExternalGrid(1))
    assert len(net.external_grids) == 1
