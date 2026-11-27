"""Panel for the Lithophane primitive."""

import base64
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QLabel, QPushButton

import numpy as np

from omacad.model.features.lithophane import LithophaneFeature, encode_picture
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.expr_spin import ExprDoubleSpinBox


class LithophaneDialog(BaseFeatureDialog):
    changed = Signal()

    SPINS = (  # key, label, low, high, step, suffix, shapes it belongs to, tip
        ("width", "Width:", 5, 2000, 5, " mm", ("flat",), "Width of the plate, frame included."),
        ("radius", "Radius:", 5, 1000, 1, " mm", ("cylinder", "sphere"), "Outer radius where the wall is thickest."),
        ("arc", "Arc:", 5, 360, 15, "°", ("cylinder", "sphere"), "How far round the picture goes."),
        ("height", "Height:", 5, 2000, 5, " mm", ("flat", "cylinder"), "Height, frame included."),
        ("lat_span", "Picture height:", 5, 180, 10, "°", ("sphere",),
         "How much of the globe, bottom to top round the equator, the picture covers."),
        ("opening", "Bottom opening:", 0, 1000, 1, " mm", ("sphere",),
         "Diameter of the hole for the lamp (0 = closed)."),
        ("min_thickness", "Min thickness:", 0.1, 20, 0.1, " mm", None, "Wall where the picture is white."),
        ("max_thickness", "Max thickness:", 0.2, 50, 0.2, " mm", None, "Wall where the picture is black."),
        ("detail", "Detail:", 0.05, 10, 0.05, " mm", None, "Distance between points; the nozzle width is enough."),
        ("frame", "Frame:", 0, 200, 1, " mm", ("flat", "cylinder"), "Full-thickness border (0 = none); follows the outline."),
        ("corner_radius", "Corner radius:", 0, 500, 1, " mm", ("flat",), "Radius of the rounded corners."),
        ("stand", "Stand:", 0, 200, 5, " mm", ("flat",),
         "Depth of a foot the upright plate stands in (0 = none)."),
        ("sharpen", "Sharpen:", 0, 300, 10, " %", None,
         "Crisper edges and fine detail at the printed resolution."),
        ("denoise", "Denoise:", 0, 5, 0.5, " px", None, "Smooths grain and JPEG blocks before the relief is made."),
        ("brightness", "Brightness:", -100, 100, 5, "", None, ""),
        ("contrast", "Contrast:", -100, 200, 5, "", None, ""),
        ("gamma", "Gamma:", 0.2, 5, 0.1, "", None, "Above 1 lightens the midtones, below 1 darkens them."),
    )

    LIT_COLOUR = (255, 236, 200)     # a warm lamp
    LIT_BACKGROUND = (34, 36, 40)

    def __init__(self, parent=None):
        super().__init__("Lithophane", parent)
        self.image_data = ""
        defaults = {**LithophaneFeature.DEFAULTS, **LithophaneFeature.NEW_DEFAULTS}
        form = QFormLayout()
        self.form = form

        self.btn_image = QPushButton("Choose picture…")
        self.btn_image.setAutoDefault(False)
        self.btn_image.clicked.connect(self.choose_image)
        form.addRow("Picture:", self.btn_image)
        self.lbl_image = QLabel("")
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setVisible(False)
        form.addRow(self.lbl_image)

        self.cmb_shape = QComboBox()
        for label, key in (("Flat", "flat"), ("Cylinder / arc", "cylinder"), ("Sphere", "sphere")):
            self.cmb_shape.addItem(label, key)
        form.addRow("Shape:", self.cmb_shape)
        self.cmb_fit = QComboBox()
        for label, key in (("Keep proportions", "proportional"), ("Crop to fill", "crop"), ("Stretch", "stretch")):
            self.cmb_fit.addItem(label, key)
        self.cmb_fit.setToolTip("Keep proportions lets the height follow the picture (a sphere crops instead).")
        form.addRow("Fit:", self.cmb_fit)
        self.cmb_outline = QComboBox()
        for label, key in (("Rectangle", "rect"), ("Rounded corners", "rounded"), ("Circle / oval", "circle"),
                           ("Heart", "heart")):
            self.cmb_outline.addItem(label, key)
        form.addRow("Outline:", self.cmb_outline)
        self.cmb_tone = QComboBox()
        for label, key in (("Light-correct", "light"), ("Linear", "linear")):
            self.cmb_tone.addItem(label, key)
        self.cmb_tone.setCurrentIndex(self.cmb_tone.findData(defaults["tone"]))
        self.cmb_tone.setToolTip("Light-correct: the light that shines through follows the picture, so midtones "
                                 "come out as midtones (light fades exponentially in plastic). Linear: thickness "
                                 "straight from lightness, as older lithophanes were made.")
        form.addRow("Tone:", self.cmb_tone)

        self.spins = {}
        for key, label, low, high, step, suffix, _shapes, tip in self.SPINS:
            spin = ExprDoubleSpinBox()
            spin.setRange(low, high)
            spin.setDecimals(2)
            spin.setSingleStep(step)
            spin.setSuffix(suffix)
            spin.setValue(defaults[key])
            spin.setToolTip(tip)
            spin.valueChanged.connect(lambda _: self.changed.emit())
            self.spins[key] = spin
            form.addRow(label, spin)

        self.checks = {}
        for key, label, tip in (("upright", "Stand upright", "Best for printing; off = lying with the relief up."),
                                ("auto_levels", "Auto levels",
                                 "The picture's darkest and lightest parts become black and white: full contrast."),
                                ("invert", "Invert", "Light areas become thick (for a relief lit from the front)."),
                                ("mirror", "Mirror", "Flip left and right, for viewing from the back.")):
            box = QCheckBox(label)
            box.setToolTip(tip)
            box.setChecked(defaults[key])
            box.toggled.connect(lambda _: self.changed.emit())
            self.checks[key] = box
            form.addRow(box)

        for combo in (self.cmb_shape, self.cmb_fit, self.cmb_outline):
            combo.currentIndexChanged.connect(self._shape_changed)
        self.cmb_tone.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.checks["upright"].toggled.connect(self._shape_changed)
        self.main_layout.addLayout(form)
        self.lbl_lit_title = QLabel("Lit from behind:")
        self.lbl_lit = QLabel("")
        self.lbl_lit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_lit.setToolTip("How the print looks with a lamp behind it, from the same thickness the body gets.")
        for w in (self.lbl_lit_title, self.lbl_lit):
            w.setVisible(False)
            self.main_layout.addWidget(w)
        self.lbl_problem = QLabel("")
        self.lbl_problem.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_problem)
        self.add_buttons()
        self._shape_changed()

    def _shape_changed(self, *_):
        shape = self.cmb_shape.currentData()
        for key, *_rest, shapes, _tip in self.SPINS:
            on = shapes is None or shape in shapes
            if key == "height":
                on = on and self.cmb_fit.currentData() != "proportional"
            if key == "corner_radius":
                on = on and self.cmb_outline.currentData() == "rounded"
            if key == "stand":
                on = on and self.checks["upright"].isChecked()
            self._show(self.spins[key], on)
        self._show(self.checks["upright"], shape == "flat")
        self._show(self.cmb_outline, shape == "flat")
        self.changed.emit()

    def _show(self, field, on):
        field.setVisible(on)
        label = self.form.labelForField(field)
        if label is not None:
            label.setVisible(on)

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose picture", "", "Pictures (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All files (*)")
        if path:
            self.load_image(path)

    def load_image(self, path) -> bool:
        try:
            data = encode_picture(str(path))
        except Exception as exc:       # Pillow raises many kinds for a broken or unknown file
            self.lbl_problem.setText(f"Could not read the picture: {exc}")
            return False
        self.set_image(data, os.path.basename(str(path)))
        return True

    def set_image(self, data: str, name: str = "Change picture…"):
        self.image_data = data
        self.btn_image.setText(name)
        pix = QPixmap()
        if data and pix.loadFromData(base64.b64decode(data)):
            self.lbl_image.setPixmap(pix.scaled(180, 110, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
            self.lbl_image.setVisible(True)
        self.changed.emit()

    def get_params(self) -> dict:
        flat = self.cmb_shape.currentData() == "flat"
        outline = self.cmb_outline.currentData() if flat else "rect"
        return {"image_data": self.image_data, "shape": self.cmb_shape.currentData(),
                "fit": self.cmb_fit.currentData(), "tone": self.cmb_tone.currentData(), "outline": outline,
                **{k: s.value() for k, s in self.spins.items()},
                **{k: c.isChecked() for k, c in self.checks.items()},
                **({} if outline == "rounded" else {"corner_radius": 0.0}),
                **({} if flat and self.checks["upright"].isChecked() else {"stand": 0.0})}

    def set_params(self, params: dict):
        for combo, key in ((self.cmb_shape, "shape"), (self.cmb_fit, "fit"), (self.cmb_outline, "outline")):
            combo.setCurrentIndex(max(0, combo.findData(params.get(key))))
        # an older step without a tone was made linear: editing it must not change it unasked
        self.cmb_tone.setCurrentIndex(max(0, self.cmb_tone.findData(params.get("tone", "linear"))))
        for fields, setter in ((self.spins, "setValue"), (self.checks, "setChecked")):
            for key, field in fields.items():
                if key in params:
                    getattr(field, setter)(params[key])
        if params.get("image_data"):
            self.set_image(params["image_data"])

    def get_expressions(self) -> dict:
        return {k: e for k, e in ((k, s.expression()) for k, s in self.spins.items()) if e}

    def build_preview(self, translation=None):
        """The solid for the current values (coarse in interactive mode), or None with the reason shown."""
        feat = LithophaneFeature("tmp", "tmp", translation=translation, **self.get_params())
        try:
            solid = feat.build_solid()
        except ValueError as exc:
            self.lbl_problem.setText(str(exc))
            return None
        self.show_backlit(feat)
        w, h = feat.size()
        note = "" if feat.shape == "sphere" else f"{w:.1f} x {h:.1f} mm"
        if feat.effective_detail() > feat.detail + 1e-6:
            note += f"{'. ' if note else ''}Detail is limited to {feat.effective_detail():.2f} mm at this size."
        self.lbl_problem.setText(note)
        return solid

    def show_backlit(self, feat: LithophaneFeature) -> None:
        """The picture as the print will look lit from behind (warm light through the wall, outside the outline dark)."""
        try:
            lit, inside = feat.backlit(220)
        except Exception:           # a preview only: the panel still works without it
            self.lbl_lit.setVisible(False)
            self.lbl_lit_title.setVisible(False)
            return
        light, back = np.array(self.LIT_COLOUR, float), np.array(self.LIT_BACKGROUND, float)
        rgb = back + (light - back) * np.clip(lit, 0, 1)[..., None]
        rgb[~inside] = back * 0.6
        rgb = np.ascontiguousarray(rgb.astype(np.uint8))
        h, w = rgb.shape[:2]
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self.lbl_lit.setPixmap(QPixmap.fromImage(img))
        self.lbl_lit.setVisible(True)
        self.lbl_lit_title.setVisible(True)

    def accept(self):
        from omacad.model import quality
        prev = quality.is_interactive_mode()
        quality.set_interactive_mode(True)       # a quick check only; the step builds the fine mesh
        try:
            ok = self.build_preview() is not None
        finally:
            quality.set_interactive_mode(prev)
        if ok:
            super().accept()
