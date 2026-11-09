"""Graphics for buses, lines, transformers, generators and loads."""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QBrush, QFont, QPainter, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsTextItem


class EquipmentSymbol(QGraphicsItem):
    def __init__(self, kind, component, parent=None):
        super().__init__(parent)
        self.kind, self.component = kind, component
        self.setZValue(3)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setToolTip(f'{kind} at bus {component.bus}')

    def boundingRect(self):
        return QRectF(-18, -18, 36, 36)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.kind == 'Generator':
            painter.setPen(QPen(QColor('#059669'), 2))
            painter.setBrush(QBrush(QColor('#ecfdf5')))
            painter.drawEllipse(QRectF(-14, -14, 28, 28))
            painter.drawText(QRectF(-14, -14, 28, 28), Qt.AlignmentFlag.AlignCenter, 'G')
        else:
            painter.setPen(QPen(QColor('#ea580c'), 2))
            painter.setBrush(QBrush(QColor('#fff7ed')))
            painter.drawPolygon(QPolygonF([QPointF(0, 14), QPointF(-13, -11), QPointF(13, -11)]))


class BusItem(QGraphicsLineItem):
    def __init__(self, bus):
        super().__init__(-25, 0, 25, 0)
        self.bus, self.branches, self.voltage = bus, [], None
        self.equipment_symbols = []
        self._color = QColor('#2563eb')
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(2)
        self.label = QGraphicsTextItem('', self)
        self.label.setDefaultTextColor(QColor('#1e293b'))
        self.label.setFont(QFont('Arial', 9))
        self.label.setPos(-45, -43)
        self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.clear_voltage()

    def _pen(self):
        selected = self.isSelected()
        self.setPen(QPen(QColor('#f59e0b') if selected else self._color, 8 if selected else 6))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for branch in list(self.branches):
                branch.update_position()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._pen()
        return super().itemChange(change, value)

    def set_voltage(self, vm, va):
        self.voltage = (float(vm), float(va))
        self._color = QColor('#16a34a') if self.bus.vmin <= vm <= self.bus.vmax else QColor('#dc2626')
        self.label.setPlainText(f'Bus {self.bus.number} ({self.bus.bus_type})\n{vm:.4f} pu, {va:.2f}°')
        self._pen()

    def clear_voltage(self):
        self.voltage = None
        self._color = QColor('#2563eb')
        self.label.setPlainText(f'Bus {self.bus.number} ({self.bus.bus_type})')
        self.setToolTip(f'Bus {self.bus.number}\nType: {self.bus.bus_type}\nBase: {self.bus.base_kv} kV')
        self._pen()

    def set_equipment(self, generators=None, loads=None):
        for symbol in self.equipment_symbols:
            symbol.setParentItem(None)
            if symbol.scene() is not None:
                symbol.scene().removeItem(symbol)
        self.equipment_symbols.clear()
        components = [('Generator', g) for g in (generators or []) if g.in_service]
        components += [('Load', l) for l in (loads or []) if l.in_service]
        for i, (kind, component) in enumerate(components):
            symbol = EquipmentSymbol(kind, component, self)
            symbol.setPos((i - (len(components) - 1) / 2) * 43, 55)
            self.equipment_symbols.append(symbol)


class BranchItem(QGraphicsLineItem):
    def __init__(self, branch, from_item, to_item):
        super().__init__()
        self.branch, self.from_item, self.to_item = branch, from_item, to_item
        self.kind = 'Transformer' if hasattr(branch, 'tap_ratio') else 'Line'
        self._color = QColor('#9333ea') if self.kind == 'Transformer' else QColor('#475569')
        self.setZValue(0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.label = QGraphicsTextItem('T' if self.kind == 'Transformer' else '', self)
        self.label.setDefaultTextColor(self._color)
        self.label.setFont(QFont('Arial', 10, QFont.Weight.Bold))
        self.label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setToolTip(f'{self.kind}: {branch.from_bus} → {branch.to_bus}\nR={branch.r}, X={branch.x}')
        self._pen()
        from_item.branches.append(self)
        to_item.branches.append(self)
        self.update_position()

    def _pen(self):
        self.setPen(QPen(QColor('#f59e0b') if self.isSelected() else self._color, 4 if self.isSelected() else 2.5))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._pen()
        return super().itemChange(change, value)

    def update_position(self):
        p1, p2 = self.from_item.scenePos(), self.to_item.scenePos()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
        self.label.setPos((p1.x() + p2.x()) / 2 + 4, (p1.y() + p2.y()) / 2 - 20)

    def detach(self):
        for bus in (self.from_item, self.to_item):
            if self in bus.branches:
                bus.branches.remove(self)
