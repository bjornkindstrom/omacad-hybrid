"""Text outlines for sketches (Fusion's Text and Text On Path): glyph outlines from Qt, laid out in sketch units (mm).

`layout(...)` returns a shapely geometry (polygons with their counters as holes) in the sketch's u/v coordinates.
Heights follow capital letters: Height 10 mm means a capital letter is 10 mm tall.
"""
import math
from typing import Dict, Optional

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

PIXELS = 1000          # the font is outlined at this size and scaled down: curves stay smooth


def _ensure_app():
    """Fonts need a Q(Gui)Application; the app has one, scripts and tests may not."""
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _font(family: str, bold: bool, italic: bool):
    from PySide6.QtGui import QFont
    font = QFont(family or "Sans Serif")
    font.setPixelSize(PIXELS)
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _even_odd(path) -> Optional[object]:
    """The filled area of a QPainterPath (even-odd, y up) as a shapely geometry."""
    rings = []
    for poly in path.toSubpathPolygons():
        pts = [(p.x(), -p.y()) for p in poly]
        if len(pts) >= 3:
            ring = Polygon(pts)
            if not ring.is_valid:
                ring = ring.buffer(0)
            if not ring.is_empty:
                rings.append(ring)
    if not rings:
        return None
    rings.sort(key=lambda r: -r.area)
    area = rings[0]
    for r in rings[1:]:
        area = area.symmetric_difference(r)       # a ring inside a ring is a counter (the hole of an O)
    return area


def _glyphs(text: str, font):
    """(geometry at the origin with y up, advance width) in font units for one string."""
    from PySide6.QtGui import QFontMetricsF, QPainterPath
    path = QPainterPath()
    path.addText(0.0, 0.0, font, text)
    return _even_odd(path), QFontMetricsF(font).horizontalAdvance(text)


# ---------------------------------------------------------------------------------------------------------- the path

class _Path:
    """A curve the text follows: position and left normal at distance s along it (s may run past the ends of a circle)."""

    def __init__(self, spec: Dict):
        self.kind = spec["kind"]
        if self.kind == "line":
            self.p1 = np.asarray(spec["p1"], dtype=float)
            d = np.asarray(spec["p2"], dtype=float) - self.p1
            self.length = float(np.hypot(*d))
            self.t = d / max(self.length, 1e-12)
        else:
            self.c = np.asarray(spec["center"], dtype=float)
            self.r = float(spec["radius"])
            if self.kind == "circle":       # clockwise from the top: left of travel is the outside
                self.a0, self.dir, self.length = math.pi / 2.0, -1.0, 2.0 * math.pi * self.r
            else:                           # an arc from its start to its end along its own sweep
                self.a0 = float(spec["a0"])
                self.dir = 1.0 if spec["ccw"] else -1.0
                sweep = (float(spec["a1"]) - self.a0) % (2 * math.pi) if spec["ccw"] else (self.a0 - float(spec["a1"])) % (2 * math.pi)
                self.length = self.r * (sweep if sweep > 1e-9 else 2 * math.pi)

    def at(self, s: np.ndarray):
        """(points (n,2), left normals (n,2))."""
        s = np.asarray(s, dtype=float)
        if self.kind == "line":
            pts = self.p1[None, :] + s[:, None] * self.t[None, :]
            nrm = np.tile(np.array([-self.t[1], self.t[0]]), (len(s), 1))
            return pts, nrm
        ang = self.a0 + self.dir * s / self.r
        radial = np.stack([np.cos(ang), np.sin(ang)], axis=1)
        pts = self.c[None, :] + self.r * radial
        tangent = self.dir * np.stack([-np.sin(ang), np.cos(ang)], axis=1)
        nrm = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
        return pts, nrm


# ------------------------------------------------------------------------------------------------------------ layout

def _transform(geom, anchor, angle_deg, flip_h, flip_v):
    """Mirror about the anchor, then turn about it by the angle (counter-clockwise), then move it onto the anchor."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    fx, fy = (-1.0 if flip_h else 1.0), (-1.0 if flip_v else 1.0)
    return shapely.transform(geom, lambda c: np.stack([anchor[0] + (c[:, 0] * fx) * ca - (c[:, 1] * fy) * sa,
                                                       anchor[1] + (c[:, 0] * fx) * sa + (c[:, 1] * fy) * ca], axis=1))


def _frame(p) -> Optional[object]:
    from PySide6.QtGui import QFont, QFontMetricsF
    font = _font(p["font"], p["bold"], p["italic"])
    spacing = float(p.get("spacing", 0.0))
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + spacing)
    fm = QFontMetricsF(font)
    scale = p["height"] / max(fm.capHeight(), 1e-9)
    lines = p["text"].split("\n")
    pitch = fm.lineSpacing()
    parts, widths = [], []
    for i, line in enumerate(lines):
        geom, adv = _glyphs(line, font) if line else (None, 0.0)
        widths.append(adv)
        if geom is not None:
            parts.append((i, geom))
    if not parts:
        return None
    cap = fm.capHeight()
    top = cap                                           # first line's capital height above its baseline
    bottom = -pitch * (len(lines) - 1)                  # last line's baseline
    v_off = {"top": -top, "middle": -(top + bottom) / 2.0, "bottom": -bottom}.get(p["v_align"], -bottom)
    placed = []
    for i, geom in parts:
        h_off = {"left": 0.0, "center": -widths[i] / 2.0, "right": -widths[i]}.get(p["h_align"], 0.0)
        placed.append(shapely.transform(geom, lambda c, i=i, h=h_off: np.stack(
            [(c[:, 0] + h) * scale, (c[:, 1] - pitch * i + v_off) * scale], axis=1)))
    return unary_union(placed)


def fit_in_box(geom, box, margin: float = 0.0):
    """(geometry, scale): `geom` scaled as large as fits in a box of (width, height) less `margin` on every side,
    centred on (0, 0). The
    letters' own outline is measured, not the font's line box, so the text really fills the box and stays centred
    when the font changes. With `geom` laid out at height 1 the scale is the capital height it gets."""
    if geom is None or geom.is_empty:
        return None, 0.0
    m = max(0.0, float(margin))
    w, h = max(float(box[0]) - 2 * m, 1e-3), max(float(box[1]) - 2 * m, 1e-3)
    x0, y0, x1, y1 = geom.bounds
    bw, bh = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    s = min(w / bw, h / bh)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return shapely.transform(geom, lambda c: np.stack([(c[:, 0] - cx) * s, (c[:, 1] - cy) * s], axis=1)), s


def _on_path(p) -> Optional[object]:
    from PySide6.QtGui import QFontMetricsF
    font = _font(p["font"], p["bold"], p["italic"])
    fm = QFontMetricsF(font)
    scale = p["height"] / max(fm.capHeight(), 1e-9)
    path = _Path(p["path"])
    text = p["text"].replace("\n", " ")
    chars = [(ch, fm.horizontalAdvance(ch)) for ch in text]
    if not chars:
        return None
    track = float(p.get("spacing", 0.0)) / 100.0
    advances = np.array([a * (1.0 + track) * scale for _, a in chars])
    natural = float(advances.sum())
    if p.get("fit") and len(chars) > 1:
        # a circle closes on itself (n gaps); a line or arc has n-1: the last letter ends where the path ends
        gaps = len(chars) if path.kind == "circle" else len(chars) - 1
        advances = advances + (path.length - natural) / gaps
        natural = float(advances.sum()) if path.kind == "circle" else path.length
    if path.kind == "circle":
        s0 = {"left": 0.0, "center": -natural / 2.0, "right": -natural}.get(p["h_align"], -natural / 2.0)
    else:
        s0 = {"left": 0.0, "center": (path.length - natural) / 2.0, "right": path.length - natural}.get(p["h_align"], 0.0)
    below = p.get("placement") == "below"
    drop = fm.capHeight() * scale if below else 0.0
    seg = p["height"] / 6.0
    pieces, pen = [], 0.0
    for (ch, _adv), adv in zip(chars, advances):
        if not ch.strip():
            pen += adv
            continue
        geom, _ = _glyphs(ch, font)
        if geom is not None:
            local = shapely.transform(geom, lambda c: c * scale)
            local = shapely.segmentize(local, seg)
            base = s0 + pen

            def warp(c, base=base):
                pts, nrm = path.at(base + c[:, 0])
                return pts + nrm * (c[:, 1] - drop)[:, None]

            bent = shapely.transform(local, warp)
            if not bent.is_valid:
                bent = bent.buffer(0)
            pieces.append(bent)
        pen += adv
    return unary_union(pieces) if pieces else None


def layout(*, text: str, font: str = "Sans Serif", height: float = 10.0, bold: bool = False, italic: bool = False,
           spacing: float = 0.0, h_align: str = "left", v_align: str = "bottom", flip_h: bool = False,
           flip_v: bool = False, angle: float = 0.0, anchor=(0.0, 0.0), path: Optional[Dict] = None,
           placement: str = "above", fit: bool = False, box=None, margin: float = 0.0):
    """The text as polygons in sketch units, or an empty MultiPolygon. With `box` (width, height) the text fills
    that box as far as it can, centred on `anchor` (the box's centre), whatever the font: see `fit_in_box`."""
    _ensure_app()
    if not text.strip() or height <= 0:
        return MultiPolygon()
    p = dict(text=text, font=font, height=float(height), bold=bold, italic=italic, spacing=spacing, h_align=h_align,
             v_align=v_align, path=path, placement=placement, fit=fit)
    if path is not None:
        geom = _on_path(p)                      # follows the path where it is: no frame placement
    elif box is not None:
        geom = fit_in_box(_frame(dict(p, height=1.0, v_align="middle")), box, margin)[0]
        if geom is not None:
            geom = _transform(geom, anchor, angle, flip_h, flip_v)
    else:
        geom = _frame(p)
        if geom is not None:
            geom = _transform(geom, anchor, angle, flip_h, flip_v)
    if geom is None or geom.is_empty:
        return MultiPolygon()
    return geom
