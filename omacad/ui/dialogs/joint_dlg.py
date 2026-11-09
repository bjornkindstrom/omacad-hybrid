"""
Omacad - Smart Joint Dialog
Panel for configuring Revolute and Slider joints with min/max limits, interactive scrubbing, and animation.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QPushButton, QCheckBox, QLabel, QHBoxLayout, QSlider, QWidget
)
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class JointDialog(BaseFeatureDialog):
    changed = Signal()
    pick_requested = Signal(bool)

    def __init__(self, doc: Document, parent=None, preselected_body_id=None):
        super().__init__("Joint", parent)
        self.doc = doc
        self.origin = np.array([0.0, 0.0, 0.0], dtype=float)
        self.axis = np.array([0.0, 0.0, 1.0], dtype=float)
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(25)
        self._anim_timer.timeout.connect(self._step_animation)
        self._anim_dir = 1.0

        form = QFormLayout()

        # Moving / Target body
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
        form.addRow("Moving Body:", self.cmb_target)

        # Reference / Fixed body
        self.cmb_ref = QComboBox()
        self.cmb_ref.addItem("(Ground / Fixed)", None)
        for bid, b in doc.bodies.items():
            self.cmb_ref.addItem(f"Body: {b.name}", bid)
        form.addRow("Reference:", self.cmb_ref)

        # Joint Type
        self.cmb_type = QComboBox()
        self.cmb_type.addItem("↻ Revolute (Hinge)", "revolute")
        self.cmb_type.addItem("↔️ Slider (Linear)", "slider")
        self.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Type:", self.cmb_type)

        # Axis & Origin picking
        self.btn_pick = QPushButton("Pick edge or cylinder in 3D…")
        self.btn_pick.setCheckable(True)
        self.btn_pick.setToolTip("Click a straight edge, circular rim, or hole to align the joint axis and pivot.")
        self.btn_pick.toggled.connect(lambda on: self.pick_requested.emit(on))
        form.addRow("Align:", self.btn_pick)

        # Axis preset
        self.cmb_axis = QComboBox()
        self.cmb_axis.addItem("Inferred / Picked", "custom")
        self.cmb_axis.addItem("X Axis", "X")
        self.cmb_axis.addItem("Y Axis", "Y")
        self.cmb_axis.addItem("Z Axis", "Z")
        self.cmb_axis.currentIndexChanged.connect(self._on_axis_preset_changed)
        form.addRow("Axis:", self.cmb_axis)

        # Limits checkbox
        self.chk_limits = QCheckBox("Enable limits (Min / Max)")
        self.chk_limits.setChecked(True)
        self.chk_limits.toggled.connect(self._on_limits_toggled)
        form.addRow("Limits:", self.chk_limits)

        # Min / Max limit spinboxes
        self.spn_min = ExprDoubleSpinBox()
        self.spn_min.setRange(-3600.0, 3600.0)
        self.spn_min.setDecimals(1)
        self.spn_min.setSuffix(" °")
        self.spn_min.setValue(0.0)
        form.addRow("Min limit:", self.spn_min)

        self.spn_max = ExprDoubleSpinBox()
        self.spn_max.setRange(-3600.0, 3600.0)
        self.spn_max.setDecimals(1)
        self.spn_max.setSuffix(" °")
        self.spn_max.setValue(90.0)
        form.addRow("Max limit:", self.spn_max)

        # Quick limits buttons
        limits_bar = QHBoxLayout()
        self.btn_set_min = QPushButton("Set current as Min")
        self.btn_set_min.clicked.connect(lambda: self.spn_min.setValue(self.spn_val.value()))
        self.btn_set_max = QPushButton("Set current as Max")
        self.btn_set_max.clicked.connect(lambda: self.spn_max.setValue(self.spn_val.value()))
        limits_bar.addWidget(self.btn_set_min)
        limits_bar.addWidget(self.btn_set_max)
        limits_widget = QWidget()
        limits_widget.setLayout(limits_bar)
        form.addRow("", limits_widget)

        # Current articulation value
        self.spn_val = ExprDoubleSpinBox()
        self.spn_val.setRange(-3600.0, 3600.0)
        self.spn_val.setDecimals(1)
        self.spn_val.setSuffix(" °")
        self.spn_val.setValue(0.0)
        form.addRow("Value / Angle:", self.spn_val)

        # Interactive scrubber slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(0)
        self.slider.valueChanged.connect(self._on_slider_moved)
        form.addRow("Scrub motion:", self.slider)

        # Play / Animate button
        anim_bar = QHBoxLayout()
        self.btn_animate = QPushButton("▶️ Play Animation")
        self.btn_animate.setCheckable(True)
        self.btn_animate.toggled.connect(self._toggle_animation)
        anim_bar.addWidget(self.btn_animate)
        anim_widget = QWidget()
        anim_widget.setLayout(anim_bar)
        form.addRow("", anim_widget)

        self.pair_form_rows(form, [
            (self.cmb_target, self.cmb_ref),
            (self.cmb_type, self.cmb_axis),
            (self.spn_min, self.spn_max),
        ])

        self.main_layout.addLayout(form)
        self.add_buttons()

        self.cmb_target.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.spn_val.valueChanged.connect(self._on_spin_val_changed)
        self.spn_min.valueChanged.connect(self._update_slider_range)
        self.spn_max.valueChanged.connect(self._update_slider_range)

    def _on_limits_toggled(self, enabled: bool):
        self.spn_min.setEnabled(enabled)
        self.spn_max.setEnabled(enabled)
        self.btn_set_min.setEnabled(enabled)
        self.btn_set_max.setEnabled(enabled)
        self.changed.emit()

    def _on_type_changed(self):
        is_rev = (self.cmb_type.currentData() == "revolute")
        suffix = " °" if is_rev else " mm"
        self.spn_min.setSuffix(suffix)
        self.spn_max.setSuffix(suffix)
        self.spn_val.setSuffix(suffix)
        if not is_rev:
            self.spn_min.setRange(-10000.0, 10000.0)
            self.spn_max.setRange(-10000.0, 10000.0)
            self.spn_val.setRange(-10000.0, 10000.0)
            if self.spn_max.value() == 90.0:
                self.spn_max.setValue(50.0)
        else:
            self.spn_min.setRange(-3600.0, 3600.0)
            self.spn_max.setRange(-3600.0, 3600.0)
            self.spn_val.setRange(-3600.0, 3600.0)
        self.changed.emit()

    def _on_axis_preset_changed(self):
        mode = self.cmb_axis.currentData()
        if mode == "X":
            self.axis = np.array([1.0, 0.0, 0.0])
        elif mode == "Y":
            self.axis = np.array([0.0, 1.0, 0.0])
        elif mode == "Z":
            self.axis = np.array([0.0, 0.0, 1.0])
        self.changed.emit()

    def set_inferred(self, jtype: str, origin: np.ndarray, axis: np.ndarray):
        idx = self.cmb_type.findData(jtype)
        if idx >= 0:
            self.cmb_type.setCurrentIndex(idx)
        self.origin = np.asarray(origin, dtype=float)
        norm = np.linalg.norm(axis)
        self.axis = np.asarray(axis, dtype=float) / (norm if norm > 1e-9 else 1.0)
        self.cmb_axis.setCurrentIndex(0)  # custom
        self.btn_pick.setChecked(False)
        self.changed.emit()

    def _update_slider_range(self):
        mn, mx = self.spn_min.value(), self.spn_max.value()
        val = self.spn_val.value()
        if mx > mn:
            t = np.clip((val - mn) / (mx - mn), 0.0, 1.0)
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(t * 1000.0)))
            self.slider.blockSignals(False)
        self.changed.emit()

    def _on_slider_moved(self, slider_val: int):
        mn, mx = self.spn_min.value(), self.spn_max.value()
        if mx > mn:
            val = mn + (slider_val / 1000.0) * (mx - mn)
            self.spn_val.blockSignals(True)
            self.spn_val.setValue(round(val, 1))
            self.spn_val.blockSignals(False)
        self.changed.emit()

    def _on_spin_val_changed(self, val: float):
        self._update_slider_range()
        self.changed.emit()

    def _toggle_animation(self, on: bool):
        if on:
            self.btn_animate.setText("⏸ Pause Animation")
            self._anim_timer.start()
        else:
            self.btn_animate.setText("▶️ Play Animation")
            self._anim_timer.stop()

    def _step_animation(self):
        mn, mx = self.spn_min.value(), self.spn_max.value()
        if mx <= mn:
            return
        step = (mx - mn) * 0.02 * self._anim_dir
        val = self.spn_val.value() + step
        if val >= mx:
            val = mx
            self._anim_dir = -1.0
        elif val <= mn:
            val = mn
            self._anim_dir = 1.0
        self.spn_val.setValue(val)

    def target_body_id(self) -> str:
        idx = self.cmb_target.currentIndex()
        if 0 <= idx < len(self.body_ids):
            return self.body_ids[idx]
        return ""

    def ref_body_id(self) -> Optional[str]:
        return self.cmb_ref.currentData()

    def joint_type(self) -> str:
        return self.cmb_type.currentData() or "revolute"

    def limits(self) -> Tuple[bool, float, float]:
        return self.chk_limits.isChecked(), self.spn_min.value(), self.spn_max.value()

    def current_value(self) -> float:
        return self.spn_val.value()

    def set_current_value(self, val: float):
        self.spn_val.setValue(val)
