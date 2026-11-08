
"""
Module 11 demonstration.

Run a load-flow study and export:
- CSV tables
- Excel workbook
- PDF report
- Four PNG charts
"""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from gui.controller import (
    load_network,
    run_study,
)
from gui.results_charts import ResultsCharts

from loadflow.results_export import (
    export_csv,
    export_excel,
    export_pdf,
)


def main():
    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    network = load_network("IEEE 14-Bus")

    study = run_study(
        network,
        tolerance=1e-8,
        max_iterations=50,
    )

    output = Path("results/module11")
    output.mkdir(parents=True, exist_ok=True)

    csv_paths = export_csv(
        study,
        output / "csv",
    )

    excel_path = export_excel(
        study,
        output / "loadflow_results.xlsx",
    )

    pdf_path = export_pdf(
        study,
        output / "loadflow_report.pdf",
    )

    charts = ResultsCharts()
    charts.set_study(study)

    chart_files = {
        "Voltage Magnitude": "voltage_profile.png",
        "Voltage Angle": "voltage_angles.png",
        "Convergence": "convergence.png",
        "Branch Loading": "branch_loading.png",
    }

    for chart_name, filename in chart_files.items():
        charts.chart_combo.setCurrentText(
            chart_name
        )

        charts.save_png(
            output / filename
        )

    print("=" * 65)
    print("APSA MODULE 11: RESULTS VISUALIZATION AND EXPORT")
    print("=" * 65)

    print("Network: IEEE 14-Bus")
    print("Converged:", study.solution.converged)
    print("Iterations:", study.solution.iterations)

    print(
        "Final mismatch:",
        f"{study.solution.mismatch:.10e} pu"
    )

    print(
        "Total active loss:",
        f"{study.flows.total_p_loss:.6f} MW"
    )

    print("\nCSV files:")
    for path in csv_paths:
        print(" ", path)

    print("\nExcel:", excel_path)
    print("PDF:", pdf_path)

    print("\nCharts:")
    for filename in chart_files.values():
        print(" ", output / filename)

    print("\nModule 11 demonstration completed.")


if __name__ == "__main__":
    main()
