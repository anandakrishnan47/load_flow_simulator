"""Undoable single-line diagram scene with complete APSA project JSON support."""
from copy import deepcopy
from dataclasses import asdict, fields
import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand, QUndoStack
from PySide6.QtWidgets import QGraphicsScene
from loadflow.models import Bus, Line, Transformer, Generator, Load, Shunt, ExternalGrid, Network
from gui.diagram_items import BusItem, BranchItem

COMPONENTS = {
    'buses': (Bus, 'add_bus'),
    'lines': (Line, 'add_line'),
    'transformers': (Transformer, 'add_transformer'),
    'generators': (Generator, 'add_generator'),
    'loads': (Load, 'add_load'),
    'shunts': (Shunt, 'add_shunt'),
    'external_grids': (ExternalGrid, 'add_external_grid'),
}


class SnapshotCommand(QUndoCommand):
    def __init__(self, scene, before, after, label):
        super().__init__(label)
        self.diagram_scene = scene
        self.before, self.after = deepcopy(before), deepcopy(after)

    def undo(self):
        self.diagram_scene._restore(*self.before)

    def redo(self):
        self.diagram_scene._restore(*self.after)


class DiagramScene(QGraphicsScene):
    def __init__(self, network=None, parent=None):
        super().__init__(parent)
        self.network = Network()
        self.bus_items = {}
        self.branch_items = []
        self.undo_stack = QUndoStack(self)
        self._restoring = False
        self._drag_start_positions = None
        self.setSceneRect(-100, -100, 1000, 700)
        if network is not None:
            self.set_network(network)

    def _snapshot(self):
        return deepcopy(self.network), deepcopy(self.positions())

    def _restore(self, network, positions):
        self._restoring = True
        try:
            self.network = deepcopy(network)
            self.rebuild(positions)
        finally:
            self._restoring = False

    def _push_snapshot(self, before_network, before_positions, description):
        if self._restoring:
            return
        before = (before_network, before_positions)
        after = self._snapshot()
        if before != after:
            self.undo_stack.push(SnapshotCommand(self, before, after, description))

    def record_external_edit(self, before_network, before_positions, description='Edit component'):
        self._push_snapshot(before_network, before_positions, description)

    def undo(self):
        if self.undo_stack.canUndo():
            self.undo_stack.undo()

    def redo(self):
        if self.undo_stack.canRedo():
            self.undo_stack.redo()

    def can_undo(self):
        return self.undo_stack.canUndo()

    def can_redo(self):
        return self.undo_stack.canRedo()

    def clear_history(self):
        self.undo_stack.clear()

    def set_network(self, network):
        if not isinstance(network, Network):
            raise TypeError('Expected a Network')
        self.network = deepcopy(network)
        self.rebuild()
        self.clear_history()

    def get_network(self):
        return deepcopy(self.network)

    def rebuild(self, positions=None):
        positions = positions or {}
        self.clear()
        self.bus_items, self.branch_items = {}, []
        buses = [b for b in self.network.buses if b.in_service]
        columns = max(1, math.ceil(math.sqrt(len(buses))))
        for index, bus in enumerate(buses):
            item = BusItem(bus)
            x, y = positions.get(bus.number, ((index % columns) * 150 + 80, (index // columns) * 110 + 80))
            self.addItem(item)
            item.setPos(float(x), float(y))
            self.bus_items[bus.number] = item
            item.set_equipment(
                [g for g in self.network.generators if g.bus == bus.number],
                [l for l in self.network.loads if l.bus == bus.number],
            )
        for branch in self.network.lines + self.network.transformers:
            if not branch.in_service or branch.from_bus not in self.bus_items or branch.to_bus not in self.bus_items:
                continue
            item = BranchItem(branch, self.bus_items[branch.from_bus], self.bus_items[branch.to_bus])
            self.addItem(item)
            self.branch_items.append(item)
        self._update_scene_bounds()

    def _update_scene_bounds(self):
        if not self.bus_items:
            self.setSceneRect(-100, -100, 1000, 700)
        else:
            rect = self.itemsBoundingRect()
            rect.adjust(-100, -100, 100, 100)
            self.setSceneRect(rect)

    def positions(self):
        return {n: (float(i.pos().x()), float(i.pos().y())) for n, i in self.bus_items.items()}

    def add_bus(self, number, bus_type='PQ', base_kv=132.0, x=100, y=100):
        number, base_kv, x, y = int(number), float(base_kv), float(x), float(y)
        if bus_type not in ('Slack', 'PV', 'PQ') or base_kv <= 0 or not all(map(math.isfinite, (base_kv, x, y))):
            raise ValueError('Invalid bus parameters')
        if bus_type == 'Slack' and any(b.bus_type == 'Slack' and b.in_service for b in self.network.buses):
            raise ValueError('Slack bus already exists')
        before_network, before_positions = self._snapshot()
        bus = Bus(number=number, name=f'Bus {number}', base_kv=base_kv, bus_type=bus_type)
        self.network.add_bus(bus)
        new_positions = dict(before_positions)
        new_positions[number] = (x, y)
        self.rebuild(new_positions)
        self._push_snapshot(before_network, before_positions, f'Add bus {number}')
        return bus

    def remove_bus(self, number):
        number = int(number)
        bus = next((b for b in self.network.buses if b.number == number), None)
        if bus is None:
            raise ValueError('Bus does not exist')
        if bus.bus_type == 'Slack':
            raise ValueError('Cannot remove slack bus')
        before_network, before_positions = self._snapshot()
        self.network.buses = [b for b in self.network.buses if b.number != number]
        for name in ('lines', 'transformers'):
            setattr(self.network, name, [b for b in getattr(self.network, name) if number not in (b.from_bus, b.to_bus)])
        for name in ('generators', 'loads', 'shunts', 'external_grids'):
            setattr(self.network, name, [c for c in getattr(self.network, name) if c.bus != number])
        before_positions.pop(number, None)
        # Capture the actual pre-delete positions separately for undo.
        original_positions = {**before_positions, number: self.bus_items[number].pos()}
        original_positions[number] = (float(original_positions[number].x()), float(original_positions[number].y()))
        self.rebuild(before_positions)
        self._push_snapshot(before_network, original_positions, f'Remove bus {number}')

    def add_line(self, from_bus, to_bus, r=0.02, x=0.06, b=0.0, rating_mva=100.0):
        before_network, before_positions = self._snapshot()
        branch = Line(from_bus=int(from_bus), to_bus=int(to_bus), r=float(r), x=float(x), b=float(b), rating_mva=float(rating_mva))
        self.network.add_line(branch)
        self.rebuild(before_positions)
        self._push_snapshot(before_network, before_positions, 'Add line')
        return branch

    def add_transformer(self, from_bus, to_bus, r=0.01, x=0.05, rating_mva=100.0, tap_ratio=1.0, phase_shift=0.0):
        before_network, before_positions = self._snapshot()
        branch = Transformer(from_bus=int(from_bus), to_bus=int(to_bus), r=float(r), x=float(x), rating_mva=float(rating_mva), tap_ratio=float(tap_ratio), phase_shift=float(phase_shift))
        self.network.add_transformer(branch)
        self.rebuild(before_positions)
        self._push_snapshot(before_network, before_positions, 'Add transformer')
        return branch

    def remove_branch(self, branch):
        before_network, before_positions = self._snapshot()
        for collection in (self.network.lines, self.network.transformers):
            for index, candidate in enumerate(collection):
                if candidate is branch:
                    del collection[index]
                    self.rebuild(before_positions)
                    self._push_snapshot(before_network, before_positions, 'Remove branch')
                    return
        raise ValueError('Branch not found')

    def mousePressEvent(self, event):
        if not self._restoring:
            self._drag_start_positions = self.positions()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        previous = self._drag_start_positions
        self._drag_start_positions = None
        if not self._restoring and previous is not None and previous != self.positions():
            self._push_snapshot(deepcopy(self.network), previous, 'Move bus')
            self._update_scene_bounds()

    def apply_solution(self, result):
        if not result.converged:
            raise ValueError('Cannot display a nonconverged solution')
        for number, item in self.bus_items.items():
            if number in result.bus_index:
                index = result.bus_index[number]
                item.set_voltage(float(result.vm[index]), float(result.va[index]))

    def clear_solution(self):
        for item in self.bus_items.values():
            item.clear_voltage()

    @staticmethod
    def _validate_positions(raw, valid_numbers):
        if not isinstance(raw, dict):
            raise ValueError('Invalid positions')
        positions = {}
        for key, coords in raw.items():
            try:
                number = int(key)
                if not isinstance(coords, (list, tuple)) or len(coords) != 2:
                    raise ValueError('Expected pair')
                x, y = float(coords[0]), float(coords[1])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Invalid coordinates for bus {key}') from exc
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError(f'Nonfinite coordinates for bus {key}')
            if number in valid_numbers:
                positions[number] = (x, y)
        return positions

    def save_layout(self, path):
        path = Path(path)
        data = {'version': 1, 'positions': {str(k): list(v) for k, v in self.positions().items()}}
        path.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
        return path

    def load_layout(self, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Unsupported layout format')
        positions = self._validate_positions(data.get('positions'), set(self.bus_items))
        before_network, before_positions = self._snapshot()
        for number, (x, y) in positions.items():
            self.bus_items[number].setPos(QPointF(x, y))
        self._update_scene_bounds()
        self._push_snapshot(before_network, before_positions, 'Load layout')

    def project_to_dict(self):
        network = {'base_mva': self.network.base_mva}
        for name in COMPONENTS:
            network[name] = [asdict(item) for item in getattr(self.network, name)]
        return {'format': 'APSA_LOAD_FLOW_PROJECT', 'version': 2, 'network': network,
                'diagram': {'positions': {str(k): list(v) for k, v in self.positions().items()}}}

    def save_project(self, path):
        path = Path(path)
        path.write_text(json.dumps(self.project_to_dict(), indent=2, allow_nan=False), encoding='utf-8')
        return path

    @staticmethod
    def network_from_dict(data):
        if not isinstance(data, dict):
            raise ValueError('Invalid network data')
        base_mva = float(data['base_mva'])
        if not math.isfinite(base_mva) or base_mva <= 0:
            raise ValueError('Invalid base MVA')
        network = Network(base_mva=base_mva)
        for name, (cls, method) in COMPONENTS.items():
            entries = data.get(name, [])
            if not isinstance(entries, list):
                raise ValueError(f'Invalid {name} collection')
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) - {f.name for f in fields(cls)}:
                    raise ValueError(f'Invalid {cls.__name__} fields')
                values = dict(entry)
                if cls is Load:
                    for key in ('zip_p', 'zip_q'):
                        if key in values:
                            if not isinstance(values[key], (list, tuple)) or len(values[key]) != 3:
                                raise ValueError(f'Invalid {key}')
                            values[key] = tuple(values[key])
                getattr(network, method)(cls(**values))
        return network

    def load_project(self, path):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('format') != 'APSA_LOAD_FLOW_PROJECT' or data.get('version') != 2:
            raise ValueError('Unsupported APSA project')
        network = self.network_from_dict(data['network'])
        positions = self._validate_positions(data['diagram']['positions'], {b.number for b in network.buses if b.in_service})
        self.network = network
        self.rebuild(positions)
        self.clear_history()
        return self.get_network()

    def bus_count(self):
        return len(self.bus_items)

    def branch_count(self):
        return len(self.branch_items)

    def selected_bus_items(self):
        return [item for item in self.selectedItems() if isinstance(item, BusItem)]

    def selected_branch_items(self):
        return [item for item in self.selectedItems() if isinstance(item, BranchItem)]
