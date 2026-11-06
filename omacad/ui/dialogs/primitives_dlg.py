"""Dialogs for primitive 3D solid bodies: Box, Cylinder, Prism (hexagon), Sphere."""

from typing import Optional, Tuple, Any
from PySide6.QtWidgets import QFormLayout, QComboBox, QPushButton, QHBoxLayout, QLabel, QSpinBox, QCheckBox
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

        self.pair_form_rows(form, [      # two fields per row to save vertical space
            (self.spn_length, self.spn_width),
            (self.spn_height, self.spn_taper),
            (self.cmb_placement, self.spn_wall)])
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

        if type(self) is CylinderDialog:
            self.pair_form_rows(form, [
                (self.spn_radius, self.spn_height),
                (self.spn_taper, self.spn_wall)])
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
        self.pair_form_rows(self.form, [
            (self.spn_radius, self.spn_sides),
            (self.spn_height, self.spn_taper),
            (self.cmb_placement, self.spn_wall)])

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
        self.pair_form_rows(self.form, [
            (self.spn_radius, self.spn_top),
            (self.spn_height, self.spn_wall)])

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


class BoxInRowDialog(BaseFeatureDialog):
    """Dialog for creating boxes in a row with fillets/chamfer, honeycomb, slide-over lids, and object grouping (Björn #151)."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__("Box in a Row", parent, embedded)
        self.plane_origin = None
        self.plane_normal = None
        self.plane_u = None
        self.plane_v = None

        form = QFormLayout()

        # Row configuration
        self.spn_count = QSpinBox()
        self.spn_count.setRange(1, 50)
        self.spn_count.setValue(2)
        self.spn_count.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Boxes count:", self.spn_count)

        self.spn_spacing = ExprDoubleSpinBox()
        self.spn_spacing.setRange(0.0, 1000.0)
        self.spn_spacing.setValue(0.0)
        self.spn_spacing.setSuffix(" mm")
        self.spn_spacing.setToolTip("Distance between adjacent boxes (0 = side by side).")
        self.spn_spacing.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Spacing:", self.spn_spacing)

        # Box dimensions
        self.spn_length = ExprDoubleSpinBox()
        self.spn_length.setRange(1.0, 10000.0)
        self.spn_length.setValue(60.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Length (X):", self.spn_length)

        self.spn_width = ExprDoubleSpinBox()
        self.spn_width.setRange(1.0, 10000.0)
        self.spn_width.setValue(40.0)
        self.spn_width.setSuffix(" mm")
        self.spn_width.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Width (Y):", self.spn_width)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(1.0, 10000.0)
        self.spn_height.setValue(30.0)
        self.spn_height.setSuffix(" mm")
        self.spn_height.setToolTip("Inner clear height (Z) from inside box floor to underside of lid.")
        self.spn_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Height (Z):", self.spn_height)

        self.spn_wall = ExprDoubleSpinBox()
        self.spn_wall.setRange(0.2, 500.0)
        self.spn_wall.setValue(2.0)
        self.spn_wall.setSuffix(" mm")
        self.spn_wall.setToolTip("Shell wall thickness.")
        self.spn_wall.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Wall thickness:", self.spn_wall)

        self.spn_bottom = ExprDoubleSpinBox()
        self.spn_bottom.setRange(0.2, 500.0)
        self.spn_bottom.setValue(2.0)
        self.spn_bottom.setSuffix(" mm")
        self.spn_bottom.setToolTip("Bottom floor thickness.")
        self.spn_bottom.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Bottom thickness:", self.spn_bottom)

        # Outer edge
        self.spn_outer_round = ExprDoubleSpinBox()
        self.spn_outer_round.setRange(0.0, 500.0)
        self.spn_outer_round.setValue(2.0)
        self.spn_outer_round.setSuffix(" mm")
        self.spn_outer_round.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_outer_kind = QComboBox()
        self.cmb_outer_kind.addItem("Fillet", "fillet")
        self.cmb_outer_kind.addItem("Chamfer", "chamfer")
        self.cmb_outer_kind.currentIndexChanged.connect(lambda _: self.changed.emit())
        r_out = QHBoxLayout()
        r_out.setContentsMargins(0, 0, 0, 0)
        r_out.addWidget(self.spn_outer_round, 1)
        r_out.addWidget(self.cmb_outer_kind)
        form.addRow("Outer corners:", r_out)

        # Inner edge
        self.spn_inner_round = ExprDoubleSpinBox()
        self.spn_inner_round.setRange(0.0, 500.0)
        self.spn_inner_round.setValue(1.0)
        self.spn_inner_round.setSuffix(" mm")
        self.spn_inner_round.valueChanged.connect(lambda _: self.changed.emit())
        self.cmb_inner_kind = QComboBox()
        self.cmb_inner_kind.addItem("Fillet", "fillet")
        self.cmb_inner_kind.addItem("Chamfer", "chamfer")
        self.cmb_inner_kind.currentIndexChanged.connect(lambda _: self.changed.emit())
        r_in = QHBoxLayout()
        r_in.setContentsMargins(0, 0, 0, 0)
        r_in.addWidget(self.spn_inner_round, 1)
        r_in.addWidget(self.cmb_inner_kind)
        form.addRow("Inner corners:", r_in)

        # Honeycomb floor
        self.chk_honeycomb = QCheckBox("Cut honeycomb into floor, walls and lid")
        self.chk_honeycomb.setChecked(False)
        self.chk_honeycomb.toggled.connect(lambda _: self.changed.emit())
        form.addRow("Honeycomb:", self.chk_honeycomb)

        self.spn_hc_size = ExprDoubleSpinBox()
        self.spn_hc_size.setRange(1.0, 100.0)
        self.spn_hc_size.setValue(5.0)
        self.spn_hc_size.setSuffix(" mm")
        self.spn_hc_size.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  Cell size:", self.spn_hc_size)

        self.spn_hc_wall = ExprDoubleSpinBox()
        self.spn_hc_wall.setRange(0.4, 20.0)
        self.spn_hc_wall.setValue(1.2)
        self.spn_hc_wall.setSuffix(" mm")
        self.spn_hc_wall.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  Grid wall:", self.spn_hc_wall)

        # Slide-over lid
        self.chk_lid = QCheckBox("Create slide lid(s) in groove")
        self.chk_lid.setChecked(True)
        self.chk_lid.toggled.connect(lambda _: self.changed.emit())
        form.addRow("Lids:", self.chk_lid)

        self.spn_lip_height = ExprDoubleSpinBox()
        self.spn_lip_height.setRange(1.0, 500.0)
        self.spn_lip_height.setValue(2.2)
        self.spn_lip_height.setSuffix(" mm")
        self.spn_lip_height.setToolTip("Distance from the top rim down to the sliding groove shelf.")
        self.spn_lip_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  Groove height:", self.spn_lip_height)

        self.spn_lip_step = ExprDoubleSpinBox()
        self.spn_lip_step.setRange(0.2, 50.0)
        self.spn_lip_step.setValue(1.0)
        self.spn_lip_step.setSuffix(" mm")
        self.spn_lip_step.setToolTip("Depth of the sliding groove into the box walls.")
        self.spn_lip_step.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  Groove depth:", self.spn_lip_step)

        self.spn_clearance = ExprDoubleSpinBox()
        self.spn_clearance.setRange(0.0, 5.0)
        self.spn_clearance.setSingleStep(0.1)
        self.spn_clearance.setValue(0.2)
        self.spn_clearance.setSuffix(" mm")
        self.spn_clearance.setToolTip("3D printer clearance gap for smooth sliding.")
        self.spn_clearance.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  3D print clearance:", self.spn_clearance)

        self.spn_slot_length = ExprDoubleSpinBox()
        self.spn_slot_length.setRange(0.0, 500.0)
        self.spn_slot_length.setSpecialValueText("Auto")
        self.spn_slot_length.setSuffix(" mm")
        self.spn_slot_length.setToolTip("Length of the finger slot in the lid (across the box). Auto = default.")
        self.spn_slot_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  Slot length:", self.spn_slot_length)

        self.spn_slot_width = ExprDoubleSpinBox()
        self.spn_slot_width.setRange(0.0, 100.0)
        self.spn_slot_width.setSpecialValueText("Auto")
        self.spn_slot_width.setSuffix(" mm")
        self.spn_slot_width.setToolTip("Width of the finger slot in the lid. Auto = default.")
        self.spn_slot_width.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("  Slot width:", self.spn_slot_width)

        # Placement
        self.cmb_placement = QComboBox()
        _add_placements(self.cmb_placement, (
            ("Bottom on origin", "bottom_center", "Centred in X and Y, from Z 0 up to the height"),
            ("Corner on origin", "corner", "X, Y and Z from 0 upwards"),
            ("Centred on origin", "center", "Centred in X, Y and Z"),
            ("On a face…", "on_face", "On a face or plane you pick in the 3D view")))
        self.cmb_placement.currentIndexChanged.connect(self._on_placement_changed)
        form.addRow("Placement:", self.cmb_placement)

        self.btn_face = QPushButton("Pick face…")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        self.lbl_face = QLabel("Default: XY ground plane")
        self.lbl_face.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        face_row = QHBoxLayout()
        face_row.setContentsMargins(0, 0, 0, 0)
        face_row.addWidget(self.btn_face)
        face_row.addWidget(self.lbl_face, 1)
        self.face_row_widget = face_row
        form.addRow("Target Face:", face_row)

        self.pair_form_rows(form, [      # two fields per row to save vertical space
            (self.spn_count, self.spn_spacing), (self.spn_length, self.spn_width),
            (self.spn_wall, self.spn_bottom), (self.spn_hc_size, self.spn_hc_wall),
            (self.spn_lip_height, self.spn_lip_step), (self.spn_slot_length, self.spn_slot_width)])
        self.main_layout.addLayout(form)
        self.lbl_problem = QLabel()
        self.lbl_problem.setStyleSheet("color: #e06c75; font-size: 11px;")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self._update_face_row_visibility()

    def _on_placement_changed(self):
        self._update_face_row_visibility()
        self.changed.emit()

    def _update_face_row_visibility(self):
        is_face = self.cmb_placement.currentData() == "on_face"
        for i in range(self.face_row_widget.count()):
            w = self.face_row_widget.itemAt(i).widget()
            if w:
                w.setVisible(is_face)

    def set_target_plane(self, plane):
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

    def get_params(self) -> dict:
        return {
            "count": self.spn_count.value(),
            "spacing": self.spn_spacing.value(),
            "length": self.spn_length.value(),
            "width": self.spn_width.value(),
            "height": self.spn_height.value(),
            "wall_thickness": self.spn_wall.value(),
            "bottom_thickness": self.spn_bottom.value(),
            "outer_round": self.spn_outer_round.value(),
            "outer_round_kind": self.cmb_outer_kind.currentData(),
            "inner_round": self.spn_inner_round.value(),
            "inner_round_kind": self.cmb_inner_kind.currentData(),
            "honeycomb": self.chk_honeycomb.isChecked(),
            "honeycomb_size": self.spn_hc_size.value(),
            "honeycomb_wall": self.spn_hc_wall.value(),
            "has_lid": self.chk_lid.isChecked(),
            "lip_height": self.spn_lip_height.value(),
            "lip_step": self.spn_lip_step.value(),
            "clearance": self.spn_clearance.value(),
            "snap_size": 0.6,  # no snap detent any more (#162); only feeds the automatic slot size
            "tab_size": 0.6,
            "slot_length": self.spn_slot_length.value(),
            "slot_width": self.spn_slot_width.value(),
            "center": self.cmb_placement.currentData(),
            "plane_origin": self.plane_origin if self.cmb_placement.currentData() == "on_face" else None,
            "plane_normal": self.plane_normal if self.cmb_placement.currentData() == "on_face" else None,
            "plane_u": self.plane_u if self.cmb_placement.currentData() == "on_face" else None,
            "plane_v": self.plane_v if self.cmb_placement.currentData() == "on_face" else None,
        }

    def set_params(self, params: dict):
        if "count" in params:
            self.spn_count.setValue(int(params["count"]))
        if "spacing" in params:
            self.spn_spacing.setValue(float(params["spacing"]))
        if "length" in params:
            self.spn_length.setValue(float(params["length"]))
        if "width" in params:
            self.spn_width.setValue(float(params["width"]))
        if "height" in params:
            self.spn_height.setValue(float(params["height"]))
        if "wall_thickness" in params:
            self.spn_wall.setValue(float(params["wall_thickness"]))
        if "bottom_thickness" in params:
            self.spn_bottom.setValue(float(params["bottom_thickness"]))
        if "outer_round" in params:
            self.spn_outer_round.setValue(float(params["outer_round"]))
        if "outer_round_kind" in params:
            idx = self.cmb_outer_kind.findData(params["outer_round_kind"])
            if idx >= 0:
                self.cmb_outer_kind.setCurrentIndex(idx)
        if "inner_round" in params:
            self.spn_inner_round.setValue(float(params["inner_round"]))
        if "inner_round_kind" in params:
            idx = self.cmb_inner_kind.findData(params["inner_round_kind"])
            if idx >= 0:
                self.cmb_inner_kind.setCurrentIndex(idx)
        if "honeycomb" in params:
            self.chk_honeycomb.setChecked(bool(params["honeycomb"]))
        if "honeycomb_size" in params:
            self.spn_hc_size.setValue(float(params["honeycomb_size"]))
        if "honeycomb_wall" in params:
            self.spn_hc_wall.setValue(float(params["honeycomb_wall"]))
        if "has_lid" in params:
            self.chk_lid.setChecked(bool(params["has_lid"]))
        if "lip_height" in params:
            self.spn_lip_height.setValue(float(params["lip_height"]))
        if "lip_step" in params:
            self.spn_lip_step.setValue(float(params["lip_step"]))
        if "clearance" in params:
            self.spn_clearance.setValue(float(params["clearance"]))
        if "slot_length" in params:
            self.spn_slot_length.setValue(float(params["slot_length"]))
        if "slot_width" in params:
            self.spn_slot_width.setValue(float(params["slot_width"]))
        if "center" in params:
            idx = self.cmb_placement.findData(params["center"])
            if idx >= 0:
                self.cmb_placement.setCurrentIndex(idx)


class StarBracketsDialog(BaseFeatureDialog):
    """Dialog for creating parametric 3D-printable star brackets and foot supports (Björn)."""

    changed = Signal()

    def __init__(self, parent=None, embedded: bool = False):
        super().__init__("Star Brackets", parent, embedded)
        form = QFormLayout()

        self.chk_assembled = QCheckBox("Show assembled star")
        self.chk_assembled.setToolTip("Show the full assembled star (10 tubes + 10 brackets + 2 feet). Off: 3D-printable parts layout.")
        self.chk_assembled.setChecked(False)
        self.chk_assembled.toggled.connect(lambda _: self.changed.emit())
        form.addRow("View mode:", self.chk_assembled)

        self.spn_tube_length = ExprDoubleSpinBox()
        self.spn_tube_length.setRange(20.0, 3000.0)
        self.spn_tube_length.setValue(250.0)
        self.spn_tube_length.setSuffix(" mm")
        self.spn_tube_length.setToolTip("Length of each square aluminum tube.")
        self.spn_tube_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Tube length:", self.spn_tube_length)

        self.spn_tube_size = ExprDoubleSpinBox()
        self.spn_tube_size.setRange(2.0, 100.0)
        self.spn_tube_size.setValue(10.0)
        self.spn_tube_size.setSuffix(" mm")
        self.spn_tube_size.setToolTip("Square aluminum tube nominal width and height.")
        self.spn_tube_size.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Tube size:", self.spn_tube_size)

        self.spn_clearance = ExprDoubleSpinBox()
        self.spn_clearance.setRange(0.0, 5.0)
        self.spn_clearance.setSingleStep(0.05)
        self.spn_clearance.setValue(0.25)
        self.spn_clearance.setSuffix(" mm")
        self.spn_clearance.setToolTip("Fit tolerance for 3D printer (inner socket size = tube + clearance).")
        self.spn_clearance.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Clearance:", self.spn_clearance)

        self.spn_wall = ExprDoubleSpinBox()
        self.spn_wall.setRange(0.8, 20.0)
        self.spn_wall.setValue(2.5)
        self.spn_wall.setSuffix(" mm")
        self.spn_wall.setToolTip("Plastic wall thickness around the socket.")
        self.spn_wall.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Wall thickness:", self.spn_wall)

        self.spn_depth = ExprDoubleSpinBox()
        self.spn_depth.setRange(5.0, 200.0)
        self.spn_depth.setValue(25.0)
        self.spn_depth.setSuffix(" mm")
        self.spn_depth.setToolTip("How far the tube inserts into the bracket socket.")
        self.spn_depth.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Socket depth:", self.spn_depth)

        self.spn_hole_dia = ExprDoubleSpinBox()
        self.spn_hole_dia.setRange(1.0, 20.0)
        self.spn_hole_dia.setValue(3.5)
        self.spn_hole_dia.setSuffix(" mm")
        self.spn_hole_dia.setToolTip("Screw hole diameter (e.g. 3.5 mm for M3/M3.5).")
        self.spn_hole_dia.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Screw hole diameter:", self.spn_hole_dia)

        self.spn_hole_offset = ExprDoubleSpinBox()
        self.spn_hole_offset.setRange(2.0, 100.0)
        self.spn_hole_offset.setValue(12.0)
        self.spn_hole_offset.setSuffix(" mm")
        self.spn_hole_offset.setToolTip("Distance from open arm end to center of screw hole.")
        self.spn_hole_offset.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Screw hole offset:", self.spn_hole_offset)

        self.chk_double_holes = QCheckBox("Double screw holes")
        self.chk_double_holes.setToolTip("Place two screw holes along each socket arm for extra stability.")
        self.chk_double_holes.setChecked(False)
        self.chk_double_holes.toggled.connect(self._on_double_holes_toggled)
        form.addRow("Double holes:", self.chk_double_holes)

        self.spn_hole_spacing = ExprDoubleSpinBox()
        self.spn_hole_spacing.setRange(5.0, 100.0)
        self.spn_hole_spacing.setValue(15.0)
        self.spn_hole_spacing.setSuffix(" mm")
        self.spn_hole_spacing.setToolTip("Center-to-center distance between double screw holes.")
        self.spn_hole_spacing.setEnabled(False)
        self.spn_hole_spacing.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Hole spacing:", self.spn_hole_spacing)

        self.chk_reinforcement = QCheckBox("Reinforcement web")
        self.chk_reinforcement.setToolTip("Add solid structural stiffening web between socket arms on both brackets.")
        self.chk_reinforcement.setChecked(True)
        self.chk_reinforcement.toggled.connect(lambda _: self.changed.emit())
        form.addRow("Reinforcement:", self.chk_reinforcement)

        self.chk_post = QCheckBox("Connector post")
        self.chk_post.setToolTip("Add a vertical square socket with a chamfered base and a screw hole on both bracket types, so two stars can be joined with tubes.")
        self.chk_post.setChecked(True)
        self.chk_post.toggled.connect(self._on_post_toggled)
        form.addRow("Connector post:", self.chk_post)

        self.spn_post_height = ExprDoubleSpinBox()
        self.spn_post_height.setRange(10.0, 100.0)
        self.spn_post_height.setValue(25.0)
        self.spn_post_height.setSuffix(" mm")
        self.spn_post_height.setToolTip("Height of the connector post above the bracket plate.")
        self.spn_post_height.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Post height:", self.spn_post_height)

        self.chk_second_star = QCheckBox("Second star + connecting tubes")
        self.chk_second_star.setToolTip("Add the second star above the first, joined by 10 adjustable connecting tubes in the connector posts.")
        self.chk_second_star.setChecked(False)
        self.chk_second_star.toggled.connect(self._on_second_star_toggled)
        form.addRow("Second star:", self.chk_second_star)

        self.spn_cross_tube_length = ExprDoubleSpinBox()
        self.spn_cross_tube_length.setRange(20.0, 2000.0)
        self.spn_cross_tube_length.setValue(150.0)
        self.spn_cross_tube_length.setSuffix(" mm")
        self.spn_cross_tube_length.setToolTip("Length of the 10 connecting tubes between the first and second star.")
        self.spn_cross_tube_length.setEnabled(False)
        self.spn_cross_tube_length.valueChanged.connect(lambda _: self.changed.emit())
        form.addRow("Connecting tube length:", self.spn_cross_tube_length)

        self.spn_outer_angle = ExprDoubleSpinBox()
        self.spn_outer_angle.setRange(10.0, 160.0)
        self.spn_outer_angle.setValue(36.0)
        self.spn_outer_angle.setSuffix(" °")
        self.spn_outer_angle.setToolTip("Outer apex angle (36° for 5-pointed star). Changing this automatically updates the inner angle.")
        self.spn_outer_angle.valueChanged.connect(self._on_outer_angle_changed)
        form.addRow("Outer angle (tip):", self.spn_outer_angle)

        self.spn_inner_angle = ExprDoubleSpinBox()
        self.spn_inner_angle.setRange(10.0, 170.0)
        self.spn_inner_angle.setValue(108.0)
        self.spn_inner_angle.setSuffix(" °")
        self.spn_inner_angle.setToolTip("Inner valley angle (108° for 5-pointed star). Changing this automatically updates the outer angle.")
        self.spn_inner_angle.valueChanged.connect(self._on_inner_angle_changed)
        form.addRow("Inner angle (valley):", self.spn_inner_angle)

        self.spn_foot_width = ExprDoubleSpinBox()
        self.spn_foot_width.setRange(15.0, 200.0)
        self.spn_foot_width.setValue(40.0)
        self.spn_foot_width.setSuffix(" mm")
        self.spn_foot_width.setToolTip("Width of the ground base plate.")
        self.spn_foot_width.valueChanged.connect(lambda _: self.changed.emit())

        self.spn_foot_length = ExprDoubleSpinBox()
        self.spn_foot_length.setRange(20.0, 300.0)
        self.spn_foot_length.setValue(70.0)
        self.spn_foot_length.setSuffix(" mm")
        self.spn_foot_length.setToolTip("Length of the ground base plate (front-to-back stability).")
        self.spn_foot_length.valueChanged.connect(lambda _: self.changed.emit())

        self.spn_foot_thickness = ExprDoubleSpinBox()
        self.spn_foot_thickness.setRange(2.0, 50.0)
        self.spn_foot_thickness.setValue(4.0)
        self.spn_foot_thickness.setSuffix(" mm")
        self.spn_foot_thickness.setToolTip("Thickness of the ground base plate.")
        self.spn_foot_thickness.valueChanged.connect(lambda _: self.changed.emit())

        self.spn_foot_angle = ExprDoubleSpinBox()
        self.spn_foot_angle.setRange(5.0, 85.0)
        self.spn_foot_angle.setValue(36.0)
        self.spn_foot_angle.setSuffix(" °")
        self.spn_foot_angle.setToolTip("Angle of the bottom tube to the ground (36° for 5-pointed star).")
        self.spn_foot_angle.valueChanged.connect(lambda _: self.changed.emit())

        # The foot supports are switched off for now: their fields stay as hidden values (old files keep theirs).
        # Two fields per row to save vertical space (Björn #168)
        self.pair_form_rows(form, [
            (self.spn_tube_length, self.spn_tube_size), (self.spn_clearance, self.spn_wall),
            (self.spn_depth, self.spn_hole_dia), (self.spn_hole_offset, self.spn_hole_spacing),
            (self.chk_double_holes, self.chk_reinforcement), (self.chk_post, self.chk_second_star),
            (self.spn_post_height, self.spn_cross_tube_length),
            (self.spn_outer_angle, self.spn_inner_angle)])

        self.main_layout.addLayout(form)
        self.lbl_problem = QLabel()
        self.lbl_problem.setStyleSheet("color: #e06c75; font-size: 11px;")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()

    def _on_post_toggled(self, checked: bool):
        self.spn_post_height.setEnabled(checked)
        self.changed.emit()

    def _on_second_star_toggled(self, checked: bool):
        self.spn_cross_tube_length.setEnabled(checked)
        if checked:
            self.chk_post.setChecked(True)
            self.chk_assembled.setChecked(True)
        self.changed.emit()

    def _on_double_holes_toggled(self, checked: bool):
        self.spn_hole_spacing.setEnabled(checked)
        self.changed.emit()

    def _on_outer_angle_changed(self, val):
        if getattr(self, "_syncing_angles", False):
            return
        self._syncing_angles = True
        try:
            outer_val = float(val)
            inner_val = max(10.0, min(170.0, round(outer_val + 72.0, 2)))
            self.spn_inner_angle.setValue(inner_val)
            fta = max(5.0, min(85.0, round(54.0 - outer_val / 2.0, 2)))
            self.spn_foot_angle.setValue(fta)
        finally:
            self._syncing_angles = False
        self.changed.emit()

    def _on_inner_angle_changed(self, val):
        if getattr(self, "_syncing_angles", False):
            return
        self._syncing_angles = True
        try:
            inner_val = float(val)
            outer_val = max(10.0, min(160.0, round(inner_val - 72.0, 2)))
            self.spn_outer_angle.setValue(outer_val)
            fta = max(5.0, min(85.0, round(54.0 - outer_val / 2.0, 2)))
            self.spn_foot_angle.setValue(fta)
        finally:
            self._syncing_angles = False
        self.changed.emit()

    def get_params(self) -> dict:
        return {
            "assembled": self.chk_assembled.isChecked(),
            "tube_length": self.spn_tube_length.value(),
            "tube_size": self.spn_tube_size.value(),
            "clearance": self.spn_clearance.value(),
            "wall_thickness": self.spn_wall.value(),
            "socket_depth": self.spn_depth.value(),
            "hole_diameter": self.spn_hole_dia.value(),
            "hole_offset": self.spn_hole_offset.value(),
            "double_holes": self.chk_double_holes.isChecked(),
            "hole_spacing": self.spn_hole_spacing.value(),
            "reinforcement": self.chk_reinforcement.isChecked(),
            "post": self.chk_post.isChecked(),
            "post_height": self.spn_post_height.value(),
            "second_star": self.chk_second_star.isChecked(),
            "cross_tube_length": self.spn_cross_tube_length.value(),
            "outer_angle": self.spn_outer_angle.value(),
            "inner_angle": self.spn_inner_angle.value(),
            "foot_width": self.spn_foot_width.value(),
            "foot_length": self.spn_foot_length.value(),
            "foot_thickness": self.spn_foot_thickness.value(),
            "foot_tube_angle": self.spn_foot_angle.value(),
        }

    def set_params(self, params: dict):
        if getattr(self, "_syncing_angles", False):
            return
        self._syncing_angles = True
        try:
            if "assembled" in params:
                self.chk_assembled.setChecked(bool(params["assembled"]))
            if "tube_length" in params:
                self.spn_tube_length.setValue(float(params["tube_length"]))
            if "tube_size" in params:
                self.spn_tube_size.setValue(float(params["tube_size"]))
            if "clearance" in params:
                self.spn_clearance.setValue(float(params["clearance"]))
            if "wall_thickness" in params:
                self.spn_wall.setValue(float(params["wall_thickness"]))
            if "socket_depth" in params:
                self.spn_depth.setValue(float(params["socket_depth"]))
            if "hole_diameter" in params:
                self.spn_hole_dia.setValue(float(params["hole_diameter"]))
            if "hole_offset" in params:
                self.spn_hole_offset.setValue(float(params["hole_offset"]))
            if "double_holes" in params:
                self.chk_double_holes.setChecked(bool(params["double_holes"]))
                self.spn_hole_spacing.setEnabled(bool(params["double_holes"]))
            if "hole_spacing" in params:
                self.spn_hole_spacing.setValue(float(params["hole_spacing"]))
            if "reinforcement" in params:
                self.chk_reinforcement.setChecked(bool(params["reinforcement"]))
            self.chk_post.setChecked(bool(params.get("post", False)))
            self.spn_post_height.setEnabled(self.chk_post.isChecked())
            if "post_height" in params:
                self.spn_post_height.setValue(float(params["post_height"]))
            self.chk_second_star.setChecked(bool(params.get("second_star", False)))
            self.spn_cross_tube_length.setEnabled(self.chk_second_star.isChecked())
            if "cross_tube_length" in params:
                self.spn_cross_tube_length.setValue(float(params["cross_tube_length"]))
            if "outer_angle" in params:
                outer_a = float(params["outer_angle"])
                self.spn_outer_angle.setValue(outer_a)
                self.spn_inner_angle.setValue(round(outer_a + 72.0, 2))
                self.spn_foot_angle.setValue(round(54.0 - outer_a / 2.0, 2))
            elif "inner_angle" in params:
                inner_a = float(params["inner_angle"])
                self.spn_inner_angle.setValue(inner_a)
                self.spn_outer_angle.setValue(round(inner_a - 72.0, 2))
                self.spn_foot_angle.setValue(round(54.0 - (inner_a - 72.0) / 2.0, 2))
            if "foot_width" in params:
                self.spn_foot_width.setValue(float(params["foot_width"]))
            if "foot_length" in params:
                self.spn_foot_length.setValue(float(params["foot_length"]))
            if "foot_thickness" in params:
                self.spn_foot_thickness.setValue(float(params["foot_thickness"]))
            if "foot_tube_angle" in params:
                self.spn_foot_angle.setValue(float(params["foot_tube_angle"]))
        finally:
            self._syncing_angles = False
