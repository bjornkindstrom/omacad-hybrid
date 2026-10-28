"""Tool panel for the sketch tools (Björn #76): what to do next, and a field with a slider for every number the tool
takes (the same values as the Tab fields in the view). A value set here is locked until it is cleared or the tool
changes, so several shapes of the same size can be drawn in a row; empty fields follow the mouse."""

from typing import Dict, Optional

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QLabel, QPushButton

from omacad.ui import dyn_input
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.numeric_slider import add_numeric_sliders

TITLES = {
    "LINE": "Line", "RECT": "Rectangle", "ROUNDED_RECT": "Rounded Rectangle", "CENTER_RECT": "Center Rectangle",
    "CENTER_ROUNDED_RECT": "Center Rounded Rectangle", "CIRCLE": "Circle", "SMART_CIRCLE": "Smart Circle",
    "POLYGON": "Polygon", "ARC": "3-Point Arc", "SLOT": "Slot", "TEXT": "Text", "OFFSET": "Offset", "MIRROR": "Mirror",
    "FILLET": "Fillet", "TRIM": "Trim", "MOVE": "Move", "DIMENSION": "Dimension",
}
HINTS = {
    "LINE": "Click the start, then the end. Lines chain on; right-click or Esc ends the chain.",
    "RECT": "Click one corner, then the opposite corner.",
    "ROUNDED_RECT": "Click one corner, then the opposite corner.",
    "CENTER_RECT": "Click the centre, then a corner.",
    "CENTER_ROUNDED_RECT": "Click the centre, then a corner.",
    "CIRCLE": "Click the centre, then a point on the circle.",
    "SMART_CIRCLE": "Type the diameter, Enter, then the distances to the nearest vertical and horizontal lines.",
    "POLYGON": "Click the centre, then a corner.",
    "ARC": "Click the start, then the end, then a point on the arc. It sticks where it meets a line smoothly.",
    "SLOT": "Click the first centre, then the second, then how wide.",
    "TEXT": "Click where the text goes (two clicks for Text In Box).",
    "TRIM": "Click the piece of a line, circle or arc to remove.",
    "DIMENSION": "Click a line, circle, two points or two lines, then where the dimension goes.",
    "MOVE": "Click the elements, Enter, then the base point and where it goes. Or type X / Y here.",
}
UNITS = {"Angle": "°", "Sides": ""}
RANGES = {"Angle": (-360.0, 360.0), "Sides": (3.0, 200.0), "X": (-100000.0, 100000.0), "Y": (-100000.0, 100000.0)}
DEFAULTS_NOT_LOCKS = ("Sides", "Radius")     # these set the palette's default instead of locking one shape


class SketchToolPanel(QGroupBox):
    """Fields follow the live values while drawing; editing one locks it (emits `locked`)."""

    locked = Signal(str, float)      # field name, value
    unlocked = Signal()              # Clear: every field follows the mouse again
    default_changed = Signal(str, float)

    def __init__(self, parent=None):
        super().__init__("Tool", parent)
        self.form = QFormLayout(self)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.form.addRow(self.hint)
        self.spins: Dict[str, ExprDoubleSpinBox] = {}
        self.locks: Dict[str, float] = {}
        self.tool: Optional[str] = None
        self.chk_copy: Optional[QCheckBox] = None

    def show_tool(self, tool: str, axis_names=("X", "Y")) -> None:
        """Rebuild for `tool`; hidden for tools with their own panel or nothing to show."""
        self.tool = tool
        self.locks = {}
        self.spins = {}
        self.chk_copy = None
        while self.form.rowCount() > 1:     # row 0 is the hint
            self.form.removeRow(1)
        if tool not in TITLES:
            self.hide()
            return
        self.setTitle(TITLES[tool])
        u_lbl, v_lbl = axis_names
        hint = HINTS.get(tool, "")
        if tool == "MOVE":
            hint = f"Click the elements, Enter, then the base point and where it goes. Or type {u_lbl} / {v_lbl} here."
        self.hint.setText(hint)
        label_map = {"X": u_lbl, "Y": v_lbl} if tool == "MOVE" else {}
        for name in dyn_input.FIELDS.get(tool, []):
            lbl = label_map.get(name, name)
            spin = ExprDoubleSpinBox()
            lo, hi = RANGES.get(name, (0.0, 100000.0))
            spin.setRange(lo, hi)
            spin.setDecimals(0 if name == "Sides" else 2)
            spin.setSingleStep(1.0 if name in ("Sides", "Angle") else 0.5)
            spin.setSuffix(UNITS.get(name, " mm"))
            spin.setToolTip(f"{lbl}: type or drag to lock it; empty follows the mouse." if name not in DEFAULTS_NOT_LOCKS
                            else f"{lbl} for the next shapes.")
            spin.valueChanged.connect(lambda v, n=name: self._edited(n, v))
            self.form.addRow(lbl, spin)
            self.spins[name] = spin
        if tool == "MOVE":
            self.chk_copy = QCheckBox("Copy (keep the originals)")
            self.chk_copy.setToolTip("Move a copy of the picked elements and leave the originals where they are.")
            self.form.addRow(self.chk_copy)
        if any(n not in DEFAULTS_NOT_LOCKS for n in self.spins):
            clear = QPushButton("Follow the mouse")
            clear.setToolTip("Clear the typed values: every field follows the mouse again.")
            clear.setAutoDefault(False)
            clear.clicked.connect(self.clear_locks)
            self.form.addRow(clear)
        add_numeric_sliders(self)
        self.show()

    def _edited(self, name: str, value: float) -> None:
        if name in DEFAULTS_NOT_LOCKS:
            self.default_changed.emit(name, value)
            return
        self.locks[name] = value
        self._mark(name, True)
        self.locked.emit(name, value)

    def _mark(self, name: str, on: bool) -> None:
        spin = self.spins.get(name)
        if spin is not None:
            font = spin.font()
            font.setBold(on)
            spin.setFont(font)

    def clear_locks(self) -> None:
        for name in list(self.locks):
            self._mark(name, False)
        self.locks = {}
        self.unlocked.emit()

    def set_hint(self, text: str) -> None:
        if self.hint.text() != text:
            self.hint.setText(text)

    def set_values(self, values: Dict[str, float]) -> None:
        """Show live (or default) values in the fields that are not locked, without emitting anything."""
        for name, v in values.items():
            spin = self.spins.get(name)
            if spin is not None and name not in self.locks and not spin.hasFocus():
                with QSignalBlocker(spin):
                    spin.setValue(v)
                parent = spin.parentWidget()
                if hasattr(parent, "sync"):
                    parent.sync()

    def lock_from_typing(self, name: str, value: float) -> None:
        """A value typed in the view's Tab field: show it here as locked too."""
        spin = self.spins.get(name)
        if spin is None or name in DEFAULTS_NOT_LOCKS:
            return
        self.locks[name] = value
        with QSignalBlocker(spin):
            spin.setValue(value)
        self._mark(name, True)
