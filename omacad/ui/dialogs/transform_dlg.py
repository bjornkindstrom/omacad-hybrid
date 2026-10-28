"""Dialog for Move / Rotate Body feature with interactive axis dragging."""

from typing import Dict
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QPushButton, QCheckBox, QLabel
)
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class MoveBodyDialog(BaseFeatureDialog):
    changed = Signal()
    axis_changed = Signal(str)
    f2f_changed = Signal()       # direction or centring changed after the two faces were clicked

    def __init__(self, doc: Document, parent=None, preselected_body_id=None):
        super().__init__("Move / Rotate Body", parent)
        self.doc = doc
        self.active_axis = "X"
        form = QFormLayout()

        # Target body selection
        self.cmb_target = QComboBox()
        self.body_ids = []
        target_idx = 0
        for bid, b in doc.bodies.items():
            self.body_ids.append(bid)
            self.cmb_target.addItem(f"Body: {b.name}")
            if bid == preselected_body_id:
                target_idx = len(self.body_ids) - 1
        if self.body_ids:
            self.cmb_target.setCurrentIndex(target_idx)
        form.addRow("Target Body:", self.cmb_target)
        self.chk_copy_body = QCheckBox("Activate copy")
        self.chk_copy_body.setToolTip("Keep the original body and create a moved copy.")
        form.addRow("Mode:", self.chk_copy_body)

        # Translation
        self.spn_dx = ExprDoubleSpinBox()
        self.spn_dx.setRange(-10000.0, 10000.0)
        self.spn_dx.setDecimals(2)
        self.spn_dx.setSuffix(" mm")
        self.spn_dx.setValue(0.0)
        form.addRow("Move X (dx):", self.spn_dx)

        self.spn_dy = ExprDoubleSpinBox()
        self.spn_dy.setRange(-10000.0, 10000.0)
        self.spn_dy.setDecimals(2)
        self.spn_dy.setSuffix(" mm")
        self.spn_dy.setValue(0.0)
        form.addRow("Move Y (dy):", self.spn_dy)

        self.spn_dz = ExprDoubleSpinBox()
        self.spn_dz.setRange(-10000.0, 10000.0)
        self.spn_dz.setDecimals(2)
        self.spn_dz.setSuffix(" mm")
        self.spn_dz.setValue(0.0)
        form.addRow("Move Z (dz):", self.spn_dz)

        # Pivot point for rotation
        self.cmb_pivot = QComboBox()
        self.cmb_pivot.addItem("Body centre", "center")
        self.cmb_pivot.addItem("Origin (0, 0, 0)", "origin")
        self.cmb_pivot.addItem("Picked point", "point")
        self.cmb_pivot.setToolTip("Picked point: rotate about the first point picked with 'Pick points' below.")
        form.addRow("Pivot:", self.cmb_pivot)

        # Point to point: a point on the body (an edge end or a corner a rounding hides), then where it goes
        self.from_point = self.to_point = None
        self.btn_points = QPushButton("Pick points…")
        self.btn_points.setCheckable(True)
        self.btn_points.setToolTip("Click a point on the body: the end of a straight edge, or the sharp corner a rounding "
                                   "hides (move near the rounding to see it). It becomes the rotation pivot. Then click "
                                   "where it should go (a point on another body or the origin), or press Esc to keep "
                                   "just the pivot. Dx/dy/dz are added on top.")
        form.addRow("Point to point:", self.btn_points)
        self.lbl_points = QLabel()
        self.lbl_points.setWordWrap(True)
        form.addRow("", self.lbl_points)
        self._show_points()

        # Rotation
        self.spn_rx = ExprDoubleSpinBox()
        self.spn_rx.setRange(-3600.0, 3600.0)
        self.spn_rx.setDecimals(2)
        self.spn_rx.setSuffix(" °")
        self.spn_rx.setValue(0.0)
        form.addRow("Rotate X (rx):", self.spn_rx)

        self.spn_ry = ExprDoubleSpinBox()
        self.spn_ry.setRange(-3600.0, 3600.0)
        self.spn_ry.setDecimals(2)
        self.spn_ry.setSuffix(" °")
        self.spn_ry.setValue(0.0)
        form.addRow("Rotate Y (ry):", self.spn_ry)

        self.spn_rz = ExprDoubleSpinBox()
        self.spn_rz.setRange(-3600.0, 3600.0)
        self.spn_rz.setDecimals(2)
        self.spn_rz.setSuffix(" °")
        self.spn_rz.setValue(0.0)
        form.addRow("Rotate Z (rz):", self.spn_rz)

        # Lay a face flat: click a face of the body and the rotation and height below are filled in for you
        self.btn_lay = QPushButton("Lay face flat…")
        self.btn_lay.setCheckable(True)
        self.btn_lay.setToolTip("Then click the face in the 3D view that should rest on the ground (XY plane). "
                                "The rotation and height are filled in below; adjust them or press OK.")
        form.addRow("Lay on plane:", self.btn_lay)

        # Face to face: click a face of the body, then the face or plane it should go to
        self.btn_f2f = QPushButton("Pick two faces…")
        self.btn_f2f.setCheckable(True)
        self.btn_f2f.setToolTip("Click a face on the body, then click the face or plane it should move to. "
                                "The movement is filled in below; change the choices here or adjust the numbers.")
        form.addRow("Face to face:", self.btn_f2f)
        self.cmb_f2f = QComboBox()
        self.cmb_f2f.addItem("Touch", "touch")
        self.cmb_f2f.addItem("Flush", "flush")
        self.cmb_f2f.addItem("Slide", "slide")
        self.cmb_f2f.setToolTip("Touch: turn the body so the two faces meet (like parts being assembled).\n"
                                "Flush: turn it so both faces look the same way, in one plane.\n"
                                "Slide: no turning, move along the target's normal until the planes coincide.")
        form.addRow("Direction:", self.cmb_f2f)
        self.chk_f2f_centre = QCheckBox("Centre on target")
        self.chk_f2f_centre.setChecked(True)
        self.chk_f2f_centre.setToolTip("Off: the body only moves along the target's normal, sideways position stays.")
        form.addRow("", self.chk_f2f_centre)
        self.cmb_f2f.currentIndexChanged.connect(lambda *_: self.f2f_changed.emit())     # the prompt recomputes
        self.chk_f2f_centre.toggled.connect(lambda *_: self.f2f_changed.emit())

        self.main_layout.addLayout(form)
        self.add_buttons()

        for spn in (self.spn_dx, self.spn_dy, self.spn_dz, self.spn_rx, self.spn_ry, self.spn_rz):
            spn.valueChanged.connect(lambda *_: self.changed.emit())
        self.cmb_pivot.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.cmb_target.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.chk_copy_body.toggled.connect(lambda *_: self.changed.emit())

    def set_active_axis(self, axis: str):
        self.active_axis = axis
        self.axis_changed.emit(axis)

    def set_active_axis_value(self, val: float):
        if self.active_axis == "X":
            self.spn_dx.setValue(val)
        elif self.active_axis == "Y":
            self.spn_dy.setValue(val)
        elif self.active_axis == "Z":
            self.spn_dz.setValue(val)
        elif self.active_axis == "RX":
            self.spn_rx.setValue(val)
        elif self.active_axis == "RY":
            self.spn_ry.setValue(val)
        elif self.active_axis == "RZ":
            self.spn_rz.setValue(val)

    def select_body(self, body_id: str):
        if body_id in self.body_ids:
            idx = self.body_ids.index(body_id)
            self.cmb_target.setCurrentIndex(idx)

    def add_body(self, body_id: str, name: str):
        """A body made while the panel is open (a moved copy) becomes a choice too."""
        if body_id not in self.body_ids:
            self.body_ids.append(body_id)
            self.cmb_target.addItem(f"Body: {name}")

    def reset_motion(self, keep_from_point=None):
        """Back to no move (after a move was applied): numbers 0 without formulas, no target point. A from-point
        that was only the rotation pivot can stay: rotating about it left it where it was."""
        for spn in (self.spn_dx, self.spn_dy, self.spn_dz, self.spn_rx, self.spn_ry, self.spn_rz):
            spn.blockSignals(True)
            spn._expr = None
            spn.setValue(0.0)
            spn.blockSignals(False)
        self.set_points(keep_from_point, None)

    def get_values(self):
        b_idx = self.cmb_target.currentIndex()
        if b_idx < 0 or b_idx >= len(self.body_ids):
            return None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "center", {}
        bid = self.body_ids[b_idx]
        pivot = self.cmb_pivot.currentData() or "center"
        exprs = {}
        for k, spn in (("dx", self.spn_dx), ("dy", self.spn_dy), ("dz", self.spn_dz),
                       ("rx", self.spn_rx), ("ry", self.spn_ry), ("rz", self.spn_rz)):
            if spn.expression():
                exprs[k] = spn.expression()
        return (bid, self.spn_dx.value(), self.spn_dy.value(), self.spn_dz.value(),
                self.spn_rx.value(), self.spn_ry.value(), self.spn_rz.value(), pivot, exprs)

    def set_points(self, from_point=None, to_point=None):
        """The picked points ({"body", "kind", "xyz"}); a from-point makes it the rotation pivot."""
        self.from_point, self.to_point = from_point, to_point
        if from_point is not None:
            self.cmb_pivot.setCurrentIndex(self.cmb_pivot.findData("point"))
        elif self.cmb_pivot.currentData() == "point":
            self.cmb_pivot.setCurrentIndex(0)
        self._show_points()
        self.changed.emit()

    def get_points(self):
        return self.from_point, self.to_point

    def _show_points(self):
        def text(p):
            if p is None:
                return "-"
            what = {"end": "edge end", "corner": "hidden corner", "center": "circle centre", "quadrant": "circle quarter",
                    "face_center": "face centre", "top_center": "top centre", "bottom_center": "bottom centre",
                    "fixed": "origin"}.get(p.get("kind"), "point")
            return f"{what} ({p['xyz'][0]:.2f}, {p['xyz'][1]:.2f}, {p['xyz'][2]:.2f})"
        self.lbl_points.setText(f"From: {text(self.from_point)}\nTo: {text(self.to_point)}")
        self.cmb_pivot.model().item(self.cmb_pivot.findData("point")).setEnabled(self.from_point is not None)

    def get_expressions(self) -> Dict[str, str]:
        exprs = {}
        for k, spn in (("dx", self.spn_dx), ("dy", self.spn_dy), ("dz", self.spn_dz),
                       ("rx", self.spn_rx), ("ry", self.spn_ry), ("rz", self.spn_rz)):
            if spn.expression():
                exprs[k] = spn.expression()
        return exprs
