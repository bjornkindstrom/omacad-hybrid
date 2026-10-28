"""Dialog for Honeycomb: pick flat and round faces in the viewport, choose the cell shape and its sizes."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton
from omacad.model.features.honeycomb import SHAPES
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.dialogs.offset_face_dlg import FacePickMixin

HINT = ("Click flat faces and round faces (cylinders, inside or out) of one body in the viewport; click again to "
        "deselect. Through cuts to the air behind each cell, so a box wall is pierced but the wall opposite is not.")


class HoneycombDialog(FacePickMixin, BaseFeatureDialog):
    """Honeycomb: the faces are picked in the viewport, the cells are set here."""

    changed = Signal()
    FIELDS = ("size", "wall", "margin", "depth", "angle")

    def __init__(self, parent=None, feature=None, embedded: bool = False):
        super().__init__("Honeycomb", parent, embedded)
        self.faces, self.body_id = [], ""
        editing = feature is not None
        form = QFormLayout()
        self.cmb_shape = QComboBox()
        self.cmb_shape.addItems([s.title() for s in SHAPES])
        form.addRow("Shape:", self.cmb_shape)

        def spin(lo, hi, value, suffix, tip):
            s = ExprDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(2)
            s.setSuffix(suffix)
            s.setValue(value)
            s.setToolTip(tip)
            return s

        self.spn_size = spin(0.1, 10000, 6.0, " mm", "Width of a cell across its flats (a circle's diameter).")
        self.spn_wall = spin(0.0, 10000, 1.5, " mm", "Material left between two cells.")
        self.spn_margin = spin(0.0, 10000, 3.0, " mm", "Distance kept to the face's edges and to holes already in it.")
        self.chk_through = QCheckBox("Through")
        self.chk_through.setChecked(True)
        self.chk_through.setToolTip("Each cell goes through to the air behind it (the far wall of a box stays whole).")
        self.spn_depth = spin(0.01, 10000, 1.0, " mm", "How deep the cells go into the face.")
        self.spn_angle = spin(-360, 360, 0.0, " °", "Turns the pattern on the face. Round faces take steps of 90°, "
                              "so the pattern closes all the way round.")
        self.chk_partial = QCheckBox("Cut edge cells")
        self.chk_partial.setToolTip("Cells that cross the margin are cut off by it (pieces under a quarter are left out). "
                                    "Off: whole cells only.")
        form.addRow("Cell size:", self.spn_size)
        form.addRow("Wall:", self.spn_wall)
        form.addRow("Margin to edge:", self.spn_margin)
        form.addRow("", self.chk_through)
        form.addRow("Depth:", self.spn_depth)
        form.addRow("Rotation:", self.spn_angle)
        form.addRow("", self.chk_partial)
        self.lbl_count = QLabel("" if editing else HINT)
        self.lbl_count.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_count)
        self.main_layout.addLayout(form)
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_info)
        if not editing:
            btn = QPushButton("Clear selection")
            btn.setAutoDefault(False)
            btn.clicked.connect(self.clear)
            self.main_layout.addWidget(btn)
        self.add_buttons()
        if feature is not None:
            self.load(feature)
        self.spn_depth.setEnabled(not self.chk_through.isChecked())
        self.chk_through.toggled.connect(lambda on: self.spn_depth.setEnabled(not on))
        self.cmb_shape.currentIndexChanged.connect(lambda *_: self.changed.emit())
        for w in (self.spn_size, self.spn_wall, self.spn_margin, self.spn_depth, self.spn_angle):
            w.valueChanged.connect(lambda *_: self.changed.emit())
        for w in (self.chk_through, self.chk_partial):
            w.toggled.connect(lambda *_: self.changed.emit())

    def _spins(self):
        return dict(zip(self.FIELDS, (self.spn_size, self.spn_wall, self.spn_margin, self.spn_depth, self.spn_angle)))

    def load(self, f):
        self.faces, self.body_id = list(f.faces), f.target_body_id
        self.cmb_shape.setCurrentIndex(SHAPES.index(f.shape))
        for key, s in self._spins().items():
            s.setValue(getattr(f, key))
            if f.exprs.get(key):
                s.set_expression(f.exprs[key])
        self.chk_through.setChecked(f.through)
        self.chk_partial.setChecked(f.partial)

    def _update_count(self):
        n = len(self.faces)
        self.lbl_count.setText(f"{n} face{'s' if n != 1 else ''} selected. Click faces to add or remove them." if n else HINT)

    def params(self) -> dict:
        out = {key: s.value() for key, s in self._spins().items()}
        out.update(shape=SHAPES[self.cmb_shape.currentIndex()], through=self.chk_through.isChecked(),
                   partial=self.chk_partial.isChecked())
        return out

    def get_expressions(self) -> dict:
        return {key: s.expression() for key, s in self._spins().items() if s.expression()}
