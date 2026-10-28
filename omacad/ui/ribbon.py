"""
Omacad - Top Ribbon Toolbar
Fusion 360 style ribbon with SOLID, SKETCH tabs and tool buttons.
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabBar, QTabWidget, QToolButton, QLabel, QFrame, QSizePolicy, QScrollArea
)
from PySide6.QtGui import QFont, QFontMetrics
from omacad.ui.sketch_tools import RECT_TOOLS, rect_icon
from omacad.ui import commands

CIRCLE_TOOLS = ('CIRCLE', 'SMART_CIRCLE')
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.model.document import Document



def ribbon_button_scale() -> float:
    from omacad.ui.settings import get_settings
    try:
        return float(get_settings().get("button_scale", 1.0))
    except Exception:
        return 1.0


def ribbon_labels() -> bool:
    """Whether ribbon buttons show their name under the icon (off = icon only, name in the tooltip)."""
    from omacad.ui.settings import get_settings
    return bool(get_settings().get("show_button_labels", False))


def ribbon_height(scale: float) -> int:
    """Height of the ribbon tab widget: tab bar + one row of buttons."""
    if ribbon_labels():
        return max(70, int(round(104 * scale)))
    return max(50, int(round(66 * scale)))


# Studio: buttons without frames; a light blue fill marks the active tool, a blue outline a suggested one.
_STUDIO_BUTTON = """
    QToolButton { background-color: transparent; border: 1px solid transparent; border-radius: 6px; color: @text; }
    QToolButton:hover { background-color: @field; border: 1px solid @border; color: @text; }
    QToolButton:pressed, QToolButton:checked { background-color: @selection; border: 1px solid @selection; color: @accent; }
    QToolButton:disabled { color: @muted; }
    QToolButton[suggested="true"] { background-color: @selection; border: 1px solid @accent; }
    QToolButton::menu-indicator { image: none; width: 0; }
"""


class RibbonButton(QToolButton):
    """Large Fusion 360 style ribbon tool button with vertical icon and label."""

    def __init__(self, text: str, icon_symbol: str, parent: Optional[QWidget] = None, command: str = ""):
        super().__init__(parent)
        self.raw_text = text
        self.icon_symbol = icon_symbol
        self.icon_command = command         # a command id: lets the Studio icons give it its own icon
        self.setText(text)
        self.apply_scale()
        self.setToolTip("")

    def setToolTip(self, tip: str):
        """The tooltip always starts with the button's name, since the label may be hidden."""
        name = " ".join(self.raw_text.split())
        super().setToolTip(f"<b>{name}</b><br>{tip}" if tip and tip != name else f"<b>{name}</b>")

    def apply_scale(self):
        scale = ribbon_button_scale()
        icon_px = max(18, int(round(30 * scale)))
        font_px = max(8, int(round(10 * scale)))
        min_h = max(44, int(round(62 * scale)))
        labels = ribbon_labels()
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if labels
                                else Qt.ToolButtonStyle.ToolButtonIconOnly)
        if not labels:
            min_h = icon_px + max(6, int(round(8 * scale)))
        self.setIcon(theme.command_icon(self.icon_command, self.icon_symbol, icon_px))
        self.setIconSize(QSize(icon_px, icon_px))
        self.setMinimumHeight(min_h)
        style(self, f"""
            QToolButton {{
                background-color: rgba(45, 49, 54, 0.4);
                border: 1px solid #3E434B;
                border-radius: 4px;
                color: #D2D6DC;
                font-size: {font_px}px;
                font-weight: 500;
                text-align: center;
                padding: {max(1, int(round(2 * scale)))}px;
            }}
            QToolButton:hover {{
                background-color: #353A42;
                border: 1px solid #5A6270;
                color: #FFFFFF;
            }}
            QToolButton:pressed, QToolButton:checked {{
                background-color: #E26D28;
                border: 1px solid #FF7E36;
                color: #FFFFFF;
            }}
            QToolButton[suggested="true"] {{
                border: 1px solid #E26D28;
                background-color: rgba(226, 109, 40, 0.16);
            }}
        """, studio=_STUDIO_BUTTON)
        self.ensurePolished()
        if not labels:
            self.setMinimumWidth(icon_px + max(8, int(round(10 * scale))))
            return
        fm = self.fontMetrics()
        widest = max(fm.horizontalAdvance(line) for line in self.text().split("\n"))
        base_w = max(40, int(round(54 * scale)))
        pad_w = max(8, int(round(12 * scale)))
        self.setMinimumWidth(max(base_w, widest + pad_w))


class Ribbon(QWidget):
    """Top command ribbon for CAD workspaces."""

    # Action Signals
    create_sketch_clicked = Signal()
    extrude_clicked = Signal()
    hole_clicked = Signal()
    revolve_clicked = Signal()
    emboss_clicked = Signal()
    fillet_clicked = Signal()
    project_clicked = Signal()
    chamfer_clicked = Signal()
    pattern_clicked = Signal()
    pattern_kind_clicked = Signal(str)
    offset_plane_clicked = Signal()
    section_clicked = Signal()
    measure_clicked = Signal()
    parameters_clicked = Signal()
    box_clicked = Signal()
    cylinder_clicked = Signal()
    hexagon_clicked = Signal()
    cone_clicked = Signal()
    sweep_clicked = Signal()
    loft_clicked = Signal()
    pipe_clicked = Signal()
    jar_clicked = Signal()
    combine_clicked = Signal()
    delete_clicked = Signal()
    split_body_clicked = Signal()
    shell_clicked = Signal()
    offset_face_clicked = Signal()
    honeycomb_clicked = Signal()
    move_clicked = Signal()
    thread_clicked = Signal()
    canvas_clicked = Signal()
    import_3mf_clicked = Signal()
    inspect_clicked = Signal()
    settings_clicked = Signal()

    # Sketch Tools
    constraint_clicked = Signal(str)  # HORIZONTAL, VERTICAL, PARALLEL, ...
    sketch_tool_selected = Signal(str)  # "LINE", "RECT", "CENTER_RECT", "CIRCLE", "ARC", "SLOT", "FILLET", "DIMENSION"
    finish_sketch_clicked = Signal()
    fix_sketch_clicked = Signal()
    toggle_construction_clicked = Signal()
    construction_tool_requested = Signal(str)     # draw this tool as construction geometry (LINE, CIRCLE)

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.doc.add_change_listener(self.sync_active_tab)
        self.doc.add_change_listener(self.sync_context)
        self.selected_edge_count = lambda: 0     # set by the main window (edges are picked in the view)
        self.suggested = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setObjectName("Ribbon")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        style(self, "QWidget#Ribbon { background: transparent; }",
              "QWidget#Ribbon { background-color: @surface; border-bottom: 1px solid @border; }")

        # Tab Widget
        self.tabs = QTabWidget()
        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(ribbon_height(scale))
        layout.addWidget(self.tabs)

        # 1. SOLID Tab
        self.solid_tab = QWidget()
        self.setup_solid_tab()
        self.tabs.addTab(self._scrollable(self.solid_tab), "SOLID")

        # 2. SKETCH Tab
        self.sketch_tab = QWidget()
        self.setup_sketch_tab()
        self.tabs.addTab(self._scrollable(self.sketch_tab), "SKETCH")

        # The SOLID / SKETCH selector is not part of the ribbon: it is a small bar the main window puts in the 3D view,
        # above the Browser. The QTabWidget keeps the pages; its own tab bar is hidden and this one drives it.
        self.tabs.tabBar().hide()
        self.workspace_bar = QTabBar()
        self.workspace_bar.setDrawBase(False)
        self.workspace_bar.setExpanding(False)
        self.workspace_bar.setUsesScrollButtons(False)       # it is tiny; never scroll its two tabs
        self.workspace_bar.addTab("SOLID")
        self.workspace_bar.addTab("SKETCH")
        self.workspace_bar.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.workspace_bar.setCurrentIndex)
        # Hide sketch tab by default until sketch is started
        self.tabs.setTabVisible(1, False)
        self.workspace_bar.setTabVisible(1, False)
        self.equalize_buttons()
        self.fit_height()

    def equalize_buttons(self):
        """Every ribbon button gets the same size (in both tabs): with names, the widest plain button sets the width
        and the tallest the height; icon-only, icon plus a small margin. Buttons sized after their own text looked
        uneven. (Dropdown buttons draw their arrow inside the same size.)"""
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)       # buttons of a rebuilt tab are gone first
        buttons = self.findChildren(RibbonButton)
        if not buttons:
            return
        for b in buttons:
            b.setMinimumSize(0, 0)
            b.setMaximumSize(16777215, 16777215)
        scale = ribbon_button_scale()
        icon_px = max(18, int(round(30 * scale)))
        if ribbon_labels():
            plain = [b for b in buttons if not b.menu()] or buttons
            w = max(b.sizeHint().width() for b in plain)
            h = max(b.sizeHint().height() for b in buttons)
        else:
            w = icon_px + max(8, int(round(10 * scale)))
            h = icon_px + max(6, int(round(8 * scale)))
        for b in buttons:
            b.setFixedSize(w, h)

    def fit_height(self):
        """The ribbon is as high as its tab bar plus the tallest page (the sketch page has two rows of constraint
        buttons). A fixed number clipped the buttons on Windows, where the tab bar and fonts are taller."""
        pages = max(self.solid_tab.sizeHint().height(), self.sketch_tab.sizeHint().height())
        need = pages + 10      # + the sideways scrollbar (the tab selector is not in the ribbon)
        self.tabs.setFixedHeight(max(ribbon_height(ribbon_button_scale()), need))

    def update_button_scale(self):
        """Update heights, icons and fonts for all ribbon buttons when button_scale setting changes."""
        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(ribbon_height(scale))
        for btn in self.findChildren(RibbonButton):
            btn.apply_scale()
        self.equalize_buttons()
        self.fit_height()
        if hasattr(self, "btn_finish") and self.btn_finish:
            self.btn_finish.setMinimumSize(max(100, int(round(140 * scale))), max(34, int(round(48 * scale))))

    @staticmethod
    def _scrollable(content: QWidget) -> QScrollArea:
        """A ribbon page scrolls sideways instead of squashing its buttons when the window is narrow
        (e.g. tiled to half the screen)."""
        area = QScrollArea()
        area.setWidget(content)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        style(area, """
            QScrollArea { background: transparent; }
            QScrollBar:horizontal { height: 6px; background: transparent; margin: 0; }
            QScrollBar::handle:horizontal { background: #484F5A; border-radius: 3px; min-width: 30px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """, "QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget { background: transparent; }")
        return area

    def rebuild_ribbon(self):
        """Reconstruct both tabs to reflect updated button scale, grouping, or tool preferences."""
        # Clean up existing children in solid_tab and sketch_tab
        for tab in (self.solid_tab, self.sketch_tab):
            layout = tab.layout()
            if layout is not None:
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
                QWidget().setLayout(layout)

        scale = ribbon_button_scale()
        self.tabs.setFixedHeight(ribbon_height(scale))
        self.setup_solid_tab()
        self.setup_sketch_tab()
        self.equalize_buttons()
        self.fit_height()
        self.sync_active_tab()
        self.suggested = set()
        self.sync_context()

    # --- building blocks: every button and menu entry comes from omacad.ui.commands ----------------------------------
    def _emit_command(self, cid: str):
        c = commands.get(cid)
        if c.signal == "sketch_tool_selected":
            self.select_sketch_tool(c.arg)          # also checks the right button
        elif c.arg is not None:
            getattr(self, c.signal).emit(c.arg)
        else:
            getattr(self, c.signal).emit()

    def _command_button(self, cid: str, checkable: bool = False) -> "RibbonButton":
        c = commands.get(cid)
        btn = RibbonButton(commands.button_text(cid), c.icon, command=cid)
        btn.setCheckable(checkable)
        btn.setToolTip(commands.tooltip(cid))
        btn.setProperty("command", cid)
        btn.clicked.connect(lambda _=False, cid=cid: self._emit_command(cid))
        self.command_buttons[cid] = btn
        return btn

    def _command_menu(self, parent, cids) -> "QMenu":
        from PySide6.QtWidgets import QMenu
        menu = QMenu(parent)
        theme.style_menu(menu)
        for cid in cids:
            c = commands.get(cid)
            act = menu.addAction(theme.command_icon(cid, c.icon, 18), commands.menu_text(cid))
            act.setToolTip(c.tip)
            act.triggered.connect(lambda _=False, cid=cid: self._emit_command(cid))
        return menu

    def _dropdown(self, row, spec, grouped: bool):
        """A ribbon dropdown (Primitives, Insert, ...) or, when not grouped, its commands as separate buttons."""
        did, text, icon, tip, cids = spec
        if not grouped:
            for cid in cids:
                row.addWidget(self._command_button(cid))
            return
        btn = RibbonButton(f"{text}\n▾", icon, command=did)
        btn.setToolTip(tip)
        btn.setProperty("command", did)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setMenu(self._command_menu(btn, cids))
        self.command_buttons[did] = btn
        row.addWidget(btn)

    def _group(self, h_layout, title: str, first: bool = False) -> QHBoxLayout:
        """A named group of buttons (Fusion style: the group's name under its buttons). Returns the button row."""
        if not first:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            style(sep, "color: #353940;", "QFrame { color: @border; }")
            h_layout.addWidget(sep)
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        col.addLayout(row)
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style(caption, "color: #8A919C; font-size: 9px; font-weight: bold; letter-spacing: 1px; background: transparent;",
              "QLabel { color: @muted; font-size: 10px; font-weight: 600; }")
        col.addWidget(caption)
        box.setObjectName(f"RibbonGroup_{title}")
        h_layout.addWidget(box)
        return row

    def setup_solid_tab(self):
        from omacad.ui.settings import get_settings
        settings = get_settings()
        grouped = {"primitives": bool(settings.get("group_primitives", True)),
                   "modify_body": bool(settings.get("group_modify", False)),
                   "inspect": bool(settings.get("group_inspect", True)),
                   "insert": True}
        self.command_buttons = {}
        h_layout = QHBoxLayout(self.solid_tab)
        h_layout.setContentsMargins(4, 1, 4, 1)
        h_layout.setSpacing(2)
        for i, (title, items) in enumerate(commands.SOLID_GROUPS):
            row = self._group(h_layout, title, first=i == 0)
            for item in items:
                if isinstance(item, tuple):
                    self._dropdown(row, item, grouped[item[0]])
                elif item == "pattern":          # the button patterns as before, its arrow picks the kind
                    btn = self._command_button("pattern")
                    btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                    btn.setMenu(self._command_menu(btn, commands.PATTERNS))
                    row.addWidget(btn)
                else:
                    row.addWidget(self._command_button(item))
        h_layout.addStretch()
        # app preferences, not a modelling command: no group, but level with the group buttons (not centred on them
        # together with their group names below)
        h_layout.addWidget(self._command_button("settings"), 0, Qt.AlignmentFlag.AlignTop)

    def setup_sketch_tab(self):
        from omacad.ui.settings import get_settings
        settings = get_settings()
        group_constraints = bool(settings.get("group_constraints", True))
        sketch_buttons = {        # the names the main window and tests use for the sketch buttons
            "line": "btn_line", "polygon": "btn_polygon", "arc": "btn_arc", "spline": "btn_spline", "slot": "btn_slot", "text": "btn_text",
            "offset_sketch": "btn_offset_sk", "mirror_sketch": "btn_mirror_sk", "project": "btn_project_sk",
            "dimension": "btn_dim", "fillet_sketch": "btn_fillet_sk", "trim": "btn_trim_sk", "move_sketch": "btn_move",
            "rotate_sketch": "btn_rotate_sk", "construction": "btn_construct",
        }
        h_layout = QHBoxLayout(self.sketch_tab)
        h_layout.setContentsMargins(4, 1, 4, 1)
        h_layout.setSpacing(2)
        scale = ribbon_button_scale()
        for i, (title, items) in enumerate(commands.SKETCH_GROUPS):
            row = self._group(h_layout, title, first=i == 0)
            for item in items:
                if item == "rect":
                    self._build_rect_button()
                    row.addWidget(self.btn_rect)
                elif item == "circle":
                    self.btn_circle = self._command_button("circle", checkable=True)
                    self.btn_circle.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                    self.btn_circle.setMenu(self._command_menu(self.btn_circle, ["circle", "smart_circle"]))
                    row.addWidget(self.btn_circle)
                elif item == "construction":
                    # the arrow picks what to draw as a helper line straight away (Björn #97)
                    self.btn_construct = self._command_button("construction", checkable=True)
                    self.btn_construct.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                    from PySide6.QtWidgets import QMenu
                    menu = QMenu(self.btn_construct)
                    theme.style_menu(menu)
                    for tool, label in (("LINE", "Construction Line"), ("CIRCLE", "Construction Circle")):
                        act = menu.addAction(label)
                        act.triggered.connect(lambda _=False, t=tool: self.construction_tool_requested.emit(t))
                    self.btn_construct.setMenu(menu)
                    row.addWidget(self.btn_construct)
                elif item == "constraints":
                    self._build_constraints(row, group_constraints, scale)
                else:
                    btn = self._command_button(item, checkable=item != "project" and item != "measure")
                    if item in sketch_buttons:
                        setattr(self, sketch_buttons[item], btn)
                    row.addWidget(btn)
        h_layout.addStretch()

        # Big Green Finish Sketch Button (Fusion 360 hallmark)
        self.btn_finish = QToolButton()
        theme.set_button_text(self.btn_finish, "✅  " + commands.label("finish_sketch"), 20, colour="#FFFFFF")
        self.btn_finish.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_finish.setToolTip(commands.tooltip("finish_sketch"))
        self.btn_finish.setMinimumSize(max(100, int(round(140 * scale))), max(34, int(round(48 * scale))))
        style(self.btn_finish, """
            QToolButton {{
                background-color: #2E7D32;
                border: 1px solid #388E3C;
                border-radius: 4px;
                color: #FFFFFF;
                font-weight: bold;
                font-size: 13px;
                padding: 4px 8px;
            }}
            QToolButton:hover {{
                background-color: #388E3C;
            }}
            QToolButton:pressed {{
                background-color: #1B5E20;
            }}
        """)
        self.btn_finish.clicked.connect(self.finish_sketch_clicked)
        h_layout.addWidget(self.btn_finish)

    CONSTRAINTS = (
        ("HORIZONTAL", "Horizontal", "━", "Make selected lines horizontal"),
        ("VERTICAL", "Vertical", "┃", "Make selected lines vertical"),
        ("COINCIDENT", "Coincident", "•", "Join nearest end points of two selected curves"),
        ("PARALLEL", "Parallel", "∥", "Make selected lines parallel"),
        ("PERPENDICULAR", "Perpendicular", "⟂", "Make selected lines perpendicular"),
        ("EQUAL", "Equal", "＝", "Equal length (lines) or radius (circles)"),
        ("TANGENT", "Tangent", "◠", "Tangent constraint between line and circle, or two curves"),
        ("CONCENTRIC", "Concentric", "◎", "Share same centre point for two circles/arcs"),
        ("MIDPOINT", "Midpoint", "⋈", "Put an end point or circle centre on the middle of a line (select it, then the line)"),
        ("SYMMETRIC", "Symmetric", "⇋", "Mirror two lines or circles across a third selected line"),
        ("CENTER", "Center", "⊙", "Align two rectangle centres horizontally; dimension the vertical edge gap"),
        ("FIX", "Fix", "🔒", "Lock selected lines/circles/points in place"),
    )

    def _build_constraints(self, row, grouped: bool, scale: float):
        if not grouped:
            for ctype, label, icon, tip in self.CONSTRAINTS:
                btn = RibbonButton(label, icon)
                btn.setToolTip(tip + "  (select elements first)")
                btn.clicked.connect(lambda _=False, c=ctype: self.constraint_clicked.emit(c))
                row.addWidget(btn)
            return
        from PySide6.QtWidgets import QMenu, QToolButton
        btn = RibbonButton("Constraints\n▾", "⟂")
        btn.setToolTip("Sketch constraints: select elements first, then pick one")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        theme.style_menu(menu)
        for ctype, label, icon, tip in self.CONSTRAINTS:
            act = menu.addAction(theme.tool_icon(icon, 22), label)
            act.setToolTip(tip + "  (select elements first)")
            act.triggered.connect(lambda _=False, c=ctype: self.constraint_clicked.emit(c))
        btn.setMenu(menu)
        row.addWidget(btn)

    def _build_rect_button(self):
        """One rectangle button with a dropdown: the button itself draws the default rectangle,
        the arrow lists all kinds and lets you pick which one is the default (remembered)."""
        from PySide6.QtGui import QAction, QActionGroup
        from PySide6.QtWidgets import QMenu, QToolButton
        from omacad.ui.settings import get_settings
        self.btn_rect = RibbonButton("Rounded\nRect", "▢")      # widest label sets the width
        self.btn_rect.setCheckable(True)
        self.btn_rect.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        menu = QMenu(self.btn_rect)
        theme.style_menu(menu)
        for tool, (label, _icon) in RECT_TOOLS.items():
            act = menu.addAction(rect_icon(tool, 22), label.replace("\n", " "))
            act.triggered.connect(lambda _=False, t=tool: self.select_sketch_tool(t))
        menu.addSeparator()
        default_menu = menu.addMenu("Button default")
        theme.style_menu(default_menu)
        group = QActionGroup(default_menu)
        self._rect_default_actions = {}
        for tool, (label, _icon) in RECT_TOOLS.items():
            act = default_menu.addAction(rect_icon(tool, 22), label.replace("\n", " "))
            act.setCheckable(True)
            act.setActionGroup(group)
            act.triggered.connect(lambda _=False, t=tool: self.set_rect_default(t))
            self._rect_default_actions[tool] = act
        self.btn_rect.setMenu(menu)
        self.btn_rect.clicked.connect(lambda: self.select_sketch_tool(self.rect_default))
        self.set_rect_default(get_settings().get("rect_default_tool", "RECT"), save=False)

    def set_rect_default(self, tool: str, save: bool = True):
        """The rectangle kind the button draws when clicked; shown on the button and remembered."""
        from omacad.ui.settings import get_settings
        if tool not in RECT_TOOLS:
            tool = "RECT"
        self.rect_default = tool
        label, _icon = RECT_TOOLS[tool]
        self.btn_rect.setText(label)
        self.btn_rect.icon_symbol = tool.lower()       # its own picture; kept when the buttons are restyled
        self.btn_rect.setIcon(rect_icon(tool, 30))     # the default kind's own picture shows on the button
        self._rect_default_actions[tool].setChecked(True)
        if save:
            get_settings().set("rect_default_tool", tool)

    def select_sketch_tool(self, tool_name: str):
        self.btn_line.setChecked(tool_name == "LINE")
        self.btn_rect.setChecked(tool_name in RECT_TOOLS)
        self.btn_circle.setChecked(tool_name in CIRCLE_TOOLS)
        self.btn_polygon.setChecked(tool_name == "POLYGON")
        self.btn_arc.setChecked(tool_name == "ARC")
        if hasattr(self, "btn_spline"):
            self.btn_spline.setChecked(tool_name == "SPLINE")
        self.btn_slot.setChecked(tool_name == "SLOT")
        self.btn_text.setChecked(tool_name == "TEXT")
        if hasattr(self, "btn_fillet_sk"):
            self.btn_fillet_sk.setChecked(tool_name == "FILLET")
        if hasattr(self, "btn_offset_sk"):
            self.btn_offset_sk.setChecked(tool_name == "OFFSET")
        if hasattr(self, "btn_mirror_sk"):
            self.btn_mirror_sk.setChecked(tool_name == "MIRROR")
        if hasattr(self, "btn_trim_sk"):
            self.btn_trim_sk.setChecked(tool_name == "TRIM")
        self.btn_dim.setChecked(tool_name == "DIMENSION")
        self.btn_move.setChecked(tool_name == "MOVE")
        self.btn_rotate_sk.setChecked(tool_name == "ROTATE")
        self.sketch_tool_selected.emit(tool_name)

    def selection_context(self) -> str:
        """What is selected, in the words of commands.CONTEXT ("" for nothing / in a sketch)."""
        doc = self.doc
        if doc.active_sketch is not None:
            return ""
        if self.selected_edge_count():
            return "edges"
        if doc.selected_profile:
            return "profile"
        bodies = [b for b in doc.selected_body_ids if b in doc.bodies]
        return "bodies" if len(bodies) >= 2 else ("body" if bodies else "")

    def sync_context(self):
        """Give the buttons that fit the current selection an accent border (a dropdown gets it for its members)."""
        cids = set(commands.CONTEXT.get(self.selection_context(), ()))
        for spec in (commands.PRIMITIVES, commands.INSERT, commands.MODIFY_BODY, commands.INSPECT):
            if cids & set(spec[4]):
                cids.add(spec[0])
        if cids == self.suggested:
            return
        self.suggested = cids
        for cid, btn in getattr(self, "command_buttons", {}).items():
            try:
                on = cid in cids
                if bool(btn.property("suggested")) != on:
                    btn.setProperty("suggested", on)
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)
            except RuntimeError:        # a button of a rebuilt tab that is already gone
                pass

    def sync_active_tab(self):
        """Shows/hides SKETCH tab when sketch is active."""
        is_sketching = (self.doc.active_sketch is not None)
        self.tabs.setTabVisible(1, is_sketching)
        self.workspace_bar.setTabVisible(1, is_sketching)
        self.workspace_bar.resize(self.workspace_bar.sizeHint())      # grows with the SKETCH tab
        if is_sketching:
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)
            for btn in (
                self.btn_line, self.btn_rect, self.btn_circle, self.btn_arc,
                self.btn_slot, self.btn_polygon, self.btn_text, self.btn_fillet_sk,
                self.btn_trim_sk, self.btn_mirror_sk, self.btn_offset_sk,
                self.btn_dim, self.btn_move, self.btn_rotate_sk,
            ):
                btn.setChecked(False)

