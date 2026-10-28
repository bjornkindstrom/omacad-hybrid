"""
Omacad - Settings Dialog
GUI for configuring user preferences including custom colors, UI layout, sketch & view options, and system preferences.
"""

from typing import Dict, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLineEdit, QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QPushButton, QComboBox, QCheckBox, QDoubleSpinBox, QColorDialog,
    QFrame, QGridLayout, QScrollArea, QListWidget, QSizePolicy
)

from omacad.ui import theme
from omacad.ui.settings import finished_sketch_grey, get_settings, rgb01_to_hex


ROLE_THEMES = theme.ROLE_THEMES   # Studio, Graphite, Atelier: they come with the Studio line icons


class ColorRow(QWidget):
    changed = Signal()

    def __init__(self, label: str, current_hex: Optional[str], default_hex: Optional[str] = None,
                 parent: Optional[QWidget] = None, theme_colour=None):
        super().__init__(parent)
        self.current_hex = current_hex
        self.default_hex = default_hex
        self.theme_colour = theme_colour or (lambda: theme.palette().highlight01())   # rgb01 shown for "Theme"

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(10)

        self.lbl = QLabel(label)
        self.lbl.setMinimumWidth(180)
        lay.addWidget(self.lbl)

        self.btn_swatch = QPushButton()
        self.btn_swatch.setFixedSize(90, 30)
        self.btn_swatch.setAccessibleName(f"Choose {label.rstrip(chr(58))} colour")
        self.btn_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swatch.clicked.connect(self.choose_color)
        lay.addWidget(self.btn_swatch)

        self.btn_reset = QPushButton("Follow theme" if default_hex is None else "Reset")
        self.btn_reset.clicked.connect(self.reset_color)
        lay.addWidget(self.btn_reset)
        lay.addStretch()

        self.update_swatch()

    def update_swatch(self):
        if self.current_hex:
            self.btn_swatch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.current_hex};
                    border: 1px solid #5A6270;
                    border-radius: 4px;
                }}
            """)
            self.btn_swatch.setText(self.current_hex)
            color = QColor(self.current_hex)
            ink = "#17191C" if color.lightnessF() > 0.55 else "#FFFFFF"
            self.btn_swatch.setStyleSheet(self.btn_swatch.styleSheet() +
                                         f"QPushButton {{ color: {ink}; padding: 0; font-size: 11px; }}")
        else:
            # Theme default highlight
            hex_th = rgb01_to_hex(*self.theme_colour())
            ink = "#17191C" if QColor(hex_th).lightnessF() > 0.55 else "#FFFFFF"   # readable on light colours too
            self.btn_swatch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_th};
                    border: 1px dashed #7A8290;
                    border-radius: 4px;
                    color: {ink};
                    font-size: 10px;
                }}
            """)
            self.btn_swatch.setText("Theme")
            self.btn_swatch.setStyleSheet(self.btn_swatch.styleSheet() + "QPushButton { padding: 0; }")

    def choose_color(self):
        initial = QColor(self.current_hex) if self.current_hex else QColor(*[int(c * 255) for c in theme.palette().highlight01()])
        color = QColorDialog.getColor(initial, self, "Choose colour")
        if color.isValid():
            self.current_hex = color.name().upper()
            self.update_swatch()
            self.changed.emit()

    def reset_color(self):
        self.current_hex = self.default_hex
        self.update_swatch()
        self.changed.emit()


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(550)
        theme.style(self, theme._BASE_CSS + """
            QDialog { background: #202226; }
            QTabWidget::pane { border: none; }
            QListWidget#SettingsNavigation { background: #24262B; border: none;
                border-radius: 10px; padding: 8px; outline: none; }
            QListWidget#SettingsNavigation::item { padding: 13px 10px;
                margin-bottom: 4px; border-radius: 6px; }
            QListWidget#SettingsNavigation::item:selected { background: #3A4050;
                color: #FFFFFF; border-left: 3px solid #FFA63C; }
            QFrame#SettingsCard { background: #292B30; border: 1px solid #414550;
                border-radius: 10px; }
            QLabel#SettingsTitle { font-size: 24px; font-weight: 600; }
            QLabel#SettingsSection { font-size: 14px; font-weight: 600; }
            QLabel#SettingsDescription { color: #9AA0A6; }
            QPushButton#SettingsSave { background: #FFA63C; color: #202226;
                border: none; font-weight: 600; padding: 9px 24px; }
        """, theme._STUDIO_CSS + """
            QDialog { background: @window; }
            QListWidget#SettingsNavigation { background: @surface; border: 1px solid @border; border-radius: 8px; }
            QListWidget#SettingsNavigation::item { color: @text; border-left: 3px solid transparent; }
            QListWidget#SettingsNavigation::item:hover { background: @field; }
            QListWidget#SettingsNavigation::item:selected { background: @selection; color: @accent; border-left: 3px solid @accent; }
            QFrame#SettingsCard { background: @surface; border: 1px solid @border; border-radius: 8px; }
            QLabel#SettingsTitle { color: @text; font-size: 26px; font-weight: 500; }
            QLabel#SettingsSection { color: @text; font-size: 17px; font-weight: 500; }
            QLabel#SettingsDescription { color: @muted; }
            QPushButton#SettingsSave { background: @accent; color: @on_accent; border: 1px solid @accent; }
            QPushButton#SettingsSave:hover { background: @accent_hover; }
        """)

        self.settings = get_settings()
        self._just_saved = ""

        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)
        main_lay.setSpacing(14)

        heading = QLabel("Settings")
        heading.setObjectName("SettingsTitle")
        main_lay.addWidget(heading)
        subtitle = QLabel("Make Omacad feel right for the way you work.")
        subtitle.setObjectName("SettingsDescription")
        main_lay.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.navigation = QListWidget()
        self.navigation.setObjectName("SettingsNavigation")
        self.navigation.setAccessibleName("Settings categories")
        self.navigation.setFixedWidth(160)
        self.navigation.addItems(["Appearance", "Interface", "Sketch & View", "General"])
        body.addWidget(self.navigation)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        body.addWidget(self.tabs, 1)
        main_lay.addLayout(body, 1)
        self.navigation.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.navigation.setCurrentRow)
        self.navigation.setCurrentRow(0)

        # ----------------------------------------------------
        # Tab 1: Appearance & Colours (🎨 Appearance)
        # ----------------------------------------------------
        tab_appearance = QWidget()
        lay_appearance = QVBoxLayout(tab_appearance)
        lay_appearance.setContentsMargins(12, 12, 12, 12)
        lay_appearance.setSpacing(12)

        # Theme mode
        theme_row = QHBoxLayout()
        lbl_theme = QLabel("Theme Mode:")
        lbl_theme.setMinimumWidth(200)
        self.cmb_theme_mode = QComboBox()
        self._fill_theme_choices()

        chosen = theme.chosen_theme(self.settings.get("theme_mode", "omarchy"), self.settings.get("theme_name"))
        select_key = chosen or "omarchy"

        idx = self.cmb_theme_mode.findData(select_key)
        self.cmb_theme_mode.setCurrentIndex(max(0, idx))
        self.cmb_theme_mode.setToolTip("Studio: light and calm, white panels and a blue accent.\n"
                                       "Graphite: dark and compact, amber for the active choice.\n"
                                       "Atelier: warm grey, forest green accent, soft corners.\n"
                                       "Follow Omarchy: syncs live with the Omarchy theme.")
        theme_row.addWidget(lbl_theme)
        theme_row.addWidget(self.cmb_theme_mode)
        theme_row.addStretch()
        lay_appearance.addLayout(theme_row)

        # Icon Theme selector
        icon_row = QHBoxLayout()
        lbl_icon = QLabel("Icon Theme:")
        lbl_icon.setMinimumWidth(200)
        self.cmb_icon_theme = QComboBox()
        self.cmb_icon_theme.addItem("Solid", "solid")
        self.cmb_icon_theme.addItem("Blueprint", "blueprint")
        self.cmb_icon_theme.addItem("Colour-coded", "semantic")
        self.cmb_icon_theme.addItem("Studio (line, accent colour when active)", "studio")
        cur_icon = self.settings.get("icon_theme", "solid")
        idx_icon = self.cmb_icon_theme.findData(cur_icon)
        self.cmb_icon_theme.setCurrentIndex(max(0, idx_icon))
        self.cmb_icon_theme.setToolTip("Choose the icon style for ribbon and sketch toolbar buttons.")
        # picking the Studio theme suggests its icons too (shown here, saved only with Save)
        self.cmb_theme_mode.activated.connect(
            lambda _i: self.cmb_theme_mode.currentData() in ROLE_THEMES
            and self.cmb_icon_theme.setCurrentIndex(self.cmb_icon_theme.findData("studio")))
        icon_row.addWidget(lbl_icon)
        icon_row.addWidget(self.cmb_icon_theme)
        icon_row.addStretch()
        lay_appearance.addLayout(icon_row)

        info_lbl = QLabel("Customise colours for 3D arrows, highlights and tools in the view:")
        info_lbl.setStyleSheet("color: #9AA0A6; font-size: 11px; margin-top: 8px;")
        lay_appearance.addWidget(info_lbl)

        self.row_arrow = ColorRow("Extrude arrow / dragger:", self.settings.get("arrow_color"), default_hex=None)
        lay_appearance.addWidget(self.row_arrow)

        self.row_measure = ColorRow("Measure tool (overlay):", self.settings.get("measure_color"), default_hex="#FFAA3C")
        lay_appearance.addWidget(self.row_measure)

        self.row_sketch = ColorRow("Active sketch lines:", self.settings.get("sketch_line_color"), default_hex="#4CE0FF")
        lay_appearance.addWidget(self.row_sketch)

        self.row_construct = ColorRow("Construction lines:", self.settings.get("sketch_construction_color"), default_hex="#FFCC4D")
        lay_appearance.addWidget(self.row_construct)
        self.row_finished = ColorRow("Finished sketches:", self.settings.get("sketch_finished_color"),
                                     theme_colour=finished_sketch_grey)
        lay_appearance.addWidget(self.row_finished)

        self.row_hover = ColorRow("Line under the cursor:", self.settings.get("hover_line_color"), default_hex="#FFFFFF")
        lay_appearance.addWidget(self.row_hover)

        self.spn_hover_w = self._width_row(lay_appearance, "Line under cursor, thickness:", "hover_line_width", 3.5,
                                           "How thick the edge or sketch line gets when you hover over it. Normal lines are about 1-1.6 px, so a bigger number makes the difference bigger.")
        self.spn_sketch_w = self._width_row(lay_appearance, "Sketch lines, thickness:", "sketch_line_width", 1.6,
                                            "How thick the lines of the sketch you are editing are drawn.")
        self.spn_selected_w = self._width_row(lay_appearance, "Selected lines, thickness:", "selected_line_width", 2.4,
                                              "How thick selected sketch lines are drawn.")
        self.row_selected = ColorRow("Selected lines:", self.settings.get("selected_line_color"), default_hex=None)
        lay_appearance.addWidget(self.row_selected)

        self.row_highlight = ColorRow("Highlight:", self.settings.get("highlight_color"), default_hex=None)
        lay_appearance.addWidget(self.row_highlight)

        # Button to open Theme Editor dialog
        btn_editor_row = QHBoxLayout()
        self.btn_open_theme_editor = QPushButton("Edit theme…")
        self.btn_open_theme_editor.setToolTip("Customise every single colour in the interface and save custom theme palettes.")
        self.btn_open_theme_editor.clicked.connect(self._open_theme_editor)
        btn_editor_row.addWidget(self.btn_open_theme_editor)
        btn_editor_row.addStretch()
        lay_appearance.addSpacing(6)
        lay_appearance.addLayout(btn_editor_row)

        lay_appearance.addStretch()
        self.tabs.addTab(self._make_scrollable(tab_appearance), "🎨 Appearance")

        # ----------------------------------------------------
        # Tab 2: Interface & Layout (🖥️ Interface)
        # ----------------------------------------------------
        tab_ui = QWidget()
        lay_ui = QVBoxLayout(tab_ui)
        lay_ui.setContentsMargins(12, 12, 12, 12)
        lay_ui.setSpacing(12)

        # Toolbar button size / UI density
        btn_size_row = QHBoxLayout()
        lbl_btn_size = QLabel("Toolbar button size:")
        lbl_btn_size.setMinimumWidth(200)
        self.cmb_btn_size = QComboBox()
        self.cmb_btn_size.addItem("Compact / Low resolution (75%)", 0.75)
        self.cmb_btn_size.addItem("Medium (default, 100%)", 1.0)
        self.cmb_btn_size.addItem("Large (125%)", 1.25)
        self.cmb_btn_size.addItem("Extra large (150%)", 1.5)
        cur_scale = float(self.settings.get("button_scale", 1.0))
        idx_scale = self.cmb_btn_size.findData(cur_scale)
        if idx_scale < 0:
            self.cmb_btn_size.addItem(f"Custom ({int(round(cur_scale * 100))}%)", cur_scale)
            idx_scale = self.cmb_btn_size.count() - 1
        self.cmb_btn_size.setCurrentIndex(max(0, idx_scale))
        self.cmb_btn_size.setToolTip("Adjusts the height and icon sizes of buttons in the top toolbar ribbon. Ideal for laptops or low-resolution screens.")
        btn_size_row.addWidget(lbl_btn_size)
        btn_size_row.addWidget(self.cmb_btn_size)
        btn_size_row.addStretch()
        lay_ui.addLayout(btn_size_row)

        self.chk_labels = QCheckBox("Show button names under toolbar icons (otherwise only on hover)")
        self.chk_labels.setChecked(bool(self.settings.get("show_button_labels", False)))
        lay_ui.addWidget(self.chk_labels)

        # Palette position
        pos_row = QHBoxLayout()
        lbl_pos = QLabel("Sketch palette position:")
        lbl_pos.setMinimumWidth(200)
        self.cmb_pos = QComboBox()
        self.cmb_pos.addItem("Bottom right (recommended)", "bottom_right")
        self.cmb_pos.addItem("Top left", "top_left")
        self.cmb_pos.addItem("Bottom left", "bottom_left")
        self.cmb_pos.addItem("Top right", "top_right")
        cur_pos = self.settings.get("palette_position", "bottom_right")
        idx_pos = self.cmb_pos.findData(cur_pos)
        if idx_pos >= 0:
            self.cmb_pos.setCurrentIndex(idx_pos)
        pos_row.addWidget(lbl_pos)
        pos_row.addWidget(self.cmb_pos)
        pos_row.addStretch()
        lay_ui.addLayout(pos_row)

        # Autohide on measure
        self.chk_autohide = QCheckBox("Hide the sketch palette automatically while measuring (M)")
        self.chk_autohide.setToolTip("Stops the palette from covering lines or dimensions while you measure.")
        self.chk_autohide.setChecked(bool(self.settings.get("autohide_palette_on_measure", True)))
        lay_ui.addWidget(self.chk_autohide)

        # Toolbar Ribbon Grouping
        grp_lbl = QLabel("Toolbar grouping (saves horizontal space on smaller screens):")
        grp_lbl.setStyleSheet("color: #9AA0A6; font-size: 11px; margin-top: 6px;")
        lay_ui.addWidget(grp_lbl)

        self.chk_group_primitives = QCheckBox("Group Primitives into dropdown (Box, Cylinder, Prism, Thread)")
        self.chk_group_primitives.setChecked(bool(self.settings.get("group_primitives", True)))
        self.chk_group_primitives.setToolTip("Puts 3D primitive tools into a compact Primitives ▾ dropdown menu.")
        lay_ui.addWidget(self.chk_group_primitives)

        self.chk_group_modify = QCheckBox("Group Modify into dropdown (Combine, Split Body, Shell, Move, Delete)")
        self.chk_group_modify.setChecked(bool(self.settings.get("group_modify", False)))
        self.chk_group_modify.setToolTip("Puts solid modification tools into a compact Modify ▾ dropdown menu.")
        lay_ui.addWidget(self.chk_group_modify)

        self.chk_group_inspect = QCheckBox("Group Inspect into dropdown (Measure, Section View, Parameters)")
        self.chk_group_inspect.setChecked(bool(self.settings.get("group_inspect", True)))
        self.chk_group_inspect.setToolTip("Puts measurement, sectioning and parameters into an Inspect ▾ dropdown menu.")
        lay_ui.addWidget(self.chk_group_inspect)

        self.chk_group_constraints = QCheckBox("Sketch Constraints as a dropdown menu")
        self.chk_group_constraints.setChecked(bool(self.settings.get("group_constraints", True)))
        self.chk_group_constraints.setToolTip("Puts the sketch constraints into one Constraints ▾ dropdown with full-size icons. Off = one button per constraint.")
        lay_ui.addWidget(self.chk_group_constraints)

        lay_ui.addStretch()
        self.tabs.addTab(self._make_scrollable(tab_ui), "🖥️ Interface")

        # ----------------------------------------------------
        # Tab 4: Sketch & 3D View (📐 Sketch & View)
        # ----------------------------------------------------
        tab_sketch = QWidget()
        lay_sketch = QVBoxLayout(tab_sketch)
        lay_sketch.setContentsMargins(12, 12, 12, 12)
        lay_sketch.setSpacing(12)

        # Invert zoom
        self.chk_invert_zoom = QCheckBox("Reverse the mouse wheel zoom direction")
        self.chk_invert_zoom.setChecked(bool(self.settings.get("invert_zoom", False)))
        lay_sketch.addWidget(self.chk_invert_zoom)

        self.chk_tangent_edges = QCheckBox("Show tangent edges (a line where a flat face runs smoothly into a curve)")
        self.chk_tangent_edges.setChecked(bool(self.settings.get("show_tangent_edges", False)))
        lay_sketch.addWidget(self.chk_tangent_edges)

        # Grid step
        grid_row = QHBoxLayout()
        lbl_grid = QLabel("Grid step (mm):")
        lbl_grid.setMinimumWidth(200)
        self.spn_grid = QDoubleSpinBox()
        self.spn_grid.setRange(0.5, 100.0)
        self.spn_grid.setValue(float(self.settings.get("grid_step", 5.0)))
        self.spn_grid.setSuffix(" mm")
        grid_row.addWidget(lbl_grid)
        grid_row.addWidget(self.spn_grid)
        grid_row.addStretch()
        lay_sketch.addLayout(grid_row)

        guide_gap_row = QHBoxLayout()
        lbl_guide_gap = QLabel("Guide line gap:")
        lbl_guide_gap.setMinimumWidth(200)
        self.spn_guide_gap = QDoubleSpinBox()
        self.spn_guide_gap.setRange(1.0, 50.0)
        self.spn_guide_gap.setDecimals(1)
        self.spn_guide_gap.setSingleStep(1.0)
        self.spn_guide_gap.setSuffix(" px")
        self.spn_guide_gap.setValue(float(self.settings.get("guide_line_gap", 6.0)))
        self.spn_guide_gap.setToolTip("Space between guide (construction) line dashes in screen pixels, independent of zoom.")
        guide_gap_row.addWidget(lbl_guide_gap)
        guide_gap_row.addWidget(self.spn_guide_gap)
        guide_gap_row.addStretch()
        lay_sketch.addLayout(guide_gap_row)

        # Default fillet radius
        fillet_row = QHBoxLayout()
        lbl_fillet = QLabel("Default radius for Sketch Fillet:")
        lbl_fillet.setMinimumWidth(200)
        self.spn_fillet = QDoubleSpinBox()
        self.spn_fillet.setRange(0.1, 1000.0)
        self.spn_fillet.setValue(float(self.settings.get("fillet_default_radius", 2.0)))
        self.spn_fillet.setSuffix(" mm")
        fillet_row.addWidget(lbl_fillet)
        fillet_row.addWidget(self.spn_fillet)
        fillet_row.addStretch()
        lay_sketch.addLayout(fillet_row)

        primitive_row = QHBoxLayout()
        primitive_row.addWidget(QLabel("Primitive drag decimals:"))
        self.cmb_primitive_decimals = QComboBox()
        for decimals, label in [(0, "0 — whole millimetres"), (1, "1 — 0.1 mm"), (2, "2 — 0.01 mm")]:
            self.cmb_primitive_decimals.addItem(label, decimals)
        self.cmb_primitive_decimals.setCurrentIndex(max(0, self.cmb_primitive_decimals.findData(
            int(self.settings.get("primitive_drag_decimals", 0)))))
        self.cmb_primitive_decimals.setToolTip("Precision when dragging primitive size handles. Exact values can still be typed in the dimension fields.")
        primitive_row.addWidget(self.cmb_primitive_decimals)
        primitive_row.addStretch()
        lay_sketch.addLayout(primitive_row)

        # The extrude arrow
        arrow_row = QHBoxLayout()
        lbl_arrow = QLabel("Extrude arrow size:")
        lbl_arrow.setMinimumWidth(200)
        self.spn_arrow_size = QDoubleSpinBox()
        self.spn_arrow_size.setRange(0.3, 4.0)
        self.spn_arrow_size.setSingleStep(0.1)
        self.spn_arrow_size.setDecimals(1)
        self.spn_arrow_size.setSuffix(" ×")
        self.spn_arrow_size.setValue(float(self.settings.get("arrow_size", 1.0)))
        arrow_row.addWidget(lbl_arrow)
        arrow_row.addWidget(self.spn_arrow_size)
        arrow_row.addStretch()
        lay_sketch.addLayout(arrow_row)

        gap_row = QHBoxLayout()
        lbl_gap = QLabel("Arrow distance from surface:")
        lbl_gap.setMinimumWidth(200)
        self.spn_arrow_gap = QDoubleSpinBox()
        self.spn_arrow_gap.setRange(0.0, 20.0)
        self.spn_arrow_gap.setSingleStep(0.5)
        self.spn_arrow_gap.setDecimals(1)
        self.spn_arrow_gap.setSuffix(" mm")
        self.spn_arrow_gap.setValue(float(self.settings.get("arrow_gap", 2.0)))
        self.spn_arrow_gap.setToolTip("The arrow is drawn this far off the surface, in the direction it points, so it never starts inside the material.")
        gap_row.addWidget(lbl_gap)
        gap_row.addWidget(self.spn_arrow_gap)
        gap_row.addStretch()
        lay_sketch.addLayout(gap_row)

        # Smoothness of round shapes
        q_row = QHBoxLayout()
        lbl_q = QLabel("Curve smoothness:")
        lbl_q.setMinimumWidth(200)
        self.cmb_curves = QComboBox()
        for label, n in (("Light (32), fastest", 32), ("Normal (64)", 64), ("Smooth (96), default", 96),
                         ("Extra smooth (192)", 192), ("Seamless (360), heavy", 360)):
            self.cmb_curves.addItem(label, n)
        cur = int(self.settings.get("curve_segments", 96))
        idx_c = self.cmb_curves.findData(cur)
        if idx_c < 0:
            self.cmb_curves.addItem(f"Custom ({cur})", cur)
            idx_c = self.cmb_curves.count() - 1
        self.cmb_curves.setCurrentIndex(idx_c)
        self.cmb_curves.setToolTip("How many flat pieces a circle is cut into. More = smoother round surfaces but heavier for the computer. Applies to the whole model, which is rebuilt.")
        q_row.addWidget(lbl_q)
        q_row.addWidget(self.cmb_curves)
        q_row.addStretch()
        lay_sketch.addLayout(q_row)

        # Camera: projection type and perspective field of view
        proj_row = QHBoxLayout()
        lbl_proj = QLabel("Camera type (3D view):")
        lbl_proj.setMinimumWidth(200)
        self.cmb_projection = QComboBox()
        self.cmb_projection.addItem("Perspective", "perspective")
        self.cmb_projection.addItem("Orthographic (no perspective)", "orthographic")
        self.cmb_projection.setCurrentIndex(max(0, self.cmb_projection.findData(self.settings.get("view_projection", "perspective"))))
        proj_row.addWidget(lbl_proj)
        proj_row.addWidget(self.cmb_projection)
        proj_row.addStretch()
        lay_sketch.addLayout(proj_row)

        fov_row = QHBoxLayout()
        lbl_fov = QLabel("Perspective (field of view):")
        lbl_fov.setMinimumWidth(200)
        self.spn_fov = QDoubleSpinBox()
        self.spn_fov.setRange(10.0, 60.0)
        self.spn_fov.setDecimals(0)
        self.spn_fov.setSuffix("°")
        self.spn_fov.setValue(float(self.settings.get("view_fov", 30.0)))
        self.spn_fov.setToolTip("Lower = flatter image and less distortion. The zoom does not change.")
        fov_row.addWidget(lbl_fov)
        fov_row.addWidget(self.spn_fov)
        fov_row.addWidget(QLabel("lower = flatter, less skewed"))
        fov_row.addStretch()
        lay_sketch.addLayout(fov_row)

        lay_sketch.addStretch()
        self.tabs.addTab(self._make_scrollable(tab_sketch), "📐 Sketch & View")

        # ----------------------------------------------------
        # Tab 5: System & Feedback (⚙️ General)
        # ----------------------------------------------------
        tab_general = QWidget()
        lay_general = QVBoxLayout(tab_general)
        lay_general.setContentsMargins(12, 12, 12, 12)
        lay_general.setSpacing(12)

        # Request for change
        rfc_row = QHBoxLayout()
        lbl_rfc = QLabel("Your name on change requests:")
        lbl_rfc.setMinimumWidth(200)
        self.edt_rfc_name = QLineEdit(str(self.settings.get("rfc_name") or ""))
        self.edt_rfc_name.setPlaceholderText("Help > Request a change (F8)")
        rfc_row.addWidget(lbl_rfc)
        rfc_row.addWidget(self.edt_rfc_name)
        lay_general.addLayout(rfc_row)

        tok_row = QHBoxLayout()
        lbl_tok = QLabel("GitHub token for requests (optional):")
        lbl_tok.setMinimumWidth(200)
        self.edt_rfc_token = QLineEdit(str(self.settings.get("rfc_token") or ""))
        self.edt_rfc_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_rfc_token.setPlaceholderText("empty = use the one built into the app")
        tok_row.addWidget(lbl_tok)
        tok_row.addWidget(self.edt_rfc_token)
        lay_general.addLayout(tok_row)

        # AI Agent for fixing errors / reporting problems
        from omacad import feedback
        agent_row = QHBoxLayout()
        lbl_agent = QLabel("AI agent for fixing errors (F10):")
        lbl_agent.setMinimumWidth(200)
        self.cmb_ai_agent = QComboBox()
        cur_agent = self.settings.get("ai_agent", "omarchy")
        for key, name in feedback.available_agents():
            self.cmb_ai_agent.addItem(name, key)
        idx_agent = self.cmb_ai_agent.findData(cur_agent)
        if idx_agent >= 0:
            self.cmb_ai_agent.setCurrentIndex(idx_agent)
        self.cmb_ai_agent.setToolTip("Choose which coding agent to open when reporting a problem (F10) to fix it.")
        agent_row.addWidget(lbl_agent)
        agent_row.addWidget(self.cmb_ai_agent)
        agent_row.addStretch()
        lay_general.addLayout(agent_row)

        # Restart on a new version
        self.chk_auto_restart = QCheckBox("Restart automatically when a new version has been committed (work is saved and restored)")
        self.chk_auto_restart.setChecked(bool(self.settings.get("auto_restart", True)))
        lay_general.addWidget(self.chk_auto_restart)

        lay_general.addStretch()
        self.tabs.addTab(self._make_scrollable(tab_general), "⚙️ General")

        # ----------------------------------------------------
        # Bottom buttons
        # ----------------------------------------------------
        self._group_page(lay_appearance, [
            (theme_row, "Theme & icons"),
            (info_lbl, "Colours & line weights"),
            (btn_editor_row, "Custom theme")])
        self._group_page(lay_ui, [
            (btn_size_row, "Toolbar size & labels"),
            (pos_row, "Sketch palette"),
            (grp_lbl, "Toolbar organisation")])
        self._group_page(lay_sketch, [
            (self.chk_invert_zoom, "Navigation & edges"),
            (grid_row, "Sketch & precision"),
            (arrow_row, "Extrude handles"),
            (q_row, "Rendering & camera")])
        self._group_page(lay_general, [
            (rfc_row, "Change requests"),
            (agent_row, "Problem reporting & updates")])
        self.spn_fov.setEnabled(self.cmb_projection.currentData() == "perspective")
        self.cmb_projection.currentIndexChanged.connect(
            lambda: self.spn_fov.setEnabled(self.cmb_projection.currentData() == "perspective"))

        btn_row = QHBoxLayout()
        btn_reset_all = QPushButton("Reset to defaults")
        btn_reset_all.clicked.connect(self.reset_all)
        btn_row.addWidget(btn_reset_all)
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save")
        btn_save.setObjectName("SettingsSave")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self.save_and_close)
        btn_row.addWidget(btn_save)

        main_lay.addLayout(btn_row)
        from omacad.ui.numeric_slider import add_numeric_sliders
        add_numeric_sliders(self)

        # Ensure dialog fits comfortably within screen boundaries (e.g. on Windows laptops)
        self.resize(960, 740)
        screen = self.screen().availableGeometry()
        self.resize(min(self.width(), screen.width() - 40),
                    min(self.height(), screen.height() - 80))

    @staticmethod
    def _group_page(layout, sections):
        """Group existing controls without changing their values or save bindings."""
        items = []
        while layout.count():
            items.append(layout.takeAt(0))
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)
        current = None
        for item in items:
            content = item.widget() or item.layout()
            if content is None:
                continue
            title = next((title for first, title in sections if first is content), None)
            if title:
                card = QFrame()
                card.setObjectName("SettingsCard")
                current = QVBoxLayout(card)
                current.setContentsMargins(18, 16, 18, 18)
                current.setSpacing(14)
                heading = QLabel(title)
                heading.setObjectName("SettingsSection")
                current.addWidget(heading)
                layout.addWidget(card)
            if item.widget():
                current.addWidget(item.widget())
            else:
                current.addLayout(item.layout())
        layout.addStretch()
        for label in layout.parentWidget().findChildren(QLabel):
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            if label.parentWidget().__class__ is ColorRow:
                label.setMinimumWidth(165)
            if label.styleSheet():
                label.setStyleSheet("")
                label.setObjectName("SettingsDescription")
        for field in layout.parentWidget().findChildren(QComboBox):
            field.setMinimumWidth(150)
            field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for field in layout.parentWidget().findChildren(QDoubleSpinBox):
            field.setMinimumWidth(120)
        for check in layout.parentWidget().findChildren(QCheckBox):
            text = check.text()
            if " (" in text:
                short, detail = text.split(" (", 1)
                check.setText(short)
                description = QLabel(detail.rstrip(")"))
                description.setWordWrap(True)
                description.setObjectName("SettingsDescription")
                parent_layout = check.parentWidget().layout()
                parent_layout.insertWidget(parent_layout.indexOf(check) + 1, description)

    @staticmethod
    def _make_scrollable(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(widget)
        widget.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)
        return scroll

    def _fill_theme_choices(self):
        self.cmb_theme_mode.clear()
        self.cmb_theme_mode.addItem("Studio (light, blue accent)", "studio")
        self.cmb_theme_mode.addItem("Graphite (dark, amber accent)", "graphite")
        self.cmb_theme_mode.addItem("Atelier (warm, green accent)", "atelier")
        self.cmb_theme_mode.addItem("Follow Omarchy", "omarchy")
        for name in theme.custom_themes():
            self.cmb_theme_mode.addItem(f"Custom: {name}", f"user:{name}")

    def _open_theme_editor(self):
        from omacad.ui.theme_editor import ThemeEditorDialog
        dlg = ThemeEditorDialog(self)
        dlg.editor.saved.connect(self._theme_saved)
        dlg.exec()

    def _theme_saved(self, key: str):
        """A theme was saved (or deleted) in the editor."""
        self._just_saved = key
        # Refresh theme mode combo box so custom themes show up
        cur_data = self.cmb_theme_mode.currentData()
        self._fill_theme_choices()
        idx = self.cmb_theme_mode.findData(key if key else cur_data)
        if idx >= 0:
            self.cmb_theme_mode.setCurrentIndex(idx)

    def reject(self):
        theme.set_preview(None)
        super().reject()

    def reset_all(self):
        self.row_arrow.reset_color()
        self.row_measure.reset_color()
        self.row_sketch.reset_color()
        self.row_construct.reset_color()
        self.row_finished.reset_color()
        self.row_highlight.reset_color()
        self.row_hover.reset_color()
        self.spn_hover_w.setValue(3.5)
        self.spn_sketch_w.setValue(1.6)
        self.spn_selected_w.setValue(2.4)
        self.row_selected.reset_color()
        idx_p = self.cmb_pos.findData("bottom_right")
        if idx_p >= 0:
            self.cmb_pos.setCurrentIndex(idx_p)
        self.chk_autohide.setChecked(True)
        self.chk_invert_zoom.setChecked(False)
        self.chk_tangent_edges.setChecked(False)
        self.cmb_primitive_decimals.setCurrentIndex(0)
        self.spn_guide_gap.setValue(6.0)
        self.spn_grid.setValue(5.0)
        self.spn_fillet.setValue(2.0)
        self.chk_auto_restart.setChecked(True)
        self.cmb_theme_mode.setCurrentIndex(max(0, self.cmb_theme_mode.findData("omarchy")))   # the default
        self.cmb_icon_theme.setCurrentIndex(0)
        self.cmb_curves.setCurrentIndex(max(0, self.cmb_curves.findData(96)))
        self.spn_arrow_size.setValue(1.0)
        self.spn_arrow_gap.setValue(2.0)
        self.cmb_btn_size.setCurrentIndex(max(0, self.cmb_btn_size.findData(1.0)))
        self.chk_labels.setChecked(False)
        self.chk_group_primitives.setChecked(True)
        self.chk_group_modify.setChecked(False)
        self.chk_group_inspect.setChecked(True)
        self.chk_group_constraints.setChecked(True)
        idx_ai = self.cmb_ai_agent.findData("omarchy")
        if idx_ai >= 0:
            self.cmb_ai_agent.setCurrentIndex(idx_ai)

    def _width_row(self, layout, label: str, key: str, default: float, tip: str) -> QDoubleSpinBox:
        """A labelled px-thickness field for `key`, added to `layout`."""
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setMinimumWidth(200)
        spn = QDoubleSpinBox()
        spn.setRange(0.5, 12.0)
        spn.setSingleStep(0.2)
        spn.setDecimals(1)
        spn.setSuffix(" px")
        spn.setValue(float(self.settings.get(key, default)))
        spn.setToolTip(tip)
        row.addWidget(lbl)
        row.addWidget(spn)
        row.addStretch()
        layout.addLayout(row)
        return spn

    def accept(self):
        self.save_and_close()

    def save_and_close(self):
        new_data = {
            "arrow_color": self.row_arrow.current_hex,
            "measure_color": self.row_measure.current_hex,
            "sketch_line_color": self.row_sketch.current_hex,
            "sketch_construction_color": self.row_construct.current_hex,
            "sketch_finished_color": self.row_finished.current_hex,
            "highlight_color": self.row_highlight.current_hex,
            "hover_line_color": self.row_hover.current_hex,
            "hover_line_width": self.spn_hover_w.value(),
            "sketch_line_width": self.spn_sketch_w.value(),
            "selected_line_width": self.spn_selected_w.value(),
            "selected_line_color": self.row_selected.current_hex,
            "palette_position": self.cmb_pos.currentData(),
            "autohide_palette_on_measure": self.chk_autohide.isChecked(),
            "invert_zoom": self.chk_invert_zoom.isChecked(),
            "show_tangent_edges": self.chk_tangent_edges.isChecked(),
            "primitive_drag_decimals": self.cmb_primitive_decimals.currentData(),
            "guide_line_gap": self.spn_guide_gap.value(),
            "grid_step": self.spn_grid.value(),
            "fillet_default_radius": self.spn_fillet.value(),
            "arrow_size": self.spn_arrow_size.value(),
            "arrow_gap": self.spn_arrow_gap.value(),
            "button_scale": float(self.cmb_btn_size.currentData() or 1.0),
            "show_button_labels": self.chk_labels.isChecked(),
            "group_primitives": self.chk_group_primitives.isChecked(),
            "group_modify": self.chk_group_modify.isChecked(),
            "group_inspect": self.chk_group_inspect.isChecked(),
            "group_constraints": self.chk_group_constraints.isChecked(),
            "ai_agent": str(self.cmb_ai_agent.currentData() or "omarchy"),
            "curve_segments": self.cmb_curves.currentData(),
            "view_projection": self.cmb_projection.currentData(),
            "view_fov": self.spn_fov.value(),
            "auto_restart": self.chk_auto_restart.isChecked(),
            "rfc_name": self.edt_rfc_name.text().strip(),
            "rfc_token": self.edt_rfc_token.text().strip(),
            "icon_theme": self.cmb_icon_theme.currentData(),
        }

        # Resolve theme mode choice
        mode_val = str(self.cmb_theme_mode.currentData() or "")
        if mode_val == "omarchy":
            new_data["theme_mode"] = "omarchy"
            fixed_name = None
        else:   # Studio, Graphite, Atelier or a theme made in the editor ("user:<name>")
            new_data["theme_mode"] = "fixed"
            new_data["theme_name"] = mode_val
            fixed_name = mode_val

        theme.PREVIEW = None
        self.settings.update(new_data)
        theme.clear_icon_cache()
        theme.set_fixed_theme(fixed_name)
        super().accept()
