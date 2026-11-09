from gui.controller import update_loads, validate_network, load_network


def test_validate_sample():
    assert validate_network(load_network("3-Bus Example"))


def test_unchanged_loads_preserved():
    network = load_network("3-Bus Example")
    values = {b.number: (
        sum(l.pd for l in network.loads if l.in_service and l.bus == b.number),
        sum(l.qd for l in network.loads if l.in_service and l.bus == b.number),
    ) for b in network.buses if b.in_service}
    edited = update_loads(network, values)
    assert edited.loads == network.loads


def test_invalid_bus_rejected():
    import pytest
    with pytest.raises(ValueError):
        update_loads(load_network("3-Bus Example"), {99999: (10, 5)})
