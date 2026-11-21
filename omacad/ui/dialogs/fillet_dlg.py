"""Dialog for RoundEdges (Fillet and Chamfer)."""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel, QCheckBox, QPushButton, QWidget, QHBoxLayout, QToolButton
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog

_HELP = ("Click edges or a face (all its edges) in the viewport; click again to deselect. "
         "Double-click = whole loop, X = see-through, Backspace = undo last, Ctrl+Backspace = clear.")


class RoundEdgesDialog(BaseFeatureDialog):
    """Fillet / Chamfer like Fusion's: pick edges in the viewport, set the radius or the chamfer type
    (equal distance, two distances, distance and angle). The view shows the finished result live."""

    changed = Signal()
    tangent_chain_toggled = Signal(bool)
    add_set_requested = Signal()          # keep the picked edges with the current radius, pick more (Fusion's "+")
    set_size_changed = Signal(int, float)
    set_removed = Signal(int)

    CHAMFER_TYPES = (("equal", "Equal distance"), ("two", "Two distances"), ("angle", "Distance and angle"))

    def __init__(self, parent=None, kind: str = "fillet", size: float = 2.0, editing: bool = False, embedded: bool = False,
                 chamfer_type: str = "equal", size2: float = 0.0, angle: float = 45.0, flip: bool = False,
                 tangent_chain: bool = True):
        super().__init__("Fillet / Chamfer", parent, embedded)
        self._editing = editing
        form = QFormLayout()
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(["Fillet (round)", "Chamfer (bevel)"])
        self.cmb_kind.setCurrentIndex(1 if kind == "chamfer" else 0)
        form.addRow("Type:", self.cmb_kind)
        self.cmb_chamfer = QComboBox()
        for _key, label in self.CHAMFER_TYPES:
            self.cmb_chamfer.addItem(label)
        self.cmb_chamfer.setCurrentIndex(next((i for i, (k, _) in enumerate(self.CHAMFER_TYPES) if k == chamfer_type), 0))
        self.lbl_chamfer = QLabel("Chamfer type:")
        form.addRow(self.lbl_chamfer, self.cmb_chamfer)
        self.spn_size = ExprDoubleSpinBox()
        self.spn_size.setRange(-10000.0 if kind == "fillet" else 0.01, 10000.0)
        self.spn_size.setDecimals(3)
        self.spn_size.setSuffix(" mm")
        self.spn_size.setValue(size)
        self.spn_size.setToolTip("Radius (fillet) or distance (chamfer). A negative fillet cuts a concave cove into supported outside edges. Formulas and parameter names work.")
        self.lbl_size = QLabel("Radius:")
        form.addRow(self.lbl_size, self.spn_size)
        self.spn_size2 = ExprDoubleSpinBox()
        self.spn_size2.setRange(0.01, 10000.0)
        self.spn_size2.setDecimals(3)
        self.spn_size2.setSuffix(" mm")
        self.spn_size2.setValue(size2 if size2 > 0 else abs(size))
        self.spn_size2.setToolTip("Distance on the second face (the wall, for a top or bottom edge).")
        self.lbl_size2 = QLabel("Distance 2:")
        form.addRow(self.lbl_size2, self.spn_size2)
        self.spn_angle = ExprDoubleSpinBox()
        self.spn_angle.setRange(1.0, 89.0)
        self.spn_angle.setDecimals(2)
        self.spn_angle.setSuffix(" °")
        self.spn_angle.setValue(angle)
        self.spn_angle.setToolTip("Angle between the first face and the bevel (45° = equal distances).")
        self.lbl_angle = QLabel("Angle:")
        form.addRow(self.lbl_angle, self.spn_angle)
        self.chk_flip = QCheckBox("Flip (swap the two faces)")
        self.chk_flip.setChecked(flip)
        form.addRow("", self.chk_flip)
        self.chk_chain = QCheckBox("Tangent chain")
        self.chk_chain.setChecked(tangent_chain)
        self.chk_chain.setToolTip("Clicking an edge also selects the edges joined to it smoothly (as in Fusion).")
        if not editing:
            form.addRow("", self.chk_chain)
        pairs = [(self.cmb_kind, self.cmb_chamfer), (self.spn_size2, self.spn_angle)]
        if not editing:
            pairs.append((self.chk_flip, self.chk_chain))
        self.pair_form_rows(form, pairs)
        self.lbl_count = QLabel("" if editing else _HELP)
        self.lbl_count.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_count)
        # radius sets: edges kept with their own radius while more are picked (one step, one corner blend)
        self.sets_form = QFormLayout()
        self._set_spins = []
        self.btn_add_set = QPushButton("➕ New radius for more edges")
        self.btn_add_set.setToolTip("Keeps the selected edges with this radius; then pick other edges and give them "
                                    "another radius. All are rounded in one step, so corners where they meet blend "
                                    "(like the + in Fusion's Fillet). Exact on B-rep bodies.")
        self.btn_add_set.setEnabled(False)
        self.btn_add_set.clicked.connect(self.add_set_requested.emit)
        if not editing:
            self.main_layout.addLayout(self.sets_form)
        self.main_layout.addLayout(form)
        if not editing:
            self.main_layout.addWidget(self.btn_add_set)
        self.add_buttons()
        self.cmb_kind.currentIndexChanged.connect(self._kind_changed)
        self.cmb_chamfer.currentIndexChanged.connect(lambda *_: (self._sync_fields(), self.changed.emit()))
        for spin in (self.spn_size, self.spn_size2, self.spn_angle):
            spin.valueChanged.connect(lambda *_: self.changed.emit())
        self.chk_flip.toggled.connect(lambda *_: self.changed.emit())
        self.chk_chain.toggled.connect(self.tangent_chain_toggled.emit)
        self._sync_fields()
        QTimer.singleShot(0, self.spn_size, lambda: (self.spn_size.setFocus(), self.spn_size.selectAll()))

    def _sync_fields(self):
        """Show only the fields the current type uses (Fusion swaps the rows the same way)."""
        chamfer = self.kind() == "chamfer"
        ctype = self.chamfer_type()
        self.lbl_size.setText(("Distance 1:" if ctype == "two" else "Distance:") if chamfer else "Radius:")
        for w, show in ((self.lbl_chamfer, chamfer), (self.cmb_chamfer, chamfer),
                        (self.lbl_size2, chamfer and ctype == "two"), (self.spn_size2, chamfer and ctype == "two"),
                        (self.lbl_angle, chamfer and ctype == "angle"), (self.spn_angle, chamfer and ctype == "angle"),
                        (self.chk_flip, chamfer and ctype != "equal")):
            w.setVisible(show)

    def _kind_changed(self, *_):
        if self.kind() == "fillet":
            self.spn_size.setRange(-10000.0, 10000.0)
        else:
            if self.spn_size.value() < 0:
                self.spn_size.setValue(abs(self.spn_size.value()))
            self.spn_size.setRange(0.01, 10000.0)
        self._sync_fields()
        self.changed.emit()

    def kind(self) -> str:
        return "chamfer" if self.cmb_kind.currentIndex() == 1 else "fillet"

    def chamfer_type(self) -> str:
        return self.CHAMFER_TYPES[max(self.cmb_chamfer.currentIndex(), 0)][0]

    def tangent_chain(self) -> bool:
        return self.chk_chain.isChecked()

    def values(self) -> dict:
        """Everything a FilletFeature needs besides the edges."""
        return {"size": self.spn_size.value(), "kind": self.kind(), "chamfer_type": self.chamfer_type(),
                "size2": self.spn_size2.value(), "angle": self.spn_angle.value(), "flip": self.chk_flip.isChecked()}

    def set_count(self, n: int):
        self.lbl_count.setText(f"{n} edge{'s' if n != 1 else ''} selected. Click edges or a face to add or remove them."
                               if n else _HELP)
        self.btn_add_set.setEnabled(n > 0)

    def add_set_row(self, count: int, size: float):
        """A kept radius set: its own radius field and a remove button."""
        index = len(self._set_spins)
        spin = ExprDoubleSpinBox()
        spin.setRange(0.01, 10000.0)
        spin.setDecimals(3)
        spin.setSuffix(" mm")
        spin.setValue(abs(size))
        spin.setToolTip("Radius (or distance) of the edges in this set.")
        remove = QToolButton()
        remove.setText("✕")
        remove.setToolTip("Remove this set (its edges are not rounded)")
        field = QWidget()
        lay = QHBoxLayout(field)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(spin, 1)
        lay.addWidget(remove)
        self.sets_form.addRow(QLabel(f"Set {index + 1} · {count} edge{'s' if count != 1 else ''}:"), field)
        self._set_spins.append(spin)
        spin.valueChanged.connect(lambda v, s=spin: self.set_size_changed.emit(self._set_spins.index(s), float(v)))
        remove.clicked.connect(lambda *_, s=spin: self._remove_set(s))

    def _remove_set(self, spin):
        index = self._set_spins.index(spin)
        self._set_spins.pop(index)
        self.sets_form.removeRow(index)
        for i in range(self.sets_form.rowCount()):            # renumber the labels
            item = self.sets_form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            if item is not None and item.widget() is not None:
                text = item.widget().text()
                item.widget().setText(f"Set {i + 1}" + text[text.index(" ·"):])
        self.set_removed.emit(index)

    def get_expressions(self) -> dict:
        out = {}
        for key, spin in (("size", self.spn_size), ("size2", self.spn_size2), ("angle", self.spn_angle)):
            e = spin.expression()
            if e:
                out[key] = e
        return out
