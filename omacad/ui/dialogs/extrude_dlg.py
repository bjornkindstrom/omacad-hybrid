"""Dialog for linear solid extrusion with live preview."""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QLabel, QHBoxLayout, QPushButton
)
from omacad.ui.theme import style
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class ExtrudeDialog(BaseFeatureDialog):
    """Non-modal dialog for linear solid extrusion with live preview."""

    changed = Signal()
    pick_face_requested = Signal()

    def __init__(self, doc: Document, parent=None, embedded: bool = False):
        super().__init__("Extrude", parent, embedded)
        self.doc = doc
        form = QFormLayout()

        # Profile selection
        self.cmb_profile = QComboBox()
        self.profile_keys = []
        for s_id, s in doc.sketches.items():
            for p_idx, p in enumerate(s.profiles):
                label = f"{s.name} · {p_idx + 1} · {p.area:.0f} mm²"
                self.cmb_profile.addItem(label)
                self.profile_keys.append((s_id, p_idx))

        if not self.profile_keys:
            self.cmb_profile.addItem("No closed sketch profiles found!")
            self.cmb_profile.setEnabled(False)

        form.addRow("Profile:", self.cmb_profile)

        # Distance
        self.spn_dist = ExprDoubleSpinBox()
        self.spn_dist.setRange(-10000.0, 10000.0)
        self.spn_dist.setValue(25.0)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.setToolTip("Type a value or a formula, e.g. -10, 10-1 or 2x(3+5)")
        self.btn_face = QPushButton("To face…")
        self.btn_face.setToolTip("Click another face (or origin plane) in the viewport: the distance to it is filled in")
        self.btn_face.setAutoDefault(False)
        self.btn_face.clicked.connect(self.pick_face_requested)
        dist_row = QHBoxLayout()
        dist_row.setContentsMargins(0, 0, 0, 0)
        dist_row.addWidget(self.spn_dist, 1)
        dist_row.addWidget(self.btn_face)
        form.addRow("Distance:", dist_row)

        # Start Offset (distance from sketch plane before extrusion starts)
        self.spn_offset = ExprDoubleSpinBox()
        self.spn_offset.setRange(-10000.0, 10000.0)
        self.spn_offset.setValue(0.0)
        self.spn_offset.setSuffix(" mm")
        self.spn_offset.setToolTip("Start offset along the sketch normal before the extrusion begins (0 = starts at the sketch plane)")
        form.addRow("Start Offset:", self.spn_offset)

        # Twist: the profile turns about its centre on the way up (Lennart #85; Fusion needs a sweep for this)
        self.spn_twist = ExprDoubleSpinBox()
        self.spn_twist.setRange(-3600.0, 3600.0)
        self.spn_twist.setValue(0.0)
        self.spn_twist.setSuffix(" °")
        self.spn_twist.setToolTip("Turn the profile this many degrees about its centre from start to end (0 = straight). Negative turns the other way.")
        form.addRow("Twist:", self.spn_twist)

        # Direction
        self.cmb_dir = QComboBox()
        self.cmb_dir.addItems(["One Side", "Symmetric", "Two Sides"])
        self.cmb_dir.currentIndexChanged.connect(self._on_dir_changed)
        form.addRow("Direction:", self.cmb_dir)

        self.spn_dist2 = ExprDoubleSpinBox()
        self.spn_dist2.setRange(0.0, 10000.0)
        self.spn_dist2.setValue(10.0)
        self.spn_dist2.setSuffix(" mm")
        self.lbl_dist2 = QLabel("Distance 2:")
        form.addRow(self.lbl_dist2, self.spn_dist2)
        self._on_dir_changed(0)

        # Operation
        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Auto", "New Body", "Join", "Cut (Difference)", "Intersect"])
        self.cmb_op.setToolTip("Auto: cuts when the extrusion goes into a body, joins when it starts on a body's face and goes out, otherwise makes a new body.")
        form.addRow("Operation:", self.cmb_op)

        hint = QLabel("Click a profile to select it; Shift+click adds or removes more (a ring and the circle inside it are separate profiles). Distance accepts formulas (10-1, 2x(3+5)).")
        hint.setWordWrap(True)
        style(hint, "color: #8A929C;")
        self.main_layout.addWidget(hint)
        self.main_layout.addLayout(form)
        self.add_buttons()

        self.cmb_profile.setPlaceholderText("Click a profile in the view")
        if doc.selected_profile in self.profile_keys:
            self.cmb_profile.setCurrentIndex(self.profile_keys.index(doc.selected_profile))
        elif len(self.profile_keys) > 1:
            self.cmb_profile.setCurrentIndex(-1)   # nothing is picked for you when there is a choice
        QTimer.singleShot(0, self, self.focus_primary)   # the context drops it if the panel is gone
        for sig in (self.cmb_profile.currentIndexChanged, self.cmb_dir.currentIndexChanged,
                    self.cmb_op.currentIndexChanged, self.spn_dist.valueChanged, self.spn_dist2.valueChanged,
                    self.spn_offset.valueChanged, self.spn_twist.valueChanged):
            sig.connect(lambda *_: self.changed.emit())

    def reload_profiles(self):
        """Rebuild the profile list (a face sketch may have been added while the dialog is open)."""
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.clear()
        self.profile_keys = []
        for s_id, sk in self.doc.sketches.items():
            for p_idx, p in enumerate(sk.profiles):
                self.cmb_profile.addItem(f"{sk.name} · {p_idx + 1} · {p.area:.0f} mm²")
                self.profile_keys.append((s_id, p_idx))
        self.cmb_profile.setEnabled(bool(self.profile_keys))
        self.cmb_profile.blockSignals(False)

    def set_distance(self, value: float):
        """Used by 'To face': one-sided extrusion by the given (signed) distance."""
        self.cmb_dir.setCurrentIndex(0)
        self.spn_dist.setValue(round(value, 4))
        self.focus_primary()

    def select_profile(self, key):
        """Selects a (sketch_id, profile_idx) in the combo (e.g. picked in the viewport)."""
        if key in self.profile_keys:
            self.cmb_profile.setCurrentIndex(self.profile_keys.index(key))

    def get_operation(self) -> str:
        return {0: "auto", 1: "new_body", 2: "join", 3: "cut", 4: "intersect"}.get(self.cmb_op.currentIndex(), "auto")

    def set_auto_result(self, op: str):
        """Shows what 'Auto' currently resolves to, e.g. 'Auto (Cut)'."""
        names = {"new_body": "New Body", "join": "Join", "cut": "Cut", "intersect": "Intersect"}
        self.cmb_op.setItemText(0, f"Auto ({names.get(op, op)})")

    def _on_dir_changed(self, idx: int):
        two = idx == 2
        self.spn_dist2.setVisible(two)
        self.lbl_dist2.setVisible(two)
        # Symmetric/two-sided lengths are magnitudes
        self.spn_dist.setMinimum(0.1 if idx else -10000.0)

    def get_expressions(self) -> dict:
        """Formulas typed into the distance/offset fields (None-valued entries dropped)."""
        out = {
            "distance": self.spn_dist.expression(),
            "distance2": self.spn_dist2.expression(),
            "start_offset": self.spn_offset.expression(),
            "twist": self.spn_twist.expression(),
        }
        return {k: v for k, v in out.items() if v}

    def get_start_offset(self) -> float:
        return self.spn_offset.value()

    def get_twist(self) -> float:
        return self.spn_twist.value()

    def get_direction(self):
        return ["one_side", "symmetric", "two_sides"][self.cmb_dir.currentIndex()], self.spn_dist2.value()

    def get_values(self):
        idx = self.cmb_profile.currentIndex()
        if not self.profile_keys or idx < 0:
            return None, 0, 0.0, "new_body"

        s_id, p_idx = self.profile_keys[idx]
        dist = self.spn_dist.value()
        op = self.get_operation()
        return s_id, p_idx, dist, op
