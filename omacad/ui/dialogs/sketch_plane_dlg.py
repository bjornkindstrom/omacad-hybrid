"""Dialogs for selecting sketch planes and offset construction planes."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel, QHBoxLayout, QPushButton
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox


class SketchPlaneDialog(BaseFeatureDialog):
    """Dialog to choose which reference plane to sketch on."""

    def __init__(self, parent=None):
        super().__init__("Select Sketch Plane", parent)
        form = QFormLayout()

        self.cmb_plane = QComboBox()
        self.cmb_plane.addItems(["XY Plane (Top / Ground)", "XZ Plane (Front)", "YZ Plane (Right / Side)"])
        form.addRow("Plane:", self.cmb_plane)

        self.main_layout.addLayout(form)
        self.add_buttons()

    def get_plane_name(self) -> str:
        idx = self.cmb_plane.currentIndex()
        return ["XY", "XZ", "YZ"][idx]


class OffsetPlaneDialog(BaseFeatureDialog):
    """Offset plane: a plane parallel to the chosen plane or face, at a distance or up to any surface."""
    changed = Signal()
    surface_requested = Signal()
    edge_requested = Signal()

    def __init__(self, base_name: str, parent=None, embedded=False):
        super().__init__("Offset Plane", parent, embedded)
        info = QLabel(f"From: {base_name}\nType a distance (formulas and parameters work) or press 'To surface…' "
                      "and click a face, a cylinder or a sphere: the plane then touches it. An angle turns the plane "
                      "about its X or Y direction or about an edge you click.")
        info.setWordWrap(True)
        self.main_layout.addWidget(info)
        form = QFormLayout()
        row = QHBoxLayout()
        self.spn_dist = ExprDoubleSpinBox()
        self.spn_dist.setRange(-10000.0, 10000.0)
        self.spn_dist.setDecimals(3)
        self.spn_dist.setValue(10.0)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.valueChanged.connect(lambda *_: self.changed.emit())
        row.addWidget(self.spn_dist, 1)
        self.btn_surface = QPushButton("To surface…")
        self.btn_surface.setAutoDefault(False)
        self.btn_surface.setToolTip("Click a flat or curved surface; the plane is placed tangent to it")
        self.btn_surface.clicked.connect(self.surface_requested.emit)
        row.addWidget(self.btn_surface)
        form.addRow("Distance:", row)
        # Plane at Angle (Björn #51): turn the plane about a line in it before offsetting
        self.spn_angle = ExprDoubleSpinBox()
        self.spn_angle.setRange(-180.0, 180.0)
        self.spn_angle.setDecimals(2)
        self.spn_angle.setValue(0.0)
        self.spn_angle.setSuffix(" °")
        self.spn_angle.setToolTip("Turn the plane about the axis below (0 = parallel to the start plane)")
        self.spn_angle.valueChanged.connect(lambda *_: (self._sync_axis(), self.changed.emit()))
        form.addRow("Angle:", self.spn_angle)
        axis_row = QHBoxLayout()
        self.cmb_axis = QComboBox()
        self.cmb_axis.addItems(["Plane's X direction", "Plane's Y direction", "An edge (click it)"])
        self.cmb_axis.currentIndexChanged.connect(self._axis_changed)
        axis_row.addWidget(self.cmb_axis, 1)
        self.btn_edge = QPushButton("Pick edge…")
        self.btn_edge.setAutoDefault(False)
        self.btn_edge.setToolTip("Click a straight edge of a body: the plane turns about it")
        self.btn_edge.clicked.connect(self.edge_requested.emit)
        axis_row.addWidget(self.btn_edge)
        self.lbl_axis = QLabel("Rotate about:")
        form.addRow(self.lbl_axis, axis_row)
        self.edge = None            # (point, direction) of the picked edge
        self.main_layout.addLayout(form)
        self.add_buttons()
        self._sync_axis()

    def _axis_changed(self, *_):
        self._sync_axis()
        if self.cmb_axis.currentIndex() == 2 and self.edge is None:
            self.edge_requested.emit()
        self.changed.emit()

    def _sync_axis(self):
        self.btn_edge.setVisible(self.cmb_axis.currentIndex() == 2)

    def set_edge(self, point, direction):
        self.edge = (point, direction)
        self.cmb_axis.blockSignals(True)
        self.cmb_axis.setCurrentIndex(2)
        self.cmb_axis.blockSignals(False)
        self._sync_axis()
        self.btn_edge.setText("Edge picked ✓")
        self.changed.emit()

    def get_distance(self) -> float:
        return self.spn_dist.value()

    def get_angle(self) -> float:
        return self.spn_angle.value()

    def get_axis(self, plane):
        """(point or None, direction) of the axis the plane turns about, for `plane` (the start plane)."""
        idx = self.cmb_axis.currentIndex()
        if idx == 2:
            return self.edge if self.edge is not None else (None, None)
        return None, (plane.u_axis if idx == 0 else plane.v_axis)

    def get_expressions(self) -> dict:
        out = {}
        for key, spin in (("distance", self.spn_dist), ("angle", self.spn_angle)):
            e = spin.expression()
            if e:
                out[key] = e
        return out
