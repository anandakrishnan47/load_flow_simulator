
"""Interactive APSA single-line diagram editor."""

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGraphicsView,
    QInputDialog, QFileDialog,
    QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QDoubleSpinBox,
    QLabel,
)

from gui.diagram_scene import DiagramScene
from gui.diagram_items import BusItem, BranchItem


class DiagramEditor(QWidget):
    def __init__(self, network=None, parent=None):
        super().__init__(parent)

        self.scene = DiagramScene(network)
        self.build_ui()

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
        ]

        for text, callback in actions:
            button = QPushButton(text)
            button.clicked.connect(callback)
            toolbar.addWidget(button)

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

        root.addWidget(self.view)

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

        positions = self.scene.positions()

        # Change the actual network bus, not only
        # the graphical item.
        bus.base_kv = base_kv
        bus.vm = vm
        bus.vmin = vmin
        bus.vmax = vmax

        self.scene.rebuild(positions)

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

        positions = self.scene.positions()

        branch.r = r
        branch.x = x
        branch.rating_mva = rating

        if transformer:
            branch.tap_ratio = values[3]
            branch.phase_shift = values[4]
        else:
            branch.b = values[3]

        self.scene.rebuild(positions)

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
