
"""E4234 Load Flow Simulator entry point."""

from loadflow.models import (
    Network, Bus, Line, Generator,
    Load, ExternalGrid
)


def create_sample_network():
    net = Network(base_mva=100.0)

    net.add_bus(
        Bus(1, "Slack Bus", 132.0, "Slack")
    )
    net.add_bus(
        Bus(2, "Generator Bus", 132.0, "PV")
    )
    net.add_bus(
        Bus(3, "Load Bus", 132.0, "PQ")
    )

    net.add_line(
        Line(1, 2, 0.02, 0.06, 0.03)
    )
    net.add_line(
        Line(1, 3, 0.08, 0.24, 0.025)
    )
    net.add_line(
        Line(2, 3, 0.06, 0.18, 0.02)
    )

    net.add_external_grid(
        ExternalGrid(bus=1)
    )

    net.add_generator(
        Generator(bus=2, pg=40.0, vg=1.02)
    )

    net.add_load(
        Load(bus=3, pd=60.0, qd=30.0)
    )

    return net


if __name__ == "__main__":
    net = create_sample_network()

    print("E4234 Load Flow Simulator")
    print("Buses:", len(net.buses))
    print("Lines:", len(net.lines))
    print("Generators:", len(net.generators))
    print("Loads:", len(net.loads))
