"""Panel for Sweep, Loft and Pipe (Björn #46): profiles and the path are clicked in the 3D view, as in Fusion."""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QListWidget, QHBoxLayout

from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox

OPERATIONS = (("new_body", "New Body"), ("join", "Join"), ("cut", "Cut"), ("intersect", "Intersect"))
TITLES = {"sweep": "Sweep", "loft": "Loft", "pipe": "Pipe"}
HELP = {
    "sweep": "Click the profiles in the 3D view (every click adds one, a click again drops it; same sketch), then press Path and click the path: body edges (as in Fillet; joined edges follow, X = "
             "see-through) or a sketch's line, arc or circle (everything joined to it comes along). Profile / Path "
             "below says which one the next click picks.",
    "loft": "Click the profiles in the order the loft passes through them (two or more, on different planes). "
            "Click a profile again to drop it, or use the list below to add, remove and reorder profiles.",
    "pipe": "Click the path in the 3D view - body edges (as in Fillet) or a sketch's line, arc or circle; joined "
            "pieces come along - and set the diameter; a wall thickness makes it a tube.",
}


def path_entities(sketch) -> list:
    """The elements of a sketch that make a path: drawn lines, arcs and circles (not construction or face edges)."""
    from omacad.model.sketch_entities import SketchArc, SketchCircle, SketchLine
    return [e.entity_id for e in sketch.entities
            if isinstance(e, (SketchLine, SketchArc, SketchCircle))
            and not getattr(e, "is_construction", False) and not getattr(e, "projected", False)]


def path_chain(sketch, entity_id: str) -> list:
    """The clicked path element and every line/arc joined to it end to end (a circle stands alone)."""
    from omacad.model.sketch_entities import SketchCircle
    usable = set(path_entities(sketch))
    ent = next((e for e in sketch.entities if e.entity_id == entity_id), None)
    if ent is None or entity_id not in usable:
        return []
    if isinstance(ent, SketchCircle):
        return [entity_id]
    by_id = {e.entity_id: e for e in sketch.entities}
    return [i for i in sketch.connected_entities(entity_id)
            if i in usable and not isinstance(by_id.get(i), SketchCircle)]


class SweepLoftDialog(BaseFeatureDialog):
    changed = Signal()
    active_changed = Signal(str)      # "profile" / "path": which selection the next click in the view goes to

    def __init__(self, doc, mode: str, parent=None, embedded: bool = False):
        super().__init__(TITLES[mode], parent, embedded)
        self.doc, self.mode = doc, mode
        info = QLabel(HELP[mode])
        info.setWordWrap(True)
        self.main_layout.addWidget(info)
        form = QFormLayout()
        self.lbl_profiles = QLabel("")
        # Fusion-style selection fields: the checked one takes the next click in the view
        self.btn_profile = QPushButton("Profile")
        self.btn_path = QPushButton("Path")
        for b, target in ((self.btn_profile, "profile"), (self.btn_path, "path")):
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, t=target: self.set_active(t))
        if mode != "pipe":
            form.addRow(self.btn_profile if mode == "sweep" else QLabel("Profiles:"), self.lbl_profiles)
        self.lbl_path = QLabel("click an edge, a line, arc or circle")
        self.path_ref = None                # (sketch id, [entity ids])
        if mode != "loft":
            form.addRow(self.btn_path, self.lbl_path)
        self.active = "path" if mode == "pipe" else "profile"
        self.spn_diam = self._spin(5.0, 0.01, 10000.0, " mm", "Outside diameter of the pipe")
        self.spn_thick = self._spin(0.0, 0.0, 5000.0, " mm", "Wall thickness (0 = solid rod)")
        self.spn_twist = self._spin(0.0, -3600.0, 3600.0, " °", "Turn the profile this much from start to end")
        if mode == "pipe":
            form.addRow("Diameter:", self.spn_diam)
            form.addRow("Wall:", self.spn_thick)
        if mode in ("sweep", "loft"):
            form.addRow("Twist:", self.spn_twist)
        self.cmb_op = QComboBox()
        for _key, label in OPERATIONS:
            self.cmb_op.addItem(label)
        self.cmb_op.currentIndexChanged.connect(lambda *_: self.changed.emit())
        form.addRow("Operation:", self.cmb_op)
        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addLayout(form)
        if mode == "loft":
            self.profile_list = QListWidget()
            self.profile_list.setMaximumHeight(130)
            self.main_layout.addWidget(self.profile_list)
            self.profile_choice = QComboBox()
            for sid, sketch in doc.sketches.items():
                for i, profile in enumerate(sketch.profiles):
                    self.profile_choice.addItem(f"{sketch.name}: profile {i + 1} ({profile.area:.1f} mm²)", (sid, i))
            self.main_layout.addWidget(self.profile_choice)
            buttons = QHBoxLayout()
            for label, slot in (("Add", self.add_profile), ("Remove", self.remove_profile),
                                ("↑", lambda: self.move_profile(-1)), ("↓", lambda: self.move_profile(1))):
                button = QPushButton(label)
                button.setAutoDefault(False)
                button.clicked.connect(slot)
                buttons.addWidget(button)
            self.main_layout.addLayout(buttons)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self.profiles = []                  # [(sketch id, profile index)] in pick order
        self.set_profiles([])
        self.set_active(self.active)
        if mode == "pipe":
            QTimer.singleShot(0, self, self.focus_primary)

    def _spin(self, value, lo, hi, suffix, tip):
        s = ExprDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(3)
        s.setSuffix(suffix)
        s.setValue(value)
        s.setToolTip(tip)
        s.valueChanged.connect(lambda *_: self.changed.emit())
        return s

    def set_profiles(self, profiles):
        self.profiles = list(profiles)
        names = [self.doc.sketches[s].name for s, _ in self.profiles if s in self.doc.sketches]
        if self.mode == "sweep":
            self.lbl_profiles.setText((names[0] + (f" ({len(names)} profiles)" if len(names) > 1 else ""))
                                      if names else "click a profile")
        else:
            self.lbl_profiles.setText(" → ".join(names) if names else "click the first profile")
        if self.mode == "loft":
            row = self.profile_list.currentRow()
            self.profile_list.clear()
            self.profile_list.addItems([f"{n + 1}. {self.doc.sketches[s].name}: profile {i + 1}"
                                       for n, (s, i) in enumerate(self.profiles)])
            self.profile_list.setCurrentRow(min(max(row, 0), len(self.profiles) - 1))
        self.changed.emit()

    def add_profile(self):
        ref = self.profile_choice.currentData()
        if ref is not None and ref not in self.profiles:
            self.set_profiles([*self.profiles, ref])
            self.profile_list.setCurrentRow(len(self.profiles) - 1)

    def remove_profile(self):
        row = self.profile_list.currentRow()
        if row >= 0:
            self.set_profiles(self.profiles[:row] + self.profiles[row + 1:])

    def move_profile(self, delta):
        row = self.profile_list.currentRow()
        dest = row + delta
        if 0 <= row < len(self.profiles) and 0 <= dest < len(self.profiles):
            profiles = list(self.profiles)
            profiles[row], profiles[dest] = profiles[dest], profiles[row]
            self.set_profiles(profiles)
            self.profile_list.setCurrentRow(dest)

    def set_active(self, target: str):
        """Which selection the next click in the view goes to: "profile" or "path"."""
        self.active = target if self.mode == "sweep" else ("path" if self.mode == "pipe" else "profile")
        self.btn_profile.setChecked(self.active == "profile")
        self.btn_path.setChecked(self.active == "path")
        self.active_changed.emit(self.active)

    def set_path(self, sketch_id: str, entity_id: str) -> bool:
        sketch = self.doc.sketches.get(sketch_id)
        ids = path_chain(sketch, entity_id) if sketch is not None else []
        if not ids:
            return False
        self.path_ref = (sketch_id, ids)
        self.lbl_path.setText(f"{sketch.name}: {len(ids)} element{'s' if len(ids) != 1 else ''}")
        self.changed.emit()
        return True

    def set_edge_path(self, refs) -> None:
        """Body edges as the path (picked like Fillet edges); none = no path."""
        from omacad.model.features.sweep import EDGES
        self.path_ref = (EDGES, list(refs)) if refs else None
        self.lbl_path.setText(f"{len(refs)} edge{'s' if len(refs) != 1 else ''}" if refs else
                              "click an edge, a line, arc or circle")
        self.changed.emit()

    def path(self):
        return self.path_ref

    def operation(self) -> str:
        return OPERATIONS[max(self.cmb_op.currentIndex(), 0)][0]

    def get_expressions(self) -> dict:
        out = {}
        for key, spin in (("diameter", self.spn_diam), ("thickness", self.spn_thick), ("twist", self.spn_twist)):
            e = spin.expression()
            if e:
                out[key] = e
        return out
