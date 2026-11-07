
from main import create_sample_network
from loadflow.ybus import build_ybus, print_ybus


def main():
    network = create_sample_network()

    ybus, bus_index = build_ybus(network)

    print("E4234 Load Flow Simulator")
    print("Module 2: Ybus Matrix Formation")

    print_ybus(ybus, bus_index)

    print("\nMatrix shape:", ybus.shape)
    print("Nonzero elements:", ybus.nnz)


if __name__ == "__main__":
    main()
