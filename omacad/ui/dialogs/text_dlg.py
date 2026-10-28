"""Dialog for the sketch Text tool: the options of Fusion's Text dialog (Type, Text, Font, style, Height, Character
Spacing, Alignment, Flip, and for Text On Path: Placement and Fit to Path)."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFontComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QWidget)
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.ui.theme import themeify
from omacad.ui.expr_spin import ExprDoubleSpinBox

H_ALIGN = (("Left", "left"), ("Centre", "center"), ("Right", "right"))
V_ALIGN = (("Top", "top"), ("Middle", "middle"), ("Bottom", "bottom"))


class ThemedFontComboBox(QFontComboBox):
    """The font list is a popup of its own that the dialog's stylesheet does not reach (it came up black), and Qt may
    rebuild its list when the dialog is docked, so the theme is applied each time it opens."""

    POPUP_CSS = """
        QListView {
            background-color: #25282D;
            border: 1px solid #4D535E;
            color: #E0E3E7;
            selection-background-color: #E26D28;
            selection-color: #FFFFFF;
            outline: none;
        }
    """

    def showPopup(self):
        self.view().setStyleSheet(themeify(self.POPUP_CSS))
        super().showPopup()


class TextDialog(BaseFeatureDialog):
    """Text options. `changed` fires on every edit; `params()` is what SketchText takes (besides anchor and path)."""

    changed = Signal()

    def __init__(self, parent=None, editing: bool = False, embedded: bool = True):
        super().__init__("Text", parent, embedded)
        form = QFormLayout()

        self.cmb_type = QComboBox()
        self.cmb_type.addItem("Text", "text")
        self.cmb_type.addItem("Text On Path", "path")
        self.cmb_type.addItem("Text In Box", "box")
        self.cmb_type.setToolTip("Text: letters in a frame, placed where you click.\n"
                                 "Text On Path: letters along a circle, arc or line of the sketch.\n"
                                 "Text In Box: click two corners; the text fills the box, centred, and fits again "
                                 "when you change the font or the text.")
        form.addRow("Type:", self.cmb_type)

        self.edt_text = QPlainTextEdit("Text")
        self.edt_text.setFixedHeight(64)
        self.edt_text.setToolTip("One or more lines.")
        form.addRow("Text:", self.edt_text)

        self.lbl_path = QLabel("")
        self.lbl_path.setWordWrap(True)
        form.addRow("Path:", self.lbl_path)

        self.cmb_font = ThemedFontComboBox()
        self.cmb_font.setToolTip("Pick a font that is not a single-line font if the text is to be embossed or extruded.")
        form.addRow("Font:", self.cmb_font)

        style_row = QHBoxLayout()
        style_row.setContentsMargins(0, 0, 0, 0)
        self.chk_bold = QPushButton("B")
        self.chk_bold.setCheckable(True)
        self.chk_bold.setFixedWidth(40)
        self.chk_bold.setStyleSheet("padding: 4px 0px;")        # the dialog's button padding is wider than these
        self.chk_bold.setToolTip("Bold")
        self.chk_italic = QPushButton("I")
        self.chk_italic.setCheckable(True)
        self.chk_italic.setFixedWidth(40)
        self.chk_italic.setStyleSheet("padding: 4px 0px;")
        self.chk_italic.setToolTip("Italic")
        bold = QFont()
        bold.setBold(True)
        self.chk_bold.setFont(bold)
        ital = QFont()
        ital.setItalic(True)
        self.chk_italic.setFont(ital)
        style_row.addWidget(self.chk_bold)
        style_row.addWidget(self.chk_italic)
        style_row.addStretch()
        form.addRow("Style:", style_row)

        self.spn_height = ExprDoubleSpinBox()
        self.spn_height.setRange(0.1, 1000.0)
        self.spn_height.setDecimals(2)
        self.spn_height.setSuffix(" mm")
        self.spn_height.setValue(10.0)
        self.spn_height.setToolTip("The height of a capital letter.")
        form.addRow("Height:", self.spn_height)

        self.spn_margin = ExprDoubleSpinBox()
        self.spn_margin.setRange(0.0, 1000.0)
        self.spn_margin.setDecimals(2)
        self.spn_margin.setSuffix(" mm")
        self.spn_margin.setToolTip("Text In Box: room kept free between the text and each side of the box.")
        form.addRow("Margin:", self.spn_margin)

        self.spn_spacing = ExprDoubleSpinBox()
        self.spn_spacing.setRange(-50.0, 500.0)
        self.spn_spacing.setDecimals(0)
        self.spn_spacing.setSuffix(" %")
        self.spn_spacing.setToolTip("Extra space between the letters, in percent of the font's own spacing (0 % keeps it).")
        form.addRow("Character spacing:", self.spn_spacing)

        self.cmb_h = QComboBox()
        for label, key in H_ALIGN:
            self.cmb_h.addItem(label, key)
        form.addRow("Horizontal:", self.cmb_h)
        self.cmb_v = QComboBox()
        for label, key in V_ALIGN:
            self.cmb_v.addItem(label, key)
        self.cmb_v.setCurrentIndex(2)
        form.addRow("Vertical:", self.cmb_v)

        self.spn_angle = ExprDoubleSpinBox()
        self.spn_angle.setRange(-360.0, 360.0)
        self.spn_angle.setDecimals(1)
        self.spn_angle.setSuffix(" °")
        form.addRow("Angle:", self.spn_angle)

        self.flip_box = QWidget()
        flip_row = QHBoxLayout(self.flip_box)
        flip_row.setContentsMargins(0, 0, 0, 0)
        self.chk_flip_h = QCheckBox("Horizontal")
        self.chk_flip_v = QCheckBox("Vertical")
        flip_row.addWidget(self.chk_flip_h)
        flip_row.addWidget(self.chk_flip_v)
        form.addRow("Flip:", self.flip_box)

        self.cmb_place = QComboBox()
        self.cmb_place.addItem("Above", "above")
        self.cmb_place.addItem("Below", "below")
        self.cmb_place.setToolTip("Above: on the left of the way the path runs (outside a circle). Below: on the other side.")
        form.addRow("Placement:", self.cmb_place)
        self.chk_fit = QCheckBox("Fit to path")
        self.chk_fit.setToolTip("Spread the letters evenly over the whole path.")
        form.addRow("", self.chk_fit)

        self.main_layout.addLayout(form)
        self.add_buttons()
        self._path_rows = (self.lbl_path, self.cmb_place, self.chk_fit)
        self._frame_rows = (self.cmb_v, self.spn_angle, self.flip_box)
        self._box_rows = (self.spn_margin,)
        self._box_hidden = (self.cmb_v,)        # a box centres the text: its height and vertical place are set by it
        self.cmb_type.currentIndexChanged.connect(self._type_changed)
        self.edt_text.textChanged.connect(self.changed)
        for w in (self.cmb_font, self.cmb_h, self.cmb_v, self.cmb_place):
            w.currentIndexChanged.connect(lambda *_: self.changed.emit())
        for w in (self.chk_bold, self.chk_italic, self.chk_flip_h, self.chk_flip_v, self.chk_fit):
            w.toggled.connect(lambda *_: self.changed.emit())
        for w in (self.spn_height, self.spn_margin, self.spn_spacing, self.spn_angle):
            w.valueChanged.connect(lambda *_: self.changed.emit())
        self._type_changed()

    # --- type ----------------------------------------------------------------------------------------------------
    def is_path(self) -> bool:
        return self.cmb_type.currentData() == "path"

    def is_box(self) -> bool:
        return self.cmb_type.currentData() == "box"

    def show_fitted_height(self, height: float) -> None:
        """Text In Box: the height the box gives the text, shown in the (then read-only) height field."""
        self.spn_height.blockSignals(True)
        self.spn_height.setValue(max(self.spn_height.minimum(), height))
        self.spn_height.blockSignals(False)

    def _type_changed(self):
        path = self.is_path()
        box = self.is_box()
        for w in self._path_rows:
            w.setVisible(path)
            lab = self.layout_label(w)
            if lab is not None:
                lab.setVisible(path)
        for w in self._frame_rows:
            show = not path and not (box and w in self._box_hidden)
            w.setVisible(show)
            lab = self.layout_label(w)
            if lab is not None:
                lab.setVisible(show)
        for w in self._box_rows:
            w.setVisible(box)
            lab = self.layout_label(w)
            if lab is not None:
                lab.setVisible(box)
        self.spn_height.setReadOnly(box)
        self.spn_height.setToolTip("Set by the box: the text fills it." if box else "The height of a capital letter.")
        self.changed.emit()

    def layout_label(self, widget):
        form = self.findChild(QFormLayout)
        if form is None:
            return None
        return form.labelForField(widget)

    def set_path_text(self, text: str) -> None:
        self.lbl_path.setText(text)

    # --- values --------------------------------------------------------------------------------------------------
    def params(self) -> dict:
        """The options as SketchText arguments (no anchor, no path id)."""
        return {
            "text": self.edt_text.toPlainText(),
            "font": self.cmb_font.currentFont().family(),
            "height": self.spn_height.value(),
            "bold": self.chk_bold.isChecked(),
            "italic": self.chk_italic.isChecked(),
            "spacing": self.spn_spacing.value(),
            "h_align": self.cmb_h.currentData(),
            "v_align": self.cmb_v.currentData(),
            "flip_h": self.chk_flip_h.isChecked(),
            "flip_v": self.chk_flip_v.isChecked(),
            "angle": self.spn_angle.value(),
            "placement": self.cmb_place.currentData(),
            "fit": self.chk_fit.isChecked(),
            "margin": self.spn_margin.value(),
        }

    def set_params(self, ent) -> None:
        """Fills the fields from an existing SketchText (editing it)."""
        for w in (self.cmb_type, self.edt_text, self.cmb_font, self.cmb_h, self.cmb_v, self.cmb_place, self.chk_bold,
                  self.chk_italic, self.chk_flip_h, self.chk_flip_v, self.chk_fit, self.spn_height, self.spn_spacing,
                  self.spn_angle, self.spn_margin):
            w.blockSignals(True)
        try:
            self.cmb_type.setCurrentIndex(1 if ent.path_id else (2 if getattr(ent, "box", None) else 0))
            self.edt_text.setPlainText(ent.text)
            self.cmb_font.setCurrentFont(QFont(ent.font))
            self.cmb_h.setCurrentIndex(max(0, self.cmb_h.findData(ent.h_align)))
            self.cmb_v.setCurrentIndex(max(0, self.cmb_v.findData(ent.v_align)))
            self.cmb_place.setCurrentIndex(max(0, self.cmb_place.findData(ent.placement)))
            self.chk_bold.setChecked(ent.bold)
            self.chk_italic.setChecked(ent.italic)
            self.chk_flip_h.setChecked(ent.flip_h)
            self.chk_flip_v.setChecked(ent.flip_v)
            self.chk_fit.setChecked(ent.fit)
            self.spn_height.setValue(ent.height)
            self.spn_spacing.setValue(ent.spacing)
            self.spn_angle.setValue(ent.angle)
            self.spn_margin.setValue(getattr(ent, "margin", 0.0))
        finally:
            for w in (self.cmb_type, self.edt_text, self.cmb_font, self.cmb_h, self.cmb_v, self.cmb_place, self.chk_bold,
                      self.chk_italic, self.chk_flip_h, self.chk_flip_v, self.chk_fit, self.spn_height, self.spn_spacing,
                      self.spn_angle, self.spn_margin):
                w.blockSignals(False)
        self._type_changed()
