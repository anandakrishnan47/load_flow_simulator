
"""Download the four MATPOWER IEEE benchmark cases."""

from pathlib import Path
from urllib.request import urlopen

CASES = ("case14", "case30", "case57", "case118")

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "MATPOWER/matpower/master/data"
)

DESTINATION = Path("data/ieee")


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)

    for name in CASES:
        url = f"{BASE_URL}/{name}.m"
        destination = DESTINATION / f"{name}.m"

        print(f"Downloading {name}...")

        with urlopen(url, timeout=30) as response:
            content = response.read()

        if (
            b"mpc.baseMVA" not in content
            or b"mpc.bus" not in content
            or b"mpc.branch" not in content
            or b"mpc.gen" not in content
        ):
            raise ValueError(
                f"Invalid MATPOWER data: {name}"
            )

        destination.write_bytes(content)
        print(f"Saved: {destination}")

    print("\nAll four benchmark cases downloaded.")


if __name__ == "__main__":
    main()
