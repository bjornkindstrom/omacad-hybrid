"""Dialog for Emboss (Fusion's): the profiles are picked in the view, the rest is typed here:
Effect (Emboss / Deboss, which follows the sign of the Depth), Depth, Flip, Horizontal / Vertical distance, Rotation."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox


class EmbossDialog(BaseFeatureDialog):
    changed = Signal()
    select_text_requested = Signal()

    def __init__(self, parent=None, depth: float = 1.0, editing: bool = False, embedded: bool = True):
        super().__init__("Emboss", parent, embedded)
        form = QFormLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_info)
        self.btn_text = QPushButton("Select all text of this sketch")
        self.btn_text.setToolTip("Picks every letter (not the holes inside O, A, B ...) of the sketch you have selected.")
        self.btn_text.clicked.connect(self.select_text_requested)
        if editing:
            self.btn_text.hide()
            self.lbl_info.hide()
        else:
            self.main_layout.addWidget(self.btn_text)

        self.cmb_effect = QComboBox()
        self.cmb_effect.addItem("Emboss", "emboss")
        self.cmb_effect.addItem("Deboss", "deboss")
        self.cmb_effect.setToolTip("Emboss adds material (positive depth), Deboss removes it (negative depth).")
        form.addRow("Effect:", self.cmb_effect)

        self.spn_depth = ExprDoubleSpinBox()
        self.spn_depth.setRange(-1000.0, 1000.0)
        self.spn_depth.setDecimals(3)
        self.spn_depth.setSingleStep(0.1)
        self.spn_depth.setSuffix(" mm")
        self.spn_depth.setValue(depth)
        self.spn_depth.setToolTip("Positive embosses, negative debosses. Formulas and parameter names work.")
        form.addRow("Depth:", self.spn_depth)

        self.chk_flip = QCheckBox("Flip normal")
        self.chk_flip.setToolTip("Reverses the side of the sketch the letters grow from.")
        form.addRow("", self.chk_flip)

        self.chk_wrap = QCheckBox("Wrap around curved surface")
        self.chk_wrap.setChecked(True)
        self.chk_wrap.setToolTip("When checked, text and shapes wrap around cylindrical surfaces (even beyond the cylinder width). Uncheck for straight projection.")
        form.addRow("", self.chk_wrap)

        self.spn_dx = ExprDoubleSpinBox()
        self.spn_dx.setRange(-10000.0, 10000.0)
        self.spn_dx.setDecimals(3)
        self.spn_dx.setSuffix(" mm")
        self.spn_dx.setToolTip("Horizontal distance: moves the letters along the sketch's u axis.")
        form.addRow("Horizontal:", self.spn_dx)
        self.spn_dy = ExprDoubleSpinBox()
        self.spn_dy.setRange(-10000.0, 10000.0)
        self.spn_dy.setDecimals(3)
        self.spn_dy.setSuffix(" mm")
        form.addRow("Vertical:", self.spn_dy)
        self.spn_rot = ExprDoubleSpinBox()
        self.spn_rot.setRange(-360.0, 360.0)
        self.spn_rot.setDecimals(2)
        self.spn_rot.setSuffix(" °")
        form.addRow("Rotation:", self.spn_rot)

        self.main_layout.addLayout(form)
        self.add_buttons()
        self._sync_effect_from_depth()
        self.cmb_effect.currentIndexChanged.connect(self._effect_changed)
        self.spn_depth.valueChanged.connect(self._depth_changed)
        self.chk_flip.toggled.connect(lambda *_: self.changed.emit())
        self.chk_wrap.toggled.connect(lambda *_: self.changed.emit())
        for w in (self.spn_dx, self.spn_dy, self.spn_rot):
            w.valueChanged.connect(lambda *_: self.changed.emit())

    # The effect and the sign of the depth are one choice, as in Fusion: changing the one changes the other.
    def _sync_effect_from_depth(self):
        self.cmb_effect.blockSignals(True)
        self.cmb_effect.setCurrentIndex(0 if self.spn_depth.value() >= 0 else 1)
        self.cmb_effect.blockSignals(False)

    def _depth_changed(self, *_):
        self._sync_effect_from_depth()
        self.changed.emit()

    def _effect_changed(self, *_):
        d = abs(self.spn_depth.value()) or 1.0
        self.spn_depth.blockSignals(True)
        self.spn_depth.setValue(d if self.cmb_effect.currentData() == "emboss" else -d)
        self.spn_depth.blockSignals(False)
        self.changed.emit()

    def set_info(self, text: str) -> None:
        self.lbl_info.setText(text)

    def get_values(self) -> dict:
        return {"depth": self.spn_depth.value(), "flip": self.chk_flip.isChecked(), "dx": self.spn_dx.value(),
                "dy": self.spn_dy.value(), "rotation": self.spn_rot.value(), "wrap": self.chk_wrap.isChecked()}

    def set_values(self, feat) -> None:
        self.spn_depth.setValue(feat.depth)
        self.chk_flip.setChecked(feat.flip)
        self.chk_wrap.setChecked(getattr(feat, "wrap", True))
        self.spn_dx.setValue(feat.dx)
        self.spn_dy.setValue(feat.dy)
        self.spn_rot.setValue(feat.rotation)
        for key, spn in (("depth", self.spn_depth), ("dx", self.spn_dx), ("dy", self.spn_dy), ("rotation", self.spn_rot)):
            if feat.exprs.get(key):
                spn.set_expression(feat.exprs[key])

    def get_expressions(self) -> dict:
        out = {}
        for key, spn in (("depth", self.spn_depth), ("dx", self.spn_dx), ("dy", self.spn_dy), ("rotation", self.spn_rot)):
            if spn.expression():
                out[key] = spn.expression()
        return out
