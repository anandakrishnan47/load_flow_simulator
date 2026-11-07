
from loadflow.models import (
    Bus,
    Line,
    Generator,
    Load,
    ExternalGrid,
    Network,
)


def create_sample_network():
    network = Network(base_mva=100.0)

    network.add_bus(
        Bus(1, "Slack Bus", 132.0, "Slack")
    )

    network.add_bus(
        Bus(2, "Generator Bus", 132.0, "PV")
    )

    network.add_bus(
        Bus(3, "Load Bus", 132.0, "PQ")
    )

    network.add_line(
        Line(1, 2, r=0.02, x=0.06, b=0.03)
    )

    network.add_line(
        Line(1, 3, r=0.08, x=0.24, b=0.025)
    )

    network.add_line(
        Line(2, 3, r=0.06, x=0.18, b=0.02)
    )

    network.add_external_grid(
        ExternalGrid(bus=1)
    )

    network.add_generator(
        Generator(bus=2, pg=40.0, vg=1.02)
    )

    network.add_load(
        Load(bus=3, pd=60.0, qd=30.0)
    )

    return network


if __name__ == "__main__":
    network = create_sample_network()

    print("E4234 Load Flow Simulator")
    print("-------------------------")
    print("Number of buses:", len(network.buses))
    print("Number of lines:", len(network.lines))
    print("Number of generators:", len(network.generators))
    print("Number of loads:", len(network.loads))
