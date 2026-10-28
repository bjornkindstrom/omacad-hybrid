"""
Omacad - Theme
Follows the active Omarchy theme (~/.local/state/omarchy/current/theme/colors.toml) and its
font, and re-applies itself live when the theme is switched.

The widgets' stylesheets were written with a fixed dark palette. Instead of rewriting every
colour, `themeify` maps them onto the Omarchy palette:
  * neutral greys/blues are placed on the line from the theme's darkest background to its
    foreground by lightness (so light themes invert correctly),
  * the orange accent family becomes the theme accent (chrome) or the theme's most vivid
    colour (the 3D highlight),
  * saturated semantic colours (greens, snap-marker blues ...) are left alone.
"""

import colorsys
import re
import subprocess
import sys
import tomllib
import weakref
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap

STATE_DIR = Path.home() / ".local/state/omarchy/current"
COLORS_FILE = STATE_DIR / "theme/colors.toml"
NAME_FILE = STATE_DIR / "theme.name"

# Bundled themes (the Omarchy ones, copied into assets/themes so they also exist where Omarchy does not, e.g. Windows).
THEMES_DIR = Path(__file__).resolve().parents[2] / "assets" / "themes"
BUILTIN = "builtin"          # the original Omacad dark palette
CUSTOM_DIR = Path.home() / ".config" / "omacad" / "themes"   # themes made in the Settings theme editor
CUSTOM_PREFIX = "user:"      # FIXED_THEME / theme_name of a custom theme: "user:<name>"
PREVIEW: Optional[dict] = None   # unsaved colours from the theme editor, shown live
FIXED_THEME: Optional[str] = None
ROLE_THEMES = ("studio", "graphite", "atelier")   # the themes offered in Settings, next to Follow Omarchy
DEFAULT_ROLE_THEME = "studio"   # None = follow the Omarchy theme live; otherwise the name of a bundled theme (or BUILTIN)

RGB = Tuple[float, float, float]


def _rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(c: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(v))) for v in c))


def _lum(c: RGB) -> float:
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255.0


def _sat(c: RGB) -> float:
    mx, mn = max(c), min(c)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _chroma(c: RGB) -> float:
    return (max(c) - min(c)) / 255.0


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))  # type: ignore[return-value]


ORANGE_BASE = _rgb("#E26D28")   # the accent every stylesheet was written with
NEUTRAL_MAX_CHROMA = 0.25  # (max-min)/255; HSV saturation would misjudge very dark navy greys


class Palette:
    """Omarchy colours plus the derived roles the app needs. Without a theme file the app
    keeps its original look (identity mapping)."""

    def __init__(self, data: Optional[dict]):
        self.loaded = bool(data)
        d = data or {}

        def col(key: str, default: str) -> RGB:
            return _rgb(d.get(key, default))

        self.mode = d.get("mode", "dark")
        self.background = col("background", "#1E2022")
        self.darker = col("darker_background", "#1A1C1E")
        self.foreground = col("foreground", "#E0E3E7")
        self.accent = col("accent", "#E26D28")
        self.muted = col("muted", "#8E95A0")
        # most vivid colour of the theme: used for 3D selection/hover highlights
        vivid = [col(k, "#000000") for k in (
            "accent", "red", "yellow", "green", "cyan", "blue", "magenta",
            "bright_red", "bright_yellow", "bright_green", "bright_cyan", "bright_blue", "bright_magenta",
        ) if k in d]
        best = max(vivid, key=lambda c: _sat(c) * (0.4 + _lum(c)), default=ORANGE_BASE)
        self.highlight = best if (self.loaded and _sat(best) >= 0.3) else ORANGE_BASE
        if not self.loaded:
            self.highlight = ORANGE_BASE
        # explicit overrides from the theme editor
        self.canvas = _rgb(d["canvas"]) if "canvas" in d else None
        self.grid = _rgb(d["grid"]) if "grid" in d else None
        if "highlight" in d:
            self.highlight = _rgb(d["highlight"])
        # Studio-style themes name their surfaces outright (white panels on a grey-blue window, own fields and
        # dividers) instead of letting the dark greys slide along one line; other themes leave these out.
        self.surfaces = {k: _rgb(d[k]) for k in ("window", "surface", "field", "border") if k in d}
        self.studio = len(self.surfaces) == 4
        self.font = d.get("font") or ""
        self.selection = _rgb(d["selection"]) if "selection" in d else None
        self.on_accent = _rgb(d["on_accent"]) if "on_accent" in d else None
        self.ok = col("green", "#2E7D32")         # "done / fully defined" text in the role themes
        self.radius = float(d.get("radius", 8))

    # -- mapping -----------------------------------------------------------
    def _neutral(self, c: RGB) -> RGB:
        if self.studio:
            return self._studio_neutral(c)
        t = max(0.0, min(1.0, (_lum(c) - 0.10) / 0.80))
        return _mix(self.darker, self.foreground, t)

    def _studio_neutral(self, c: RGB) -> RGB:
        """The dark stylesheets use their greys by role: the darkest for fields and the status bar, the window a step
        up, panels and menus above that, then buttons, dividers, muted text and text. Each band gets its Studio
        surface, so panels come out white while fields and the window stay grey-blue."""
        s = self.surfaces
        stops = [(_lum(_rgb(h)), role) for h, role in (
            ("#1A1C1E", s["field"]), ("#1E2022", s["window"]), ("#25282C", s["surface"]), ("#2D3136", s["field"]),
            ("#3D424A", s["border"]), ("#555C68", s["border"]), ("#8E95A0", self.muted), ("#E0E3E7", self.foreground))]
        lum = _lum(c)
        if lum <= stops[0][0]:
            return stops[0][1]
        for (l0, c0), (l1, c1) in zip(stops, stops[1:]):
            if lum <= l1:
                return _mix(c0, c1, (lum - l0) / (l1 - l0))
        return self.foreground

    def map_alpha(self, c: RGB, a: float) -> float:
        """Studio panels are solid white cards; the dark themes' see-through panels (alpha >= 0.7) become opaque."""
        if self.studio and a >= 0.7 and _chroma(c) < NEUTRAL_MAX_CHROMA:
            return 1.0
        return a

    def _accentish(self, c: RGB, target: RGB) -> RGB:
        ratio = max(c) / max(ORANGE_BASE)
        return tuple(min(255.0, v * ratio) for v in target)  # type: ignore[return-value]

    def map_rgb(self, c: RGB, orange: str = "accent") -> RGB:
        if not self.loaded:
            return c
        if _lum(c) > 0.97 and _sat(c) < 0.05:
            return c  # pure white text stays white
        if _chroma(c) < NEUTRAL_MAX_CHROMA:
            return self._neutral(c)
        h, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
        if 0.03 <= h <= 0.12 and s > 0.5:  # the orange family
            return self._accentish(c, self.accent if orange == "accent" else self.highlight)
        return c

    def map_hex(self, h: str) -> str:
        return _hex(self.map_rgb(_rgb(h)))

    # -- roles used directly by the viewport ----------------------------------
    def canvas_rgb01(self) -> Tuple[float, float, float]:
        if self.canvas is not None:
            return tuple(v / 255.0 for v in self.canvas)  # type: ignore[return-value]
        c = _mix(self.darker, self.background, 0.5) if self.loaded else (41, 43, 48)
        return tuple(v / 255.0 for v in c)  # type: ignore[return-value]

    def grid_rgb01(self) -> Tuple[float, float, float]:
        if self.grid is not None:
            return tuple(v / 255.0 for v in self.grid)  # type: ignore[return-value]
        c = _mix(tuple(v * 255 for v in self.canvas_rgb01()), self.foreground, 0.16)
        return tuple(v / 255.0 for v in c)  # type: ignore[return-value]

    def highlight01(self, lighten: float = 0.0) -> Tuple[float, float, float]:
        c = _mix(self.highlight, (255, 255, 255), lighten)
        return tuple(v / 255.0 for v in c)  # type: ignore[return-value]


def available_themes() -> List[str]:
    """Names of the bundled themes, for the settings list."""
    try:
        return sorted(p.stem for p in THEMES_DIR.glob("*.toml"))
    except OSError:
        return []


def custom_themes() -> List[str]:
    """Names of the themes saved from the theme editor."""
    try:
        return sorted(p.stem for p in CUSTOM_DIR.glob("*.toml"))
    except OSError:
        return []


def load_theme_data(key: str) -> Optional[dict]:
    """Raw colours of a theme key: BUILTIN (editor defaults), "user:<name>" or a bundled theme name."""
    try:
        if key == BUILTIN:
            return None
        base = CUSTOM_DIR / f"{key[len(CUSTOM_PREFIX):]}.toml" if key.startswith(CUSTOM_PREFIX) else THEMES_DIR / f"{key}.toml"
        with open(base, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def safe_theme_name(name: str) -> str:
    return re.sub(r"[^\w\- ]", "", name).strip()


def save_custom_theme(name: str, data: dict) -> str:
    """Writes ~/.config/omacad/themes/<name>.toml and returns its theme key."""
    name = safe_theme_name(name)
    if not name:
        raise ValueError("Give the theme a name")
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v!r}" for k, v in data.items() if v is not None]
    (CUSTOM_DIR / f"{name}.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return CUSTOM_PREFIX + name


def delete_custom_theme(name: str) -> None:
    try:
        (CUSTOM_DIR / f"{safe_theme_name(name)}.toml").unlink()
    except OSError:
        pass


def current_theme_data() -> Optional[dict]:
    """Raw colours of the theme in use (a picked theme, or Omarchy's current one), e.g. for the theme editor."""
    if FIXED_THEME:
        return load_theme_data(FIXED_THEME)
    try:
        with open(COLORS_FILE, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def set_preview(data: Optional[dict]) -> None:
    """Show unsaved editor colours live (None = back to the chosen theme)."""
    global PREVIEW
    PREVIEW = data
    refresh()


def set_fixed_theme(name: Optional[str]) -> None:
    """Pick a theme by hand (the app then ignores Omarchy theme switches), or None to follow Omarchy again."""
    global FIXED_THEME
    FIXED_THEME = name or None
    refresh()


def chosen_theme(mode: str, name: Optional[str]) -> Optional[str]:
    """The theme a saved choice stands for: None = follow Omarchy, a proposal theme, or a theme made in the editor.
    The older picks (Fusion 360, light, Tokyo, Nord ...) are no longer offered and open as Studio."""
    if mode == "omarchy":
        return None
    if mode == "fixed" and name and (name in ROLE_THEMES or name.startswith(CUSTOM_PREFIX)):
        return name
    return DEFAULT_ROLE_THEME


def apply_saved_choice() -> None:
    """Read the theme choice from the settings; called at start-up before any widget is built."""
    global FIXED_THEME, _palette, _font
    try:
        from omacad.ui.settings import get_settings
        st = get_settings()
        FIXED_THEME = chosen_theme(st.get("theme_mode", "omarchy"), st.get("theme_name"))
    except Exception:
        FIXED_THEME = None
    _palette = load_palette()
    _font = current_font()


def load_palette() -> Palette:
    if PREVIEW:
        return Palette(PREVIEW)
    if FIXED_THEME:
        if FIXED_THEME == BUILTIN:
            return Palette(None)
        return Palette(load_theme_data(FIXED_THEME))
    try:
        with open(COLORS_FILE, "rb") as f:
            return Palette(tomllib.load(f))
    except (OSError, tomllib.TOMLDecodeError):
        return Palette(None)


def current_font() -> str:
    """The theme's own font (Studio: Noto Sans), else the Omarchy UI font (monospace by default in Omarchy)."""
    if _palette.font:
        return _palette.font
    try:
        out = subprocess.run(["omarchy-font-current"], capture_output=True, text=True, timeout=2).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


_palette = load_palette()
_font = current_font()
_styled: List[Tuple["weakref.ref", str]] = []

_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")
_FONT = re.compile(r"font-family:[^;]*;")


def font_family() -> str:
    return _font or ("Segoe UI" if sys.platform == "win32" else "Sans")


# ---- Icons --------------------------------------------------------------------
















def style_menu(menu) -> None:
    """A context menu in the app's colours (the default one came out black on the transparent overlays)."""
    style(menu, _MENU_CSS, _STUDIO_CSS)


def action_with_icon(menu, text: str, px: int = 22):
    """menu.addAction for a label that starts with an emoji: the emoji becomes the icon."""
    emoji, rest = split_emoji(text)
    if emoji:
        return menu.addAction(emoji_icon(emoji, px), rest)
    return menu.addAction(text)


def palette() -> Palette:
    return _palette


_ARROW_DIR = Path.home() / ".cache/omacad/arrows"


def _arrow_png(direction: str) -> str:
    """Path of a small up/down arrow image in the theme's text colour (for spin box buttons)."""
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF
    colour = _palette.map_hex("#E0E3E7")
    path = _ARROW_DIR / f"{direction}_{colour.lstrip('#')}.png"
    if not path.exists():
        _ARROW_DIR.mkdir(parents=True, exist_ok=True)
        pm = QPixmap(18, 18)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colour))
        pts = [(3, 12), (15, 12), (9, 5)] if direction == "up" else [(3, 6), (15, 6), (9, 13)]
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        p.end()
        pm.save(str(path))
    return str(path)


def themeify(css: str) -> str:
    """Maps the colours (and font) of a stylesheet onto the active Omarchy theme."""
    if "@ARROW_UP@" in css:
        css = css.replace("@ARROW_UP@", _arrow_png("up").replace("\\", "/"))
    if "@ARROW_DOWN@" in css:
        css = css.replace("@ARROW_DOWN@", _arrow_png("down").replace("\\", "/"))
    css = _HEX.sub(lambda m: _palette.map_hex(m.group(0)), css)

    def rgba(m):
        r, g, b = _palette.map_rgb((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        a = m.group(4)
        if a is not None:
            a = f"{_palette.map_alpha((r, g, b), float(a)):g}"
        return f"rgba({round(r)}, {round(g)}, {round(b)}, {a})" if a is not None else f"rgb({round(r)}, {round(g)}, {round(b)})"
    css = _RGBA.sub(rgba, css)
    if _font:
        fallback = "sans-serif" if _palette.font else "monospace"
        css = _FONT.sub(f'font-family: "{_font}", {fallback};', css)
    return css


def _sheet(css: str, studio_css: str) -> str:
    """The widget's stylesheet; with a Studio theme its extra rules come last so they win. A sheet of bare
    declarations (no selector) cannot be followed by rules, so there the Studio rules replace it."""
    if not (studio_css and _palette.studio):
        return themeify(css)
    return (themeify(css) if "{" in css else "") + studio_sheet(studio_css)


def studio_sheet(css: str) -> str:
    """Rules written for the role themes (Studio, Graphite, Atelier): @window/@surface/@field/@border/@text/@muted/
    @accent/@selection name their roles, plus derived ones (@on_accent = text on the accent, hover/pressed shades,
    a stronger border). Corner radii follow the theme's `radius` (8 px = Studio; 6 px rules scale with it)."""
    p = _palette
    dark = p.mode == "dark"
    shade = (0, 0, 0) if not dark else (255, 255, 255)
    roles = dict(p.surfaces, text=p.foreground, muted=p.muted, accent=p.accent,
                 selection=p.selection or _mix(p.accent, p.surfaces["surface"], 0.85),
                 on_accent=p.on_accent or ((255, 255, 255) if _lum(p.accent) < 0.55 else (20, 24, 30)),
                 accent_hover=_mix(p.accent, shade, 0.12), accent_pressed=_mix(p.accent, shade, 0.25),
                 border_strong=_mix(p.surfaces["border"], p.foreground, 0.22), ok=p.ok)
    for name in sorted(roles, key=len, reverse=True):
        css = css.replace(f"@{name}", _hex(roles[name]))
    if p.radius != 8:
        css = re.sub(r"border-radius: (8|6)px", lambda m: f"border-radius: {round(p.radius * int(m.group(1)) / 8)}px", css)
    return css


def style(widget, css: str, studio: str = "") -> None:
    """setStyleSheet that follows the theme, including later theme switches. `studio` = extra rules used only
    while a Studio theme is active (calm, borderless buttons, light blue for the active state)."""
    widget.setStyleSheet(_sheet(css, studio))
    _styled.append((weakref.ref(widget), css, studio))


def qcolor(r: int, g: int, b: int, a: int = 255) -> QColor:
    """Themed QColor for painter code (orange becomes the 3D highlight colour)."""
    nr, ng, nb = _palette.map_rgb((r, g, b), orange="highlight")
    return QColor(round(nr), round(ng), round(nb), a)


def apply_qt_palette() -> None:
    """Gives Qt's own palette the theme colours too: widgets without a stylesheet (the inside of scroll
    areas, the ribbon behind the buttons) otherwise stay Fusion dark whatever the theme is."""
    from PySide6.QtGui import QPalette
    from PySide6.QtWidgets import QApplication, QToolTip
    app = QApplication.instance()
    if app is None:
        return
    m = lambda h: QColor(_palette.map_hex(h))
    pal = QPalette()
    for role, h in ((QPalette.ColorRole.Window, "#1E2022"), (QPalette.ColorRole.Base, "#25282C"),
                    (QPalette.ColorRole.AlternateBase, "#2D3136"), (QPalette.ColorRole.Button, "#2D3136"),
                    (QPalette.ColorRole.ToolTipBase, "#25282C"), (QPalette.ColorRole.Text, "#E0E3E7"),
                    (QPalette.ColorRole.WindowText, "#E0E3E7"), (QPalette.ColorRole.ButtonText, "#E0E3E7"),
                    (QPalette.ColorRole.ToolTipText, "#E0E3E7")):
        pal.setColor(role, m(h))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(*(round(v) for v in _palette.accent)))
    pal.setColor(QPalette.ColorRole.HighlightedText,
                 QColor("#FFFFFF") if _palette.studio else QColor(*(round(v) for v in _palette.darker)))
    app.setPalette(pal)
    QToolTip.setPalette(pal)


def refresh() -> None:
    global _palette, _font
    _palette = load_palette()
    _font = current_font()
    apply_qt_palette()
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(indicator_stylesheet())
    alive = []
    for ref, css, studio in _styled:
        w = ref()
        if w is not None:
            try:
                w.setStyleSheet(_sheet(css, studio))
                alive.append((ref, css, studio))
            except RuntimeError:
                pass  # widget already deleted
    _styled[:] = alive


class ThemeWatcher(QObject):
    """Emits `changed` after the Omarchy theme (or its colours) changed on disk."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fs = QFileSystemWatcher(self)
        self._fs.fileChanged.connect(self._poke)
        self._fs.directoryChanged.connect(self._poke)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)  # a theme switch rewrites many files
        self._timer.timeout.connect(self._reload)
        self._watch()

    def _watch(self):
        paths = [str(p) for p in (STATE_DIR, STATE_DIR / "theme", NAME_FILE, COLORS_FILE) if p.exists()]
        missing = [p for p in paths if p not in self._fs.files() + self._fs.directories()]
        if missing:
            self._fs.addPaths(missing)

    def _poke(self, *_):
        self._timer.start()

    def _reload(self):
        self._watch()  # replaced files fall out of the watch list
        if FIXED_THEME or PREVIEW:
            return     # a theme was picked by hand: Omarchy theme switches are ignored
        refresh()
        self.changed.emit()





def indicator_stylesheet() -> str:
    """Tick boxes (also inside lists and trees) drawn from two small SVGs in the theme's colours: a visible empty box
    and a filled box with a white tick. (QSS borders are not painted for item-view indicators, so images are used.)"""
    import tempfile
    accent = _palette.map_hex("#E26D28")
    border, fill = _palette.map_hex("#6B7280"), _palette.map_hex("#2A2F37")
    folder = Path(tempfile.gettempdir()) / "omacad-ui"
    folder.mkdir(parents=True, exist_ok=True)
    off, on = folder / "check_off.svg", folder / "check_on.svg"
    off.write_text(f'<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="14" height="14" rx="3" '
                   f'fill="{fill}" stroke="{border}" stroke-width="1.4"/></svg>', encoding="utf-8")
    on.write_text(f'<svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="14" height="14" rx="3" '
                  f'fill="{accent}" stroke="{accent}" stroke-width="1.4"/><polyline points="4,8.5 7,11.5 12,5" fill="none" '
                  f'stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>', encoding="utf-8")
    views = "QListView::indicator, QTreeView::indicator, QCheckBox::indicator"
    return (themeify(_MENU_CSS) + f"{views} {{ width: 16px; height: 16px; }}\n"
            + ", ".join(f"{v}:unchecked" for v in views.split(", ")) + f" {{ image: url({off.as_posix()}); }}\n"
            + ", ".join(f"{v}:checked" for v in views.split(", ")) + f" {{ image: url({on.as_posix()}); }}\n")


def base_stylesheet() -> str:
    return themeify(_BASE_CSS)


# Icon helpers remain re-exported here for existing UI imports.
from omacad.ui.theme_styles import _MENU_CSS, _BASE_CSS, _STUDIO_CSS
from omacad.ui.theme_icons import (
    ICONS_DIR, EMOJI_TO_TOOL, STUDIO_ICONS, COMMAND_ICONS, named_icon, command_icon, studio_symbol, set_button_text, clear_icon_cache, tool_icon, emoji_icon, split_emoji,
    BigIconStyle, ensure_big_icon_style
)
