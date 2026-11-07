"""Panel for Sketch Pattern (Björn #75): rows and columns, or around a centre, with a slider on every number."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton

from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.numeric_slider import add_numeric_sliders


class SketchPatternPanel(QGroupBox):
    changed = Signal()
    accepted = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__("Pattern", parent)
        form = QFormLayout(self)
        self.info = QLabel("Copies of the picked elements. OK keeps them, Esc / Cancel removes them.")
        self.info.setWordWrap(True)
        form.addRow(self.info)
        self.kind = QComboBox()
        self.kind.addItem("Rectangular", "rectangular")
        self.kind.addItem("Circular", "circular")
        self.kind.addItem("All four corners", "corners")
        form.addRow("Type", self.kind)
        self.linked = QCheckBox("Linked holes (same diameter)")
        self.linked.setChecked(True)
        self.linked.setToolTip("The original circle controls the copies’ diameter. Positions remain independent.")
        self.linked.toggled.connect(self.changed)
        form.addRow(self.linked)
        self.corner_info = QLabel("Keeps the same inset from the surrounding outline at all four corners.")
        self.corner_info.setWordWrap(True)
        form.addRow(self.corner_info)

        def spin(suffix, lo, hi, decimals=2, step=1.0):
            s = ExprDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(decimals)
            s.setSingleStep(step)
            s.setSuffix(suffix)
            s.valueChanged.connect(self.changed)
            return s
        self.count_x, self.count_y = spin("", 1, 500, 0), spin("", 1, 500, 0)
        self.spacing_x, self.spacing_y = spin(" mm", -100000, 100000), spin(" mm", -100000, 100000)
        self.count = spin("", 2, 500, 0)
        self.angle = spin("°", -360, 360, 1, 5.0)
        self.centre = QComboBox()
        self.rect_rows = [("Count X", self.count_x), ("Spacing X", self.spacing_x),
                          ("Count Y", self.count_y), ("Spacing Y", self.spacing_y)]
        self.circ_rows = [("Count", self.count), ("Angle", self.angle), ("Centre", self.centre)]
        for label, w in self.rect_rows + self.circ_rows:
            form.addRow(label, w)
        from omacad.ui.dialogs.base import BaseFeatureDialog
        BaseFeatureDialog.pair_form_rows(form, [
            (self.count_x, self.spacing_x),
            (self.count_y, self.spacing_y),
            (self.count, self.angle)])
        row = QHBoxLayout()
        self.cancel, self.ok = QPushButton("Cancel"), QPushButton("OK")
        for b in (self.cancel, self.ok):
            b.setAutoDefault(False)
            row.addWidget(b)
        self.cancel.clicked.connect(self.cancelled)
        self.ok.clicked.connect(self._accept)
        form.addRow(row)
        self._form = form
        self.kind.currentIndexChanged.connect(self._show_rows)
        self.kind.currentIndexChanged.connect(self.changed)
        self.centre.currentIndexChanged.connect(self.changed)
        enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        enter.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        enter.activated.connect(self._accept)
        add_numeric_sliders(self)
        self._show_rows()

    def _show_rows(self):
        kind = self.kind.currentData()
        self.corner_info.setVisible(kind == "corners")
        for rows, visible in ((self.rect_rows, kind == "rectangular"), (self.circ_rows, kind == "circular")):
            for _label, w in rows:
                w.setVisible(visible)
                parent = w.parentWidget()
                host = parent if getattr(parent, "field", None) is w else w
                host.setVisible(visible)
                label = self._form.labelForField(w) or self._form.labelForField(host)
                if label is not None:
                    label.setVisible(visible)

    def _accept(self):
        for s in (self.count_x, self.count_y, self.spacing_x, self.spacing_y, self.count, self.angle):
            s.interpretText()
        self.accepted.emit()

    def configure(self, spacing, centres, corners_available=False):
        """Start values: three copies along X a sensible distance apart, or six around the first centre."""
        for w in (self.count_x, self.count_y, self.spacing_x, self.spacing_y, self.count, self.angle, self.centre):
            w.blockSignals(True)
        index = self.kind.findData("corners")
        self.kind.model().item(index).setEnabled(corners_available)
        self.kind.setItemData(index, "Select elements inside a closed sketch outline.", Qt.ItemDataRole.ToolTipRole)
        if not corners_available and self.kind.currentData() == "corners":
            self.kind.setCurrentIndex(0)
        self.count_x.setValue(3)
        self.count_y.setValue(1)
        self.spacing_x.setValue(round(spacing[0], 2))
        self.spacing_y.setValue(round(spacing[1], 2))
        self.count.setValue(6)
        self.angle.setValue(360)
        self.centre.clear()
        for key, label in centres:
            self.centre.addItem(label, key)
        for w in (self.count_x, self.count_y, self.spacing_x, self.spacing_y, self.count, self.angle, self.centre):
            w.blockSignals(False)
        for w in (self.count_x, self.count_y, self.spacing_x, self.spacing_y, self.count, self.angle):
            parent = w.parentWidget()
            if hasattr(parent, "sync"):
                parent.sync(rescale=True)
