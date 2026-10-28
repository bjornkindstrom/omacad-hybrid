"""Dialog for revolving sketch profiles around an axis with live preview."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QComboBox, QLabel
from omacad.ui.theme import style
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class RevolveDialog(BaseFeatureDialog):
    """Revolve a sketch profile around an axis (Fusion 360 style): profile, axis, angle, direction, operation."""

    changed = Signal()

    def __init__(self, doc: Document, parent=None, embedded: bool = False):
        super().__init__("Revolve", parent, embedded)
        self.doc = doc
        form = QFormLayout()
        self.cmb_profile = QComboBox()
        self.profile_keys = []
        self.cmb_axis = QComboBox()
        self.axis_keys = []
        self.reload_profiles()
        form.addRow("Profile:", self.cmb_profile)
        form.addRow("Axis:", self.cmb_axis)

        self.cmb_dir = QComboBox()
        self.cmb_dir.addItems(["One Side", "Symmetric", "Two Sides"])
        form.addRow("Direction:", self.cmb_dir)
        self.spn_angle = ExprDoubleSpinBox()
        self.spn_angle.setRange(-360.0, 360.0)
        self.spn_angle.setDecimals(2)
        self.spn_angle.setValue(360.0)
        self.spn_angle.setSuffix(" °")
        self.spn_angle.setToolTip("360 = a full turn. Negative turns the other way. Formulas and parameter names work.")
        self.lbl_angle = QLabel("Angle:")
        form.addRow(self.lbl_angle, self.spn_angle)
        self.spn_angle2 = ExprDoubleSpinBox()
        self.spn_angle2.setRange(0.0, 360.0)
        self.spn_angle2.setValue(45.0)
        self.spn_angle2.setSuffix(" °")
        self.lbl_angle2 = QLabel("Angle 2:")
        form.addRow(self.lbl_angle2, self.spn_angle2)

        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Auto", "New Body", "Join", "Cut (Difference)", "Intersect"])
        self.cmb_op.setToolTip("Auto: cuts when the revolve goes into a body, joins when it touches one, otherwise makes a new body.")
        form.addRow("Operation:", self.cmb_op)

        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        style(self.lbl_info, "color: #E57373;")
        hint = QLabel("Click a profile in the view (Shift+click adds more), choose the axis, then the angle. "
                      "A construction line drawn in the sketch is the usual axis. The profile may touch the axis but not cross it.")
        hint.setWordWrap(True)
        style(hint, "color: #8A929C;")
        self.main_layout.addWidget(hint)
        self.main_layout.addLayout(form)
        self.main_layout.addWidget(self.lbl_info)
        self.add_buttons()
        self.cmb_dir.currentIndexChanged.connect(self._dir_changed)
        self._dir_changed()
        if doc.selected_profile in self.profile_keys:
            self.cmb_profile.setCurrentIndex(self.profile_keys.index(doc.selected_profile))
        elif len(self.profile_keys) > 1:
            self.cmb_profile.setCurrentIndex(-1)
        self.cmb_profile.currentIndexChanged.connect(lambda *_: (self.reload_axes(), self.changed.emit()))
        for sig in (self.cmb_axis.currentIndexChanged, self.cmb_dir.currentIndexChanged, self.cmb_op.currentIndexChanged,
                    self.spn_angle.valueChanged, self.spn_angle2.valueChanged):
            sig.connect(lambda *_: self.changed.emit())
        self.reload_axes()

    def reload_profiles(self):
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.clear()
        self.profile_keys = []
        for s_id, sk in self.doc.sketches.items():
            for p_idx, p in enumerate(sk.profiles):
                self.cmb_profile.addItem(f"{sk.name} · {p_idx + 1} · {p.area:.0f} mm²")
                self.profile_keys.append((s_id, p_idx))
        if not self.profile_keys:
            self.cmb_profile.addItem("No closed sketch profiles found!")
        self.cmb_profile.setEnabled(bool(self.profile_keys))
        self.cmb_profile.setPlaceholderText("Click a profile in the view")
        self.cmb_profile.blockSignals(False)

    def reload_axes(self):
        """The axes on offer: the sketch's own lines (construction lines first) and its horizontal / vertical axis."""
        self.cmb_axis.blockSignals(True)
        self.cmb_axis.clear()
        self.axis_keys = []
        idx = self.cmb_profile.currentIndex()
        sk = self.doc.sketches.get(self.profile_keys[idx][0]) if 0 <= idx < len(self.profile_keys) else None
        if sk is not None:
            lines = [e for e in sk.entities if getattr(e, "entity_type", "") == "line"]
            lines.sort(key=lambda e: not e.is_construction)
            for e in lines:
                tag = "construction line" if e.is_construction else "line"
                self.cmb_axis.addItem(f"{'⎯ ' if e.is_construction else ''}{tag} ({e.p1[0]:.1f}, {e.p1[1]:.1f}) → ({e.p2[0]:.1f}, {e.p2[1]:.1f})")
                self.axis_keys.append(("line", e.entity_id))
        u_lbl, v_lbl = sk.plane.axis_names() if sk is not None else ("X", "Y")
        for text, key in ((f"Sketch {v_lbl} axis (vertical)", ("v",)), (f"Sketch {u_lbl} axis (horizontal)", ("u",))):
            self.cmb_axis.addItem(text)
            self.axis_keys.append(key)
        # a construction line is the natural axis; otherwise the vertical axis
        first_constr = next((i for i, k in enumerate(self.axis_keys) if k[0] == "line" and sk is not None and sk.get_entity(k[1]).is_construction), None)
        self.cmb_axis.setCurrentIndex(first_constr if first_constr is not None else len(self.axis_keys) - 2)
        self.cmb_axis.blockSignals(False)

    def _dir_changed(self, *_):
        i = self.cmb_dir.currentIndex()
        self.lbl_angle.setText("Total angle:" if i == 1 else "Angle:" if i == 0 else "Angle 1:")
        self.spn_angle2.setVisible(i == 2)
        self.lbl_angle2.setVisible(i == 2)
        self.spn_angle.setMinimum(-360.0 if i == 0 else 0.1)

    def select_profile(self, key):
        if key in self.profile_keys:
            self.cmb_profile.setCurrentIndex(self.profile_keys.index(key))

    def get_operation(self) -> str:
        return {0: "auto", 1: "new_body", 2: "join", 3: "cut", 4: "intersect"}.get(self.cmb_op.currentIndex(), "auto")

    def set_auto_result(self, op: str):
        names = {"new_body": "New Body", "join": "Join", "cut": "Cut", "intersect": "Intersect"}
        self.cmb_op.setItemText(0, f"Auto ({names.get(op, op)})")

    def get_direction(self) -> str:
        return ["one_side", "symmetric", "two_sides"][self.cmb_dir.currentIndex()]

    def get_axis(self):
        i = self.cmb_axis.currentIndex()
        return self.axis_keys[i] if 0 <= i < len(self.axis_keys) else ("v",)

    def get_expressions(self) -> dict:
        out = {"angle": self.spn_angle.expression(), "angle2": self.spn_angle2.expression() if self.cmb_dir.currentIndex() == 2 else None}
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        idx = self.cmb_profile.currentIndex()
        if not self.profile_keys or idx < 0:
            return None, 0
        return self.profile_keys[idx]
