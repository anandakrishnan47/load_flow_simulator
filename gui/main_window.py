
"""
E4234 Advanced Power System Analysis
APSA Load Flow Simulator

Module 9  - PySide6 GUI
Module 10 - Interactive Single-Line Diagram
Module 11 - Results Visualization and Export
"""

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QPlainTextEdit,
    QMessageBox,
    QHeaderView,
    QSplitter,
)

from gui.controller import (
    NETWORKS,
    load_network,
    update_loads,
)

from gui.worker import LoadFlowWorker
from gui.diagram_editor import DiagramEditor

# Module 11
from gui.results_charts import ResultsCharts
from gui.export_dialog import ExportPanel


def table_item(value, editable=False):
    """Create a table item with optional editing."""
    item = QTableWidgetItem(str(value))

    if not editable:
        item.setFlags(
            item.flags()
            & ~Qt.ItemFlag.ItemIsEditable
        )

    return item


def configure_table(table, headings):
    """Configure a Qt result/input table."""
    table.setColumnCount(len(headings))
    table.setHorizontalHeaderLabels(headings)

    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch
    )

    table.setAlternatingRowColors(True)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "APSA | Newton-Raphson Load Flow Simulator"
        )
        self.resize(1450, 900)

        self.network = None
        self.study = None
        self.worker = None

        self.build_ui()
        self.load_selected_network()

    # ==================================================
    # BUILD USER INTERFACE
    # ==================================================

    def build_ui(self):

        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)

        # ----------------------------------------------
        # APPLICATION HEADING
        # ----------------------------------------------

        heading = QLabel(
            "APSA Load Flow Simulator"
        )
        heading.setObjectName("mainHeading")
        root.addWidget(heading)

        subtitle = QLabel(
            "E4234 Advanced Power System Analysis | "
            "Newton-Raphson AC Power Flow"
        )
        root.addWidget(subtitle)

        # ----------------------------------------------
        # STUDY CONFIGURATION
        # ----------------------------------------------

        controls = QGroupBox("Study Configuration")
        controls_layout = QGridLayout(controls)

        self.network_combo = QComboBox()
        self.network_combo.addItems(NETWORKS.keys())

        self.load_button = QPushButton("Load Network")

        self.tolerance_spin = QDoubleSpinBox()
        self.tolerance_spin.setDecimals(10)
        self.tolerance_spin.setRange(1e-10, 1e-2)
        self.tolerance_spin.setSingleStep(1e-8)
        self.tolerance_spin.setValue(1e-8)

        self.iterations_spin = QSpinBox()
        self.iterations_spin.setRange(1, 200)
        self.iterations_spin.setValue(40)

        self.q_limits_check = QCheckBox(
            "Enforce generator reactive limits"
        )

        self.run_button = QPushButton("Run Load Flow")
        self.run_button.setObjectName("runButton")

        controls_layout.addWidget(
            QLabel("Network:"), 0, 0
        )
        controls_layout.addWidget(
            self.network_combo, 0, 1
        )
        controls_layout.addWidget(
            self.load_button, 0, 2
        )

        controls_layout.addWidget(
            QLabel("Tolerance (pu):"), 1, 0
        )
        controls_layout.addWidget(
            self.tolerance_spin, 1, 1
        )

        controls_layout.addWidget(
            QLabel("Maximum iterations:"), 1, 2
        )
        controls_layout.addWidget(
            self.iterations_spin, 1, 3
        )

        controls_layout.addWidget(
            self.q_limits_check, 2, 0, 1, 2
        )
        controls_layout.addWidget(
            self.run_button, 2, 2, 1, 2
        )

        root.addWidget(controls)

        # ----------------------------------------------
        # STATUS LABEL
        # ----------------------------------------------

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        root.addWidget(self.status_label)

        # ----------------------------------------------
        # MAIN SPLITTER
        # ----------------------------------------------

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ----------------------------------------------
        # LEFT PANEL: NETWORK LOAD DATA
        # ----------------------------------------------

        input_box = QGroupBox(
            "Network Data - Editable Loads"
        )
        input_layout = QVBoxLayout(input_box)

        self.load_table = QTableWidget()

        configure_table(
            self.load_table,
            [
                "Bus",
                "Type",
                "Pd (MW)",
                "Qd (MVAr)",
            ],
        )

        input_layout.addWidget(self.load_table)

        help_label = QLabel(
            "Edit Pd and Qd, then click Run Load Flow.\n"
            "Bus numbers and types are read-only.\n"
            "After editing the diagram, click "
            "Apply Diagram Changes."
        )
        help_label.setWordWrap(True)
        input_layout.addWidget(help_label)

        # Module 10: Apply diagram changes
        self.sync_diagram_button = QPushButton(
            "Apply Diagram Changes"
        )
        input_layout.addWidget(
            self.sync_diagram_button
        )

        splitter.addWidget(input_box)

        # ----------------------------------------------
        # RIGHT PANEL: TABS
        # ----------------------------------------------

        self.tabs = QTabWidget()

        # MODULE 10: SINGLE-LINE DIAGRAM
        self.diagram_editor = DiagramEditor()

        self.tabs.addTab(
            self.diagram_editor,
            "Single-Line Diagram",
        )

        # MODULE 11: RESULTS CHARTS
        self.results_charts = ResultsCharts()

        self.tabs.addTab(
            self.results_charts,
            "Charts",
        )

        # ----------------------------------------------
        # BUS RESULTS TAB
        # ----------------------------------------------

        self.bus_table = QTableWidget()

        configure_table(
            self.bus_table,
            [
                "Bus",
                "Type",
                "Vm (pu)",
                "Angle (deg)",
                "P (MW)",
                "Q (MVAr)",
            ],
        )

        self.tabs.addTab(
            self.bus_table,
            "Bus Results",
        )

        # ----------------------------------------------
        # BRANCH FLOWS TAB
        # ----------------------------------------------

        self.branch_table = QTableWidget()

        configure_table(
            self.branch_table,
            [
                "Type",
                "From",
                "To",
                "P From",
                "Q From",
                "P To",
                "Q To",
                "P Loss",
                "Loading %",
            ],
        )

        self.tabs.addTab(
            self.branch_table,
            "Branch Flows",
        )

        # ----------------------------------------------
        # SUMMARY TAB
        # ----------------------------------------------

        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)

        self.tabs.addTab(
            self.summary_text,
            "Summary",
        )

        # ----------------------------------------------
        # CONVERGENCE TAB
        # ----------------------------------------------

        self.history_text = QPlainTextEdit()
        self.history_text.setReadOnly(True)

        self.tabs.addTab(
            self.history_text,
            "Convergence",
        )

        splitter.addWidget(self.tabs)
        splitter.setSizes([400, 1000])

        root.addWidget(splitter, stretch=1)

        # ----------------------------------------------
        # MODULE 11: EXPORT PANEL
        # ----------------------------------------------

        self.export_panel = ExportPanel()
        root.addWidget(self.export_panel)

        # ----------------------------------------------
        # SIGNAL CONNECTIONS
        # ----------------------------------------------

        self.load_button.clicked.connect(
            self.load_selected_network
        )
        self.run_button.clicked.connect(
            self.run_load_flow
        )
        self.sync_diagram_button.clicked.connect(
            self.sync_diagram_to_network
        )

        # ----------------------------------------------
        # STYLESHEET
        # ----------------------------------------------

        self.setStyleSheet("""
            QMainWindow {
                background: #f4f7fb;
            }

            QLabel#mainHeading {
                font-size: 24px;
                font-weight: bold;
                color: #17365d;
                margin: 6px;
            }

            QGroupBox {
                font-weight: bold;
                border: 1px solid #cbd5e1;
                border-radius: 7px;
                margin-top: 12px;
                padding-top: 12px;
                background: white;
            }

            QPushButton {
                padding: 8px;
                border-radius: 5px;
                background: #e2e8f0;
            }

            QPushButton#runButton {
                background: #1764a8;
                color: white;
                font-weight: bold;
            }

            QPushButton#runButton:disabled {
                background: #94a3b8;
            }

            QTableWidget {
                background: white;
                alternate-background-color: #f1f5f9;
                gridline-color: #e2e8f0;
            }

            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                background: white;
            }

            QLabel#statusLabel {
                padding: 5px;
                font-weight: bold;
            }
        """)

    # ==================================================
    # LOAD NETWORK
    # ==================================================

    def load_selected_network(self):

        if self.worker is not None:
            return

        name = self.network_combo.currentText()

        try:
            network = load_network(name)

        except Exception as exc:
            self.status_label.setText(
                f"Failed to load {name}"
            )

            QMessageBox.critical(
                self,
                "Network Loading Error",
                str(exc),
            )
            return

        self.network = network
        self.study = None

        # Update the single-line diagram.
        self.diagram_editor.set_network(network)

        self.populate_load_table()
        self.clear_results()

        self.status_label.setText(
            f"Loaded {name}: {len(network.buses)} buses"
        )

    # ==================================================
    # APPLY DIAGRAM CHANGES
    # ==================================================

    def sync_diagram_to_network(self):

        if self.worker is not None:
            return

        self.network = self.diagram_editor.get_network()
        self.study = None

        self.populate_load_table()
        self.clear_results()

        self.diagram_editor.scene.clear_solution()

        self.status_label.setText(
            "Diagram changes applied. "
            "Review loads before solving."
        )

    # ==================================================
    # POPULATE LOAD TABLE
    # ==================================================

    def populate_load_table(self):

        buses = [
            bus for bus in self.network.buses
            if bus.in_service
        ]

        self.load_table.setRowCount(len(buses))

        for row, bus in enumerate(buses):

            pd = sum(
                load.pd
                for load in self.network.loads
                if load.in_service
                and load.bus == bus.number
            )

            qd = sum(
                load.qd
                for load in self.network.loads
                if load.in_service
                and load.bus == bus.number
            )

            self.load_table.setItem(
                row, 0,
                table_item(bus.number)
            )

            self.load_table.setItem(
                row, 1,
                table_item(bus.bus_type)
            )

            self.load_table.setItem(
                row, 2,
                table_item(f"{pd:.6f}", True)
            )

            self.load_table.setItem(
                row, 3,
                table_item(f"{qd:.6f}", True)
            )

    # ==================================================
    # READ LOAD TABLE
    # ==================================================

    def read_load_table(self):

        values = {}

        for row in range(
            self.load_table.rowCount()
        ):

            number = int(
                self.load_table.item(row, 0).text()
            )

            try:
                pd = float(
                    self.load_table.item(row, 2).text()
                )

                qd = float(
                    self.load_table.item(row, 3).text()
                )

            except (ValueError, AttributeError):
                raise ValueError(
                    f"Invalid load at row {row + 1}"
                )

            if (
                not math.isfinite(pd)
                or not math.isfinite(qd)
            ):
                raise ValueError(
                    f"Nonfinite load at bus {number}"
                )

            values[number] = (pd, qd)

        return values

    # ==================================================
    # RUN NEWTON-RAPHSON LOAD FLOW
    # ==================================================

    def run_load_flow(self):

        if self.worker is not None:
            return

        if self.network is None:
            QMessageBox.warning(
                self,
                "No Network",
                "Load a network first.",
            )
            return

        try:
            # Use the electrical network currently
            # held by the diagram editor.
            edited = update_loads(
                self.diagram_editor.get_network(),
                self.read_load_table(),
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Invalid Input",
                str(exc),
            )
            return

        self.study = None
        self.clear_results()

        # Remove old voltage coloring.
        self.diagram_editor.scene.clear_solution()

        # Disable editing while solving.
        self.run_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.network_combo.setEnabled(False)
        self.load_table.setEnabled(False)
        self.diagram_editor.setEnabled(False)
        self.sync_diagram_button.setEnabled(False)

        self.status_label.setText(
            "Solving load flow..."
        )

        self.worker = LoadFlowWorker(
            edited,
            tolerance=self.tolerance_spin.value(),
            max_iterations=self.iterations_spin.value(),
            enforce_q_limits=(
                self.q_limits_check.isChecked()
            ),
            parent=self,
        )

        self.worker.completed.connect(
            self.on_completed
        )
        self.worker.failed.connect(
            self.on_failed
        )
        self.worker.finished.connect(
            self.on_worker_finished
        )

        self.worker.start()

    # ==================================================
    # LOAD FLOW COMPLETED
    # ==================================================

    def on_completed(self, study):

        self.study = study

        # Existing Module 9 result tables.
        self.populate_results(study)

        # Module 10 voltage visualization.
        self.diagram_editor.apply_solution(
            study.solution
        )

        # Module 11 charts and export controls.
        self.results_charts.set_study(study)
        self.export_panel.set_study(study)

        solution = study.solution

        self.status_label.setText(
            f"Converged in {solution.iterations} "
            f"iterations | "
            f"Mismatch: {solution.mismatch:.3e} pu"
        )

    # ==================================================
    # LOAD FLOW FAILED
    # ==================================================

    def on_failed(self, message):

        self.study = None
        self.clear_results()

        self.status_label.setText(
            "Load flow failed"
        )

        QMessageBox.critical(
            self,
            "Load Flow Error",
            message,
        )

    # ==================================================
    # BACKGROUND WORKER FINISHED
    # ==================================================

    def on_worker_finished(self):

        worker = self.worker

        self.run_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.network_combo.setEnabled(True)
        self.load_table.setEnabled(True)

        self.diagram_editor.setEnabled(True)
        self.sync_diagram_button.setEnabled(True)

        if worker is not None:
            worker.deleteLater()

        self.worker = None

    # ==================================================
    # CLEAR OLD RESULTS
    # ==================================================

    def clear_results(self):

        self.study = None

        self.bus_table.setRowCount(0)
        self.branch_table.setRowCount(0)

        self.summary_text.clear()
        self.history_text.clear()

        # Module 11:
        # Prevent exporting stale results.
        self.results_charts.clear_study()
        self.export_panel.set_study(None)

    # ==================================================
    # POPULATE RESULT TABLES
    # ==================================================

    def populate_results(self, study):

        network = study.network
        solution = study.solution
        flows = study.flows

        buses = [
            bus for bus in network.buses
            if bus.in_service
        ]

        self.bus_table.setRowCount(len(buses))

        final_types = (
            study.q_limits.bus_types
            if study.q_limits is not None
            else {
                bus.number: bus.bus_type
                for bus in buses
            }
        )

        # ----------------------------------------------
        # BUS RESULTS
        # ----------------------------------------------

        for row, bus in enumerate(buses):

            i = solution.bus_index[bus.number]

            values = [
                bus.number,
                final_types[bus.number],
                f"{solution.vm[i]:.6f}",
                f"{solution.va[i]:.6f}",
                (
                    f"{solution.p_calc[i] * network.base_mva:.5f}"
                ),
                (
                    f"{solution.q_calc[i] * network.base_mva:.5f}"
                ),
            ]

            for col, value in enumerate(values):
                self.bus_table.setItem(
                    row, col,
                    table_item(value)
                )

            if (
                solution.vm[i] < bus.vmin
                or solution.vm[i] > bus.vmax
            ):
                for col in range(len(values)):
                    self.bus_table.item(
                        row, col
                    ).setBackground(
                        QColor("#fff0c2")
                    )

        # ----------------------------------------------
        # BRANCH RESULTS
        # ----------------------------------------------

        self.branch_table.setRowCount(
            len(flows.branches)
        )

        for row, branch in enumerate(
            flows.branches
        ):

            values = [
                branch.kind,
                branch.from_bus,
                branch.to_bus,
                f"{branch.p_from:.4f}",
                f"{branch.q_from:.4f}",
                f"{branch.p_to:.4f}",
                f"{branch.q_to:.4f}",
                f"{branch.p_loss:.5f}",
                f"{branch.loading_percent:.2f}",
            ]

            for col, value in enumerate(values):
                self.branch_table.setItem(
                    row, col,
                    table_item(value)
                )

            if branch.loading_percent > 100:
                for col in range(len(values)):
                    self.branch_table.item(
                        row, col
                    ).setBackground(
                        QColor("#ffd7d7")
                    )

        # ----------------------------------------------
        # SUMMARY
        # ----------------------------------------------

        summary = [
            "APSA LOAD FLOW SUMMARY",
            "=" * 45,
            f"Buses: {len(buses)}",
            f"Branches: {len(flows.branches)}",
            f"Converged: {solution.converged}",
            f"NR iterations: {solution.iterations}",
            (
                "Maximum mismatch: "
                f"{solution.mismatch:.10e} pu"
            ),
            "",
            (
                "Total active loss: "
                f"{flows.total_p_loss:.6f} MW"
            ),
            (
                "Net branch reactive absorption: "
                f"{flows.total_q_net:.6f} MVAr"
            ),
            (
                "Maximum loading: "
                f"{flows.max_loading_percent:.3f} %"
            ),
            "",
            (
                "P balance residual: "
                f"{flows.bus_p_balance_error:.8e} MW"
            ),
            (
                "Q balance residual: "
                f"{flows.bus_q_balance_error:.8e} MVAr"
            ),
        ]

        if study.q_limits is not None:
            summary.extend([
                "",
                "GENERATOR Q-LIMIT ENFORCEMENT",
                (
                    "Outer iterations: "
                    f"{study.q_limits.outer_iterations}"
                ),
                (
                    "PV-to-PQ switched buses: "
                    f"{study.q_limits.switched_buses}"
                ),
            ])

        self.summary_text.setPlainText(
            "\n".join(summary)
        )

        # ----------------------------------------------
        # CONVERGENCE HISTORY
        # ----------------------------------------------

        history = [
            "NEWTON-RAPHSON MISMATCH HISTORY",
            "=" * 45,
        ]

        for index, mismatch in enumerate(
            solution.mismatch_history
        ):
            history.append(
                f"Iteration {index:3d}: "
                f"{mismatch:.10e} pu"
            )

        if study.q_limits is not None:
            history.append(
                "\nHistory shown is for the final "
                "inner Newton-Raphson solve."
            )

        self.history_text.setPlainText(
            "\n".join(history)
        )

    # ==================================================
    # SAFE WINDOW CLOSING
    # ==================================================

    def closeEvent(self, event):

        if (
            self.worker is not None
            and self.worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "Calculation in Progress",
                "Wait for the current calculation "
                "to finish before closing.",
            )

            event.ignore()
            return

        super().closeEvent(event)
