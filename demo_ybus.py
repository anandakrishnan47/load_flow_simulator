
from main import create_sample_network
from loadflow.ybus import build_ybus



def main():
    net = create_sample_network()

    ybus, bus_index = build_ybus(net)

    print("Ybus Matrix (pu)")
    print("----------------")

    for number, index in bus_index.items():
        print(f"Bus {number}: index {index}")

    print("\n", ybus.toarray())


if __name__ == "__main__":
    main()
