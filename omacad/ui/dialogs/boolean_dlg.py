"""Dialogs for Boolean operations: Combine (Join, Cut, Intersect) and Split Body."""

from typing import Optional
import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel, QGroupBox, QCheckBox, QDoubleSpinBox
from omacad.model.document import Document
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.theme import style


class CombineDialog(BaseFeatureDialog):
    """Dialog for boolean combine operations (Join, Cut, Intersect)."""

    changed = Signal()

    def __init__(self, doc: Document, parent=None, preselected_target_id: Optional[str] = None,
                 preselected_tool_id: Optional[str] = None, body_names_override: Optional[dict] = None):
        super().__init__("Combine Bodies", parent)
        self.doc = doc
        form = QFormLayout()

        if body_names_override:
            self.body_ids = list(body_names_override.keys())
            names = [body_names_override[bid] for bid in self.body_ids]
        else:
            self.body_ids = list(doc.bodies.keys())
            names = [doc.bodies[bid].name for bid in self.body_ids]

        self.cmb_target = QComboBox()
        self.cmb_target.addItems(names)
        if preselected_target_id and preselected_target_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(preselected_target_id))
        elif doc.selected_body_ids and doc.selected_body_ids[0] in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(doc.selected_body_ids[0]))
        self.cmb_target.currentIndexChanged.connect(self._target_chosen)
        form.addRow("Target Body:", self.cmb_target)

        self.cmb_tool = QComboBox()
        self.cmb_tool.addItems(names)
        t_idx = self.cmb_target.currentIndex()
        if preselected_tool_id and preselected_tool_id in self.body_ids:
            self.cmb_tool.setCurrentIndex(self.body_ids.index(preselected_tool_id))
        elif len(names) > 1:
            tool_idx = 1 if t_idx == 0 else 0
            self.cmb_tool.setCurrentIndex(tool_idx)
        self.cmb_tool.currentIndexChanged.connect(lambda _: self.changed.emit())
        form.addRow("Tool Body:", self.cmb_tool)

        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Join (Union)", "Cut (Difference)", "Intersect"])
        self.cmb_op.currentIndexChanged.connect(lambda _: self.changed.emit())
        form.addRow("Operation:", self.cmb_op)

        # Keep Tool Bodies checkbox (Fusion 360 style)
        from PySide6.QtWidgets import QCheckBox
        self.chk_keep_tool = QCheckBox("Keep tool bodies")
        self.chk_keep_tool.setChecked(False)
        self.chk_keep_tool.toggled.connect(lambda _: self.changed.emit())
        form.addRow("", self.chk_keep_tool)

        self.pair_form_rows(form, [
            (self.cmb_target, self.cmb_tool),
            (self.cmb_op, self.chk_keep_tool)])

        self.lbl_pick = QLabel()
        self.lbl_pick.setWordWrap(True)
        form.addRow(self.lbl_pick)

        self.main_layout.addLayout(form)
        self.add_buttons()

        # Like Fusion: with no body chosen beforehand, the first body clicked in the view is the target, then the tool.
        chosen = preselected_target_id in self.body_ids or bool(doc.selected_body_ids and doc.selected_body_ids[0] in self.body_ids)
        self._active_field = "tool" if chosen else "target"
        self._update_pick_hint()

    def _target_chosen(self, _index: int):
        self._active_field = "tool"
        self._update_pick_hint()
        self.changed.emit()

    def picking_target(self) -> bool:
        return self._active_field == "target"

    def _update_pick_hint(self):
        what = "the target body (the one that changes)" if self._active_field == "target" else "the tool body"
        self.lbl_pick.setText(f"Click {what} in the view.")

    def select_body(self, body_id: str):
        """A body clicked in the view: the target first (when none was chosen beforehand), then the tool."""
        if body_id not in self.body_ids:
            return
        idx = self.body_ids.index(body_id)
        if self._active_field == "target":
            if self.cmb_tool.currentIndex() == idx and len(self.body_ids) > 1:
                self.cmb_tool.setCurrentIndex(1 if idx == 0 else 0)
            if self.cmb_target.currentIndex() == idx:
                self._target_chosen(idx)
            else:
                self.cmb_target.setCurrentIndex(idx)       # -> _target_chosen
        elif idx != self.cmb_target.currentIndex():
            self.cmb_tool.setCurrentIndex(idx)

    def get_values(self):
        t_idx = self.cmb_target.currentIndex()
        tool_idx = self.cmb_tool.currentIndex()
        if not self.body_ids or t_idx < 0 or tool_idx < 0 or t_idx == tool_idx:
            return None, None, "join", False

        target_id = self.body_ids[t_idx]
        tool_id = self.body_ids[tool_idx]
        op_map = {0: "join", 1: "cut", 2: "intersect"}
        op = op_map.get(self.cmb_op.currentIndex(), "join")
        keep = self.chk_keep_tool.isChecked()
        return target_id, tool_id, op, keep


class SplitBodyDialog(BaseFeatureDialog):
    """Dialog to split a body using an offset (construction) plane or origin plane into two bodies."""

    changed = Signal()

    def __init__(self, doc: Document, parent=None, preselected_body_id: Optional[str] = None,
                 preselected_plane_id: Optional[str] = None, body_manifolds_override: Optional[dict] = None):
        super().__init__("Split Body", parent)
        self.doc = doc
        self._body_manifolds_override = body_manifolds_override
        form = QFormLayout()

        # Target Body
        if body_manifolds_override is not None:
            self.body_ids = list(body_manifolds_override.keys())
            body_names = [doc.bodies[bid].name if bid in doc.bodies else bid for bid in self.body_ids]
        else:
            self.body_ids = list(doc.bodies.keys())
            body_names = [doc.bodies[bid].name for bid in self.body_ids]
        self.cmb_target = QComboBox()
        self.cmb_target.addItems(body_names)
        if preselected_body_id and preselected_body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(preselected_body_id))
        elif doc.selected_body_ids and doc.selected_body_ids[0] in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(doc.selected_body_ids[0]))
        form.addRow("Target Body:", self.cmb_target)


        # Splitting Plane
        self.plane_keys = []
        plane_labels = []
        # Construction planes (offset planes) first
        for pid, cp in doc.construction_planes.items():
            self.plane_keys.append(pid)
            plane_labels.append(f"📐 {cp['name']}")
        # Origin planes
        for op in ("XY", "XZ", "YZ"):
            self.plane_keys.append(op)
            plane_labels.append(f"🌐 {op} Plane")

        self.cmb_plane = QComboBox()
        self.cmb_plane.addItems(plane_labels)
        if preselected_plane_id and preselected_plane_id in self.plane_keys:
            self.cmb_plane.setCurrentIndex(self.plane_keys.index(preselected_plane_id))
        form.addRow("Splitting Plane:", self.cmb_plane)

        self.pair_form_rows(form, [(self.cmb_target, self.cmb_plane)])

        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        form.addRow(self.lbl_status)

        self.main_layout.addLayout(form)

        # Lip joint group (#241)
        from omacad.ui.settings import get_settings
        cfg = get_settings()
        self.grp_lip = QGroupBox("Lip joint (lid / two-part print)")
        lip_form = QFormLayout(self.grp_lip)
        self.chk_lip = QCheckBox("Add lip")
        self.chk_lip.setChecked(bool(cfg.get("split_lip_enabled", False)))
        lip_form.addRow(self.chk_lip)

        self.cmb_lip_style = QComboBox()
        self.cmb_lip_style.addItem("Inner lip (step inside)", "inner")
        self.cmb_lip_style.addItem("Outer lip (step outside)", "outer")
        self.cmb_lip_style.addItem("Groove & tongue (centered)", "groove")
        idx_style = self.cmb_lip_style.findData(cfg.get("split_lip_style", "inner"))
        if idx_style >= 0:
            self.cmb_lip_style.setCurrentIndex(idx_style)
        lip_form.addRow("Type:", self.cmb_lip_style)

        self.spin_lip_height = QDoubleSpinBox()
        self.spin_lip_height.setRange(0.5, 100.0)
        self.spin_lip_height.setSingleStep(0.5)
        self.spin_lip_height.setValue(float(cfg.get("split_lip_height", 5.0)))
        self.spin_lip_height.setSuffix(" mm")
        lip_form.addRow("Height:", self.spin_lip_height)

        self.spin_lip_width = QDoubleSpinBox()
        self.spin_lip_width.setRange(0.0, 50.0)
        self.spin_lip_width.setSingleStep(0.5)
        self.spin_lip_width.setValue(float(cfg.get("split_lip_width", 0.0)))
        self.spin_lip_width.setSpecialValueText("Auto")
        self.spin_lip_width.setSuffix(" mm")
        lip_form.addRow("Width:", self.spin_lip_width)

        self.spin_lip_clearance = QDoubleSpinBox()
        self.spin_lip_clearance.setRange(0.0, 5.0)
        self.spin_lip_clearance.setSingleStep(0.05)
        self.spin_lip_clearance.setDecimals(2)
        self.spin_lip_clearance.setValue(float(cfg.get("split_lip_clearance", 0.2)))
        self.spin_lip_clearance.setSuffix(" mm")
        lip_form.addRow("Clearance:", self.spin_lip_clearance)

        self.cmb_lip_on = QComboBox()
        self.cmb_lip_on.addItems(["Half below the plane", "Half above the plane"])
        lip_form.addRow("Lip on:", self.cmb_lip_on)

        self.chk_lip_snap = QCheckBox("Snap-fit latch (detent bump)")
        self.chk_lip_snap.setChecked(bool(cfg.get("split_lip_snap", False)))
        lip_form.addRow(self.chk_lip_snap)
        self.main_layout.addWidget(self.grp_lip)

        self._sync_lip_enabled()
        self.add_buttons()

        self.cmb_target.currentIndexChanged.connect(self._update_status)
        self.cmb_plane.currentIndexChanged.connect(self._update_status)
        self.chk_lip.toggled.connect(self._on_lip_toggled)
        self.cmb_lip_style.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.spin_lip_height.valueChanged.connect(lambda _: self.changed.emit())
        self.spin_lip_width.valueChanged.connect(lambda _: self.changed.emit())
        self.spin_lip_clearance.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_lip_on.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.chk_lip_snap.toggled.connect(lambda _: self.changed.emit())
        self._update_status()

    def _sync_lip_enabled(self):
        on = self.chk_lip.isChecked()
        for w in (self.cmb_lip_style, self.spin_lip_height, self.spin_lip_width,
                  self.spin_lip_clearance, self.cmb_lip_on, self.chk_lip_snap):
            w.setEnabled(on)

    def _on_lip_toggled(self, _checked: bool):
        self._sync_lip_enabled()
        self.changed.emit()

    def _plane_normal_z(self, plane_id: str) -> float:
        if plane_id in self.doc.construction_planes:
            return float(self.doc.construction_planes[plane_id]["normal"][2])
        if plane_id in self.doc.origin_planes:
            return float(self.doc.origin_planes[plane_id].normal[2])
        return 1.0

    def select_plane(self, plane_id: str) -> None:
        """The splitting plane clicked in the view (origin plane name or construction plane id)."""
        if plane_id in self.plane_keys:
            self.cmb_plane.setCurrentIndex(self.plane_keys.index(plane_id))

    def _update_status(self):
        self.changed.emit()
        body_id, plane_id, _lip = self.get_values()
        if not body_id or not plane_id:
            self.lbl_status.setText("Select a body and a plane to split.")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return

        manifold = None
        if self._body_manifolds_override is not None and body_id in self._body_manifolds_override:
            manifold = self._body_manifolds_override[body_id]
        elif body_id in self.doc.bodies:
            manifold = self.doc.bodies[body_id].manifold

        if manifold is None:
            self.lbl_status.setText("Body not found.")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return

        origin, normal = None, None
        if plane_id in self.doc.construction_planes:
            cp = self.doc.construction_planes[plane_id]
            origin = np.array(cp["origin"], dtype=float)
            normal = np.array(cp["normal"], dtype=float)
        elif plane_id in self.doc.origin_planes:
            op = self.doc.origin_planes[plane_id]
            origin = np.array(op.origin, dtype=float)
            normal = np.array(op.normal, dtype=float)

        if origin is None or normal is None:
            self.lbl_status.setText("Plane not found.")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return

        norm = float(np.linalg.norm(normal))
        if norm < 1e-9:
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
            return
        normal = normal / norm
        d = float(np.dot(normal, origin))

        # Check cut
        p1 = manifold.trim_by_plane(normal, d)
        p2 = manifold.trim_by_plane(-normal, -d)
        if p1.is_empty() or p2.is_empty() or p1.volume() < 1e-6 or p2.volume() < 1e-6:
            self.lbl_status.setText("⚠️ Warning: Plane does not cut through the body.")
            style(self.lbl_status, "color: #E57373;", "QLabel { color: #C62828; }")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(False)
        else:
            self.lbl_status.setText(f"✓ Split produces 2 bodies ({p1.volume():.1f} mm³ + {p2.volume():.1f} mm³).")
            style(self.lbl_status, "color: #81C784;", "QLabel { color: @ok; }")
            if hasattr(self, "btn_ok"):
                self.btn_ok.setEnabled(True)

    def select_body(self, body_id: str):
        if body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(body_id))
            if hasattr(self, "update_preview"):
                self.update_preview()


    def get_values(self):
        b_idx = self.cmb_target.currentIndex()
        p_idx = self.cmb_plane.currentIndex()
        if b_idx < 0 or b_idx >= len(self.body_ids) or p_idx < 0 or p_idx >= len(self.plane_keys):
            return None, None, None
        plane_id = self.plane_keys[p_idx]
        lip = None
        if self.chk_lip.isChecked():
            above = self.cmb_lip_on.currentIndex() == 1
            nz = self._plane_normal_z(plane_id)
            lip_on = ("front" if above else "back") if nz >= 0.0 else ("back" if above else "front")
            lip = {
                "style": self.cmb_lip_style.currentData(),
                "height": float(self.spin_lip_height.value()),
                "width": float(self.spin_lip_width.value()),
                "clearance": float(self.spin_lip_clearance.value()),
                "lip_on": lip_on,
                "snap_fit": self.chk_lip_snap.isChecked(),
            }
        return self.body_ids[b_idx], plane_id, lip
