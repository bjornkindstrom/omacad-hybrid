"""Surface Texture: one panel for the textures of a body's surface. Cells and Knurl work on faces picked in the viewport,
Wavy Slices on a whole body. The types stay separate steps in the history, so saved files keep loading as they are."""

from typing import Any, Dict, Tuple
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from omacad.model.document import Document
from omacad.model.features.honeycomb import SHAPES, HoneycombFeature
from omacad.model.features.knurl import PATTERNS, apply_knurl
from omacad.model.features.wavy_slices import slice_body
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.dialogs.offset_face_dlg import FacePickMixin

# The step type of each texture and its name in the panel
TEXTURES = {"honeycomb": "Cells", "knurl": "Knurl", "wavy_slices": "Wavy Slices"}
BODY_TEXTURES = ("wavy_slices",)        # work on a whole body; the others on picked faces

HINTS = {
    "honeycomb": "Click flat faces and round faces (cylinders, inside or out) of one body in the viewport; click again to "
                 "deselect. Through cuts to the air behind each cell, so a box wall is pierced but the wall opposite is not.",
    "knurl": "Click outer round faces of one body in the viewport; click again to deselect.",
    "wavy_slices": "Click a body in the viewport or choose it here. It is rebuilt as stacked layers along Z.",
}


def outer_round(ref: dict) -> bool:
    return ref.get("kind") == "cylinder" and not ref.get("internal")


def preview_texture(kind: str, manifold, faces, params: Dict[str, Any]) -> Tuple[Any, str]:
    """The body with the texture on it, and a line for the panel. Raises ValueError for values that give no body."""
    if kind == "honeycomb":
        result, cells, skipped = HoneycombFeature.compute(manifold, faces, params)
        note = f" {skipped} face(s) have no room for a cell." if skipped else ""
        return result, f"{cells} cells will be cut.{note}"
    if kind == "knurl":
        result, teeth, notes = apply_knurl(manifold, faces, params)
        return result, " ".join(([f"{teeth} teeth per turn."] if teeth else []) + notes)
    return slice_body(manifold, params["waves"], params["slice_height"], params["amplitude"], params["phase_shift"],
                      params["offset"]), ""


class _Page(QWidget):
    """The settings of one texture: expression fields in `spins`, read and loaded by key."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.spins: Dict[str, ExprDoubleSpinBox] = {}
        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.form)

    def field(self, key, label, low, high, decimals, suffix, default, tip) -> ExprDoubleSpinBox:
        spin = ExprDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        spin.setValue(default)
        spin.setToolTip(tip)
        spin.valueChanged.connect(lambda *_: self.changed.emit())
        self.form.addRow(label, spin)
        self.spins[key] = spin
        return spin

    def params(self) -> Dict[str, Any]:
        return {key: spin.value() for key, spin in self.spins.items()}

    def load(self, feature) -> None:
        for key, spin in self.spins.items():
            spin.setValue(getattr(feature, key))
            if feature.exprs.get(key):
                spin.set_expression(feature.exprs[key])

    def get_expressions(self) -> Dict[str, str]:
        return {key: spin.expression() for key, spin in self.spins.items() if spin.expression()}


class _CellsPage(_Page):
    def __init__(self):
        super().__init__()
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems([s.title() for s in SHAPES])
        self.form.addRow("Shape:", self.cmb_shape)
        self.field("size", "Cell size:", 0.1, 10000, 2, " mm", 6.0,
                   "Width of a cell across its flats (a circle's diameter, a Voronoi cell's average width).")
        self.field("wall", "Wall:", 0.0, 10000, 2, " mm", 1.5, "Material left between two cells.")
        self.field("margin", "Margin to edge:", 0.0, 10000, 2, " mm", 3.0, "Distance kept to the face's edges and to holes already in it.")
        self.chk_through = QCheckBox("Through")
        self.chk_through.setChecked(True)
        self.chk_through.setToolTip("Each cell goes through to the air behind it (the far wall of a box stays whole).")
        self.form.addRow("", self.chk_through)
        self.field("depth", "Depth:", 0.01, 10000, 2, " mm", 1.0, "How deep the cells go into the face.")
        self.field("angle", "Rotation:", -360, 360, 2, " °", 0.0, "Turns the pattern on the face. Round faces take steps of 90°, "
                   "so the pattern closes all the way round (Voronoi is not turned there).")
        self.chk_partial = QCheckBox("Cut edge cells")
        self.chk_partial.setToolTip("Cells that cross the margin are cut off by it (pieces under a quarter are left out). "
                                    "Off: whole cells only.")
        self.form.addRow("", self.chk_partial)
        randomness = self.field("randomness", "Randomness:", 0.0, 100.0, 2, " %", 100.0,
                                "How far the Voronoi cells stray from a regular pattern. 0 % gives hexagons.")
        seed = self.field("seed", "Seed:", 0.0, 999999.0, 0, "", 1.0, "Picks another random layout with the same settings.")
        self.voronoi_widgets = [w for spin in (randomness, seed) for w in (self.form.labelForField(spin), spin)]
        self.chk_through.toggled.connect(self._sync)
        self.cmb_shape.currentIndexChanged.connect(self._sync)
        for signal in (self.chk_through.toggled, self.chk_partial.toggled, self.cmb_shape.currentIndexChanged):
            signal.connect(lambda *_: self.changed.emit())
        self._sync()

    def _sync(self, *_):
        self.spins["depth"].setEnabled(not self.chk_through.isChecked())
        voronoi = SHAPES[self.cmb_shape.currentIndex()] == "voronoi"
        for widget in self.voronoi_widgets:     # not setRowVisible: docking moves each field into a slider widget, which follows the field
            widget.setVisible(voronoi)

    def params(self):
        return {**super().params(), "shape": SHAPES[self.cmb_shape.currentIndex()],
                "through": self.chk_through.isChecked(), "partial": self.chk_partial.isChecked()}

    def load(self, feature):
        self.cmb_shape.setCurrentIndex(SHAPES.index(feature.shape))
        super().load(feature)
        self.chk_through.setChecked(feature.through)
        self.chk_partial.setChecked(feature.partial)


class _KnurlPage(_Page):
    def __init__(self):
        super().__init__()
        self.cmb_pattern = QComboBox()
        self.cmb_pattern.addItems([p.title() for p in PATTERNS])
        self.form.addRow("Pattern:", self.cmb_pattern)
        self.field("pitch", "Pitch:", 0.1, 100.0, 2, " mm", 1.5, "Distance between grooves round the face. It is adjusted a little so whole teeth fit.")
        self.field("depth", "Depth:", 0.01, 100.0, 2, " mm", 0.6, "How deep the grooves go into the face.")
        self.field("angle", "Angle:", 1.0, 80.0, 2, " °", 30.0, "Slant of the grooves from the axis. Straight grooves have none.")
        self.field("margin", "Margin to ends:", 0.0, 10000.0, 2, " mm", 0.0, "Plain length left at both ends of the face.")
        self.cmb_pattern.currentIndexChanged.connect(self._sync)
        self.cmb_pattern.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self._sync()

    def _sync(self, *_):
        self.spins["angle"].setEnabled(PATTERNS[self.cmb_pattern.currentIndex()] != "straight")

    def params(self):
        return {"pattern": PATTERNS[self.cmb_pattern.currentIndex()], **super().params()}

    def load(self, feature):
        self.cmb_pattern.setCurrentIndex(PATTERNS.index(feature.pattern))
        super().load(feature)


class _WavyPage(_Page):
    def __init__(self):
        super().__init__()
        self.field("waves", "Total Waves:", 1, 500, 0, "", 12, "Whole wave cycles around each slice's outline")
        self.field("slice_height", "Slice Height:", 0.1, 500.0, 2, " mm", 2.0, "Height of each layer")
        self.field("amplitude", "Max Wave Amplitude:", 0.0, 200.0, 2, " mm", 2.0, "Peak-to-peak size of the wave. 0 gives plain steps")
        self.field("phase_shift", "Wave Phase Shift:", -360.0, 360.0, 1, "°", 15.0,
                   "How far each slice's wave moves from the slice below. 360° is one whole wave")
        self.field("offset", "Offset:", -200.0, 200.0, 2, " mm", 0.0, "Moves the outline first: + outward, − inward")

    def params(self):
        values = super().params()
        values["waves"] = int(round(values["waves"]))
        return values


class SurfaceTextureDialog(FacePickMixin, BaseFeatureDialog):
    """The type is chosen at the top and only its settings show. Editing a step keeps the step's type."""

    changed = Signal()
    kind_changed = Signal(str)

    def __init__(self, doc: Document, parent=None, feature=None, kind: str = "honeycomb", body_id: str = "",
                 embedded: bool = False):
        super().__init__("Surface Texture", parent, embedded)
        self.faces, self.body_id = [], ""
        self._editing = feature is not None
        self.kinds = list(TEXTURES)
        self.body_ids = list(doc.bodies.keys())

        form = QFormLayout()
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItems(list(TEXTURES.values()))
        self.cmb_kind.setEnabled(not self._editing)
        form.addRow("Type:", self.cmb_kind)
        self.main_layout.addLayout(form)

        self.lbl_count = QLabel("")
        self.lbl_count.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_count)

        self.target_row = QWidget()
        target_form = QFormLayout(self.target_row)
        target_form.setContentsMargins(0, 0, 0, 0)
        self.cmb_target = QComboBox()
        self.cmb_target.addItems([doc.bodies[bid].name for bid in self.body_ids])
        target_form.addRow("Target Body:", self.cmb_target)
        self.main_layout.addWidget(self.target_row)

        self.pages = {"honeycomb": _CellsPage(), "knurl": _KnurlPage(), "wavy_slices": _WavyPage()}
        for page in self.pages.values():
            page.changed.connect(self.changed)
            self.main_layout.addWidget(page)

        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_info)
        self.btn_clear = QPushButton("Clear selection")
        self.btn_clear.setAutoDefault(False)
        self.btn_clear.clicked.connect(self.clear)
        self.main_layout.addWidget(self.btn_clear)
        self.add_buttons()

        first = body_id or next(iter(doc.selected_body_ids), "")
        if feature is not None:
            kind, first = feature.feature_type, feature.target_body_id
            self.faces, self.body_id = list(getattr(feature, "faces", [])), feature.target_body_id
            self.pages[kind].load(feature)
        self.select_body(first)
        self.cmb_kind.setCurrentIndex(self.kinds.index(kind))
        self._show_kind()
        self.cmb_kind.currentIndexChanged.connect(self._kind_switched)
        self.cmb_target.currentIndexChanged.connect(lambda *_: self.changed.emit())

    def kind(self) -> str:
        return self.kinds[self.cmb_kind.currentIndex()]

    @property
    def page(self) -> _Page:
        return self.pages[self.kind()]

    def _show_kind(self):
        kind = self.kind()
        for key, page in self.pages.items():
            page.setVisible(key == kind)
        on_body = kind in BODY_TEXTURES
        self.target_row.setVisible(on_body and not self._editing)
        self.btn_clear.setVisible(not on_body and not self._editing)
        self.lbl_info.setText("")
        self._update_count()

    def _kind_switched(self, *_):
        if self.kind() == "knurl":          # only outer round faces take a knurl
            self.faces = [f for f in self.faces if outer_round(f)]
            self.body_id = self.body_id if self.faces else ""
        elif self.kind() in BODY_TEXTURES and self.body_id:
            self.select_body(self.body_id)
        self._show_kind()
        self.kind_changed.emit(self.kind())
        self.changed.emit()

    def _update_count(self):
        if self._editing:
            self.lbl_count.setVisible(False)
            return
        n = len(self.faces)
        counted = n and self.kind() not in BODY_TEXTURES
        self.lbl_count.setText(f"{n} face{'s' if n != 1 else ''} selected. Click faces to add or remove them."
                               if counted else HINTS[self.kind()])

    def select_body(self, body_id: str) -> None:
        if body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(body_id))

    def on_body_clicked(self, body_id: str) -> None:
        if self.kind() in BODY_TEXTURES:
            self.select_body(body_id)

    def target_body_id(self) -> str:
        if self.kind() not in BODY_TEXTURES:
            return self.body_id
        index = self.cmb_target.currentIndex()
        return self.body_ids[index] if 0 <= index < len(self.body_ids) else ""

    def params(self) -> Dict[str, Any]:
        return self.page.params()

    def get_expressions(self) -> Dict[str, str]:
        return self.page.get_expressions()
