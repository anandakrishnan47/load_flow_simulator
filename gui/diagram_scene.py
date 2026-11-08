
"""Interactive single-line diagram scene for APSA."""

from copy import deepcopy
import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsScene

from loadflow.models import (
    Bus, Line, Transformer, Network,
)
from gui.diagram_items import BusItem, BranchItem


class DiagramScene(QGraphicsScene):
    def __init__(self, network=None, parent=None):
        super().__init__(parent)

        self.network = Network()
        self.bus_items = {}
        self.branch_items = []

        self.setSceneRect(-100, -100, 1000, 700)

        if network is not None:
            self.set_network(network)

    def set_network(self, network):
        """Load a copy of a network into the editor."""
        self.network = deepcopy(network)
        self.rebuild()

    def rebuild(self, positions=None):
        """Recreate the diagram from the network model."""
        self.clear()

        self.bus_items = {}
        self.branch_items = []

        active_buses = [
            bus for bus in self.network.buses
            if bus.in_service
        ]

        columns = max(
            1, math.ceil(math.sqrt(len(active_buses)))
        )

        for index, bus in enumerate(active_buses):
            item = BusItem(bus)

            if positions and bus.number in positions:
                x, y = positions[bus.number]
            else:
                x = (index % columns) * 150 + 80
                y = (index // columns) * 110 + 80

            self.addItem(item)
            item.setPos(float(x), float(y))
            self.bus_items[bus.number] = item

        for branch in (
            self.network.lines + self.network.transformers
        ):
            if not branch.in_service:
                continue

            if (
                branch.from_bus not in self.bus_items
                or branch.to_bus not in self.bus_items
            ):
                continue

            item = BranchItem(
                branch,
                self.bus_items[branch.from_bus],
                self.bus_items[branch.to_bus],
            )

            self.addItem(item)
            self.branch_items.append(item)

    def positions(self):
        return {
            number: (item.pos().x(), item.pos().y())
            for number, item in self.bus_items.items()
        }

    def add_bus(
        self,
        number,
        bus_type="PQ",
        base_kv=132.0,
        x=100,
        y=100,
    ):
        """Add a bus to the electrical and graphical model."""
        if bus_type not in ("Slack", "PV", "PQ"):
            raise ValueError("Invalid bus type")

        if bus_type == "Slack" and any(
            bus.bus_type == "Slack" and bus.in_service
            for bus in self.network.buses
        ):
            raise ValueError("A slack bus already exists")

        positions = self.positions()

        bus = Bus(
            number=int(number),
            name=f"Bus {number}",
            base_kv=float(base_kv),
            bus_type=bus_type,
        )

        self.network.add_bus(bus)

        positions[bus.number] = (float(x), float(y))
        self.rebuild(positions)

        return bus

    def add_line(
        self,
        from_bus,
        to_bus,
        r=0.02,
        x=0.06,
        b=0.0,
        rating_mva=100.0,
    ):
        positions = self.positions()

        line = Line(
            from_bus=int(from_bus),
            to_bus=int(to_bus),
            r=float(r),
            x=float(x),
            b=float(b),
            rating_mva=float(rating_mva),
        )

        self.network.add_line(line)
        self.rebuild(positions)

        return line

    def add_transformer(
        self,
        from_bus,
        to_bus,
        r=0.01,
        x=0.05,
        rating_mva=100.0,
        tap_ratio=1.0,
        phase_shift=0.0,
    ):
        positions = self.positions()

        transformer = Transformer(
            from_bus=int(from_bus),
            to_bus=int(to_bus),
            r=float(r),
            x=float(x),
            rating_mva=float(rating_mva),
            tap_ratio=float(tap_ratio),
            phase_shift=float(phase_shift),
        )

        self.network.add_transformer(transformer)
        self.rebuild(positions)

        return transformer

    def remove_bus(self, number):
        number = int(number)

        bus = next(
            (
                bus for bus in self.network.buses
                if bus.number == number
            ),
            None,
        )

        if bus is None:
            raise ValueError("Bus does not exist")

        if bus.bus_type == "Slack":
            raise ValueError(
                "Cannot remove the slack bus"
            )

        positions = self.positions()
        positions.pop(number, None)

        self.network.buses = [
            b for b in self.network.buses
            if b.number != number
        ]

        self.network.lines = [
            line for line in self.network.lines
            if number not in (
                line.from_bus, line.to_bus
            )
        ]

        self.network.transformers = [
            t for t in self.network.transformers
            if number not in (
                t.from_bus, t.to_bus
            )
        ]

        self.network.generators = [
            g for g in self.network.generators
            if g.bus != number
        ]

        self.network.loads = [
            load for load in self.network.loads
            if load.bus != number
        ]

        self.network.shunts = [
            shunt for shunt in self.network.shunts
            if shunt.bus != number
        ]

        self.network.external_grids = [
            grid for grid in self.network.external_grids
            if grid.bus != number
        ]

        self.rebuild(positions)

    
def remove_branch(self, branch):
    """Remove exactly the selected branch instance."""
    positions = self.positions()

    for collection in (
        self.network.lines,
        self.network.transformers,
    ):
        for index, candidate in enumerate(collection):
            if candidate is branch:
                del collection[index]
                self.rebuild(positions)
                return

    raise ValueError("Branch not found")

    def apply_solution(self, result):
        """Display voltages from a converged solution."""
        if not result.converged:
            raise ValueError(
                "Cannot display a nonconverged solution"
            )

        for number, item in self.bus_items.items():
            i = result.bus_index[number]
            item.set_voltage(
                result.vm[i],
                result.va[i],
            )

    def clear_solution(self):
        for item in self.bus_items.values():
            item.clear_voltage()

    def save_layout(self, path):
        """Save bus coordinates, not electrical parameters."""
        path = Path(path)

        data = {
            "version": 1,
            "positions": {
                str(number): [x, y]
                for number, (x, y) in self.positions().items()
            },
        }

        path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

    def load_layout(self, path):
        path = Path(path)

        data = json.loads(
            path.read_text(encoding="utf-8")
        )

        if data.get("version") != 1:
            raise ValueError(
                "Unsupported diagram layout version"
            )

        positions = {}

        for number, coords in data["positions"].items():
            number = int(number)

            if number not in self.bus_items:
                continue

            if (
                not isinstance(coords, list)
                or len(coords) != 2
            ):
                raise ValueError(
                    "Invalid bus position"
                )

            x, y = map(float, coords)

            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError(
                    "Nonfinite bus position"
                )

            positions[number] = (x, y)

        for number, (x, y) in positions.items():
            self.bus_items[number].setPos(x, y)
