
"""
Module 12: End-to-end APSA integration tests.

Tests the existing numerical and reporting modules
without changing their implementations.
"""

import math

import numpy as np
import pytest

from gui.controller import (
    load_network,
    run_study,
    update_loads,
)

from loadflow.ybus import build_ybus
from loadflow.power import calculate_power
from loadflow.results_export import (
    extract_results,
    export_csv,
    export_excel,
    export_pdf,
)


NETWORKS = [
    ("3-Bus Example", 3),
    ("IEEE 14-Bus", 14),
    ("IEEE 30-Bus", 30),
    ("IEEE 57-Bus", 57),
    ("IEEE 118-Bus", 118),
]


@pytest.fixture(scope="module", params=NETWORKS)
def solved_case(request):
    name, expected_buses = request.param

    network = load_network(name)

    study = run_study(
        network,
        tolerance=1e-8,
        max_iterations=50,
    )

    return name, expected_buses, study


def test_network_converges(solved_case):
    _, _, study = solved_case

    assert study.solution.converged
    assert study.solution.mismatch <= 1e-8


def test_correct_bus_count(solved_case):
    _, expected_buses, study = solved_case

    assert len(study.solution.bus_index) == expected_buses


def test_voltage_results_finite(solved_case):
    _, _, study = solved_case

    vm = np.asarray(study.solution.vm, dtype=float)
    va = np.asarray(study.solution.va, dtype=float)

    assert np.isfinite(vm).all()
    assert np.isfinite(va).all()
    assert (vm > 0).all()


def test_ybus_and_calculated_power_consistency(solved_case):
    _, _, study = solved_case

    ybus, bus_index = build_ybus(study.network)

    vm = np.asarray(study.solution.vm, dtype=float)

    # Module 5 returns voltage angles in degrees.
    va = np.deg2rad(
        np.asarray(study.solution.va, dtype=float)
    )

    p, q = calculate_power(ybus, vm, va)

    for bus_number, i in study.solution.bus_index.items():
        j = bus_index[bus_number]

        assert p[j] == pytest.approx(
            study.solution.p_calc[i],
            abs=1e-7,
        )

        assert q[j] == pytest.approx(
            study.solution.q_calc[i],
            abs=1e-7,
        )


def test_branch_active_loss_consistency(solved_case):
    _, _, study = solved_case

    individual_loss = sum(
        branch.p_loss
        for branch in study.flows.branches
    )

    assert individual_loss == pytest.approx(
        study.flows.total_p_loss,
        abs=1e-6,
    )


def test_bus_active_power_balance(solved_case):
    _, _, study = solved_case

    # Branch terminal powers use the convention:
    # positive = power entering the branch.
    branch_loss = sum(
        branch.p_from + branch.p_to
        for branch in study.flows.branches
    )

    bus_injection = sum(
        study.solution.p_calc
    ) * study.network.base_mva

    # Shunt conductance, when present, consumes
    # active power separately from series branches.
    shunt_loss = 0.0

    for shunt in study.network.shunts:
        if not shunt.in_service:
            continue

        i = study.solution.bus_index[shunt.bus]
        vm = float(study.solution.vm[i])

        shunt_loss += shunt.gs * vm * vm

    assert bus_injection == pytest.approx(
        branch_loss + shunt_loss,
        abs=1e-4,
    )


def test_result_tables_match_solution(solved_case):
    _, expected_buses, study = solved_case

    tables = extract_results(study)

    assert len(tables["buses"]) == expected_buses

    assert len(tables["branches"]) == len(
        study.flows.branches
    )

    assert len(tables["convergence"]) == len(
        study.solution.mismatch_history
    )


def test_exported_voltage_matches_solution(tmp_path):
    network = load_network("IEEE 14-Bus")
    study = run_study(network)

    paths = export_csv(study, tmp_path)

    assert len(paths) == 4

    import pandas as pd

    buses = pd.read_csv(tmp_path / "buses.csv")

    for _, row in buses.iterrows():
        number = int(row["Bus"])
        i = study.solution.bus_index[number]

        assert row["Vm (pu)"] == pytest.approx(
            study.solution.vm[i],
            abs=1e-8,
        )


def test_all_export_formats(tmp_path):
    network = load_network("3-Bus Example")
    study = run_study(network)

    csv_paths = export_csv(
        study,
        tmp_path / "csv",
    )

    xlsx = export_excel(
        study,
        tmp_path / "results.xlsx",
    )

    pdf = export_pdf(
        study,
        tmp_path / "report.pdf",
    )

    assert len(csv_paths) == 4
    assert all(path.is_file() for path in csv_paths)

    assert xlsx.is_file()
    assert pdf.is_file()

    assert xlsx.stat().st_size > 0
    assert pdf.stat().st_size > 1000


def test_load_edit_changes_solution():
    original = load_network("3-Bus Example")

    original_study = run_study(original)

    edited = update_loads(
        original,
        {3: (80.0, 40.0)},
    )

    edited_study = run_study(edited)

    i = original_study.solution.bus_index[3]
    j = edited_study.solution.bus_index[3]

    assert edited_study.solution.converged

    assert not math.isclose(
        original_study.solution.vm[i],
        edited_study.solution.vm[j],
        abs_tol=1e-6,
    )

    # Editing must not mutate the source network.
    original_pd = sum(
        load.pd for load in original.loads
        if load.bus == 3 and load.in_service
    )

    assert original_pd == pytest.approx(60.0)
