
"""Interactive APSA single-line diagram editor."""

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGraphicsView,
    QInputDialog, QFileDialog,
    QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QDoubleSpinBox,
    QLabel, QListWidget, QSplitter,
)

from loadflow.models import Generator, Load
from gui.diagram_scene import DiagramScene
from gui.diagram_items import BusItem, BranchItem


class DiagramEditor(QWidget):
    def __init__(self, network=None, parent=None):
        super().__init__(parent)

        self.scene = DiagramScene(network)
        self.build_ui()
        self._shortcuts = []
        for keys, action in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Shift+Z", self.redo), ("Delete", self.delete_selected)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)
            self._shortcuts.append(shortcut)
        self.scene.undo_stack.indexChanged.connect(self.update_undo_buttons)
        self.update_undo_buttons()

    def build_ui(self):
        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        actions = [
            ("Add Bus", self.add_bus_dialog),
            ("Add Line", self.add_line_dialog),
            ("Add Transformer", self.add_transformer_dialog),
            ("Edit Selected", self.edit_selected),
            ("Delete Selected", self.delete_selected),
            ("Save Layout", self.save_layout_dialog),
            ("Load Layout", self.load_layout_dialog),
            ("Zoom +", self.zoom_in),
            ("Zoom -", self.zoom_out),
            ("Fit", self.fit_view),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Save Project", self.save_project_dialog),
            ("Open Project", self.open_project_dialog),
        ]

        for text, callback in actions:
            button = QPushButton(text)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
            if text == "Undo":
                self.undo_button = button
            elif text == "Redo":
                self.redo_button = button

        root.addLayout(toolbar)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(
            self.view.renderHints()
        )

        self.view.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag
        )

        self.view.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )

        container = QSplitter(Qt.Orientation.Horizontal)
        palette = QWidget()
        palette_layout = QVBoxLayout(palette)
        palette_layout.addWidget(QLabel("Component palette"))
        self.palette = QListWidget()
        self.palette.addItems(["Bus", "Line", "Transformer", "Generator", "Load"])
        self.palette.itemDoubleClicked.connect(lambda item: self.add_palette_component(item.text()))
        palette_layout.addWidget(self.palette)
        add_component = QPushButton("Add selected component")
        add_component.clicked.connect(self.add_selected_palette_component)
        palette_layout.addWidget(add_component)
        container.addWidget(palette)
        container.addWidget(self.view)
        container.setSizes([170, 850])
        root.addWidget(container)

        self.info_label = QLabel(
            "Drag buses to move them. "
            "Select a bus or branch to edit or delete."
        )
        root.addWidget(self.info_label)

    def show_error(self, exc):
        QMessageBox.warning(
            self,
            "Diagram Editor",
            str(exc),
        )

    def add_bus_dialog(self):
        number, ok = QInputDialog.getInt(
            self, "Add Bus", "Bus number:",
            1, 1, 99999,
        )
        if not ok:
            return

        try:
            self.scene.add_bus(
                number=number,
                bus_type="PQ",
                x=150,
                y=150,
            )
        except ValueError as exc:
            self.show_error(exc)

    def choose_endpoints(self):
        numbers = sorted(self.scene.bus_items)

        if len(numbers) < 2:
            raise ValueError(
                "At least two buses are required"
            )

        options = [str(n) for n in numbers]

        from_text, ok = QInputDialog.getItem(
            self, "From Bus", "From bus:",
            options, 0, False,
        )
        if not ok:
            return None

        to_text, ok = QInputDialog.getItem(
            self, "To Bus", "To bus:",
            options, 0, False,
        )
        if not ok:
            return None

        return int(from_text), int(to_text)

    def add_line_dialog(self):
        try:
            endpoints = self.choose_endpoints()
            if endpoints is None:
                return

            self.scene.add_line(
                *endpoints,
                r=0.02,
                x=0.06,
                b=0.0,
                rating_mva=100.0,
            )
        except ValueError as exc:
            self.show_error(exc)

    def add_transformer_dialog(self):
        try:
            endpoints = self.choose_endpoints()
            if endpoints is None:
                return

            self.scene.add_transformer(
                *endpoints,
                r=0.01,
                x=0.05,
                rating_mva=100.0,
            )
        except ValueError as exc:
            self.show_error(exc)

    def selected_component(self):
        selected = self.scene.selectedItems()

        # Ignore child text labels; use their parents.
        for item in selected:
            if isinstance(item, (BusItem, BranchItem)):
                return item

            parent = item.parentItem()
            if isinstance(parent, (BusItem, BranchItem)):
                return parent

        return None

    def edit_selected(self):
        item = self.selected_component()

        if item is None:
            self.show_error(
                "Select a bus or branch first."
            )
            return

        if isinstance(item, BusItem):
            self.edit_bus(item)
        else:
            self.edit_branch(item)

    def parameter_dialog(self, title, fields):
        """
        Show a form containing floating-point fields.

        fields: [(label, initial_value), ...]

        Returns a list of values, or None on cancel.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(title)

        layout = QFormLayout(dialog)
        widgets = []

        for label, initial in fields:
            spin = QDoubleSpinBox(dialog)
            spin.setDecimals(8)
            spin.setRange(-1e9, 1e9)
            spin.setValue(float(initial))
            layout.addRow(label, spin)
            widgets.append(spin)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        return [widget.value() for widget in widgets]

    def edit_bus(self, item):
        bus = item.bus

        values = self.parameter_dialog(
            f"Edit Bus {bus.number}",
            [
                ("Base voltage (kV)", bus.base_kv),
                ("Initial Vm (pu)", bus.vm),
                ("Vmin (pu)", bus.vmin),
                ("Vmax (pu)", bus.vmax),
            ],
        )

        if values is None:
            return

        base_kv, vm, vmin, vmax = values

        if (
            base_kv <= 0
            or vm <= 0
            or vmin <= 0
            or vmin >= vmax
        ):
            self.show_error("Invalid bus parameters")
            return

        before_network, positions = self.scene._snapshot()

        # Change the actual network bus, not only
        # the graphical item.
        bus.base_kv = base_kv
        bus.vm = vm
        bus.vmin = vmin
        bus.vmax = vmax

        self.scene.rebuild(positions)
        self.scene.record_external_edit(before_network, positions, "Edit bus")

    def edit_branch(self, item):
        branch = item.branch
        transformer = item.kind == "Transformer"

        fields = [
            ("Resistance R (pu)", branch.r),
            ("Reactance X (pu)", branch.x),
            ("Rating (MVA)", branch.rating_mva),
        ]

        if transformer:
            fields.extend([
                ("Tap ratio", branch.tap_ratio),
                ("Phase shift (degrees)", branch.phase_shift),
            ])
        else:
            fields.append(
                ("Total charging B (pu)", branch.b)
            )

        values = self.parameter_dialog(
            f"Edit {item.kind}",
            fields,
        )

        if values is None:
            return

        r, x, rating = values[:3]

        if (r == 0 and x == 0) or rating <= 0:
            self.show_error(
                "Invalid impedance or MVA rating"
            )
            return

        if transformer and values[3] <= 0:
            self.show_error(
                "Transformer tap ratio must be positive"
            )
            return

        before_network, positions = self.scene._snapshot()

        branch.r = r
        branch.x = x
        branch.rating_mva = rating

        if transformer:
            branch.tap_ratio = values[3]
            branch.phase_shift = values[4]
        else:
            branch.b = values[3]

        self.scene.rebuild(positions)
        self.scene.record_external_edit(before_network, positions, "Edit branch")

    def delete_selected(self):
        item = self.selected_component()

        if item is None:
            self.show_error(
                "Select a bus or branch first."
            )
            return

        try:
            if isinstance(item, BusItem):
                self.scene.remove_bus(
                    item.bus.number
                )
            else:
                self.scene.remove_branch(
                    item.branch
                )
        except ValueError as exc:
            self.show_error(exc)

    def save_layout_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Diagram Layout",
            "diagram_layout.json",
            "JSON Files (*.json)",
        )

        if path:
            try:
                self.scene.save_layout(path)
            except (OSError, ValueError) as exc:
                self.show_error(exc)

    def load_layout_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Diagram Layout",
            "",
            "JSON Files (*.json)",
        )

        if path:
            try:
                self.scene.load_layout(path)
            except (
                OSError, ValueError,
                KeyError, TypeError,
            ) as exc:
                self.show_error(exc)

    def zoom_in(self):
        self.view.scale(1.2, 1.2)

    def zoom_out(self):
        self.view.scale(1 / 1.2, 1 / 1.2)

    def set_network(self, network):
        self.scene.set_network(network)

    def apply_solution(self, result):
        self.scene.apply_solution(result)

    def get_network(self):
        """Return an independent copy of edited data."""
        return deepcopy(self.scene.network)

    # Stage 3: additional editor operations.
    def update_undo_buttons(self, *args):
        self.undo_button.setEnabled(self.scene.can_undo())
        self.redo_button.setEnabled(self.scene.can_redo())

    def undo(self):
        self.scene.undo()

    def redo(self):
        self.scene.redo()

    def fit_view(self):
        bounds = self.scene.itemsBoundingRect()
        if not bounds.isEmpty():
            self.view.fitInView(bounds.adjusted(-50, -50, 50, 50), Qt.AspectRatioMode.KeepAspectRatio)

    def add_selected_palette_component(self):
        item = self.palette.currentItem()
        if item is not None:
            self.add_palette_component(item.text())

    def add_palette_component(self, name):
        actions = {
            "Bus": self.add_bus_dialog,
            "Line": self.add_line_dialog,
            "Transformer": self.add_transformer_dialog,
            "Generator": self.add_generator_dialog,
            "Load": self.add_load_dialog,
        }
        actions[name]()

    def _choose_bus(self, title):
        options = [str(n) for n in sorted(self.scene.bus_items)]
        if not options:
            self.show_error("Add a bus first")
            return None
        selected, ok = QInputDialog.getItem(self, title, "Bus:", options, 0, False)
        return int(selected) if ok else None

    def add_generator_dialog(self):
        bus = self._choose_bus("Generator bus")
        if bus is None:
            return
        values = self.parameter_dialog("Generator", [
            ("Pg (MW)", 50.0), ("Qg (MVAr)", 0.0),
            ("Voltage setpoint (pu)", 1.0),
            ("Qmin (MVAr)", -100.0), ("Qmax (MVAr)", 100.0),
        ])
        if values is None:
            return
        pg, qg, vg, qmin, qmax = values
        if vg <= 0 or qmin > qmax:
            self.show_error("Invalid generator settings")
            return
        try:
            before_network, positions = self.scene._snapshot()
            self.scene.network.add_generator(Generator(bus=bus, pg=pg, qg=qg, vg=vg, qmin=qmin, qmax=qmax))
            self.scene.rebuild(positions)
            self.scene.record_external_edit(before_network, positions, "Add generator")
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

    def add_load_dialog(self):
        bus = self._choose_bus("Load bus")
        if bus is None:
            return
        values = self.parameter_dialog("Load", [("Pd (MW)", 20.0), ("Qd (MVAr)", 10.0)])
        if values is None:
            return
        try:
            before_network, positions = self.scene._snapshot()
            self.scene.network.add_load(Load(bus=bus, pd=values[0], qd=values[1]))
            self.scene.rebuild(positions)
            self.scene.record_external_edit(before_network, positions, "Add load")
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

    def save_project_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save APSA project", "apsa_project.json", "JSON files (*.json)")
        if path:
            try:
                self.scene.save_project(path)
            except (OSError, ValueError, TypeError) as exc:
                self.show_error(exc)

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open APSA project", "", "JSON files (*.json)")
        if path:
            try:
                self.scene.load_project(path)
                self.fit_view()
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.show_error(exc)
