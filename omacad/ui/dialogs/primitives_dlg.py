"""Dialogs for primitive 3D solid bodies: Box, Cylinder, Prism (hexagon), Sphere."""

from typing import Optional, Tuple, Any
from PySide6.QtWidgets import QFormLayout, QComboBox, QPushButton, QHBoxLayout, QLabel, QSpinBox
from PySide6.QtCore import Qt, Signal
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


def _add_taper(dialog, form):
    dialog.spn_taper = ExprDoubleSpinBox()
    dialog.spn_taper.setRange(-85., 85.)
    dialog.spn_taper.setDecimals(2)
    dialog.spn_taper.setSuffix("°")
    dialog.spn_taper.setToolTip("Positive narrows the top; negative widens it. The bottom dimensions stay fixed.")
    dialog.spn_taper.valueChanged.connect(lambda _: dialog.changed.emit())
    form.addRow("Taper angle:", dialog.spn_taper)


def _accept_primitive(dialog, kind):
    from omacad.model.features.primitives import BoxFeature, CylinderFeature, PrismFeature
    try:
        if kind == "prism":
            PrismFeature("validate", "Validate", *dialog.get_values()[:2], sides=dialog.sides(),
                         **dialog.get_smart_params()).build_solid()
        else:
            cls = BoxFeature if kind == "box" else CylinderFeature
            cls("validate", "Validate", *dialog.get_values()[:3 if kind == "box" else 2],
                **dialog.get_smart_params()).build_solid()
    except ValueError as exc:
        dialog.lbl_problem.setText(str(exc))
        return
    BaseFeatureDialog.accept(dialog)



def _add_placements(combo, items):
    """Short names in the list (the panel is narrow); what each one means is in its tooltip."""
    for label, key, tip in items:
        combo.addItem(label, key)
        combo.setItemData(combo.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)

class BoxDialog(BaseFeatureDialog):
    """Dialog for creating a primitive box/block."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__("Create Box", parent, embedded)
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        form = QFormLayout()

        self.spn_length = ExprDoubleSpinBox()
        self.spn_length.setRange(0.1, 10000.0)
        self.spn_length.setValue(50.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Length (X):", self.spn_length)

        self.spn_width = ExprDoubleSpinBox()
        self.spn_width.setRange(0.1, 10000.0)
        self.spn_width.setValue(50.0)
        self.spn_width.setSuffix(" mm")
        self.spn_width.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Width (Y):", self.spn_width)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 10000.0)
        self.spn_height.setValue(25.0)
        self.spn_height.setSuffix(" mm")
        self.spn_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Height (Z):", self.spn_height)

        _add_taper(self, form)

        # Placement mode
        self.cmb_placement = QComboBox()
        _add_placements(self.cmb_placement, (
            ("Bottom on origin", "bottom_center", "Centred in X and Y, from Z 0 up to the height"),
            ("Corner on origin", "corner", "X, Y and Z from 0 upwards"),
            ("Centred on origin", "center", "Centred in X, Y and Z"),
            ("On a face…", "on_face", "On a face or plane you pick in the 3D view")))
        self.cmb_placement.currentIndexChanged.connect(self._on_placement_changed)
        form.addRow("Placement:", self.cmb_placement)

        # On face button & label
        self.btn_face = QPushButton("Pick face…")
        self.btn_face.setToolTip("Click the face or plane in the 3D view where the box should start.")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setWordWrap(True)
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        self.face_row_widget = face_row
        form.addRow("Target Face:", face_row)

        # Smart Box options: Shell wall, Outer round, Inner round
        self.spn_wall = ExprDoubleSpinBox()
        self.spn_wall.setRange(0.0, 5000.0)
        self.spn_wall.setValue(0.0)
        self.spn_wall.setSingleStep(0.5)
        self.spn_wall.setSuffix(" mm")
        self.spn_wall.setToolTip("Shell wall thickness (0 = solid box; > 0 hollows the box with open top face).")
        self.spn_wall.valueChanged.connect(self._on_wall_changed)
        form.addRow("Shell Wall:", self.spn_wall)

        self.spn_outer_round = ExprDoubleSpinBox()
        self.spn_outer_round.setRange(0.0, 5000.0)
        self.spn_outer_round.setValue(0.0)
        self.spn_outer_round.setSingleStep(0.5)
        self.spn_outer_round.setSuffix(" mm")
        self.spn_outer_round.setToolTip("Round or bevel the outside corners and bottom edges (0 = sharp).")
        self.spn_outer_round.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_outer_kind = QComboBox()
        self.cmb_outer_kind.addItem("Fillet", "fillet")
        self.cmb_outer_kind.addItem("Chamfer", "chamfer")
        self.cmb_outer_kind.currentIndexChanged.connect(lambda _: self.changed.emit())
        outer_row = QHBoxLayout()
        outer_row.setContentsMargins(0, 0, 0, 0)
        outer_row.addWidget(self.spn_outer_round, 1)
        outer_row.addWidget(self.cmb_outer_kind)
        form.addRow("Outer Edge:", outer_row)

        self.spn_inner_round = ExprDoubleSpinBox()
        self.spn_inner_round.setRange(0.0, 5000.0)
        self.spn_inner_round.setValue(0.0)
        self.spn_inner_round.setSingleStep(0.5)
        self.spn_inner_round.setSuffix(" mm")
        self.spn_inner_round.setToolTip("Round or bevel the inside cavity corners and floor when Shell Wall > 0.")
        self.spn_inner_round.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_inner_kind = QComboBox()
        self.cmb_inner_kind.addItem("Fillet", "fillet")
        self.cmb_inner_kind.addItem("Chamfer", "chamfer")
        self.cmb_inner_kind.currentIndexChanged.connect(lambda _: self.changed.emit())
        inner_row = QHBoxLayout()
        inner_row.setContentsMargins(0, 0, 0, 0)
        inner_row.addWidget(self.spn_inner_round, 1)
        inner_row.addWidget(self.cmb_inner_kind)
        form.addRow("Inner Edge:", inner_row)

        self.main_layout.addLayout(form)
        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self._update_face_row_visibility()
        self._update_inner_enabled()

    def accept(self):
        _accept_primitive(self, "box")

    def _on_wall_changed(self, *_):
        self._update_inner_enabled()
        self.changed.emit()

    def _update_inner_enabled(self):
        has_wall = self.spn_wall.value() > 1e-4
        self.spn_inner_round.setEnabled(has_wall)
        self.cmb_inner_kind.setEnabled(has_wall)

    def _on_placement_changed(self):
        self._update_face_row_visibility()
        if self.cmb_placement.currentData() == "on_face" and self.plane_normal is None:
            self.pick_face_requested.emit()
        self.changed.emit()

    def _update_face_row_visibility(self):
        is_on_face = self.cmb_placement.currentData() == "on_face"
        self.btn_face.setVisible(is_on_face)
        self.lbl_face.setVisible(is_on_face)

    def set_target_plane(self, plane):
        """Called when user picks a face or plane in 3D viewport."""
        self.plane_origin = list(map(float, plane.origin))
        self.plane_normal = list(map(float, plane.normal))
        self.plane_u = list(map(float, plane.u_axis)) if hasattr(plane, "u_axis") else None
        self.plane_v = list(map(float, plane.v_axis)) if hasattr(plane, "v_axis") else None
        p_name = getattr(plane, "name", "Selected Face")
        n = self.plane_normal
        desc = "Horisontell" if abs(n[2]) > 0.8 else ("Vertikal" if abs(n[2]) < 0.2 else "Vinklad")
        self.lbl_face.setText(f"{p_name} ({desc})")
        if self.cmb_placement.currentData() != "on_face":
            idx = self.cmb_placement.findData("on_face")
            if idx >= 0:
                self.cmb_placement.blockSignals(True)
                self.cmb_placement.setCurrentIndex(idx)
                self.cmb_placement.blockSignals(False)
                self._update_face_row_visibility()
        self.changed.emit()

    def get_expressions(self) -> dict:
        out = {
            "length": self.spn_length.expression(),
            "width": self.spn_width.expression(),
            "height": self.spn_height.expression(),
            "taper_angle": self.spn_taper.expression(),
            "wall_thickness": self.spn_wall.expression(),
            "outer_round": self.spn_outer_round.expression(),
            "inner_round": self.spn_inner_round.expression(),
        }
        return {k: v for k, v in out.items() if v}

    def get_smart_params(self) -> dict:
        return {
            "taper_angle": self.spn_taper.value(),
            "wall_thickness": self.spn_wall.value(),
            "outer_round": self.spn_outer_round.value(),
            "outer_round_kind": self.cmb_outer_kind.currentData(),
            "inner_round": self.spn_inner_round.value(),
            "inner_round_kind": self.cmb_inner_kind.currentData(),
        }

    def set_smart_params(self, feat) -> None:
        self.spn_taper.setValue(getattr(feat, "taper_angle", 0.0))
        self.spn_wall.setValue(getattr(feat, "wall_thickness", 0.0))
        self.spn_outer_round.setValue(getattr(feat, "outer_round", 0.0))
        idx_o = self.cmb_outer_kind.findData(getattr(feat, "outer_round_kind", "fillet"))
        if idx_o >= 0:
            self.cmb_outer_kind.setCurrentIndex(idx_o)
        self.spn_inner_round.setValue(getattr(feat, "inner_round", 0.0))
        idx_i = self.cmb_inner_kind.findData(getattr(feat, "inner_round_kind", "fillet"))
        if idx_i >= 0:
            self.cmb_inner_kind.setCurrentIndex(idx_i)
        self._update_inner_enabled()

    def get_values(self):
        mode = self.cmb_placement.currentData()
        if mode == "center":
            center_val = True
        elif mode == "corner":
            center_val = False
        else:
            center_val = "bottom_center"

        use_plane = (mode == "on_face" and self.plane_origin is not None)
        return (
            self.spn_length.value(),
            self.spn_width.value(),
            self.spn_height.value(),
            center_val,
            self.plane_origin if use_plane else None,
            self.plane_normal if use_plane else None,
            self.plane_u if use_plane else None,
            self.plane_v if use_plane else None
        )


class CylinderDialog(BaseFeatureDialog):
    """Dialog for creating a primitive cylinder."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__("Create Cylinder", parent, embedded)
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        form = self.form = QFormLayout()

        self.spn_radius = ExprDoubleSpinBox()
        self.spn_radius.setRange(0.1, 10000.0)
        self.spn_radius.setValue(20.0)
        self.spn_radius.setSuffix(" mm")
        self.spn_radius.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Radius:", self.spn_radius)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 10000.0)
        self.spn_height.setValue(40.0)
        self.spn_height.setSuffix(" mm")
        self.spn_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Height:", self.spn_height)

        _add_taper(self, form)

        # Placement mode
        self.cmb_placement = QComboBox()
        _add_placements(self.cmb_placement, (
            ("Bottom on origin", "bottom_center", "Centred in X and Y, from Z 0 up to the height"),
            ("Centred on origin", "center", "Centred in X, Y and Z (half the height below Z 0)"),
            ("On a face…", "on_face", "On a face or plane you pick in the 3D view")))
        self.cmb_placement.currentIndexChanged.connect(self._on_placement_changed)
        form.addRow("Placement:", self.cmb_placement)

        # On face button & label
        self.btn_face = QPushButton("Pick face…")
        self.btn_face.setToolTip("Click the face or plane in the 3D view where the cylinder should start.")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setWordWrap(True)
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        self.face_row_widget = face_row
        form.addRow("Target Face:", face_row)

        # Smart Cylinder options: Shell wall, Outer round, Inner round
        self.spn_wall = ExprDoubleSpinBox()
        self.spn_wall.setRange(0.0, 5000.0)
        self.spn_wall.setValue(0.0)
        self.spn_wall.setSingleStep(0.5)
        self.spn_wall.setSuffix(" mm")
        self.spn_wall.setToolTip("Shell wall thickness (0 = solid cylinder; > 0 hollows the cylinder with open top face).")
        self.spn_wall.valueChanged.connect(self._on_wall_changed)
        form.addRow("Shell Wall:", self.spn_wall)

        self.spn_outer_round = ExprDoubleSpinBox()
        self.spn_outer_round.setRange(0.0, 5000.0)
        self.spn_outer_round.setValue(0.0)
        self.spn_outer_round.setSingleStep(0.5)
        self.spn_outer_round.setSuffix(" mm")
        self.spn_outer_round.setToolTip("Round or bevel the outside bottom/top rim (0 = sharp).")
        self.spn_outer_round.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_outer_kind = QComboBox()
        self.cmb_outer_kind.addItem("Fillet", "fillet")
        self.cmb_outer_kind.addItem("Chamfer", "chamfer")
        self.cmb_outer_kind.currentIndexChanged.connect(lambda _: self.changed.emit())
        outer_row = QHBoxLayout()
        outer_row.setContentsMargins(0, 0, 0, 0)
        outer_row.addWidget(self.spn_outer_round, 1)
        outer_row.addWidget(self.cmb_outer_kind)
        form.addRow("Outer Edge:", outer_row)

        self.spn_inner_round = ExprDoubleSpinBox()
        self.spn_inner_round.setRange(0.0, 5000.0)
        self.spn_inner_round.setValue(0.0)
        self.spn_inner_round.setSingleStep(0.5)
        self.spn_inner_round.setSuffix(" mm")
        self.spn_inner_round.setToolTip("Round or bevel the inside floor corner when Shell Wall > 0.")
        self.spn_inner_round.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_inner_kind = QComboBox()
        self.cmb_inner_kind.addItem("Fillet", "fillet")
        self.cmb_inner_kind.addItem("Chamfer", "chamfer")
        self.cmb_inner_kind.currentIndexChanged.connect(lambda _: self.changed.emit())
        inner_row = QHBoxLayout()
        inner_row.setContentsMargins(0, 0, 0, 0)
        inner_row.addWidget(self.spn_inner_round, 1)
        inner_row.addWidget(self.cmb_inner_kind)
        form.addRow("Inner Edge:", inner_row)

        self.main_layout.addLayout(form)
        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self._update_face_row_visibility()
        self._update_inner_enabled()

    def accept(self):
        _accept_primitive(self, "cylinder")

    def _on_wall_changed(self, *_):
        self._update_inner_enabled()
        self.changed.emit()

    def _update_inner_enabled(self):
        has_wall = self.spn_wall.value() > 1e-4
        self.spn_inner_round.setEnabled(has_wall)
        self.cmb_inner_kind.setEnabled(has_wall)

    def _on_placement_changed(self):
        self._update_face_row_visibility()
        if self.cmb_placement.currentData() == "on_face" and self.plane_normal is None:
            self.pick_face_requested.emit()
        self.changed.emit()

    def _update_face_row_visibility(self):
        is_on_face = self.cmb_placement.currentData() == "on_face"
        self.btn_face.setVisible(is_on_face)
        self.lbl_face.setVisible(is_on_face)

    def set_target_plane(self, plane):
        """Called when user picks a face or plane in 3D viewport."""
        self.plane_origin = list(map(float, plane.origin))
        self.plane_normal = list(map(float, plane.normal))
        self.plane_u = list(map(float, plane.u_axis)) if hasattr(plane, "u_axis") else None
        self.plane_v = list(map(float, plane.v_axis)) if hasattr(plane, "v_axis") else None
        p_name = getattr(plane, "name", "Selected Face")
        n = self.plane_normal
        desc = "Horisontell" if abs(n[2]) > 0.8 else ("Vertikal" if abs(n[2]) < 0.2 else "Vinklad")
        self.lbl_face.setText(f"{p_name} ({desc})")
        if self.cmb_placement.currentData() != "on_face":
            idx = self.cmb_placement.findData("on_face")
            if idx >= 0:
                self.cmb_placement.blockSignals(True)
                self.cmb_placement.setCurrentIndex(idx)
                self.cmb_placement.blockSignals(False)
                self._update_face_row_visibility()
        self.changed.emit()

    def get_expressions(self) -> dict:
        out = {
            "radius": self.spn_radius.expression(),
            "height": self.spn_height.expression(),
            "taper_angle": self.spn_taper.expression(),
            "wall_thickness": self.spn_wall.expression(),
            "outer_round": self.spn_outer_round.expression(),
            "inner_round": self.spn_inner_round.expression(),
        }
        return {k: v for k, v in out.items() if v}

    def get_smart_params(self) -> dict:
        return {
            "taper_angle": self.spn_taper.value(),
            "wall_thickness": self.spn_wall.value(),
            "outer_round": self.spn_outer_round.value(),
            "outer_round_kind": self.cmb_outer_kind.currentData(),
            "inner_round": self.spn_inner_round.value(),
            "inner_round_kind": self.cmb_inner_kind.currentData(),
        }

    def set_smart_params(self, feat) -> None:
        self.spn_taper.setValue(getattr(feat, "taper_angle", 0.0))
        self.spn_wall.setValue(getattr(feat, "wall_thickness", 0.0))
        self.spn_outer_round.setValue(getattr(feat, "outer_round", 0.0))
        idx_o = self.cmb_outer_kind.findData(getattr(feat, "outer_round_kind", "fillet"))
        if idx_o >= 0:
            self.cmb_outer_kind.setCurrentIndex(idx_o)
        self.spn_inner_round.setValue(getattr(feat, "inner_round", 0.0))
        idx_i = self.cmb_inner_kind.findData(getattr(feat, "inner_round_kind", "fillet"))
        if idx_i >= 0:
            self.cmb_inner_kind.setCurrentIndex(idx_i)
        self._update_inner_enabled()

    def get_values(self):
        mode = self.cmb_placement.currentData()
        if mode == "center":
            center_val = True
        else:
            center_val = "bottom_center"

        use_plane = (mode == "on_face" and self.plane_origin is not None)
        return (
            self.spn_radius.value(),
            self.spn_height.value(),
            center_val,
            self.plane_origin if use_plane else None,
            self.plane_normal if use_plane else None,
            self.plane_u if use_plane else None,
            self.plane_v if use_plane else None
        )


class PrismDialog(CylinderDialog):
    """The Cylinder panel for a regular prism (hexagon by default): `spn_radius` holds the size across flats."""

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent, embedded)
        self.setWindowTitle("Create Prism")
        self.form.labelForField(self.spn_radius).setText("Across flats:")
        self.spn_radius.setValue(20.0)
        self.spn_radius.setToolTip("Distance between two opposite flat sides (the wrench size for a hexagon).")
        self.spn_sides = QSpinBox()
        self.spn_sides.setRange(3, 64)
        self.spn_sides.setValue(6)
        self.spn_sides.setToolTip("Number of flat sides (6 = hexagon).")
        self.spn_sides.valueChanged.connect(lambda _: self.changed.emit())
        self.form.insertRow(self.form.getWidgetPosition(self.spn_radius)[0] + 1, "Sides:", self.spn_sides)
        self.btn_face.setToolTip("Klicka på en yta eller plan i 3D-vyn där prismat ska starta.")
        self.spn_wall.setToolTip("Shell wall thickness, square to the flats (0 = solid; > 0 hollows it with an open top).")

    def sides(self) -> int:
        return self.spn_sides.value()

    def accept(self):
        _accept_primitive(self, "prism")

    def get_expressions(self) -> dict:
        out = super().get_expressions()
        if "radius" in out:
            out["across_flats"] = out.pop("radius")
        return out


class ConeDialog(CylinderDialog):
    """The Cylinder panel for a cone or frustum (Björn #46): bottom radius, top radius (0 = a point), height.
    Taper and edge rounds do not apply; Shell Wall hollows it."""

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__(parent, embedded)
        self.setWindowTitle("Create Cone")
        self.form.labelForField(self.spn_radius).setText("Bottom radius:")
        self.spn_radius.setValue(20.0)
        self.spn_top = ExprDoubleSpinBox()
        self.spn_top.setRange(0.0, 10000.0)
        self.spn_top.setValue(0.0)
        self.spn_top.setSuffix(" mm")
        self.spn_top.setToolTip("Radius at the top (0 = a point; larger than the bottom = widening).")
        self.spn_top.valueChanged.connect(lambda _: self.changed.emit())
        self.form.insertRow(self.form.getWidgetPosition(self.spn_radius)[0] + 1, "Top radius:", self.spn_top)
        for w in (self.spn_taper, self.spn_outer_round, self.spn_inner_round):
            w.setValue(0.0)
            row = self.form.getWidgetPosition(w)[0]
            if row < 0:                      # the field sits in a row layout: hide that row
                for r in range(self.form.rowCount()):
                    item = self.form.itemAt(r, QFormLayout.ItemRole.FieldRole)
                    lay = item.layout() if item is not None else None
                    if lay is not None and any(lay.itemAt(i).widget() is w for i in range(lay.count())):
                        row = r
                        break
            if row >= 0:
                self.form.setRowVisible(row, False)

    def top_radius(self) -> float:
        return self.spn_top.value()

    def accept(self):
        from omacad.model.features.primitives import ConeFeature
        try:
            ConeFeature("validate", "Validate", *self.get_values()[:2], top_radius=self.top_radius(),
                        **self.get_smart_params()).build_solid()
        except ValueError as exc:
            self.lbl_problem.setText(str(exc))
            return
        BaseFeatureDialog.accept(self)

    def get_expressions(self) -> dict:
        out = super().get_expressions()
        e = self.spn_top.expression()
        if e:
            out["top_radius"] = e
        return out


class SphereDialog(BaseFeatureDialog):
    """Dialog for creating a primitive sphere."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Create Sphere", parent)
        form = QFormLayout()

        self.spn_radius = ExprDoubleSpinBox()
        self.spn_radius.setRange(0.1, 10000.0)
        self.spn_radius.setValue(25.0)
        self.spn_radius.setSuffix(" mm")
        self.spn_radius.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Radius:", self.spn_radius)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_expressions(self) -> dict:
        out = {"radius": self.spn_radius.expression()}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        return self.spn_radius.value()
