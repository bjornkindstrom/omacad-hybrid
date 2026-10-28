"""
Omacad - Theme editor tab (Settings).
Every colour of the look can be set by hand, previewed live and saved under a name.
Saved themes are TOML files in ~/.config/omacad/themes and show up in the Theme list.
"""

from typing import Dict, Optional

from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)
from PySide6.QtCore import Signal

from omacad.ui import theme
from omacad.ui.settings import DEFAULT_SETTINGS, get_settings

# (key, label, tooltip). Keys equal the Omarchy colour names so a saved theme is also a valid palette file.
THEME_ROLES = (
    ("background", "Background", "Main surface colour; with the dark background it sets the 3D view colour if no own 3D background is set."),
    ("darker_background", "Dark background", "Dark end of the greys: panels, menus, input fields, borders."),
    ("foreground", "Text", "Light end of the greys: text and icons."),
    ("muted", "Muted text", "Secondary text."),
    ("accent", "Accent", "Buttons, titles and active items in the interface."),
    ("highlight", "3D highlight", "Selected and hovered faces, edges and profiles in the 3D view."),
    ("canvas", "3D view background", "The background behind the model."),
    ("grid", "Grid", "The grid lines on sketch planes."),
)
# Tool colours are stored in the theme as well (None = follow the 3D highlight).
TOOL_ROLES = (
    ("tool_arrow", "arrow_color", "Extrude arrow / dragger"),
    ("tool_measure", "measure_color", "Measure tool"),
    ("tool_sketch", "sketch_line_color", "Active sketch lines"),
    ("tool_construction", "sketch_construction_color", "Construction lines"),
)


def _hex01(c) -> str:
    from omacad.ui.settings import rgb01_to_hex
    return rgb01_to_hex(*c)


class ThemeEditorTab(QWidget):
    saved = Signal(str)      # theme key of a theme that was just saved

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        from omacad.ui.settings_dialog import ColorRow
        self._ColorRow = ColorRow
        self._extra: Dict[str, str] = {}
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Start from:"))
        self.cmb_base = QComboBox()
        self.cmb_base.addItem("Current look", "@current")
        self.cmb_base.addItem("Studio (light, blue)", "studio")
        self.cmb_base.addItem("Graphite (dark, amber)", "graphite")
        self.cmb_base.addItem("Atelier (warm, green)", "atelier")
        self._fill_custom()
        self.cmb_base.activated.connect(self._load_base)
        top.addWidget(self.cmb_base, 1)
        lay.addLayout(top)

        info = QLabel("Change any colour and see it live. Name it and press Save to keep it.")
        info.setStyleSheet("color: #9AA0A6; font-size: 11px;")
        lay.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(2)
        self.rows: Dict[str, "ColorRow"] = {}
        for key, label, tip in THEME_ROLES:
            row = ColorRow(label + ":", None, None)
            row.setToolTip(tip)
            row.btn_reset.hide()
            row.changed.connect(self._preview)
            self.rows[key] = row
            il.addWidget(row)
        il.addSpacing(8)
        il.addWidget(QLabel("Tool colours:"))
        for key, _setting, label in TOOL_ROLES:
            row = ColorRow(label + ":", None, None)
            row.btn_reset.setText("Follow highlight" if key == "tool_arrow" else "Reset")
            row.changed.connect(self._preview)
            self.rows[key] = row
            il.addWidget(row)
        il.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Name:"))
        self.edt_name = QLineEdit()
        self.edt_name.setPlaceholderText("e.g. Night shift")
        bottom.addWidget(self.edt_name, 1)
        self.btn_save = QPushButton("Save theme")
        self.btn_save.clicked.connect(self._save)
        bottom.addWidget(self.btn_save)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setToolTip("Delete the saved theme with this name")
        self.btn_delete.clicked.connect(self._delete)
        bottom.addWidget(self.btn_delete)
        lay.addLayout(bottom)

        self._load_base()

    # -- loading ----------------------------------------------------------
    def _fill_custom(self):
        for name in theme.custom_themes():
            self.cmb_base.addItem(f"★ {name}", theme.CUSTOM_PREFIX + name)

    def refresh_custom(self):
        """Re-read the saved themes into the 'Start from' list."""
        for i in reversed(range(self.cmb_base.count())):
            if str(self.cmb_base.itemData(i)).startswith(theme.CUSTOM_PREFIX):
                self.cmb_base.removeItem(i)
        self._fill_custom()

    def _load_base(self, *_):
        key = self.cmb_base.currentData()
        data = (theme.current_theme_data() if key == "@current" else theme.load_theme_data(key)) or {}
        pal = theme.palette() if key == "@current" else theme.Palette(data)
        hexv = lambda c: theme._hex(c)
        # a role theme (Studio, Graphite, Atelier) keeps its surfaces: Background = the panels, Dark background = the window
        back, dark = (pal.surfaces["surface"], pal.surfaces["window"]) if pal.studio else (pal.background, pal.darker)
        values = {
            "background": hexv(back), "darker_background": hexv(dark),
            "foreground": hexv(pal.foreground), "muted": hexv(pal.muted), "accent": hexv(pal.accent),
            "highlight": hexv(pal.highlight),
            "canvas": _hex01(pal.canvas_rgb01()), "grid": _hex01(pal.grid_rgb01()),
        }
        self._extra = {k: v for k, v in data.items() if k not in values and not k.startswith("tool_") and k != "mode"}
        st = get_settings()
        self._loading = True
        for key2, val in values.items():
            self.rows[key2].current_hex = val
            self.rows[key2].default_hex = val
            self.rows[key2].update_swatch()
        for key2, setting, _label in TOOL_ROLES:
            val = data.get(key2) if key2 in data else st.get(setting)
            self.rows[key2].current_hex = val
            self.rows[key2].default_hex = DEFAULT_SETTINGS.get(setting)
            self.rows[key2].update_swatch()
        self._loading = False
        if key.startswith(theme.CUSTOM_PREFIX):
            self.edt_name.setText(key[len(theme.CUSTOM_PREFIX):])
        self._preview()

    # -- data / preview ---------------------------------------------------
    def collect(self) -> dict:
        d = dict(self._extra)
        bg = theme._rgb(self.rows["background"].current_hex)
        d["mode"] = "light" if theme._lum(bg) > 0.5 else "dark"
        for key, _label, _tip in THEME_ROLES:
            d[key] = self.rows[key].current_hex
        for key, _s, _l in TOOL_ROLES:
            if self.rows[key].current_hex:
                d[key] = self.rows[key].current_hex
        if "surface" in d:     # role theme: the edited backgrounds are its panels and window
            d["surface"], d["window"] = d["background"], d["darker_background"]
        return d

    def _preview(self):
        if self._loading:
            return
        theme.set_preview(self.collect())

    def _save(self):
        name = theme.safe_theme_name(self.edt_name.text())
        if not name:
            QMessageBox.information(self, "Save theme", "Give the theme a name first.")
            return
        if name in theme.custom_themes():
            if QMessageBox.question(self, "Save theme", f"Replace the saved theme \"{name}\"?") != QMessageBox.StandardButton.Yes:
                return
        key = theme.save_custom_theme(name, self.collect())
        self.refresh_custom()
        self.cmb_base.setCurrentIndex(max(0, self.cmb_base.findData(key)))
        self.saved.emit(key)

    def _delete(self):
        name = theme.safe_theme_name(self.edt_name.text())
        if name not in theme.custom_themes():
            return
        if QMessageBox.question(self, "Delete theme", f"Delete the saved theme \"{name}\"?") != QMessageBox.StandardButton.Yes:
            return
        theme.delete_custom_theme(name)
        self.refresh_custom()
        self.saved.emit("")


class ThemeEditorDialog(QDialog):
    """Stand-alone dialog for editing themes."""
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Theme Editor")
        self.setMinimumWidth(500)
        self.resize(540, 600)
        theme.style(self, theme._BASE_CSS)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.editor = ThemeEditorTab(self)
        lay.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

    def reject(self):
        theme.set_preview(None)
        super().reject()

