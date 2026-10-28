"""Dialog for Pattern and Mirror operations."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QListWidget, QListWidgetItem, QSpinBox,
    QCheckBox, QLabel, QPushButton
)
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class PatternDialog(BaseFeatureDialog):
    """Pattern / Mirror: copy what some steps did (e.g. a hole and its chamfers)."""

    changed = Signal()

    KINDS = ["linear", "mirror", "circular", "fill"]
    AXES = ["x", "y", "z"]
    MIRROR_MODES = ["auto", "x", "y", "xy", "diameter", "plane"]

    def __init__(self, doc: Document, parent=None, feature=None):
        super().__init__("Pattern / Mirror", parent)
        self.setFixedWidth(358)
        self.doc = doc
        form = QFormLayout()

        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(["Linear pattern", "Mirror body", "Circular pattern", "Fill face pattern"])
        form.addRow("Type:", self.cmb_kind)

        self.lst = QListWidget()
        self.lst.setFixedHeight(120)
        feats = doc.timeline.features
        if feature is not None and feature in feats:
            feats = feats[:feats.index(feature)]
        non_pat = [(i, f) for i, f in enumerate(feats) if f.feature_type != "pattern"]
        sketches = [i for i, f in non_pat if f.feature_type == "sketch"]
        if sketches and (not non_pat or non_pat[-1][1].feature_type not in ("box", "cylinder", "prism", "sphere", "thread")):
            start_idx = max(sketches)
        elif non_pat:
            start_idx = non_pat[-1][0]
            if non_pat[-1][1].feature_type == "fillet":
                for i, f in reversed(non_pat):
                    start_idx = i
                    if f.feature_type in ("box", "cylinder", "prism", "sphere", "extrude", "emboss", "revolve"):
                        break
        else:
            start_idx = 0
        for i, f in non_pat:
            item = QListWidgetItem(f.name)
            item.setData(Qt.ItemDataRole.UserRole, f.feature_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if i >= start_idx else Qt.CheckState.Unchecked)
            self.lst.addItem(item)
        self.lbl_features = QLabel("Copy these steps:")
        form.addRow(self.lbl_features, self.lst)

        # linear
        self.cmb_axis1 = QComboBox(); self.cmb_axis1.addItems(["X", "Y", "Z"])
        self.spn_count1 = QSpinBox(); self.spn_count1.setRange(2, 500); self.spn_count1.setValue(3)
        self.spn_space1 = ExprDoubleSpinBox(); self.spn_space1.setRange(0.01, 100000); self.spn_space1.setSuffix(" mm"); self.spn_space1.setValue(20.0)
        self.chk_second = QCheckBox("Second direction (grid)")
        self.cmb_axis2 = QComboBox(); self.cmb_axis2.addItems(["X", "Y", "Z"]); self.cmb_axis2.setCurrentIndex(1)
        self.spn_count2 = QSpinBox(); self.spn_count2.setRange(1, 500); self.spn_count2.setValue(2)
        self.spn_space2 = ExprDoubleSpinBox(); self.spn_space2.setRange(0.01, 100000); self.spn_space2.setSuffix(" mm"); self.spn_space2.setValue(20.0)
        # mirror
        self.cmb_mirror = QComboBox()
        self.cmb_mirror.addItems(["Auto (round body: along the diameter)", "Mirror left-right (X)", "Mirror front-back (Y)", "All four corners (X and Y)", "Along the diameter (opposite side)", "Across a plane…"])
        self.plane_keys, plane_labels = [], []
        for pid, cp in doc.construction_planes.items():
            self.plane_keys.append(pid); plane_labels.append(f"📐 {cp['name']}")
        for op in ("XY", "XZ", "YZ"):
            self.plane_keys.append(op); plane_labels.append(f"🌐 {op} Plane")
        self.cmb_mplane = QComboBox(); self.cmb_mplane.addItems(plane_labels)
        self.cmb_mplane.setCurrentIndex(self.plane_keys.index("YZ"))
        # circular
        self.cmb_rotation = QComboBox()
        self.cmb_rotation.addItems(["X", "Y", "Z", "Picked axis"])
        self.cmb_rotation.setCurrentIndex(2)
        self.picked_origin = self.picked_direction = None
        self.btn_axis = QPushButton("Pick circular edge / cylinder")
        self.btn_axis.setAutoDefault(False)
        self.lbl_axis = QLabel("No axis picked")
        self.lbl_axis.setWordWrap(True)
        self.spn_angle = ExprDoubleSpinBox(); self.spn_angle.setRange(-360, 360); self.spn_angle.setSuffix(" °"); self.spn_angle.setValue(360)
        self.cmb_about = QComboBox(); self.cmb_about.addItems(["Centre of the body", "Origin"])
        # fill
        self.spn_gap = ExprDoubleSpinBox(); self.spn_gap.setRange(0.1, 10000); self.spn_gap.setSuffix(" mm"); self.spn_gap.setValue(5.0)
        self.spn_margin = ExprDoubleSpinBox(); self.spn_margin.setRange(0.0, 10000); self.spn_margin.setSuffix(" mm"); self.spn_margin.setValue(10.0)
        self.cmb_layout = QComboBox(); self.cmb_layout.addItems(["Grid", "Staggered (honeycomb / auto)", "Triangular (alternating)"])
        self.spn_partial = QSpinBox(); self.spn_partial.setRange(0, 100); self.spn_partial.setValue(25); self.spn_partial.setSuffix(" %")
        self.spn_partial.setToolTip("Copies at the edge may be cut off by the frame. Pieces smaller than this share of a whole copy are left out. "
                                    "0 = only whole copies.")

        self.rows = {
            "linear": [("Direction:", self.cmb_axis1), ("Copies:", self.spn_count1), ("Spacing:", self.spn_space1),
                       ("", self.chk_second), ("Direction 2:", self.cmb_axis2), ("Copies 2:", self.spn_count2), ("Spacing 2:", self.spn_space2)],
            "mirror": [("Mirror:", self.cmb_mirror), ("About:", self.cmb_about)],
            "circular": [("Quantity (incl. original):", self.spn_count1), ("Axis:", self.cmb_rotation),
                         ("", self.btn_axis), ("", self.lbl_axis), ("Angle:", self.spn_angle), ("About:", self.cmb_about)],
            "fill": [("Gap between copies:", self.spn_gap), ("Margin to the edge:", self.spn_margin), ("Layout:", self.cmb_layout), ("Smallest cut piece:", self.spn_partial)],
        }
        self._kind_form = QFormLayout()
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        self.main_layout.addLayout(form)
        self.main_layout.addLayout(self._kind_form)
        self.main_layout.addWidget(self.lbl_info)
        self.add_buttons()
        self.cmb_kind.currentIndexChanged.connect(self._show_kind)
        for w_ in (self.cmb_kind, self.cmb_axis1, self.cmb_axis2, self.cmb_mirror, self.cmb_mplane, self.cmb_about, self.cmb_layout):
            w_.currentIndexChanged.connect(lambda *_: self.changed.emit())
        for w_ in (self.spn_count1, self.spn_count2, self.spn_space1, self.spn_space2, self.spn_angle, self.spn_gap, self.spn_margin, self.spn_partial):
            w_.valueChanged.connect(lambda *_: self.changed.emit())
        self.chk_second.toggled.connect(lambda *_: (self._show_kind(), self.changed.emit()))
        self.lst.itemChanged.connect(lambda *_: self.changed.emit())
        from omacad.model.features.pattern import PatternFeature
        self.round_body = any(PatternFeature._is_round(b.manifold) for b in doc.bodies.values())
        if self.round_body and feature is None:
            self.spn_count1.setValue(2)   # a copy on the other end of the diameter, until you ask for more
        self.cmb_rotation.currentIndexChanged.connect(lambda *_: (self._show_kind(), self.changed.emit()))
        self.cmb_mirror.currentIndexChanged.connect(self._show_kind)
        self._show_kind()
        if feature is not None:
            self.load(feature)

    def _show_kind(self, *_):
        """Show only the fields that belong to the chosen type."""
        for w_ in [x for rows in self.rows.values() for _, x in rows]:
            w_.setVisible(False)
        while self._kind_form.rowCount():
            row = self._kind_form.takeRow(0)
            if row.labelItem is not None and row.labelItem.widget() is not None:
                lbl = row.labelItem.widget()
                lbl.hide()          # gone at once (deleteLater alone leaves it painted for a moment)
                lbl.setParent(None)
                lbl.deleteLater()
        kind = self.KINDS[self.cmb_kind.currentIndex()]
        rows = list(self.rows[kind])
        mode = self.MIRROR_MODES[self.cmb_mirror.currentIndex()]
        if kind == "mirror" and (mode == "diameter" or (mode == "auto" and getattr(self, "round_body", False))):
            rows.insert(1, ("Copies (even spacing):", self.spn_count1))   # round body: count them out around the circle
        if kind == "mirror" and mode == "plane":
            rows = [("Mirror:", self.cmb_mirror), ("Plane:", self.cmb_mplane)]
        self.lbl_features.setText("Features (rib + fillet):" if kind == "circular" else "Copy these steps:")
        for text, widget in rows:
            if kind == "circular":
                picked = self.cmb_rotation.currentIndex() == 3
                if widget is self.lbl_axis and not picked:
                    continue
                if widget is self.cmb_about and picked:
                    continue
            if kind == "linear" and widget in (self.cmb_axis2, self.spn_count2, self.spn_space2) and not self.chk_second.isChecked():
                continue
            parent = widget.parentWidget()
            host = parent if getattr(parent, "field", None) is widget else widget
            self._kind_form.addRow(QLabel(text), host)
            host.setVisible(True)
            widget.setVisible(True)
        if getattr(self, "_is_docked", False):
            from omacad.ui.numeric_slider import add_numeric_sliders
            add_numeric_sliders(self)

    def toggle_feature(self, feature_id):
        for i in range(self.lst.count()):
            item = self.lst.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == feature_id:
                item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
                return

    def bind_timeline(self, timeline):
        handler = self.toggle_feature
        previous = timeline.feature_pick_handler
        timeline.feature_pick_handler = handler
        def clear(*_):
            if timeline.feature_pick_handler == handler:
                timeline.feature_pick_handler = previous
        self.finished.connect(clear)

    def bind_axis_picker(self, viewport):
        def begin():
            viewport.begin_plane_pick("pattern_axis")
            viewport.status_message.emit("Circular Pattern: click a circular edge or cylindrical face for the rotation axis.")

        def picked(info):
            self.picked_origin = list(map(float, info["origin"]))
            self.picked_direction = list(map(float, info["axis"]))
            self.lbl_axis.setText("Picked cylinder axis")
            self.cmb_rotation.setCurrentIndex(3)
            self.changed.emit()

        def clear(*_):
            viewport.cylinder_picked.disconnect(picked)
            if viewport.plane_pick_mode and viewport.plane_pick_purpose == "pattern_axis":
                viewport.end_plane_pick()
        self.btn_axis.clicked.connect(begin)
        viewport.cylinder_picked.connect(picked)
        self.finished.connect(clear)

    def accept(self):
        if self.kind() == "circular":
            if not self.source_ids():
                self.lbl_info.setText("Select the rib feature and its fillet in the list or timeline.")
                return
            if self.cmb_rotation.currentIndex() == 3 and self.picked_direction is None:
                self.lbl_info.setText("Pick a circular edge or cylinder to define the axis.")
                return
            if abs(self.spn_angle.value()) < 1e-6:
                self.lbl_info.setText("Enter a nonzero pattern angle.")
                return
        super().accept()

    def load(self, f):
        """Fill the dialog from an existing step (editing)."""
        self.cmb_kind.setCurrentIndex(self.KINDS.index(f.kind))
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setCheckState(Qt.CheckState.Checked if it.data(Qt.ItemDataRole.UserRole) in f.source_ids else Qt.CheckState.Unchecked)
        self.cmb_axis1.setCurrentIndex(self.AXES.index(f.axis1)); self.spn_count1.setValue(int(round(f.count1)))
        self.spn_space1.setValue(f.spacing1)
        self.chk_second.setChecked(int(round(f.count2)) > 1)
        self.cmb_axis2.setCurrentIndex(self.AXES.index(f.axis2)); self.spn_count2.setValue(max(1, int(round(f.count2))))
        self.spn_space2.setValue(f.spacing2)
        if f.mirror_mode.startswith("plane:"):
            self.cmb_mirror.setCurrentIndex(self.MIRROR_MODES.index("plane"))
            pid = f.mirror_mode.split(":", 1)[1]
            if pid in self.plane_keys:
                self.cmb_mplane.setCurrentIndex(self.plane_keys.index(pid))
        elif f.mirror_mode in self.MIRROR_MODES:
            self.cmb_mirror.setCurrentIndex(self.MIRROR_MODES.index(f.mirror_mode))
        self.cmb_about.setCurrentIndex(0 if f.about == "body" else 1)
        self.spn_angle.setValue(f.angle)
        axis = getattr(f, "rotation_axis", "z")
        self.picked_origin = getattr(f, "axis_origin", None)
        self.picked_direction = getattr(f, "axis_direction", None)
        self.cmb_rotation.setCurrentIndex(["x", "y", "z", "picked"].index(axis))
        if self.picked_origin is not None:
            self.lbl_axis.setText("Saved cylinder axis")
        if f.kind == "fill":
            self.spn_gap.setValue(f.spacing1); self.spn_margin.setValue(f.spacing2); self.spn_partial.setValue(int(round(f.count1)))
            if f.mirror_mode == "triangular":
                self.cmb_layout.setCurrentIndex(2)
            elif f.mirror_mode == "stagger":
                self.cmb_layout.setCurrentIndex(1)
            else:
                self.cmb_layout.setCurrentIndex(0)
            for key, spin in (("spacing1", self.spn_gap), ("spacing2", self.spn_margin)):
                if f.exprs.get(key):
                    spin.set_expression(f.exprs[key])
        for key, spin in (("spacing1", self.spn_space1), ("spacing2", self.spn_space2), ("angle", self.spn_angle)):
            if f.exprs.get(key):
                spin.set_expression(f.exprs[key])
        self._show_kind()

    def source_ids(self):
        return [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.CheckState.Checked]

    def kind(self) -> str:
        return self.KINDS[self.cmb_kind.currentIndex()]

    def get_params(self) -> dict:
        second = self.chk_second.isChecked()
        if self.kind() == "fill":   # gap and margin travel in the spacing fields, the layout in mirror_mode
            mode = "triangular" if self.cmb_layout.currentIndex() == 2 else ("stagger" if self.cmb_layout.currentIndex() == 1 else "grid")
            return {"axis1": "x", "count1": self.spn_partial.value(), "spacing1": self.spn_gap.value(), "axis2": "y", "count2": 1,
                    "spacing2": self.spn_margin.value(), "mirror_mode": mode,
                    "about": "body", "angle": 360.0}
        mmode = self.MIRROR_MODES[self.cmb_mirror.currentIndex()]
        if mmode == "plane":
            mmode = "plane:" + self.plane_keys[max(0, self.cmb_mplane.currentIndex())]
        return {
            "axis1": self.AXES[self.cmb_axis1.currentIndex()], "count1": self.spn_count1.value(), "spacing1": self.spn_space1.value(),
            "axis2": self.AXES[self.cmb_axis2.currentIndex()], "count2": self.spn_count2.value() if second else 1,
            "spacing2": self.spn_space2.value(), "mirror_mode": mmode,
            "about": "body" if self.cmb_about.currentIndex() == 0 else "origin", "angle": self.spn_angle.value(),
            "rotation_axis": ["x", "y", "z", "picked"][self.cmb_rotation.currentIndex()],
            "axis_origin": self.picked_origin, "axis_direction": self.picked_direction,
        }

    def get_expressions(self) -> dict:
        if self.kind() == "fill":
            out = {"spacing1": self.spn_gap.expression(), "spacing2": self.spn_margin.expression()}
            return {k: v for k, v in out.items() if v}
        out = {"spacing1": self.spn_space1.expression(), "spacing2": self.spn_space2.expression() if self.chk_second.isChecked() else None,
               "angle": self.spn_angle.expression()}
        return {k: v for k, v in out.items() if v}
