
"""
Module 6 demonstration:
Generator reactive limits and PV-PQ switching.
"""

from loadflow.models import (
    Network, Bus, Line, Generator,
    Load, ExternalGrid
)

from loadflow.qlimits import solve_with_q_limits


def create_network(qd, qmin, qmax):
    net = Network(base_mva=100.0)

    net.add_bus(
        Bus(1, "Slack", 132.0, "Slack")
    )

    net.add_bus(
        Bus(2, "Generator", 132.0, "PV")
    )

    net.add_line(
        Line(1, 2, 0.0, 0.1)
    )

    net.add_external_grid(
        ExternalGrid(
            bus=1, vm=1.0, va=0.0
        )
    )

    net.add_generator(
        Generator(
            bus=2,
            pg=0.0,
            vg=1.0,
            qmin=qmin,
            qmax=qmax,
        )
    )

    net.add_load(
        Load(
            bus=2,
            pd=0.0,
            qd=qd,
        )
    )

    return net


def run_case(title, qd, qmin, qmax):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    network = create_network(
        qd, qmin, qmax
    )

    result = solve_with_q_limits(
        network,
        tolerance=1e-10,
        max_iterations=30,
        q_tolerance=1e-5,
        max_outer_iterations=10,
        verbose=False,
    )

    print("Converged:", result.converged)
    print("Message:", result.message)
    print(
        "Outer iterations:",
        result.outer_iterations
    )

    print(
        "Switched buses:",
        result.switched_buses
    )

    print("\nFinal bus results:")
    print(
        f"{'Bus':<8}"
        f"{'Type':<10}"
        f"{'Vm (pu)':<14}"
        f"{'Angle (deg)':<16}"
    )

    for bus in network.buses:
        if not bus.in_service:
            continue

        i = result.load_flow.bus_index[
            bus.number
        ]

        print(
            f"{bus.number:<8}"
            f"{result.bus_types[bus.number]:<10}"
            f"{result.load_flow.vm[i]:<14.6f}"
            f"{result.load_flow.va[i]:<16.6f}"
        )

    print("\nGenerator reactive output:")

    for bus_number, qg in (
        result.generator_q.items()
    ):
        print(
            f"Bus {bus_number}: "
            f"Qgen = {qg:.6f} MVAr"
        )

    print(
        "\nFinal mismatch:",
        f"{result.load_flow.mismatch:.10e} pu"
    )


def main():
    print("E4234 APSA LOAD FLOW SIMULATOR")
    print("MODULE 6: GENERATOR Q LIMITS")

    run_case(
        title="CASE 1: NO REACTIVE LIMIT VIOLATION",
        qd=30.0,
        qmin=-50.0,
        qmax=50.0,
    )

    run_case(
        title="CASE 2: UPPER Q LIMIT VIOLATION",
        qd=30.0,
        qmin=-50.0,
        qmax=10.0,
    )

    run_case(
        title="CASE 3: LOWER Q LIMIT VIOLATION",
        qd=-30.0,
        qmin=-10.0,
        qmax=50.0,
    )


if __name__ == "__main__":
    main()
