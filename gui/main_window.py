
"""
E4234 Advanced Power System Analysis
APSA Load Flow Simulator

Module 9  - PySide6 GUI
Module 10 - Interactive Single-Line Diagram
Module 11 - Results Visualization and Export
"""

import math
from pathlib import Path

import shiboken6

from loadflow.models import Network

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QAction, QKeySequence
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
    QDockWidget, QFileDialog, QToolBar, QFormLayout,
)

from gui.controller import (
    NETWORKS,
    load_network,
    update_loads,
    validate_network,
)

from gui.worker import LoadFlowWorker
from gui.diagram_editor import DiagramEditor
from gui.diagram_items import EquipmentSymbol, BusItem, BranchItem

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
        self.project_path = None
        self._load_table_baseline = {}
        self._closing = False

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

        self.build_stage35_regions()

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

        self.project_path = None
        self.setWindowTitle("APSA | Newton-Raphson Load Flow Simulator")
        self.status_label.setText(
            f"Loaded {name}: {len(network.buses)} buses"
        )
        self.refresh_properties()

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
            "Diagram changes applied. Review loads before solving."
        )
        self.refresh_properties()

    # ==================================================
    # POPULATE LOAD TABLE
    # ==================================================

    def populate_load_table(self):

        buses = [
            bus for bus in self.network.buses
            if bus.in_service
        ]

        self.load_table.setRowCount(len(buses))
        self._load_table_baseline = {}

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

            self._load_table_baseline[bus.number] = (pd, qd)

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
            values = self.read_load_table()
            current = self.diagram_editor.get_network()
            active = {b.number for b in current.buses if b.in_service}
            if set(values) != active:
                raise ValueError(
                    "Diagram bus list changed. Click Apply Diagram Changes "
                    "to refresh the load table before solving."
                )
            changed = {
                number: value for number, value in values.items()
                if not all(
                    math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
                    for a, b in zip(value, self._load_table_baseline.get(number, (float('nan'), float('nan'))))
                )
            }
            edited = update_loads(current, changed)
            validate_network(edited)

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Invalid Input",
                str(exc),
            )
            return

        # Commit only changed loads to the diagram's electrical model.
        if changed:
            positions = self.diagram_editor.scene.positions()
            self.diagram_editor.scene.set_network(edited)
            for number, (x, y) in positions.items():
                if number in self.diagram_editor.scene.bus_items:
                    self.diagram_editor.scene.bus_items[number].setPos(x, y)
            self.network = self.diagram_editor.get_network()
            self.populate_load_table()

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

        self.status_label.setText("Solving load flow...")
        self.log_message("Starting Newton-Raphson study")

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

        self.log_message(f"Converged in {solution.iterations} iterations")
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

        self.status_label.setText("Load flow failed")
        self.log_message(f"Study failed: {message}")

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
    # STAGE 3.5: SEVEN-REGION MAIN WINDOW
    # ==================================================

    def build_stage35_regions(self):
        # Region 1: menu bar; region 2: toolbar.
        menus = {name: self.menuBar().addMenu(name) for name in (
            "File", "Edit", "View", "Network", "Study", "Results", "Help"
        )}
        toolbar = QToolBar("Main tools", self)
        toolbar.setObjectName("mainTools")
        self.addToolBar(toolbar)

        def action(menu, title, callback, shortcut=None, on_toolbar=False):
            item = QAction(title, self)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            item.triggered.connect(callback)
            menus[menu].addAction(item)
            if on_toolbar:
                toolbar.addAction(item)
            return item

        action("File", "New Project", self.new_project, "Ctrl+N", True)
        action("File", "Open Project...", self.open_project, "Ctrl+O", True)
        action("File", "Save Project", self.save_project, "Ctrl+S", True)
        action("File", "Save Project As...", self.save_project_as, "Ctrl+Shift+S")
        action("File", "Load Benchmark", self.load_selected_network)
        action("File", "Exit", self.close)
        action("Edit", "Undo", self.diagram_editor.scene.undo, "Ctrl+Z", True)
        action("Edit", "Redo", self.diagram_editor.scene.redo, "Ctrl+Y", True)
        action("Edit", "Delete Selected", self.diagram_editor.delete_selected, "Delete")
        action("View", "Zoom to Fit", self.diagram_editor.fit_view, "Ctrl+0", True)
        action("View", "Zoom In", self.diagram_editor.zoom_in, "Ctrl++")
        action("View", "Zoom Out", self.diagram_editor.zoom_out, "Ctrl+-")
        action("Network", "Apply Diagram Changes", self.sync_diagram_to_network)
        action("Network", "Check Network", self.check_network, on_toolbar=True)
        action("Study", "Run Newton-Raphson", self.run_load_flow, "F5", True)
        action("Results", "Bus Results", lambda: self.tabs.setCurrentWidget(self.bus_table))
        action("Results", "Branch Flows", lambda: self.tabs.setCurrentWidget(self.branch_table))
        action("Results", "Charts", lambda: self.tabs.setCurrentWidget(self.results_charts))
        action("Help", "About", lambda: QMessageBox.information(
            self, "APSA", "E4234 APSA Newton-Raphson Load Flow Simulator"
        ))

        # Region 3: component palette; region 4: diagram canvas (existing tab).
        self.palette_dock = QDockWidget("Component Palette", self)
        palette = QWidget()
        palette_layout = QVBoxLayout(palette)
        for title, callback in (
            ("Add Bus", self.diagram_editor.add_bus_dialog),
            ("Add Line", self.diagram_editor.add_line_dialog),
            ("Add Transformer", self.diagram_editor.add_transformer_dialog),
            ("Connect Transformer (click buses)", lambda: self.diagram_editor.start_connection("Transformer")),
            ("Add Generator", self.diagram_editor.add_generator_dialog),
            ("Add Load", self.diagram_editor.add_load_dialog),
            ("Edit Selected", self.diagram_editor.edit_selected),
            ("Delete Selected", self.diagram_editor.delete_selected),
        ):
            button = QPushButton(title)
            button.clicked.connect(callback)
            palette_layout.addWidget(button)
        palette_layout.addStretch()
        self.palette_dock.setWidget(palette)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.palette_dock)

        # Region 5: selected-object properties.
        self.properties_dock = QDockWidget("Properties", self)
        self.properties_text = QPlainTextEdit()
        self.properties_text.setReadOnly(True)
        properties_container = QWidget()
        properties_layout = QVBoxLayout(properties_container)
        properties_layout.addWidget(self.properties_text)
        self.properties_edit_button = QPushButton('Edit Selected Properties...')
        self.properties_edit_button.clicked.connect(self.diagram_editor.edit_selected)
        properties_layout.addWidget(self.properties_edit_button)
        self.properties_dock.setWidget(properties_container)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        # Region 6: study configuration/results already in the central area.
        # Region 7: event log and status bar.
        self.log_dock = QDockWidget("Event Log", self)
        self.event_log = QPlainTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.setMaximumBlockCount(1000)
        self.log_dock.setWidget(self.event_log)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.statusBar().showMessage("Ready")
        self.diagram_editor.scene.selectionChanged.connect(self.refresh_properties)
        self.diagram_editor.scene.undo_stack.indexChanged.connect(self.on_diagram_edit)
        self.diagram_editor.scene.undo_stack.indexChanged.connect(
            self.invalidate_study
        )
        self.refresh_properties()

    def _live_scene(self):
        """Return the scene only while its underlying Qt objects are alive.

        During pytest-qt teardown a Python wrapper can outlive its C++ object.
        A Python reference alone is therefore not sufficient.
        """
        if getattr(self, "_closing", False):
            return None
        try:
            if not shiboken6.isValid(self):
                return None
            editor = getattr(self, "diagram_editor", None)
            if editor is None or not shiboken6.isValid(editor):
                return None
            scene = getattr(editor, "scene", None)
            if scene is None or not shiboken6.isValid(scene):
                return None
            return scene
        except (RuntimeError, ReferenceError):
            return None

    def on_diagram_edit(self, *args):
        """Keep the load table aligned with structural diagram edits.

        Never discard user-entered pending load values silently.
        """
        if self._live_scene() is None or self.worker is not None:
            return
        try:
            values = self.read_load_table()
            dirty = any(
                not all(math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
                        for a, b in zip(pair, self._load_table_baseline.get(number, (float('nan'), float('nan')))))
                for number, pair in values.items()
            )
        except (ValueError, AttributeError, TypeError):
            dirty = True
        if not dirty:
            self.network = self.diagram_editor.get_network()
            self.populate_load_table()
        else:
            self.status_label.setText('Pending load table edits: apply them before refreshing diagram data')
        self.refresh_properties()

    # ==================================================
    # STAGE 3.7: BLANK PROJECT WORKSPACE
    # ==================================================

    def _has_unsaved_changes(self):
        """Check structural undo history and uncommitted table values."""
        try:
            stack = self.diagram_editor.scene.undo_stack
            if not stack.isClean():
                return True
        except RuntimeError:
            return True

        try:
            current = self.read_load_table()
            if set(current) != set(self._load_table_baseline):
                return True
            for number, pair in current.items():
                original = self._load_table_baseline[number]
                if any(
                    not math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
                    for a, b in zip(pair, original)
                ):
                    return True
        except (ValueError, TypeError, AttributeError, KeyError):
            return True
        return False

    def _confirm_discard_changes(self):
        """Ask before replacing a modified network."""
        if not self._has_unsaved_changes():
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The current network has unsaved changes.\n"
            "Discard them and create a new blank project?",
            QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Discard

    def new_project(self):
        """Create an empty editable network, without an IEEE example."""
        if self.worker is not None:
            QMessageBox.information(
                self,
                "Calculation in Progress",
                "Wait for the current load-flow calculation to finish.",
            )
            return

        if not self._confirm_discard_changes():
            return

        # Network() contains no buses, branches, generators or loads.
        # It is intentionally invalid for power flow until a slack bus
        # and the necessary network components have been created.
        network = Network(base_mva=100.0)
        self.diagram_editor.set_network(network)
        self.network = self.diagram_editor.get_network()
        self.project_path = None
        self.study = None
        self.populate_load_table()
        self.clear_results()
        self.diagram_editor.scene.clear_solution()
        self.diagram_editor.fit_view()
        self.refresh_properties()

        # The blank project is a clean initial state.
        self.diagram_editor.scene.undo_stack.setClean()
        self.setWindowTitle(
            "APSA | Untitled Project - Newton-Raphson Load Flow Simulator"
        )
        self.status_label.setText(
            "New blank project. Add a Slack bus to begin."
        )
        self.log_message(
            "Created new blank project (100 MVA base). "
            "Add a Slack bus, then connect other buses and equipment."
        )
        # Show the editor immediately, even if another results tab was active.
        self.tabs.setCurrentWidget(self.diagram_editor)

    def log_message(self, message):
        self.event_log.appendPlainText(str(message))
        self.statusBar().showMessage(str(message), 8000)

    def invalidate_study(self, *args):
        scene = self._live_scene()
        if scene is None or self.worker is not None or self.study is None:
            return
        self.clear_results()
        try:
            if shiboken6.isValid(scene):
                scene.clear_solution()
        except (RuntimeError, ReferenceError):
            return
        self.status_label.setText("Network changed: results cleared")

    def refresh_properties(self, *args):
        """Safely refresh selected component details, including during Qt teardown."""
        scene = self._live_scene()
        if scene is None:
            return
        try:
            panel = getattr(self, "properties_text", None)
            if panel is None or not shiboken6.isValid(panel):
                return
            selected = scene.selectedItems()
            item = next(
                (obj for obj in selected if isinstance(obj, (EquipmentSymbol, BusItem, BranchItem))),
                None,
            )
            if item is None:
                panel.setPlainText("Select a bus, line, transformer, generator or load in the diagram.")
                return
            component = getattr(item, "component", None)
            if component is None:
                component = getattr(item, "bus", None)
            if component is None:
                component = getattr(item, "branch", None)
            from dataclasses import asdict
            panel.setPlainText(
                "\n".join(f"{key}: {value}" for key, value in asdict(component).items())
            )
        except (RuntimeError, ReferenceError):
            # The scene or its widgets may be destroyed by Qt during teardown.
            return

    def check_network(self):
        try:
            network = self.diagram_editor.get_network()
            validate_network(network)
        except Exception as exc:
            self.log_message(f"Network check failed: {exc}")
            QMessageBox.warning(self, "Network Check", str(exc))
            return False
        self.log_message("Network check passed")
        return True

    def save_project(self):
        if self.worker is not None:
            return
        if not self.project_path:
            return self.save_project_as()
        try:
            # Commit pending load table edits without altering unchanged ZIP loads.
            values = self.read_load_table()
            current = self.diagram_editor.get_network()
            active = {b.number for b in current.buses if b.in_service}
            if set(values) != active:
                raise ValueError("Click Apply Diagram Changes to refresh the load table.")
            changed = {n: v for n, v in values.items() if not all(
                math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
                for a, b in zip(v, self._load_table_baseline.get(n, (float('nan'), float('nan'))))
            )}
            if changed:
                positions = self.diagram_editor.scene.positions()
                edited = update_loads(current, changed)
                self.diagram_editor.scene.set_network(edited)
                for number, pos in positions.items():
                    if number in self.diagram_editor.scene.bus_items:
                        self.diagram_editor.scene.bus_items[number].setPos(*pos)
                self.network = self.diagram_editor.get_network()
                self.populate_load_table()
            self.diagram_editor.scene.save_project(self.project_path)
            self.diagram_editor.scene.undo_stack.setClean()
            self.setWindowTitle(f"APSA | {Path(self.project_path).name}")
            self.log_message(f"Saved project: {self.project_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Project Error", str(exc))

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save APSA Project", self.project_path or "apsa_project.json",
            "APSA Project (*.json)"
        )
        if path:
            old = self.project_path
            self.project_path = path
            self.save_project()
            if not Path(path).is_file():
                self.project_path = old

    def open_project(self):
        if self.worker is not None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open APSA Project", "", "APSA Project (*.json)"
        )
        if not path:
            return
        try:
            network = self.diagram_editor.scene.load_project(path)
            self.network = network
            self.project_path = path
            self.setWindowTitle(f"APSA | {Path(path).name}")
            self.populate_load_table()
            self.clear_results()
            self.diagram_editor.scene.clear_solution()
            self.diagram_editor.fit_view()
            self.refresh_properties()
            self.log_message(f"Opened project: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Open Project Error", str(exc))

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

        self._closing = True
        scene = self._live_scene_for_disconnect()
        if scene is not None:
            try:
                scene.selectionChanged.disconnect(self.refresh_properties)
            except (RuntimeError, TypeError):
                pass
            try:
                stack = scene.undo_stack
                if shiboken6.isValid(stack):
                    for callback in (self.on_diagram_edit, self.invalidate_study):
                        try:
                            stack.indexChanged.disconnect(callback)
                        except (RuntimeError, TypeError):
                            pass
            except (RuntimeError, ReferenceError):
                pass
        super().closeEvent(event)

    def _live_scene_for_disconnect(self):
        """Access scene during close without the _closing restriction."""
        try:
            editor = getattr(self, "diagram_editor", None)
            if editor is None or not shiboken6.isValid(editor):
                return None
            scene = getattr(editor, "scene", None)
            return scene if scene is not None and shiboken6.isValid(scene) else None
        except (RuntimeError, ReferenceError):
            return None
