"""A small value box that floats inside the 3D view (next to what is being dimensioned).

Shows the measure as it is, you type over it (numbers, formulas or parameter names) and press Enter; Esc cancels.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.theme import style


class InlineValueBox(QFrame):
    committed = Signal()
    cancelled = Signal()

    def __init__(self, parent, label: str, value: float, lo: float = 0.0, hi: float = 50000.0,
                 suffix: str = " mm", expr: str = None):
        super().__init__(parent)
        self.edited = False          # the user typed something: stop following the cursor with the measured value
        self.setObjectName("inlineValueBox")
        style(self, """
            QFrame#inlineValueBox { background-color: rgba(30, 34, 40, 235); border: 1px solid #E26D28; border-radius: 6px; }
            QLabel { color: #D2D6DC; font-size: 11px; background: transparent; }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        self.lbl = QLabel(label)
        lay.addWidget(self.lbl)
        self.spin = ExprDoubleSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setDecimals(2)
        self.spin.setSuffix(suffix)
        self.spin.setValue(max(lo, min(hi, float(value))))
        if expr:
            self.spin.set_expression(expr)
        self.spin.setMinimumWidth(130)
        self.spin.lineEdit().textEdited.connect(lambda _t: setattr(self, "edited", True))
        self.spin.lineEdit().returnPressed.connect(self.committed)
        row = QHBoxLayout()
        row.addWidget(self.spin)
        lay.addLayout(row)
        self.adjustSize()

    def set_measure(self, label: str, value: float):
        """Follow the cursor: new kind of measure and its current value (ignored once the user has typed)."""
        self.lbl.setText(label)
        if not self.edited:
            self.spin.setValue(max(self.spin.minimum(), min(self.spin.maximum(), float(value))))
            self.spin.selectAll()

    def result(self):
        """(value, formula or None), evaluating a formula that was typed but not yet committed."""
        self.spin.interpretText()
        return self.spin.value(), self.spin.expression()

    def focus_value(self):
        self.spin.setFocus()
        self.spin.selectAll()

    def place_near(self, x: float, y: float):
        """Put the box at (x, y) plus a small offset, kept inside the parent."""
        p = self.parentWidget()
        self.adjustSize()
        bx = min(max(4, int(x) + 16), max(4, p.width() - self.width() - 4))
        by = min(max(4, int(y) + 16), max(4, p.height() - self.height() - 4))
        self.move(bx, by)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)
