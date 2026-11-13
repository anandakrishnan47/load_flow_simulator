"""Interactive APSA single-line diagram editor."""

from copy import deepcopy

from shiboken6 import isValid

from PySide6.QtCore import Qt, QMimeData, Signal
from PySide6.QtGui import QShortcut, QKeySequence, QDrag
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGraphicsView,
    QInputDialog, QFileDialog,
    QMessageBox, QDialog, QFormLayout,
    QDialogButtonBox, QDoubleSpinBox,
    QLabel, QListWidget, QSplitter, QAbstractItemView, QComboBox, QCheckBox,
)

from loadflow.models import Generator, Load
from gui.diagram_scene import DiagramScene
from gui.diagram_items import BusItem, BranchItem, EquipmentSymbol


class ComponentPalette(QListWidget):
    """Export the component name as plain-text drag data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setText('APSA_COMPONENT:' + item.text())
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class DiagramView(QGraphicsView):
    """Canvas supporting component drops and two-click branch connections."""

    componentDropped = Signal(str, float, float)
    connectionClicked = Signal(int)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setAcceptDrops(True)
        self.connection_mode = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith('APSA_COMPONENT:'):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText() and event.mimeData().text().startswith('APSA_COMPONENT:'):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        text = event.mimeData().text() if event.mimeData().hasText() else ''
        if text.startswith('APSA_COMPONENT:'):
            name = text.split(':', 1)[1]
            if name in ('Bus', 'Line', 'Transformer', 'Generator', 'Load'):
                point = self.mapToScene(event.position().toPoint())
                self.componentDropped.emit(name, point.x(), point.y())
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def mousePressEvent(self, event):
        if self.connection_mode and event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            while item is not None and not isinstance(item, BusItem):
                item = item.parentItem()
            if isinstance(item, BusItem):
                self.connectionClicked.emit(item.bus.number)
                event.accept()
                return
        super().mousePressEvent(event)


class DiagramEditor(QWidget):
    def __init__(self, network=None, parent=None):
        super().__init__(parent)

        self.scene = DiagramScene(network)
        self.build_ui()
        self._shortcuts = []
        for keys, action in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Shift+Z", self.redo), ("Delete", self.delete_selected), ("Esc", self.cancel_connection)):
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

        self.view = DiagramView(self.scene)
        self.view.componentDropped.connect(self.handle_component_drop)
        self.view.connectionClicked.connect(self.handle_connection_click)
        self._pending_connection_bus = None
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
        self.palette = ComponentPalette()
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
            "Select a bus, branch, generator or load to edit or delete."
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
                bus_type="Slack" if not any(b.bus_type == "Slack" and b.in_service for b in self.scene.network.buses) else "PQ",
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
        for item in self.scene.selectedItems():
            if isinstance(item, (EquipmentSymbol, BusItem, BranchItem)):
                return item
            parent = item.parentItem()
            if isinstance(parent, (EquipmentSymbol, BusItem, BranchItem)):
                return parent
        return None

    def edit_selected(self):
        item = self.selected_component()
        if item is None:
            self.show_error('Select a bus, branch, generator or load first.')
        elif isinstance(item, EquipmentSymbol):
            self.edit_equipment(item)
        elif isinstance(item, BusItem):
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
        # Preserve the original two-argument parameter_dialog integration API.
        # Existing automated GUI clients replace this method to supply numeric
        # edits without displaying a modal dialog.
        if 'parameter_dialog' in self.__dict__:
            values = self.parameter_dialog(
                f'Edit Bus {bus.number}',
                [('Base voltage (kV)', bus.base_kv),
                 ('Initial Vm (pu)', bus.vm),
                 ('Vmin (pu)', bus.vmin),
                 ('Vmax (pu)', bus.vmax)],
            )
            if values is None:
                return
            if len(values) != 4:
                self.show_error('Expected four bus parameters')
                return
            try:
                self.scene.edit_component(
                    bus, dict(zip(('base_kv', 'vm', 'vmin', 'vmax'), values)),
                    'Edit bus',
                )
            except (ValueError, TypeError) as exc:
                self.show_error(exc)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Edit Bus {bus.number}')
        layout = QFormLayout(dialog)
        kind = QComboBox(dialog)
        kind.addItems(['Slack', 'PV', 'PQ'])
        kind.setCurrentText(bus.bus_type)
        layout.addRow('Bus type', kind)
        fields = {}
        for key, label in (
            ('base_kv', 'Base voltage (kV)'),
            ('vm', 'Initial voltage Vm (pu)'),
            ('va', 'Initial angle Va (degrees)'),
            ('vmin', 'Minimum voltage (pu)'),
            ('vmax', 'Maximum voltage (pu)'),
        ):
            spin = QDoubleSpinBox(dialog)
            spin.setDecimals(8)
            spin.setRange(-1e9, 1e9)
            spin.setValue(float(getattr(bus, key)))
            layout.addRow(label, spin)
            fields[key] = spin
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        changes = {key: spin.value() for key, spin in fields.items()}
        changes['bus_type'] = kind.currentText()
        try:
            self.scene.edit_component(bus, changes, 'Edit bus')
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

    def edit_equipment(self, item):
        component = item.component
        kind = item.kind
        if kind == 'Generator':
            fields = [('pg', 'Active generation Pg (MW)'),
                      ('qg', 'Reactive generation Qg (MVAr)'),
                      ('vg', 'Voltage setpoint Vg (pu)'),
                      ('qmin', 'Minimum reactive power (MVAr)'),
                      ('qmax', 'Maximum reactive power (MVAr)')]
        else:
            fields = [('pd', 'Active demand Pd (MW)'),
                      ('qd', 'Reactive demand Qd (MVAr)')]
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Edit {kind} at Bus {component.bus}')
        layout = QFormLayout(dialog)
        widgets = {}
        for key, label in fields:
            spin = QDoubleSpinBox(dialog)
            spin.setDecimals(8)
            spin.setRange(-1e9, 1e9)
            spin.setValue(float(getattr(component, key)))
            layout.addRow(label, spin)
            widgets[key] = spin
        enabled = QCheckBox(dialog)
        enabled.setChecked(component.in_service)
        layout.addRow('In service', enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        changes = {key: widget.value() for key, widget in widgets.items()}
        changes['in_service'] = enabled.isChecked()
        try:
            self.scene.edit_component(component, changes, f'Edit {kind.lower()}')
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

    def edit_branch(self, item):
        branch = item.branch
        transformer = item.kind == 'Transformer'
        # Backward-compatible numerical editing interface for older GUI
        # integrations; the regular dialog below additionally supports status
        # and transformer tap-side editing.
        if 'parameter_dialog' in self.__dict__:
            labels = [('Resistance R (pu)', branch.r),
                      ('Reactance X (pu)', branch.x),
                      ('Rating (MVA)', branch.rating_mva)]
            keys = ['r', 'x', 'rating_mva']
            if transformer:
                labels += [('Tap ratio', branch.tap_ratio),
                           ('Phase shift (degrees)', branch.phase_shift)]
                keys += ['tap_ratio', 'phase_shift']
            else:
                labels += [('Total charging B (pu)', branch.b)]
                keys += ['b']
            values = self.parameter_dialog(f'Edit {item.kind}', labels)
            if values is None:
                return
            if len(values) != len(keys):
                self.show_error('Incorrect number of branch parameters')
                return
            try:
                self.scene.edit_component(branch, dict(zip(keys, values)),
                                          f'Edit {item.kind.lower()}')
            except (ValueError, TypeError) as exc:
                self.show_error(exc)
            return
        fields = [('r', 'Resistance R (pu)'), ('x', 'Reactance X (pu)'),
                  ('rating_mva', 'MVA rating')]
        if transformer:
            fields += [('tap_ratio', 'Tap ratio'), ('phase_shift', 'Phase shift (degrees)')]
        else:
            fields += [('b', 'Total line charging B (pu)')]
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Edit {item.kind}: {branch.from_bus} to {branch.to_bus}')
        layout = QFormLayout(dialog)
        widgets = {}
        for key, label in fields:
            spin = QDoubleSpinBox(dialog)
            spin.setDecimals(8)
            spin.setRange(-1e9, 1e9)
            spin.setValue(float(getattr(branch, key)))
            layout.addRow(label, spin)
            widgets[key] = spin
        tap_side = None
        if transformer:
            tap_side = QComboBox(dialog)
            tap_side.addItems(['from', 'to'])
            tap_side.setCurrentText(branch.tap_side)
            layout.addRow('Tap side', tap_side)
        enabled = QCheckBox(dialog)
        enabled.setChecked(branch.in_service)
        layout.addRow('In service', enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        changes = {key: widget.value() for key, widget in widgets.items()}
        changes['in_service'] = enabled.isChecked()
        if transformer:
            changes['tap_side'] = tap_side.currentText()
        try:
            self.scene.edit_component(branch, changes, f'Edit {item.kind.lower()}')
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

    def delete_selected(self):
        item = self.selected_component()

        if item is None:
            self.show_error(
                "Select a bus or branch first."
            )
            return

        try:
            if isinstance(item, EquipmentSymbol):
                self.scene.remove_equipment(item.component)
            elif isinstance(item, BusItem):
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
        """Safely refresh Undo/Redo during normal use and Qt teardown.

        pytest-qt and parent-widget destruction may delete the underlying
        C++ QUndoStack before a pending Qt signal is delivered.
        """
        try:
            scene = getattr(self, "scene", None)
            stack = getattr(scene, "undo_stack", None)
            undo_button = getattr(self, "undo_button", None)
            redo_button = getattr(self, "redo_button", None)
            if not all(
                obj is not None and isValid(obj)
                for obj in (self, scene, stack, undo_button, redo_button)
            ):
                return
            undo_button.setEnabled(stack.canUndo())
            redo_button.setEnabled(stack.canRedo())
        except RuntimeError:
            # A C++ Qt object was deleted between validity check and use.
            return

    def undo(self):
        self.scene.undo()

    def redo(self):
        self.scene.redo()

    def fit_view(self):
        bounds = self.scene.itemsBoundingRect()
        if not bounds.isEmpty():
            self.view.fitInView(bounds.adjusted(-50, -50, 50, 50), Qt.AspectRatioMode.KeepAspectRatio)

    def handle_component_drop(self, name, x, y):
        """Place a bus at the drop point, or start/connect equipment."""
        if name == 'Bus':
            used = {b.number for b in self.scene.network.buses}
            number = next(n for n in range(1, 100000) if n not in used)
            number, ok = QInputDialog.getInt(self, 'Place Bus', 'Bus number:', number, 1, 99999)
            if not ok:
                return
            try:
                self.scene.add_bus(number, bus_type="Slack" if not any(b.bus_type == "Slack" and b.in_service for b in self.scene.network.buses) else "PQ", x=x, y=y)
            except (ValueError, TypeError) as exc:
                self.show_error(exc)
        elif name in ('Line', 'Transformer'):
            self.start_connection(name)
        else:
            # Prefer the bus beneath the drop position; otherwise ask.
            from PySide6.QtCore import QPointF
            item = self.scene.itemAt(QPointF(x, y), self.view.transform())
            while item is not None and not isinstance(item, BusItem):
                item = item.parentItem()
            bus = item.bus.number if isinstance(item, BusItem) else self._choose_bus(f'{name} bus')
            if bus is None:
                return
            try:
                if name == 'Generator':
                    self.scene.add_generator(bus)
                else:
                    self.scene.add_load(bus)
            except (ValueError, TypeError) as exc:
                self.show_error(exc)

    def start_connection(self, kind):
        if len(self.scene.bus_items) < 2:
            self.show_error('At least two active buses are required')
            return
        self.view.connection_mode = kind
        self._pending_connection_bus = None
        self.info_label.setText(f'{kind}: click the FROM bus, then the TO bus. Press Esc to cancel.')

    def cancel_connection(self):
        self.view.connection_mode = None
        self._pending_connection_bus = None
        self.info_label.setText('Drag buses to move them. Select equipment to edit or delete.')

    def handle_connection_click(self, bus):
        kind = self.view.connection_mode
        if kind is None:
            return
        if self._pending_connection_bus is None:
            self._pending_connection_bus = bus
            self.info_label.setText(f'{kind}: from Bus {bus}; click destination bus.')
            return
        first = self._pending_connection_bus
        if first == bus:
            self.show_error('Choose two different buses')
            return
        self.cancel_connection()
        try:
            if kind == 'Line':
                self.scene.add_line(first, bus)
            else:
                self.scene.add_transformer(first, bus)
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

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
        bus = self._choose_bus('Generator bus')
        if bus is None:
            return
        values = self.parameter_dialog('Generator', [
            ('Pg (MW)', 50.0), ('Qg (MVAr)', 0.0),
            ('Voltage setpoint (pu)', 1.0),
            ('Qmin (MVAr)', -100.0), ('Qmax (MVAr)', 100.0),
        ])
        if values is None:
            return
        try:
            self.scene.add_generator(bus, *values)
        except (ValueError, TypeError) as exc:
            self.show_error(exc)

    def add_load_dialog(self):
        bus = self._choose_bus('Load bus')
        if bus is None:
            return
        values = self.parameter_dialog('Load', [('Pd (MW)', 20.0), ('Qd (MVAr)', 10.0)])
        if values is None:
            return
        try:
            self.scene.add_load(bus, *values)
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
