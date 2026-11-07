
"""Module 8: IEEE benchmark validation tests."""

from pathlib import Path

import numpy as np
import pytest

from loadflow.ieee_validation import (
    read_matpower_case,
    convert_to_network,
    validate_case,
    passes_validation,
)


DATA_DIR = Path("data/ieee")

CASES = [
    ("case14", 14),
    ("case30", 30),
    ("case57", 57),
    ("case118", 118),
]


@pytest.mark.parametrize(
    "name,expected_buses", CASES
)
def test_dataset_dimensions(name, expected_buses):
    case = read_matpower_case(
        DATA_DIR / f"{name}.m"
    )

    assert case["bus"].shape[0] == expected_buses
    assert case["baseMVA"] > 0
    assert case["gen"].shape[0] > 0
    assert case["branch"].shape[0] > 0


@pytest.mark.parametrize(
    "name,expected_buses", CASES
)
def test_network_conversion(name, expected_buses):
    case = read_matpower_case(
        DATA_DIR / f"{name}.m"
    )

    net = convert_to_network(case)

    assert len(net.buses) == expected_buses

    assert sum(
        bus.bus_type == "Slack"
        for bus in net.buses
    ) == 1

    assert (
        len(net.lines) + len(net.transformers)
    ) > 0


@pytest.mark.parametrize(
    "name,expected_buses", CASES
)
def test_reference_voltage_agreement(
    name, expected_buses
):
    result = validate_case(
        DATA_DIR / f"{name}.m"
    )

    assert result.buses == expected_buses
    assert result.apsa_converged
    assert result.reference_converged

    assert result.max_vm_error < 1e-5
    assert result.max_angle_error < 1e-3


@pytest.mark.parametrize(
    "name,expected_buses", CASES
)
def test_reference_loss_agreement(
    name, expected_buses
):
    result = validate_case(
        DATA_DIR / f"{name}.m"
    )

    assert result.p_loss_error < 1e-3
    assert result.final_mismatch < 1e-8


@pytest.mark.parametrize(
    "name,expected_buses", CASES
)
def test_complete_validation(
    name, expected_buses
):
    result = validate_case(
        DATA_DIR / f"{name}.m"
    )

    assert passes_validation(result)


def test_missing_dataset():
    with pytest.raises(FileNotFoundError):
        read_matpower_case(
            DATA_DIR / "nonexistent.m"
        )


def test_invalid_matpower_file(tmp_path):
    path = tmp_path / "invalid.m"
    path.write_text(
        "This is not a MATPOWER case."
    )

    with pytest.raises(ValueError):
        read_matpower_case(path)

def test_transformer_charging_ybus():
    """
    Verify that APSA Ybus matches PYPOWER Ybus
    for the IEEE 14-bus benchmark, including
    transformer charging.
    """

    from pypower.ext2int import ext2int
    from pypower.makeYbus import makeYbus

    from loadflow.ybus import build_ybus

    case = read_matpower_case(
        DATA_DIR / "case14.m"
    )

    network = convert_to_network(case)

    apsa_ybus, apsa_index = build_ybus(
        network
    )

    internal = ext2int(case)

    reference_ybus, _, _ = makeYbus(
        internal["baseMVA"],
        internal["bus"],
        internal["branch"],
    )

    # PYPOWER internally renumbers buses.
    # Convert its internal order to APSA indices.
    original_bus_numbers = [
        int(number)
        for number in internal["order"]["bus"]["i2e"]
    ]

    indices = [
        apsa_index[number]
        for number in original_bus_numbers
    ]

    reordered_apsa_ybus = apsa_ybus[
        indices, :
    ][:, indices]

    np.testing.assert_allclose(
        reordered_apsa_ybus.toarray(),
        reference_ybus.toarray(),
        rtol=1e-10,
        atol=1e-10,
    )
