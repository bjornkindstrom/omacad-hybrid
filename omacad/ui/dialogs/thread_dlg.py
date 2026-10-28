"""
Omacad - Thread & Coil Dialog
3D-Print optimized parametric thread dialog, docked in the right side panel.
"""

from typing import Optional, Any
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QCheckBox, QLabel, QHBoxLayout, QPushButton, QGroupBox, QVBoxLayout
)
from PySide6.QtCore import Qt, Signal
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


# Standard 3D-printing friendly thread presets: (Name, Dia, Pitch)
THREAD_PRESETS = [
    ("Custom", 0.0, 0.0),
    ("M6  (Pitch 1.25 mm)", 6.0, 1.25),
    ("M8  (Pitch 1.50 mm)", 8.0, 1.50),
    ("M10 (Pitch 2.00 mm)", 10.0, 2.00),
    ("M12 (Pitch 2.00 mm)", 12.0, 2.00),
    ("M14 (Pitch 2.00 mm)", 14.0, 2.00),
    ("M16 (Pitch 2.50 mm)", 16.0, 2.50),
    ("M20 (Pitch 2.50 mm)", 20.0, 2.50),
    ("M24 (Pitch 3.00 mm)", 24.0, 3.00),
    ("M30 (Pitch 3.50 mm)", 30.0, 3.50),
]


DEFAULT_LEAD_IN_TURNS = 0.3   # the short lead-in: works best for coils
LEAD_INS = (   # (label, taper on, turns the thread fades in and out over)
    ("Smooth ends", True, 0.75),
    ("Smooth ends, short", True, 0.3),
    ("None (full to the ends)", False, 0.75),
)


class ThreadDialog(BaseFeatureDialog):
    """Dialog for creating 3D-printable or CAD threads and coils."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, doc: Document, parent=None, preselected_body_id: Optional[str] = None):
        super().__init__("Create Thread / Coil", parent)
        self.doc = doc
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        self.body_ids = list(doc.bodies.keys())
        body_names = [doc.bodies[bid].name for bid in self.body_ids]

        form = QFormLayout()

        # Thread Type (Male bolt or Female nut/hole)
        self.cmb_type = QComboBox()
        self.cmb_type.addItem("Male (bolt)", False)
        self.cmb_type.addItem("Female (nut, hole)", True)
        self.cmb_type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Thread Type:", self.cmb_type)

        # Presets
        self.cmb_preset = QComboBox()
        for name, dia, p in THREAD_PRESETS:
            self.cmb_preset.addItem(name, (dia, p))
        self.cmb_preset.setCurrentIndex(3)  # default to M10
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Preset:", self.cmb_preset)

        # Diameter
        self.spn_dia = ExprDoubleSpinBox()
        self.spn_dia.setRange(1.0, 500.0)
        self.spn_dia.setValue(10.0)
        self.spn_dia.setSuffix(" mm")
        self.spn_dia.valueChanged.connect(self._on_dim_changed)
        form.addRow("Diameter (D):", self.spn_dia)

        # Pitch
        self.spn_pitch = ExprDoubleSpinBox()
        self.spn_pitch.setRange(0.2, 50.0)
        self.spn_pitch.setValue(2.0)
        self.spn_pitch.setSuffix(" mm")
        self.spn_pitch.valueChanged.connect(self._on_dim_changed)
        form.addRow("Pitch:", self.spn_pitch)

        # Length
        self.spn_length = ExprDoubleSpinBox()
        self.spn_length.setRange(0.5, 2000.0)
        self.spn_length.setValue(25.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.valueChanged.connect(lambda _: self.changed.emit())
        self.spn_length.setToolTip("At least one turn (the pitch) long.")
        form.addRow("Length:", self.spn_length)

        # Target Body / Application Mode
        self.cmb_target = QComboBox()
        self.cmb_target.addItem("New body", None)
        for bid, bname in zip(self.body_ids, body_names):
            self.cmb_target.addItem(f"Apply to: {bname}", bid)
        if preselected_body_id and preselected_body_id in self.body_ids:
            idx = self.cmb_target.findData(preselected_body_id)
            if idx >= 0:
                self.cmb_target.setCurrentIndex(idx)
        self.cmb_target.currentIndexChanged.connect(self._on_target_changed)
        form.addRow("Target:", self.cmb_target)

        # 3D Printing & Profile Group
        grp_3d = QGroupBox("Gängprofil & Optimeringar")
        grp_lay = QVBoxLayout(grp_3d)

        # Profile type selector
        prof_row = QHBoxLayout()
        prof_row.addWidget(QLabel("Profile:"))
        self.cmb_profile = QComboBox()
        for label, key, tip in (("Trapezoid 45°", "trapezoidal_45", "Prints without support"),
                                ("Round", "round", "A round coil or thread"),
                                ("ISO 60°", "iso_60", "Standard metric thread")):
            self.cmb_profile.addItem(label, key)
            self.cmb_profile.setItemData(self.cmb_profile.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        self.cmb_profile.currentIndexChanged.connect(lambda _: self.changed.emit())
        prof_row.addWidget(self.cmb_profile, 1)
        grp_lay.addLayout(prof_row)

        # Clearance row
        clr_layout = QHBoxLayout()
        clr_label = QLabel("Clearance:")
        self.spn_clearance = ExprDoubleSpinBox()
        self.spn_clearance.setRange(0.0, 2.0)
        self.spn_clearance.setSingleStep(0.05)
        self.spn_clearance.setValue(0.0)
        self.spn_clearance.setSuffix(" mm")
        self.spn_clearance.setToolTip("Set a gap between mating threads, for example for 3D printing.")
        self.spn_clearance.valueChanged.connect(lambda _: self.changed.emit())
        clr_layout.addWidget(clr_label)
        clr_layout.addWidget(self.spn_clearance)
        grp_lay.addLayout(clr_layout)

        lead_row = QHBoxLayout()
        lead_row.addWidget(QLabel("Lead-in:"))
        self.cmb_taper = QComboBox()
        for label, on, turns in LEAD_INS:
            self.cmb_taper.addItem(label, (on, turns))
        self.cmb_taper.setToolTip("Fasar in och ut gängans start och slut så bulten glider i muttern utan att skära snett. "
                                  "Short fasar på en tredjedels varv i stället för tre kvarts.")
        self.set_lead_in(True, DEFAULT_LEAD_IN_TURNS)
        self.cmb_taper.currentIndexChanged.connect(lambda _: self.changed.emit())
        lead_row.addWidget(self.cmb_taper, 1)
        grp_lay.addLayout(lead_row)

        form.addRow(grp_3d)

        # Placement Face button & label
        self.btn_face = QPushButton("Pick face…")
        self.btn_face.setToolTip("Click a face, a plane, or the outside or inside of a cylinder in the 3D view.")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setWordWrap(True)
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        form.addRow("Start Face:", face_row)

        # Where along the cylinder the thread sits (only when a cylinder was picked: its length is known)
        self.host_length = None
        self.cmb_anchor = QComboBox()
        self.cmb_anchor.addItem("Bottom", "bottom")
        self.cmb_anchor.addItem("Top", "top")
        self.cmb_anchor.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.spn_gap = ExprDoubleSpinBox()
        self.spn_gap.setRange(0.0, 2000.0)
        self.spn_gap.setValue(0.0)
        self.spn_gap.setSuffix(" mm")
        self.spn_gap.setToolTip("Free space kept between the cylinder end and the start of the thread.")
        self.spn_gap.valueChanged.connect(lambda _: self.changed.emit())
        anchor_row = QHBoxLayout()
        anchor_row.setContentsMargins(0, 0, 0, 0)
        anchor_row.addWidget(self.cmb_anchor, 1)
        anchor_row.addWidget(self.spn_gap)
        form.addRow("Place at:", anchor_row)
        self.host_diameter = None          # the picked cylinder's diameter (None: no cylinder)
        self.chk_follow = QCheckBox("Follow the cylinder")
        self.chk_follow.setToolTip("The thread keeps sitting on the cylinder when an earlier step (Offset Face ...) changes "
                                   "its diameter. The difference between the typed diameter and the cylinder's is kept.")
        self.chk_follow.toggled.connect(self._follow_toggled)
        form.addRow("", self.chk_follow)
        self._update_anchor_enabled()

        self.main_layout.addLayout(form)
        self.add_buttons()

    def _follow_toggled(self, on: bool):
        if on and self.host_diameter is not None and abs(self.spn_dia.value() - self.host_diameter) > 1e-6 \
                and not getattr(self, "_loading", False):
            self.spn_dia.setValue(self.host_diameter)       # switching it on: take the cylinder's diameter as it is now
        self.changed.emit()

    def set_host(self, diameter, follow: bool):
        """Used when editing an existing thread: the cylinder's diameter as it is now, and whether the thread follows it."""
        self.host_diameter = diameter
        self._loading = True
        try:
            self.chk_follow.setChecked(bool(follow) and diameter is not None)
        finally:
            self._loading = False
        self._update_anchor_enabled()

    def _update_anchor_enabled(self):
        known = self.host_length is not None
        self.chk_follow.setEnabled(known and self.host_diameter is not None)
        if not (known and self.host_diameter is not None):
            self.chk_follow.setChecked(False)
        for w in (self.cmb_anchor, self.spn_gap):
            w.setEnabled(known)
            w.setToolTip("Pick a cylinder (outside or inside) to choose which end the thread starts from." if not known
                         else w.toolTip())

    def set_anchor(self, anchor: str, gap: float, host_length):
        """Used when editing an existing thread."""
        self.host_length = host_length
        self.cmb_anchor.setCurrentIndex(max(0, self.cmb_anchor.findData(anchor)))
        self.spn_gap.setValue(float(gap))
        self._update_anchor_enabled()

    def select_body(self, body_id: str):
        """Allows interactive clicking in 3D viewport to update selected body."""
        idx = self.cmb_target.findData(body_id)
        if idx >= 0:
            self.cmb_target.setCurrentIndex(idx)

    def _on_type_changed(self):
        is_female = self.cmb_type.currentData()
        # If female, automatically default operation suggestion to apply on existing body if available
        if is_female and self.cmb_target.currentIndex() == 0 and len(self.body_ids) > 0:
            self.cmb_target.setCurrentIndex(1)
        self.changed.emit()

    def _on_preset_changed(self):
        data = self.cmb_preset.currentData()
        if data and data[0] > 0.0:
            self.spn_dia.blockSignals(True)
            self.spn_pitch.blockSignals(True)
            self.spn_dia.setValue(data[0])
            self.spn_pitch.setValue(data[1])
            self.spn_dia.blockSignals(False)
            self.spn_pitch.blockSignals(False)
        self.changed.emit()

    def _on_dim_changed(self):
        # Switch preset combo to Custom if values don't match
        cur_dia = self.spn_dia.value()
        cur_pitch = self.spn_pitch.value()
        self.spn_length.setMinimum(cur_pitch)      # a thread is at least one turn long (the kernel would stretch it silently)
        matched = False
        for idx in range(1, self.cmb_preset.count()):
            d, p = self.cmb_preset.itemData(idx)
            if abs(cur_dia - d) < 1e-3 and abs(cur_pitch - p) < 1e-3:
                self.cmb_preset.blockSignals(True)
                self.cmb_preset.setCurrentIndex(idx)
                self.cmb_preset.blockSignals(False)
                matched = True
                break
        if not matched:
            self.cmb_preset.blockSignals(True)
            self.cmb_preset.setCurrentIndex(0)  # Custom
            self.cmb_preset.blockSignals(False)
        self.changed.emit()

    def _on_target_changed(self):
        self.changed.emit()

    def set_plane(self, plane):
        if plane is None:
            self.host_length = None
            self.host_diameter = None
            self._update_anchor_enabled()
            self.plane_origin = None
            self.plane_normal = None
            self.plane_u = None
            self.plane_v = None
            self.lbl_face.setText("Default: XY ground plane")
            self.changed.emit()
            return

        self.host_length = None            # a plain face has no "other end"
        self.host_diameter = None
        self._update_anchor_enabled()
        self.plane_origin = list(map(float, plane.origin))
        self.plane_normal = list(map(float, plane.normal))
        self.plane_u = list(map(float, plane.u_axis)) if hasattr(plane, "u_axis") else None
        self.plane_v = list(map(float, plane.v_axis)) if hasattr(plane, "v_axis") else None
        p_name = getattr(plane, "name", "Selected Face")
        self.lbl_face.setText(f"{p_name}")
        self.changed.emit()

    def apply_cylinder_info(self, info: dict, body_id: Optional[str] = None):
        """Automatically configure thread settings from a clicked cylindrical surface (inside or outside)."""
        dia = float(info["diameter"])
        length = float(info["length"])
        is_internal = bool(info["is_internal"])

        self.spn_dia.blockSignals(True)
        self.spn_length.blockSignals(True)
        self.cmb_type.blockSignals(True)
        self.cmb_target.blockSignals(True)

        self.spn_dia.setValue(dia)
        self.spn_length.setValue(length)

        # Thread Type: Female if inside hole, Male if outside cylinder
        self.cmb_type.setCurrentIndex(1 if is_internal else 0)

        # Select target body if given
        if body_id and body_id in self.body_ids:
            idx = self.cmb_target.findData(body_id)
            if idx >= 0:
                self.cmb_target.setCurrentIndex(idx)

        # Automatically select recommended pitch for measured diameter
        # First check standard presets (e.g. M6, M8, M10, M12, M14, M16, M20, M24, M30)
        found_preset = False
        for p_idx in range(1, self.cmb_preset.count()):
            pd, pp = self.cmb_preset.itemData(p_idx)
            if abs(dia - pd) < 0.2:
                self.spn_pitch.blockSignals(True)
                self.spn_pitch.setValue(pp)
                self.spn_pitch.blockSignals(False)
                self.cmb_preset.blockSignals(True)
                self.cmb_preset.setCurrentIndex(p_idx)
                self.cmb_preset.blockSignals(False)
                found_preset = True
                break
        if not found_preset:
            # Automatic recommended pitch for 3D printing based on diameter
            if dia <= 3.5:
                rec_pitch = 0.7
            elif dia <= 5.5:
                rec_pitch = 1.0
            elif dia <= 7.0:
                rec_pitch = 1.25
            elif dia <= 9.0:
                rec_pitch = 1.5
            elif dia <= 15.0:
                rec_pitch = 2.0
            elif dia <= 22.0:
                rec_pitch = 2.5
            elif dia <= 28.0:
                rec_pitch = 3.0
            else:
                rec_pitch = 3.5
            self.spn_pitch.blockSignals(True)
            self.spn_pitch.setValue(rec_pitch)
            self.spn_pitch.blockSignals(False)

        # Plane placement along cylinder axis and bottom origin
        self.plane_origin = list(map(float, info["origin"]))
        self.plane_normal = list(map(float, info["axis"]))
        self.plane_u = list(map(float, info.get("u_axis", [1, 0, 0])))
        self.plane_v = list(map(float, info.get("v_axis", [0, 1, 0])))

        self.host_length = length
        self.host_diameter = dia
        self._update_anchor_enabled()
        self._loading = True
        try:
            self.chk_follow.setChecked(True)               # a thread on a cylinder follows it by default
        finally:
            self._loading = False
        kind_desc = "Internal hole" if is_internal else "External cylinder"
        self.lbl_face.setText(f"{kind_desc} (Ø{dia:g} mm, L={length:g} mm)")

        self.spn_dia.blockSignals(False)
        self.spn_length.blockSignals(False)
        self.cmb_type.blockSignals(False)
        self.cmb_target.blockSignals(False)

        self._on_dim_changed()
        self.changed.emit()

    def set_lead_in(self, on: bool, turns: float) -> None:
        """Selects the lead-in entry that matches a thread step's settings (the nearest length when it was edited)."""
        best = min(range(self.cmb_taper.count()),
                   key=lambda i: (self.cmb_taper.itemData(i)[0] != on, abs(self.cmb_taper.itemData(i)[1] - turns) if on else 0))
        self.cmb_taper.setCurrentIndex(best)

    def get_expressions(self) -> dict:
        out = {"diameter": self.spn_dia.expression(), "pitch": self.spn_pitch.expression(),
               "length": self.spn_length.expression(), "clearance": self.spn_clearance.expression(),
               "anchor_gap": self.spn_gap.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        is_female = bool(self.cmb_type.currentData())
        target_bid = self.cmb_target.currentData()
        profile_type = str(self.cmb_profile.currentData() or "trapezoidal_45")
        op = "cut" if (target_bid and is_female) else ("join" if target_bid else "new_body")

        return {
            "diameter": self.spn_dia.value(),
            "pitch": self.spn_pitch.value(),
            "length": self.spn_length.value(),
            "is_female": is_female,
            "clearance": self.spn_clearance.value(),
            "profile": profile_type,
            "taper_lead_in": bool(self.cmb_taper.currentData()[0]),
            "taper_turns": float(self.cmb_taper.currentData()[1]),
            "target_body_id": target_bid,
            "operation": op,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
            "anchor": str(self.cmb_anchor.currentData() or "bottom"),
            "anchor_gap": self.spn_gap.value(),
            "host_length": self.host_length,
            "follow_host": bool(self.chk_follow.isChecked() and self.chk_follow.isEnabled()),
            "host_offset": (self.spn_dia.value() - self.host_diameter) if self.host_diameter is not None else 0.0,
        }

