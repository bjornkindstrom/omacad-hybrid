"""Controls for rotation of selected sketch geometry."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QGroupBox, QFormLayout, QComboBox, QLabel, QPushButton, QHBoxLayout
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.numeric_slider import add_numeric_sliders


class SketchRotationPanel(QGroupBox):
    changed = Signal()
    accepted = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__("Rotate selection", parent)
        form = QFormLayout(self)
        self.pivot = QComboBox()
        form.addRow("Pivot", self.pivot)
        self.x, self.y, self.angle = (ExprDoubleSpinBox() for _ in range(3))
        for spin in (self.x, self.y, self.angle):
            spin.setRange(-100000, 100000)
            spin.setDecimals(3)
            spin.setSingleStep(1)
        self.x.setSuffix(" mm")
        self.y.setSuffix(" mm")
        self.angle.setSuffix("°")
        self.angle.setRange(-3600, 3600)
        form.addRow("Pivot X", self.x)
        form.addRow("Pivot Y", self.y)
        form.addRow("Angle", self.angle)
        self.info = QLabel()
        self.info.setWordWrap(True)
        form.addRow(self.info)
        row = QHBoxLayout()
        self.cancel, self.ok = QPushButton("Cancel"), QPushButton("OK")
        for button in (self.cancel, self.ok):
            button.setAutoDefault(False)
            row.addWidget(button)
        self.cancel.clicked.connect(self.cancelled)
        self.ok.clicked.connect(self._accept)
        form.addRow(row)
        self.pivot.currentIndexChanged.connect(self.changed)
        for spin in (self.x, self.y, self.angle):
            spin.valueChanged.connect(self.changed)
        self._enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        self._enter.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._enter.activated.connect(self._accept)
        add_numeric_sliders(self)

    def _accept(self):
        for spin in (self.x, self.y, self.angle):
            spin.interpretText()
        if self.ok.isEnabled():
            self.accepted.emit()

    def configure(self, pivots):
        self.pivot.blockSignals(True)
        self.pivot.clear()
        for key, label in (("area", "Figure area center"), ("bounds", "Selection center"),
                           ("face", "Supporting face center"), ("origin", "Sketch origin"),
                           ("custom", "Custom point")):
            if key in pivots or key == "custom":
                self.pivot.addItem(label, key)
        self.pivot.blockSignals(False)
        self.angle.blockSignals(True)
        self.angle.setValue(0)
        self.angle.blockSignals(False)

    def set_coordinates(self, point, editable):
        for spin, value in zip((self.x, self.y), point):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.setEnabled(editable)
            spin.blockSignals(False)
