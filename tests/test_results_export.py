
"""Module 11: Automated results export tests."""

import pandas as pd
import pytest

from openpyxl import load_workbook
from pypdf import PdfReader

from gui.controller import (
    load_network,
    run_study,
)

from loadflow.results_export import (
    extract_results,
    export_csv,
    export_excel,
    export_pdf,
)


@pytest.fixture(scope="module")
def study():
    network = load_network("3-Bus Example")
    return run_study(network)


def test_extract_result_tables(study):
    tables = extract_results(study)

    assert set(tables) == {
        "summary",
        "buses",
        "branches",
        "convergence",
    }


def test_bus_result_count(study):
    tables = extract_results(study)

    assert len(tables["buses"]) == 3


def test_branch_result_count(study):
    tables = extract_results(study)

    assert len(tables["branches"]) == 3


def test_voltage_values_are_valid(study):
    tables = extract_results(study)

    voltages = tables["buses"]["Vm (pu)"]

    assert (voltages > 0).all()
    assert voltages.notna().all()


def test_export_csv(study, tmp_path):
    paths = export_csv(study, tmp_path)

    assert len(paths) == 4

    for path in paths:
        assert path.exists()
        assert path.stat().st_size > 0


def test_csv_bus_data(study, tmp_path):
    export_csv(study, tmp_path)

    buses = pd.read_csv(
        tmp_path / "buses.csv"
    )

    assert len(buses) == 3
    assert "Vm (pu)" in buses.columns


def test_export_excel(study, tmp_path):
    path = tmp_path / "results.xlsx"

    export_excel(study, path)

    assert path.exists()

    workbook = load_workbook(path)

    assert workbook.sheetnames == [
        "Summary",
        "Bus Results",
        "Branch Results",
        "Convergence",
    ]


def test_excel_bus_count(study, tmp_path):
    path = tmp_path / "results.xlsx"

    export_excel(study, path)

    workbook = load_workbook(path)
    sheet = workbook["Bus Results"]

    assert sheet.max_row == 4


def test_export_pdf(study, tmp_path):
    path = tmp_path / "report.pdf"

    export_pdf(study, path)

    assert path.exists()
    assert path.stat().st_size > 1000


def test_pdf_content(study, tmp_path):
    path = tmp_path / "report.pdf"

    export_pdf(study, path)

    reader = PdfReader(str(path))

    text = "\n".join(
        page.extract_text() or ""
        for page in reader.pages
    )

    assert "APSA Load Flow Analysis Report" in text
    assert "Bus Results" in text
    assert "Branch Results" in text


def test_convergence_data(study):
    tables = extract_results(study)

    history = tables["convergence"]

    assert len(history) >= 1
    assert (
        history["Maximum Mismatch (pu)"] >= 0
    ).all()


def test_export_ieee14(tmp_path):
    network = load_network("IEEE 14-Bus")
    study = run_study(network)

    path = tmp_path / "ieee14.xlsx"
    export_excel(study, path)

    workbook = load_workbook(path)

    assert (
        workbook["Bus Results"].max_row == 15
    )
