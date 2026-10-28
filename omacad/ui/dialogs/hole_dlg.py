"""Parametric Hole command settings."""
import math
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QComboBox, QCheckBox, QLabel, QPushButton, QWidget, QHBoxLayout
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.theme_icons import tool_icon


class HoleDialog(BaseFeatureDialog):
    changed = Signal()
    pick_requested = Signal()
    place_requested = Signal()

    def __init__(self, parent=None, values=None, editing=False, embedded=False):
        super().__init__("Hole", parent, embedded)
        v = values or {}
        form = QFormLayout()
        self.points = list(v.get("points", []))
        self.plane = None
        self.lbl_points = QLabel(f"{len(self.points)} point(s) selected" if self.points else "No points selected")
        self.btn_pick = QPushButton("Select face or plane")
        self.btn_pick.clicked.connect(self.pick_requested.emit)
        self._row(form, "Select placement face or plane", "📍", self.btn_pick)
        self.btn_place = QPushButton("Place hole points")
        self.btn_place.clicked.connect(self.place_requested.emit)
        self.btn_place.setEnabled(False)
        self._row(form, "Place centers", "🎯", self.btn_place)
        self._row(form, "Placed points", "🔵", self.lbl_points)
        self.cmb_type = QComboBox()
        self.cmb_type.addItem(tool_icon("🕳️", 18), "Simple", "simple")
        self.cmb_type.addItem(tool_icon("🔩", 18), "Counterbore", "counterbore")
        self.cmb_type.addItem(tool_icon("📐", 18), "Countersink", "countersink")
        self.cmb_type.setCurrentIndex(max(0, self.cmb_type.findData(v.get("hole_type", "simple"))))
        self._row(form, "Hole type", "🕳️", self.cmb_type)
        self.spn_diameter = self._spin(v.get("diameter", 6.0), 0.01, "Hole diameter")
        self._row(form, "Hole diameter", "📏", self.spn_diameter)
        self.chk_through = QCheckBox("Through all")
        self.chk_through.setChecked(bool(v.get("through", False)))
        self._row(form, "Extent", "⬇️", self.chk_through)
        self.spn_depth = self._spin(v.get("depth", 10.0), 0.01, "Hole depth")
        self._row(form, "Hole depth", "↕️", self.spn_depth)
        self.spn_cb_diameter = self._spin(v.get("cb_diameter", 12.0), 0.01, "Counterbore diameter")
        self._row(form, "Counterbore diameter", "📏", self.spn_cb_diameter)
        self.spn_cb_depth = self._spin(v.get("cb_depth", 4.0), 0.01, "Counterbore depth")
        self._row(form, "Counterbore depth", "⬇️", self.spn_cb_depth)
        self.spn_cs_diameter = self._spin(v.get("cs_diameter", 12.0), 0.01, "Countersink diameter")
        self._row(form, "Countersink diameter", "📏", self.spn_cs_diameter)
        self.spn_cs_angle = self._spin(v.get("cs_angle", 90.0), 10.0, "Countersink angle", 170.0, " °")
        self._row(form, "Countersink angle", "📐", self.spn_cs_angle)
        self.cmb_tip = QComboBox()
        self.cmb_tip.addItem(tool_icon("➖", 18), "Flat", "flat")
        self.cmb_tip.addItem(tool_icon("🔻", 18), "Angled drill point", "angle")
        self.cmb_tip.setCurrentIndex(max(0, self.cmb_tip.findData(v.get("tip", "flat"))))
        self._row(form, "Drill point", "🔻", self.cmb_tip)
        self.spn_tip_angle = self._spin(v.get("tip_angle", 118.0), 10.0, "Drill tip angle", 170.0, " °")
        self._row(form, "Tip angle", "📐", self.spn_tip_angle)
        old_angle = float(v.get("chamfer_angle", 45.0))
        legacy_depth = float(v.get("chamfer", 0.0)) / max(0.01745, math.tan(math.radians(old_angle)))
        self.spn_chamfer_depth = self._spin(v.get("chamfer_depth", legacy_depth), 0.0,
                                             "Maximum axial reach from the selected start face. Chamfer size and angle also limit its actual depth.")
        self._row(form, "Max chamfer depth", "🔻", self.spn_chamfer_depth)
        self.spn_chamfer_angle = self._spin(v.get("chamfer_angle", 45.0), 1.0, "Chamfer angle from top face", 89.0, " °")
        self._row(form, "Chamfer angle", "📐", self.spn_chamfer_angle)
        self.main_layout.addLayout(form)
        self.add_buttons()
        self.cmb_type.currentIndexChanged.connect(self._sync)
        self.chk_through.toggled.connect(self._sync)
        self.cmb_tip.currentIndexChanged.connect(self._sync)
        for w in (self.spn_diameter, self.spn_depth, self.spn_cb_diameter, self.spn_cb_depth,
                  self.spn_cs_diameter, self.spn_cs_angle, self.spn_tip_angle, self.spn_chamfer_depth,
                  self.spn_chamfer_angle):
            w.valueChanged.connect(self.changed.emit)
        self._sync()

    @staticmethod
    def _row(form, text, symbol, field):
        label = QWidget()
        layout = QHBoxLayout(label)
        layout.setContentsMargins(0, 0, 5, 0)
        layout.setSpacing(6)
        icon = QLabel()
        icon.setPixmap(tool_icon(symbol, 16).pixmap(16, 16))
        icon.setFixedSize(16, 16)
        caption = QLabel(text)
        layout.addWidget(icon)
        layout.addWidget(caption)
        layout.addStretch(1)
        form.addRow(label, field)

    @staticmethod
    def _spin(value, minimum, tooltip, maximum=10000.0, suffix=" mm"):
        w = ExprDoubleSpinBox()
        w.setRange(minimum, maximum)
        w.setDecimals(3)
        w.setSuffix(suffix)
        w.setValue(float(value))
        w.setToolTip(tooltip)
        return w

    def _sync(self, *_):
        kind = self.cmb_type.currentData()
        for w, show in ((self.spn_depth, not self.chk_through.isChecked()),
                        (self.spn_cb_diameter, kind == "counterbore"),
                        (self.spn_cb_depth, kind == "counterbore"),
                        (self.spn_cs_diameter, kind == "countersink"),
                        (self.spn_cs_angle, kind == "countersink"),
                        (self.cmb_tip, not self.chk_through.isChecked()),
                        (self.spn_tip_angle, not self.chk_through.isChecked() and self.cmb_tip.currentData() == "angle"),
                        (self.spn_chamfer_depth, kind != "countersink"),
                        (self.spn_chamfer_angle, kind != "countersink")):
            w.setVisible(show)
        self.changed.emit()

    def set_points(self, points):
        self.points = list(points)
        prefix = f"Plane: {self.plane.name}; " if self.plane is not None else ""
        self.lbl_points.setText(f"{prefix}{len(self.points)} point(s) placed" if self.points else f"{prefix}No points placed")

    def set_plane(self, plane):
        self.plane = plane
        self.btn_place.setEnabled(plane is not None)
        if plane is not None:
            self.lbl_points.setText(f"Plane: {plane.name}; {len(self.points)} point(s) selected")

    def values(self):
        return {"points": self.points, "hole_type": self.cmb_type.currentData(),
                "diameter": self.spn_diameter.value(), "depth": self.spn_depth.value(),
                "through": self.chk_through.isChecked(), "cb_diameter": self.spn_cb_diameter.value(),
                "cb_depth": self.spn_cb_depth.value(), "cs_diameter": self.spn_cs_diameter.value(),
                "cs_angle": self.spn_cs_angle.value(), "tip": self.cmb_tip.currentData(),
                "tip_angle": self.spn_tip_angle.value(), "chamfer_depth": self.spn_chamfer_depth.value(),
                "chamfer_angle": self.spn_chamfer_angle.value()}

    def get_expressions(self):
        fields = {"diameter": self.spn_diameter, "depth": self.spn_depth,
                  "cb_diameter": self.spn_cb_diameter, "cb_depth": self.spn_cb_depth,
                  "cs_diameter": self.spn_cs_diameter, "cs_angle": self.spn_cs_angle,
                  "tip_angle": self.spn_tip_angle, "chamfer_depth": self.spn_chamfer_depth,
                  "chamfer_angle": self.spn_chamfer_angle}
        return {key: field.expression() for key, field in fields.items() if field.expression()}
