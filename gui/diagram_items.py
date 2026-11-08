
"""Graphical bus and branch items for the APSA SLD."""

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
)


class BusItem(QGraphicsLineItem):
    """Draggable busbar associated with a network bus."""

    def __init__(self, bus):
        super().__init__(-25, 0, 25, 0)

        self.bus = bus
        self.branches = []
        self.voltage = None

        self.setPen(
            QPen(QColor("#2563eb"), 6)
        )

        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
            True,
        )
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            True,
        )
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,
            True,
        )

        self.setZValue(2)

        self.label = QGraphicsTextItem(
            f"Bus {bus.number} ({bus.bus_type})",
            self,
        )
        self.label.setDefaultTextColor(
            QColor("#1e293b")
        )
        self.label.setFont(QFont("Arial", 9))
        self.label.setPos(-45, -33)

        self.setToolTip(
            f"Bus {bus.number}\n"
            f"Type: {bus.bus_type}\n"
            f"Base: {bus.base_kv} kV"
        )

    def itemChange(self, change, value):
        if change == (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
        ):
            for branch in self.branches:
                branch.update_position()

        return super().itemChange(change, value)

    def set_voltage(self, vm, va):
        """Color the bus according to solved voltage."""
        self.voltage = (float(vm), float(va))

        if vm < self.bus.vmin or vm > self.bus.vmax:
            color = QColor("#dc2626")
        else:
            color = QColor("#16a34a")

        self.setPen(QPen(color, 6))
        self.label.setPlainText(
            f"Bus {self.bus.number} ({self.bus.bus_type})\n"
            f"{vm:.4f} pu, {va:.2f}°"
        )

    def clear_voltage(self):
        self.voltage = None
        self.setPen(QPen(QColor("#2563eb"), 6))
        self.label.setPlainText(
            f"Bus {self.bus.number} ({self.bus.bus_type})"
        )


class BranchItem(QGraphicsLineItem):
    """Graphical line or transformer connecting two buses."""

    def __init__(self, branch, from_item, to_item):
        super().__init__()

        self.branch = branch
        self.from_item = from_item
        self.to_item = to_item

        self.kind = (
            "Transformer"
            if hasattr(branch, "tap_ratio")
            else "Line"
        )

        color = (
            QColor("#9333ea")
            if self.kind == "Transformer"
            else QColor("#475569")
        )

        self.setPen(QPen(color, 2.5))
        self.setZValue(0)

        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            True,
        )

        self.label = QGraphicsTextItem(
            "T" if self.kind == "Transformer" else "",
            self,
        )
        self.label.setDefaultTextColor(color)
        self.label.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        from_item.branches.append(self)
        to_item.branches.append(self)

        self.update_position()

    def update_position(self):
        p1 = self.from_item.scenePos()
        p2 = self.to_item.scenePos()

        self.setLine(
            p1.x(), p1.y(), p2.x(), p2.y()
        )

        midpoint = QPointF(
            (p1.x() + p2.x()) / 2,
            (p1.y() + p2.y()) / 2,
        )

        self.label.setPos(
            midpoint.x() + 4,
            midpoint.y() - 20,
        )

    def detach(self):
        for bus_item in (self.from_item, self.to_item):
            if self in bus_item.branches:
                bus_item.branches.remove(self)
