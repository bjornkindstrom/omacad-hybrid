"""Registry of the sketch tools. The right-click menu is built from it, so a new tool shows up there
as soon as it is listed here (a test fails if a tool the viewport handles is missing)."""

# the rectangle kinds behind the one ribbon button: tool -> (label, icon)
RECT_TOOLS = {
    "RECT": ("2-Point\nRect (R)", "🔲"),
    "CENTER_RECT": ("Center\nRect", "⛶"),
    "ROUNDED_RECT": ("Rounded\nRect", "▢"),
    "CENTER_ROUNDED_RECT": ("Center\nRounded", "▣"),
}

def rect_icon(tool: str, px: int = 24):
    """Each rectangle kind has its own picture in every icon set (assets/icons/<set>/<tool in lower case>.svg)."""
    from omacad.ui import theme
    return theme.tool_icon(tool.lower(), px)


def _entry(tool: str, cid: str, group: str):
    from omacad.ui import commands
    return (tool, commands.menu_text(cid), group, None)


# (tool, label, menu group, submenu or None). Order is the menu order: the ribbon's SKETCH groups, with the names and
# keys of omacad.ui.commands.
SKETCH_TOOLS = [
    _entry("LINE", "line", "Create"),
    *[(t, label.replace("\n", " "), "Create", "Rectangle") for t, (label, _i) in RECT_TOOLS.items()],
    _entry("CIRCLE", "circle", "Create"),
    _entry("SMART_CIRCLE", "smart_circle", "Create"),
    _entry("ARC", "arc", "Create"),
    _entry("SPLINE", "spline", "Create"),
    _entry("POLYGON", "polygon", "Create"),
    _entry("SLOT", "slot", "Create"),
    _entry("TEXT", "text", "Create"),
    _entry("OFFSET", "offset_sketch", "Create"),
    _entry("MIRROR", "mirror_sketch", "Create"),
    _entry("DIMENSION", "dimension", "Create"),
    _entry("FILLET", "fillet_sketch", "Modify"),
    _entry("TRIM", "trim", "Modify"),
    _entry("MOVE", "move_sketch", "Modify"),
    _entry("ROTATE", "rotate_sketch", "Modify"),
]
# tool names the viewport uses that are not menu entries
NON_MENU_TOOLS = {"NONE"}
