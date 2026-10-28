"""Icon rendering and menu icon style helpers."""

from pathlib import Path
from typing import Optional
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QProxyStyle, QStyle

_icon_cache = {}

ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"

EMOJI_TO_TOOL = {
    "✏️": "sketch",
    "📐": "offset_plane",
    "🖼️": "canvas",
    "📏": "measure",
    "✂️": "trim",
    "⬆️": "extrude",
    "🔄": "revolve",
    "🔘": "fillet",
    "◢": "chamfer",
    "🔁": "pattern",
    "📦": "box",
    "🥫": "cylinder",
    "⬢": "hexagon",
    "⚽": "sphere",
    "🧮": "parameters",
    "🔩": "thread",
    "🔗": "combine",
    "🪚": "split_body",
    "🐚": "shell",
    "↔️": "move",
    "✥": "move",
    "🗑️": "delete",
    "⚙️": "settings",
    "⭕": "circle",
    "⬡": "polygon",
    "⌒": "arc",
    "💊": "slot",
    "🔤": "text",
    "🔖": "emboss",
    "╭": "fillet_sk",
    "🪞": "mirror",
    "⧉": "offset_sk",
    "🟣": "project",
    "⚡": "construct",
    "🔲": "rect",
    "⛶": "rect",
    "▢": "rect",
    "▣": "rect",
    # drawn only in the Studio set; the other sets keep the emoji for these
    "〰️": "sweep",
    "🏺": "loft",
    "🧪": "pipe",
    "🔺": "cone",
    "🫙": "jar",
    "🐝": "honeycomb",
    "📥": "import",
    "📊": "statistics",
    "↻": "rotate",
    "⁘": "pattern_sk",
    "┄": "construction_line",
    "🩹": "fix_sketch",
    "✅": "finish", "✔️": "finish", "✖️": "cancel",
    "↩️": "undo", "↪️": "redo",
    "⏮": "timeline_rewind", "⏮️": "timeline_rewind", "⏭": "timeline_end", "⏭️": "timeline_end",
    "▶️": "play", "⏸️": "pause",
    "━": "c_horizontal", "┃": "c_vertical", "•": "c_coincident", "∥": "c_parallel", "⟂": "c_perpendicular",
    "＝": "c_equal", "◠": "c_tangent", "◎": "c_concentric", "⋈": "c_midpoint", "⇋": "c_symmetric", "⊙": "c_center", "🔒": "c_fix",
    "⬇️": "lay_flat", "🌐": "origin", "🎥": "camera", "🏷️": "rename", "👁": "eye", "👁️": "eye", "🚫": "eye_off",
    "💾": "save", "📂": "open", "📄": "document", "📤": "export", "🚪": "exit", "❓": "help", "ℹ️": "info",
    "🔳": "edges", "📁": "folder", "🔍": "analysis", "🔎": "find", "🧭": "locate", "🧱": "parametric",
    "🧊": "body", "●": "history_end", "🕳️": "hole", "💥": "explode", "📍": "point", "🎯": "look_at",
    "🗑": "delete", "✋": "pan", "👆": "pointer", "📋": "overview", "🛠️": "settings",
}

# Where one emoji stands for several commands, Studio draws each its own icon (other sets keep the emoji's icon)
COMMAND_ICONS = {
    "line": "line", "spline": "spline", "smart_circle": "smart_circle", "pattern_linear": "pattern_linear",
    "pattern_circular": "pattern_circular", "pattern_fill": "pattern_fill", "offset_face": "offset_face",
    "section": "section", "finish_sketch": "finish", "move_sketch": "move", "modify_body": "move",
}

STUDIO_ICONS = "studio"   # line icons in one colour (the text), blue while the tool is active

def clear_icon_cache():
    _icon_cache.clear()

def tool_icon(symbol_or_name: str, px: int = 24, colour: Optional[str] = None) -> QIcon:
    """Returns a themed SVG vector QIcon (solid, blueprint, semantic) or falls back to emoji_icon."""
    from omacad.ui.settings import get_settings
    icon_theme = get_settings().get("icon_theme", "solid")
    tool_key = EMOJI_TO_TOOL.get(symbol_or_name, symbol_or_name)
    svg_path = ICONS_DIR / icon_theme / f"{tool_key}.svg"

    if not svg_path.exists():
        return emoji_icon(symbol_or_name, px)

    # Color adaptation for current theme
    from omacad.ui import theme
    active_palette = theme.palette()
    is_light = (active_palette.mode == "light")
    cur_color = "#1D2939" if is_light else "#E0E3E7"
    if active_palette.studio:
        cur_color = theme._hex(active_palette.foreground)
    if colour and icon_theme == STUDIO_ICONS:
        cur_color = colour          # e.g. white on a coloured button
    accent_color = active_palette.map_hex("#E26D28")

    cache_key = (icon_theme, tool_key, px, is_light, cur_color, accent_color)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    try:
        svg_text = svg_path.read_text(encoding="utf-8")
        if icon_theme == STUDIO_ICONS:
            # one colour like the design proposal; the checked (active) tool gets the accent blue
            accent = theme._hex(active_palette.accent) if active_palette.studio else accent_color
            icon = QIcon(_svg_pixmap(_one_colour(svg_text, cur_color), px))
            icon.addPixmap(_svg_pixmap(_one_colour(svg_text, accent), px), QIcon.Mode.Normal, QIcon.State.On)
        else:
            # Replace currentColor with theme text color
            svg_text = svg_text.replace("currentColor", cur_color)
            if icon_theme != "semantic":
                svg_text = svg_text.replace("#E26D28", accent_color)
            icon = QIcon(_svg_pixmap(svg_text, px))
        _icon_cache[cache_key] = icon
        return icon
    except Exception:
        return emoji_icon(symbol_or_name, px)


def _one_colour(svg_text: str, colour: str) -> str:
    import re
    svg_text = re.sub(r'\s(?:fill-|stroke-)?opacity="[^"]*"', "", svg_text)   # full-strength lines, as in the proposal
    return re.sub(r"#[0-9A-Fa-f]{6}\b", colour, svg_text.replace("currentColor", colour))


def _svg_pixmap(svg_text: str, px: int) -> QPixmap:
    scale = 2
    pm = QPixmap(px * scale, px * scale)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm

def _studio_icons() -> bool:
    from omacad.ui.settings import get_settings
    return get_settings().get("icon_theme", "solid") == STUDIO_ICONS


def named_icon(name: str, fallback: str, px: int = 24) -> QIcon:
    """The Studio icon `name` when the Studio set is chosen and has it, else the fallback emoji/symbol as before."""
    if name and _studio_icons() and (ICONS_DIR / STUDIO_ICONS / f"{name}.svg").exists():
        return tool_icon(name, px)
    return emoji_icon(fallback, px)


def command_icon(cid: str, symbol: str, px: int = 24) -> QIcon:
    """A command's icon: its own Studio icon if it has one, else what its symbol gives in the chosen set."""
    if cid in COMMAND_ICONS and _studio_icons():
        return named_icon(COMMAND_ICONS[cid], symbol, px)
    return tool_icon(symbol, px)


def studio_symbol(text: str):
    """(Studio icon name, text without the emoji) when the text starts with an emoji that has a Studio icon and the
    Studio set is chosen, else (None, text): buttons and headings then show the line icon instead of the emoji."""
    emoji, rest = split_emoji(text)
    name = EMOJI_TO_TOOL.get(emoji)
    if emoji and name and _studio_icons() and (ICONS_DIR / STUDIO_ICONS / f"{name}.svg").exists():
        return name, rest
    return None, text


def set_button_text(button, text: str, px: int = 18, colour: Optional[str] = None) -> None:
    """Button text that may start with an emoji: with the Studio icons that emoji becomes the button's line icon
    (in `colour` on a coloured button)."""
    name, rest = studio_symbol(text)
    if name:
        button.setIcon(tool_icon(name, px, colour))
        button.setText(rest)
    else:
        button.setText(text)


def emoji_icon(ch: str, px: int = 24) -> QIcon:
    """The emoji drawn as a real QIcon of a chosen size (emoji in text would stay at the font size).
    With the Studio icon set, emoji that have a Studio line icon (menus, tree, timeline) use it instead."""
    name = EMOJI_TO_TOOL.get(ch)
    if name and _studio_icons() and (ICONS_DIR / STUDIO_ICONS / f"{name}.svg").exists():
        return tool_icon(ch, px)
    key = ("emoji", ch, px)
    if key not in _icon_cache:
        scale = 2  # crisp on HiDPI
        pm = QPixmap(px * scale, px * scale)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        font = QFont("Noto Color Emoji")
        font.setPixelSize(int(px * scale * 0.78))
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, ch)
        painter.end()
        pm.setDevicePixelRatio(scale)
        _icon_cache[key] = QIcon(pm)
    return _icon_cache[key]

def split_emoji(text: str):
    """('📁', 'Name') for '📁 Name'; ('', text) if the text does not start with an emoji."""
    import unicodedata
    head = text[:1]
    if head and ord(head) > 0x2000 and unicodedata.category(head) in ("So", "Sk") and head != "•":
        i = 1
        while i < len(text) and (ord(text[i]) in (0xFE0F, 0x200D) or unicodedata.category(text[i]) in ("Mn", "Sk")):
            i += 1
        return text[:i], text[i:].lstrip()
    return "", text

class BigIconStyle(QProxyStyle):
    """Larger icons everywhere in menus, tree views and tool buttons."""

    _SIZES = {
        QStyle.PixelMetric.PM_SmallIconSize: 24,
        QStyle.PixelMetric.PM_ToolBarIconSize: 30,
        QStyle.PixelMetric.PM_LargeIconSize: 36,
    }

    def pixelMetric(self, metric, option=None, widget=None):
        # Called for every widget while painting: it must never raise (an error here re-enters the style
        # while the error box is drawn and floods the screen on some PySide versions / Windows).
        try:
            size = self._SIZES.get(metric)
            if size is not None:
                return size
            return self.baseStyle().pixelMetric(metric, option, widget)
        except Exception:
            return 16

_big_icon_style_instance: Optional[BigIconStyle] = None

def ensure_big_icon_style(app) -> None:
    """Install BigIconStyle once on QApplication and keep a module-level reference."""
    global _big_icon_style_instance
    if app is not None and _big_icon_style_instance is None:
        _big_icon_style_instance = BigIconStyle("Fusion")
        app.setStyle(_big_icon_style_instance)
