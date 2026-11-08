
"""Module 11: Embedded load-flow result charts."""

import math

import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QFileDialog,
    QMessageBox,
)

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from loadflow.results_export import extract_results


class ResultsCharts(QWidget):
    CHARTS = (
        "Voltage Magnitude",
        "Voltage Angle",
        "Convergence",
        "Branch Loading",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.study = None

        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()

        self.chart_combo = QComboBox()
        self.chart_combo.addItems(self.CHARTS)

        self.save_button = QPushButton("Save Chart as PNG")

        toolbar.addWidget(self.chart_combo)
        toolbar.addWidget(self.save_button)
        root.addLayout(toolbar)

        self.figure = Figure(figsize=(9, 5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)

        root.addWidget(self.canvas)

        self.chart_combo.currentIndexChanged.connect(
            self.refresh
        )
        self.save_button.clicked.connect(
            self.save_png_dialog
        )

        self.refresh()

    def set_study(self, study):
        self.study = study
        self.refresh()

    def clear_study(self):
        self.study = None
        self.refresh()

    def refresh(self, *_):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        if self.study is None:
            ax.text(
                0.5, 0.5,
                "Run a load-flow study to display charts",
                ha="center", va="center",
                transform=ax.transAxes,
            )
            ax.set_axis_off()
            self.canvas.draw()
            return

        tables = extract_results(self.study)
        chart = self.chart_combo.currentText()

        if chart == "Voltage Magnitude":
            buses = tables["buses"]
            numbers = buses["Bus"].to_numpy()
            vm = buses["Vm (pu)"].to_numpy()
            vmin = buses["Vmin (pu)"].to_numpy()
            vmax = buses["Vmax (pu)"].to_numpy()

            ax.plot(
                numbers, vm,
                marker="o", markersize=3,
                label="Voltage magnitude",
            )
            ax.plot(
                numbers, vmin,
                linestyle="--",
                label="Lower voltage limit",
            )
            ax.plot(
                numbers, vmax,
                linestyle="--",
                label="Upper voltage limit",
            )

            violations = (vm < vmin) | (vm > vmax)
            if np.any(violations):
                ax.scatter(
                    numbers[violations],
                    vm[violations],
                    color="red",
                    s=35,
                    zorder=5,
                    label="Violation",
                )

            ax.set_xlabel("Bus Number")
            ax.set_ylabel("Voltage Magnitude (pu)")
            ax.set_title("Bus Voltage Profile")
            ax.legend()

        elif chart == "Voltage Angle":
            buses = tables["buses"]

            ax.plot(
                buses["Bus"],
                buses["Angle (deg)"],
                marker="o",
                markersize=3,
            )

            ax.set_xlabel("Bus Number")
            ax.set_ylabel("Voltage Angle (degrees)")
            ax.set_title("Bus Voltage Angle Profile")

        elif chart == "Convergence":
            history = tables["convergence"]

            values = np.maximum(
                np.abs(
                    history[
                        "Maximum Mismatch (pu)"
                    ].to_numpy(dtype=float)
                ),
                np.finfo(float).tiny,
            )

            ax.semilogy(
                history["Iteration"],
                values,
                marker="o",
            )

            ax.set_xlabel("Iteration")
            ax.set_ylabel("Maximum Mismatch (pu)")
            ax.set_title(
                "Newton-Raphson Convergence"
            )

        elif chart == "Branch Loading":
            branches = tables["branches"]

            numbers = branches["Branch"].to_numpy()
            loading = branches[
                "Loading (%)"
            ].to_numpy(dtype=float)

            finite = np.isfinite(loading)

            if np.any(finite):
                ax.bar(
                    numbers[finite],
                    loading[finite],
                )

            ax.axhline(
                100.0,
                linestyle="--",
                color="red",
                label="100% rating",
            )

            ax.set_xlabel("Branch Index")
            ax.set_ylabel("MVA Loading (%)")
            ax.set_title("Branch Loading Profile")
            ax.legend()

        ax.grid(True, alpha=0.25)
        self.figure.tight_layout()
        self.canvas.draw()

    def save_png(self, path):
        if self.study is None:
            raise ValueError(
                "No solved study available for export"
            )

        self.figure.savefig(
            str(path),
            dpi=180,
            bbox_inches="tight",
        )

    def save_png_dialog(self):
        if self.study is None:
            QMessageBox.warning(
                self,
                "No Results",
                "Run a load flow first.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Chart",
            "loadflow_chart.png",
            "PNG Images (*.png)",
        )

        if path:
            try:
                self.save_png(path)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(
                    self, "Export Error", str(exc)
                )
