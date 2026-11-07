"""Surface Texture: one panel for the textures of a body's surface. Cells, Knurl and Japandi work on faces picked in the viewport,
Wavy Slices on a whole body. The types stay separate steps in the history, so saved files keep loading as they are."""

from typing import Any, Dict, Tuple
from pathlib import Path
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
from omacad.model.document import Document
from omacad.model.features.cell_patterns import HOLE_SHAPES, MAX_RELAXATION, VORONOI_STYLES
from omacad.model.features.honeycomb import SHAPES, HoneycombFeature
from omacad.model.features.japandi import DIRECTIONS, RIMS, HEIGHTS as RIB_HEIGHTS, PATHS as RIB_PATHS, SHAPES as RIB_SHAPES, apply_japandi
from omacad.model.features.knurl import PATTERNS, apply_knurl
from omacad.model.features.wavy_slices import slice_body
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.dialogs.offset_face_dlg import FacePickMixin

# The step type of each texture and its name in the panel
TEXTURES = {"honeycomb": "Cells", "knurl": "Knurl", "japandi": "Japandi", "wavy_slices": "Wavy Slices"}
BODY_TEXTURES = ("wavy_slices",)        # work on a whole body; the others on picked faces
OUTER_ROUND_TEXTURES = ("knurl", "japandi")   # take outer round or curved faces

HINTS = {
    "honeycomb": "Click flat, cylindrical or curved faces of one body in the viewport; click again to "
                 "deselect. Through cuts to the air behind each cell, so a box wall is pierced but the wall opposite is not.",
    "knurl": "Click outer round or curved faces of one body in the viewport; click again to deselect.",
    "japandi": "Click outer round or curved faces of one body in the viewport, straight or curved like a vase; click again to deselect.",
    "wavy_slices": "Click a body in the viewport or choose it here. It is rebuilt as stacked layers along Z.",
}


def outer_round(ref: dict) -> bool:
    return (ref.get("kind") == "cylinder" and not ref.get("internal")) or ref.get("kind") == "surface"


def preview_texture(kind: str, manifold, faces, params: Dict[str, Any]) -> Tuple[Any, str]:
    """The body with the texture on it, and a line for the panel. Raises ValueError for values that give no body."""
    if kind == "honeycomb":
        result, cells, skipped = HoneycombFeature.compute(manifold, faces, params)
        note = f" {skipped} face(s) got no cells: no room for one, or too many (use a larger size)." if skipped else ""
        return result, f"{cells} cells will be cut.{note}"
    if kind == "knurl":
        result, teeth, notes = apply_knurl(manifold, faces, params)
        return result, " ".join(([f"{teeth} teeth per turn."] if teeth else []) + notes)
    if kind == "japandi":
        result, ribs, notes = apply_japandi(manifold, faces, params)
        return result, " ".join(([f"{ribs} ribs per turn."] if ribs else []) + notes)
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
        self.cmb_shape.addItems([s.upper() if s == "svg" else s.title() for s in SHAPES])
        self.form.addRow("Shape:", self.cmb_shape)

        self.svg_row = QWidget()
        svg_layout = QHBoxLayout(self.svg_row)
        svg_layout.setContentsMargins(0, 0, 0, 0)
        self.txt_svg_path = QLineEdit()
        self.txt_svg_path.setPlaceholderText("Select SVG file…")
        self.btn_browse_svg = QPushButton("Browse…")
        self.btn_browse_svg.setAutoDefault(False)
        self.btn_browse_svg.clicked.connect(self._browse_svg)
        svg_layout.addWidget(self.txt_svg_path)
        svg_layout.addWidget(self.btn_browse_svg)
        self.lbl_svg = QLabel("SVG File:")
        self.form.addRow(self.lbl_svg, self.svg_row)
        self.cmb_style = QComboBox()
        self.cmb_style.addItems([s.title() for s in VORONOI_STYLES])
        self.cmb_style.setToolTip("Even: one size. Gradient: from Smallest cell to Cell size across the face. Hotspot: small cells "
                                  "round points. Radial: rings and spokes. Nested: big cells split into small ones. "
                                  "Triangles: the triangles between the sites, also from small to large.")
        self.lbl_style = QLabel("Style:")
        self.form.addRow(self.lbl_style, self.cmb_style)
        self.field("size", "Cell size:", 0.1, 10000, 2, " mm", 6.0,
                   "Width of a cell across its flats (a circle's diameter, a Voronoi cell's average width).")
        self.field("fine_size", "Smallest cell:", 0.1, 10000, 2, " mm", 2.0, "The smallest cells of the style; Cell size sets the largest.")
        self.field("wall", "Wall:", 0.0, 10000, 2, " mm", 1.5, "Material left between two cells.")
        self.field("inner_wall", "Inner wall:", 0.0, 10000, 2, " mm", 0.8, "Material between the small cells inside a big one.")
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
        self.field("hotspots", "Hotspots:", 1, 12, 0, "", 1, "Points the small cells gather round: the face's middle first, the rest from the seed.")
        self.field("randomness", "Randomness:", 0.0, 100.0, 2, " %", 100.0,
                   "How far the Voronoi cells stray from a regular pattern. 0 % gives hexagons.")
        self.field("random_rotation", "Random rotation:", 0.0, 180.0, 2, " °", 0.0,
                   "Turns each SVG cell by a random angle up to this far either way. 180° points them anywhere. "
                   "The grid widens so turned cells keep the wall between them.")
        self.field("seed", "Seed:", 0.0, 999999.0, 0, "", 1.0, "Picks another random layout with the same settings.")
        self.field("relaxation", "Relaxation:", 0, MAX_RELAXATION, 0, "", 0, "Evens the Voronoi cells out, a little more each step. 0 keeps them as they fell.")
        self.cmb_hole = QComboBox()
        self.cmb_hole.addItems([h.title() for h in HOLE_SHAPES])
        self.cmb_hole.setToolTip("Cell: the hole follows its cell. The others put that shape in the largest circle that fits the cell.")
        self.form.addRow("Hole shape:", self.cmb_hole)
        self.field("rounding", "Rounding:", 0.0, 100.0, 0, " %", 0.0, "Rounds each cell's corners. 100 % is close to a round hole.")
        self.field("opening", "Opening:", 0.0, 100.0, 0, " %", 100.0, "Size of each hole in its cell, at the start of the face: "
                   "the bottom, or a hotspot's middle. A smaller hole leaves a thicker wall.")
        self.field("opening_end", "Opening at end:", 0.0, 100.0, 0, " %", 100.0, "The same at the far end, so the holes fade across the face.")
        BaseFeatureDialog.pair_form_rows(self.form, [
            (self.cmb_shape, self.cmb_style),
            (self.spins["size"], self.spins["wall"]),
            (self.spins["fine_size"], self.spins["inner_wall"]),
            (self.spins["margin"], self.spins["angle"]),
            (self.chk_through, self.chk_partial),
            (self.spins["randomness"], self.spins["seed"]),
            (self.spins["relaxation"], self.spins["hotspots"]),
            (self.cmb_hole, self.spins["rounding"]),
            (self.spins["opening"], self.spins["opening_end"])])
        # not setRowVisible: docking moves each field into a slider widget, which follows the field
        self.toggled = {key: [self.form.labelForField(self.spins[key]), self.spins[key]]
                        for key in ("fine_size", "inner_wall", "hotspots", "randomness", "random_rotation", "seed", "relaxation")}
        self.toggled["style"] = [self.lbl_style, self.cmb_style]
        self.toggled["svg"] = [self.lbl_svg, self.svg_row]
        self.chk_through.toggled.connect(self._sync)
        self.cmb_shape.currentIndexChanged.connect(self._sync)
        self.cmb_style.currentIndexChanged.connect(self._sync)
        self.txt_svg_path.textChanged.connect(lambda *_: self.changed.emit())
        for signal in (self.chk_through.toggled, self.chk_partial.toggled, self.cmb_shape.currentIndexChanged,
                       self.cmb_style.currentIndexChanged, self.cmb_hole.currentIndexChanged):
            signal.connect(lambda *_: self.changed.emit())
        self._sync()

    def _browse_svg(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Select SVG Pattern", "", "SVG Files (*.svg)")
        if fpath:
            self.txt_svg_path.setText(fpath)
            self.changed.emit()

    def _sync(self, *_):
        self.spins["depth"].setEnabled(not self.chk_through.isChecked())
        shape = SHAPES[self.cmb_shape.currentIndex()]
        voronoi = shape == "voronoi"
        is_svg = shape == "svg"
        style = VORONOI_STYLES[self.cmb_style.currentIndex()]
        shown = {"style": voronoi, "randomness": voronoi, "random_rotation": is_svg, "seed": voronoi or is_svg,
                 "relaxation": voronoi and style != "radial",
                 "fine_size": voronoi and style != "even" , "inner_wall": voronoi and style == "nested",
                 "hotspots": voronoi and style == "hotspot", "svg": is_svg}
        for key, widgets in self.toggled.items():
            for widget in widgets:
                widget.setVisible(shown[key])

    def params(self):
        return {**super().params(), "shape": SHAPES[self.cmb_shape.currentIndex()], "style": VORONOI_STYLES[self.cmb_style.currentIndex()],
                "hole": HOLE_SHAPES[self.cmb_hole.currentIndex()], "svg_path": self.txt_svg_path.text().strip(),
                "through": self.chk_through.isChecked(), "partial": self.chk_partial.isChecked()}

    def load(self, feature):
        self.cmb_shape.setCurrentIndex(SHAPES.index(feature.shape))
        self.cmb_style.setCurrentIndex(VORONOI_STYLES.index(feature.style))
        self.cmb_hole.setCurrentIndex(HOLE_SHAPES.index(feature.hole))
        self.txt_svg_path.setText(getattr(feature, "svg_path", ""))
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
        BaseFeatureDialog.pair_form_rows(self.form, [
            (self.spins["pitch"], self.spins["depth"]),
            (self.spins["angle"], self.spins["margin"])])
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


class _JapandiPage(_Page):
    def __init__(self):
        super().__init__()
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems([s.capitalize() for s in RIB_SHAPES])
        self.form.addRow("Shape:", self.cmb_shape)
        self.cmb_direction = QComboBox()
        self.cmb_direction.addItems([d.capitalize() for d in DIRECTIONS])
        self.cmb_direction.setToolTip("Outward: ribs stand on the face. Inward: grooves are cut into it.")
        self.form.addRow("Direction:", self.cmb_direction)
        self.field("radius", "Half-circle radius:", 0.05, 100.0, 2, " mm", 1.5, "Radius of each half-round rib, at the widest part of the face.")
        self.field("width", "Width:", 0.05, 100.0, 2, " mm", 2.0, "Width of each rib or groove, at the widest part of the face.")
        self.field("depth", "Depth:", 0.01, 100.0, 2, " mm", 2.0, "How far each rib stands out, or each groove goes in.")
        self.field("spacing", "Spacing:", 0.0, 100.0, 2, " mm", 0.0, "Distance between two ribs. It is adjusted a little so whole ribs fit.")
        self.field("twist", "Twist:", -3600.0, 3600.0, 1, " °", 0.0, "How far the ribs turn from one end of the face to the other.")
        self.field("margin", "Margin to ends:", 0.0, 10000.0, 2, " mm", 0.0, "Plain length left at both ends of the face.")
        self.cmb_rim = QComboBox()
        self.cmb_rim.addItems(["None", "Straight", "Chamfer", "Round"])
        self.cmb_rim.setToolTip("A continuous raised lip in the margin at both ends, following the whole selected wall.")
        self.form.addRow("End rim:", self.cmb_rim)
        self.field("rim_depth", "Rim projection:", 0.01, 100., 2, " mm", 2., "How far the lip projects from the wall. Margin to ends sets its height.")
        self.chk_rim_inside = QCheckBox("Also inside opening")
        self.chk_rim_inside.setToolTip("Extend a round lip into the opening of a hollow body as well.")
        self.form.addRow(self.chk_rim_inside)
        self.chk_rim_follow = QCheckBox("Meet rib ends")
        self.chk_rim_follow.setToolTip("Keep the rim smooth and meet the outward rib crests at both ends.")
        self.form.addRow(self.chk_rim_follow)
        self.chk_rim_follow.toggled.connect(lambda *_: self.changed.emit())
        self.cmb_rim.currentIndexChanged.connect(self._sync)
        self.chk_rim_inside.toggled.connect(lambda *_: self.changed.emit())
        self.cmb_path = QComboBox()
        self.cmb_path.addItems([p.capitalize() for p in RIB_PATHS])
        self.cmb_path.setToolTip("Straight: the ribs run straight along the face. Curve: each rib bows to one side in a single arc. "
                                 "Wave: each rib snakes from side to side.")
        self.form.addRow("Rib path:", self.cmb_path)
        self.field("bend", "Bend:", -360.0, 360.0, 1, " °", 20.0, "How far round the face the ribs swing at most. A negative value bends them the other way.")
        self.field("waves", "Waves:", 0.5, 100.0, 1, "", 2.0, "Whole waves from one end of the ribs to the other.")
        self.cmb_height = QComboBox()
        self.cmb_height.addItems([h.capitalize() for h in RIB_HEIGHTS])
        self.cmb_height.setToolTip("Even: the ribs have the same height all along. Arch: seen from the side they follow one arc, "
                                   "low at both ends and highest in the middle.")
        self.form.addRow("Rib height:", self.cmb_height)
        self.field("end_height", "End height:", 1.0, 100.0, 0, " %", 20.0, "Height at both ends of the ribs, as a share of the height in the middle.")
        BaseFeatureDialog.pair_form_rows(self.form, [
            (self.cmb_rim, self.spins["rim_depth"]),
            (self.cmb_height, self.spins["end_height"]),
            (self.cmb_shape, self.cmb_direction),
            (self.spins["width"], self.spins["depth"]),
            (self.spins["radius"], self.spins["spacing"]),
            (self.spins["twist"], self.spins["margin"]),
            (self.spins["bend"], self.spins["waves"])])
        # not setRowVisible: docking moves each field into a slider widget, which follows the field
        self.toggled = {key: [self.form.labelForField(self.spins[key]), self.spins[key]] for key in ("radius", "width", "depth", "bend", "waves", "end_height", "rim_depth")}
        self.cmb_direction.currentIndexChanged.connect(self._sync)
        self.cmb_shape.currentIndexChanged.connect(self._sync)
        self.cmb_path.currentIndexChanged.connect(self._sync)
        self.cmb_height.currentIndexChanged.connect(self._sync)
        for combo in (self.cmb_shape, self.cmb_direction, self.cmb_path, self.cmb_height, self.cmb_rim):
            combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self._sync()

    def _sync(self, *_):
        half_round = RIB_SHAPES[self.cmb_shape.currentIndex()] == "half-round"
        path = RIB_PATHS[self.cmb_path.currentIndex()]
        for key, shown in (("radius", half_round), ("width", not half_round), ("depth", not half_round),
                           ("bend", path != "straight"), ("waves", path == "wave"),
                           ("end_height", RIB_HEIGHTS[self.cmb_height.currentIndex()] == "arch"),
                           ("rim_depth", self.cmb_rim.currentIndex() != 0)):
            for widget in self.toggled[key]:
                widget.setVisible(shown)
        self.chk_rim_follow.setVisible(RIMS[self.cmb_rim.currentIndex()] in ("chamfer", "round") and DIRECTIONS[self.cmb_direction.currentIndex()] == "outward")
        self.chk_rim_inside.setVisible(RIMS[self.cmb_rim.currentIndex()] == "round")

    def params(self):
        return {"shape": RIB_SHAPES[self.cmb_shape.currentIndex()], "direction": DIRECTIONS[self.cmb_direction.currentIndex()],
                "path": RIB_PATHS[self.cmb_path.currentIndex()],
                "height_profile": RIB_HEIGHTS[self.cmb_height.currentIndex()],
                "rim": RIMS[self.cmb_rim.currentIndex()], "rim_inside": self.chk_rim_inside.isChecked(), "rim_follow": self.chk_rim_follow.isChecked(), **super().params()}

    def load(self, feature):
        self.cmb_shape.setCurrentIndex(RIB_SHAPES.index(feature.shape))
        self.cmb_direction.setCurrentIndex(DIRECTIONS.index(feature.direction))
        self.cmb_path.setCurrentIndex(RIB_PATHS.index(feature.path))
        self.cmb_height.setCurrentIndex(RIB_HEIGHTS.index(feature.height_profile))
        self.cmb_rim.setCurrentIndex(RIMS.index(feature.rim))
        self.chk_rim_inside.setChecked(feature.rim_inside)
        self.chk_rim_follow.setChecked(feature.rim_follow)
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
        BaseFeatureDialog.pair_form_rows(self.form, [
            (self.spins["waves"], self.spins["slice_height"]),
            (self.spins["amplitude"], self.spins["phase_shift"])])

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
        self.face_bodies = []
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

        self.pages = {"honeycomb": _CellsPage(), "knurl": _KnurlPage(), "japandi": _JapandiPage(), "wavy_slices": _WavyPage()}
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
            self.face_bodies = [feature.target_body_id] * len(self.faces)
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

    def toggle(self, ref: dict, body_id: str) -> bool:
        """Adds the face (or removes it when already picked), even across multiple bodies like a Jar and its Lid."""
        if len(self.face_bodies) != len(self.faces):
            self.face_bodies = [self.body_id] * len(self.faces)
        for i, (f, bid) in enumerate(zip(self.faces, self.face_bodies)):
            if bid == body_id and self._same(f, ref):
                self.faces.pop(i)
                self.face_bodies.pop(i)
                break
        else:
            self.faces.append(ref)
            self.face_bodies.append(body_id)
        self.body_id = self.face_bodies[0] if self.faces else ""
        self._update_count()
        self.changed.emit()
        return True

    def clear(self):
        self.faces, self.face_bodies, self.body_id = [], [], ""
        self._update_count()
        self.changed.emit()

    def faces_per_body(self):
        if not self.faces:
            return []
        if len(self.face_bodies) != len(self.faces):
            return [(self.body_id, list(self.faces))] if self.body_id else []
        order = list(dict.fromkeys(self.face_bodies))
        return [(bid, [f for f, b in zip(self.faces, self.face_bodies) if b == bid]) for bid in order if bid]

    def _kind_switched(self, *_):
        if self.kind() in OUTER_ROUND_TEXTURES:
            if len(self.face_bodies) != len(self.faces):
                self.face_bodies = [self.body_id] * len(self.faces)
            kept = [(f, b) for f, b in zip(self.faces, self.face_bodies) if outer_round(f)]
            self.faces = [f for f, _ in kept]
            self.face_bodies = [b for _, b in kept]
            self.body_id = self.face_bodies[0] if self.faces else ""
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
