
"""
Module 11: Load-flow results export.

Supports:
- CSV
- Excel (.xlsx)
- PDF

All numerical results come from an existing
converged APSA StudyResult.
"""

from pathlib import Path
import math

import pandas as pd

from openpyxl.styles import (
    Font, PatternFill, Alignment,
)
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, PageBreak,
)


def _finite(value):
    """Return a finite float, or None for missing data."""
    if value is None:
        return None

    result = float(value)
    return result if math.isfinite(result) else None


def extract_results(study):
    """
    Extract summary, bus, branch and convergence data.

    Does not modify the original study.
    """
    network = study.network
    solution = study.solution
    flows = study.flows

    if not solution.converged:
        raise ValueError(
            "Cannot export a nonconverged solution"
        )

    active_buses = [
        bus for bus in network.buses
        if bus.in_service
    ]

    final_types = (
        study.q_limits.bus_types
        if study.q_limits is not None
        else {
            bus.number: bus.bus_type
            for bus in active_buses
        }
    )

    bus_rows = []

    for bus in active_buses:
        i = solution.bus_index[bus.number]

        bus_rows.append({
            "Bus": bus.number,
            "Type": final_types[bus.number],
            "Vm (pu)": float(solution.vm[i]),
            "Angle (deg)": float(solution.va[i]),
            "P Injection (MW)": float(
                solution.p_calc[i] * network.base_mva
            ),
            "Q Injection (MVAr)": float(
                solution.q_calc[i] * network.base_mva
            ),
            "Vmin (pu)": float(bus.vmin),
            "Vmax (pu)": float(bus.vmax),
            "Voltage Violation": bool(
                solution.vm[i] < bus.vmin
                or solution.vm[i] > bus.vmax
            ),
        })

    branch_rows = []

    for number, branch in enumerate(flows.branches, 1):
        branch_rows.append({
            "Branch": number,
            "Type": branch.kind,
            "From Bus": branch.from_bus,
            "To Bus": branch.to_bus,
            "P From (MW)": float(branch.p_from),
            "Q From (MVAr)": float(branch.q_from),
            "P To (MW)": float(branch.p_to),
            "Q To (MVAr)": float(branch.q_to),
            "P Loss (MW)": float(branch.p_loss),
            "Loading (%)": _finite(
                branch.loading_percent
            ),
        })

    history_rows = [
        {
            "Iteration": index,
            "Maximum Mismatch (pu)": float(value),
        }
        for index, value in enumerate(
            solution.mismatch_history
        )
    ]

    summary_rows = [
        {"Metric": "Converged", "Value": str(solution.converged)},
        {"Metric": "Number of Buses", "Value": len(active_buses)},
        {"Metric": "Number of Branches", "Value": len(flows.branches)},
        {"Metric": "NR Iterations", "Value": solution.iterations},
        {"Metric": "Final Mismatch (pu)", "Value": float(solution.mismatch)},
        {"Metric": "Total Active Loss (MW)", "Value": float(flows.total_p_loss)},
        {"Metric": "Net Branch Reactive Absorption (MVAr)",
         "Value": float(flows.total_q_net)},
        {"Metric": "Maximum Branch Loading (%)",
         "Value": _finite(flows.max_loading_percent)},
        {"Metric": "P Balance Residual (MW)",
         "Value": float(flows.bus_p_balance_error)},
        {"Metric": "Q Balance Residual (MVAr)",
         "Value": float(flows.bus_q_balance_error)},
        {"Metric": "Q Limits Enforced",
         "Value": str(study.q_limits is not None)},
    ]

    return {
        "summary": pd.DataFrame(summary_rows),
        "buses": pd.DataFrame(bus_rows),
        "branches": pd.DataFrame(branch_rows),
        "convergence": pd.DataFrame(history_rows),
    }


def export_csv(study, directory):
    """
    Export four separate CSV files.

    Returns the list of created paths.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    tables = extract_results(study)
    paths = []

    for name, dataframe in tables.items():
        path = directory / f"{name}.csv"
        dataframe.to_csv(path, index=False)
        paths.append(path)

    return paths


def export_excel(study, path):
    """Export a formatted Excel workbook."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tables = extract_results(study)

    sheet_names = {
        "summary": "Summary",
        "buses": "Bus Results",
        "branches": "Branch Results",
        "convergence": "Convergence",
    }

    with pd.ExcelWriter(
        path,
        engine="openpyxl",
    ) as writer:

        for key, dataframe in tables.items():
            sheet_name = sheet_names[key]

            dataframe.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )

            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = (
                worksheet.dimensions
            )

            for cell in worksheet[1]:
                cell.font = Font(
                    bold=True,
                    color="FFFFFF",
                )
                cell.fill = PatternFill(
                    "solid",
                    fgColor="17365D",
                )
                cell.alignment = Alignment(
                    horizontal="center"
                )

            for column in worksheet.columns:
                values = [
                    str(cell.value)
                    if cell.value is not None
                    else ""
                    for cell in column
                ]

                width = min(
                    max(len(value) for value in values) + 2,
                    38,
                )

                letter = get_column_letter(
                    column[0].column
                )

                worksheet.column_dimensions[
                    letter
                ].width = max(width, 12)

    return path


def _pdf_value(value):
    """Format values for the PDF report."""
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _pdf_table(dataframe, columns, widths=None):
    """Build a compact ReportLab table."""
    rows = [columns]

    for record in dataframe.to_dict("records"):
        rows.append([
            _pdf_value(record[column])
            for column in columns
        ])

    table = Table(
        rows,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#F1F5F9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    return table


def export_pdf(study, path):
    """Generate a multipage engineering report."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tables = extract_results(study)
    styles = getSampleStyleSheet()

    document = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=30,
        bottomMargin=30,
    )

    story = [
        Paragraph(
            "APSA Load Flow Analysis Report",
            styles["Title"],
        ),
        Paragraph(
            "E4234 Advanced Power System Analysis",
            styles["Normal"],
        ),
        Spacer(1, 16),
        Paragraph("Study Summary", styles["Heading2"]),
    ]

    story.append(
        _pdf_table(
            tables["summary"],
            ["Metric", "Value"],
            [330, 180],
        )
    )

    story.extend([
        PageBreak(),
        Paragraph("Bus Results", styles["Heading2"]),
        Spacer(1, 8),
    ])

    bus_columns = [
        "Bus",
        "Type",
        "Vm (pu)",
        "Angle (deg)",
        "P Injection (MW)",
        "Q Injection (MVAr)",
    ]

    story.append(
        _pdf_table(
            tables["buses"],
            bus_columns,
            [50, 65, 90, 100, 125, 130],
        )
    )

    story.extend([
        PageBreak(),
        Paragraph("Branch Results", styles["Heading2"]),
        Spacer(1, 8),
    ])

    branch_columns = [
        "Branch",
        "Type",
        "From Bus",
        "To Bus",
        "P From (MW)",
        "P To (MW)",
        "P Loss (MW)",
        "Loading (%)",
    ]

    story.append(
        _pdf_table(
            tables["branches"],
            branch_columns,
            [50, 85, 65, 65, 95, 95, 95, 95],
        )
    )

    story.extend([
        PageBreak(),
        Paragraph(
            "Newton-Raphson Convergence",
            styles["Heading2"],
        ),
        Spacer(1, 8),
    ])

    story.append(
        _pdf_table(
            tables["convergence"],
            [
                "Iteration",
                "Maximum Mismatch (pu)",
            ],
            [120, 180],
        )
    )

    document.build(story)
    return path
