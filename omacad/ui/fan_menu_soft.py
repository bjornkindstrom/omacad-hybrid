"""Soft looks for the right-click fan menu (design/fan-menu-proposals): Soft Ring, Glass Donut and Tiles.

Same geometry and hit areas as the classic menu (`FanMenu.inner_sectors`/`outer_sectors`/`sub_sectors`); only the
painting differs. Colours come from the theme's roles, so the styles follow Studio Soft/Glass, Graphite, Atelier ...
- soft:  the two rings without frames, small gaps and round corners, a soft shadow; the active category is tinted,
         only the tool under the pointer is filled with the accent.
- glass: see-through rings with hairline dividers; accent arcs mark the active category and the hovered tool.
- tiles: a soft inner ring; the tools are separate rounded tiles, the hovered one lifts (bigger, accent, glow).
Labels stand horizontally under the icon in all three (the curved-text setting belongs to the classic look).
"""

import math
from typing import Dict, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

from omacad.ui import theme
from omacad.ui.settings import get_settings

STYLES = ("soft", "glass", "tiles")
GLASS_ALPHA = 165          # see-through ring fill (of 255)
OPEN_MS = 180              # opening animation: scale 0.9 -> 1 and fade in

_tint_cache: Dict[Tuple[int, int, int], QPixmap] = {}


def resolve_style(setting: Optional[str] = None) -> str:
    """The look to paint: the setting, or with "auto" Glass in a see-through theme and Soft otherwise."""
    value = setting if setting is not None else get_settings().get("fan_menu_style", "auto")
    if value in STYLES or value == "classic":
        return value
    return "glass" if theme.palette().glass else "soft"


class _Colours:
    def __init__(self):
        p = theme.palette()
        q = lambda c, a=255: QColor(int(round(c[0])), int(round(c[1])), int(round(c[2])), a)
        s = p.surfaces
        self.surface = q(s.get("surface", p.map_rgb((38, 41, 46))))
        self.field = q(s.get("field", p.map_rgb((28, 30, 34))))
        self.border = q(s.get("border", p.map_rgb((70, 75, 84))))
        self.text = q(p.foreground)
        self.muted = q(p.muted)
        self.accent = q(p.accent)
        sel = p.selection or tuple(a * 0.15 + b * 0.85 for a, b in zip(p.accent, s.get("surface", p.background)))
        self.selection = q(sel)
        self.on_accent = q(p.on_accent) if (p.studio and p.on_accent) else QColor("#FFFFFF")
        self.dark = p.mode == "dark"
        self.shadow = QColor(0, 0, 0) if self.dark else QColor(30, 41, 59)


def _with_alpha(c: QColor, a: int) -> QColor:
    c = QColor(c)
    c.setAlpha(max(0, min(255, a)))
    return c


def _tinted(icon, size: int, colour: Optional[QColor]) -> QPixmap:
    """The icon at `size`; line icons (the Studio set) are recoloured, other sets (emoji pictures) stay as they are."""
    pix = icon.pixmap(size, size)
    if colour is None or get_settings().get("icon_theme", "solid") != "studio":
        return pix
    key = (int(icon.cacheKey()), size, int(colour.rgba()))
    cached = _tint_cache.get(key)
    if cached is not None:
        return cached
    out = QPixmap(pix.size())
    out.setDevicePixelRatio(pix.devicePixelRatio())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pix)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(out.rect(), colour)
    p.end()
    if len(_tint_cache) > 400:
        _tint_cache.clear()
    _tint_cache[key] = out
    return out


def _ring_path(c: QPointF, r1: float, r2: float, start: float, span: float, inset: float = 0.0) -> QPainterPath:
    """Annular sector (degrees, counter-clockwise, Qt's 3 o'clock = 0), shrunk by `inset` px on every side."""
    rm = (r1 + r2) / 2.0
    da = math.degrees(inset / rm) if rm > 0 else 0.0
    a0, sp = start + da, max(0.5, span - 2 * da)
    r1, r2 = r1 + inset, r2 - inset
    path = QPainterPath()
    path.moveTo(c.x() + r2 * math.cos(math.radians(a0)), c.y() - r2 * math.sin(math.radians(a0)))
    path.arcTo(QRectF(c.x() - r2, c.y() - r2, 2 * r2, 2 * r2), a0, sp)
    path.lineTo(c.x() + r1 * math.cos(math.radians(a0 + sp)), c.y() - r1 * math.sin(math.radians(a0 + sp)))
    path.arcTo(QRectF(c.x() - r1, c.y() - r1, 2 * r1, 2 * r1), a0 + sp, -sp)
    path.closeSubpath()
    return path


def _rounded_sector(painter: QPainter, c: QPointF, r1, r2, start, span, fill: QColor, gap: float):
    """A sector with round corners: shrunk by `gap` and drawn with a round-join pen of 2*gap in its own colour."""
    painter.setPen(QPen(fill, 2 * gap, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(fill)
    painter.drawPath(_ring_path(c, r1, r2, start, span, gap))


def _shadow(painter: QPainter, path: QPainterPath, col: QColor, spread: float = 12.0, alpha: int = 60, dy: float = 5.0):
    """A soft drop shadow: the outline stroked a few times, widest and faintest first."""
    painter.save()
    painter.translate(0, dy)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    steps = 5
    for i in range(steps):
        w = spread * 2 * (1 - i / steps)
        painter.setPen(QPen(_with_alpha(col, alpha // steps), w, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_with_alpha(col, alpha // 2))
    painter.drawPath(path)
    painter.restore()


def _disc_shadow(painter: QPainter, c: QPointF, r: float, col: QColor, alpha: int = 55, spread: float = 18.0):
    g = QRadialGradient(QPointF(c.x(), c.y() + 5), r + spread)
    g.setColorAt(max(0.0, (r - 4) / (r + spread)), _with_alpha(col, alpha))
    g.setColorAt(1.0, _with_alpha(col, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(g)
    painter.drawEllipse(QPointF(c.x(), c.y() + 5), r + spread, r + spread)


def _arc(painter: QPainter, c: QPointF, r: float, start: float, span: float, col: QColor, width: float = 4.0):
    painter.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), int(start * 16), int(span * 16))


MIN_LABEL_PX = 8.5        # names shrink down to this before they are cut


def _label_font(label: str, max_w: float, bold: bool, font_px: float) -> Tuple[QFont, bool]:
    """The font for a name: as given, or a little smaller so the whole name fits; False when even that is too wide."""
    max_w = int(max_w) - 2        # whole pixels, with the slack QFontMetrics.elidedText wants before it keeps a name
    px = font_px
    while True:
        f = QFont()
        f.setPixelSize(max(1, round(px)))
        f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Medium)
        if QFontMetrics(f).horizontalAdvance(label) <= max_w or px - 1 < MIN_LABEL_PX:
            return f, QFontMetrics(f).horizontalAdvance(label) <= max_w
        px -= 1


def _content(painter: QPainter, item, cx: float, cy: float, icon_px: int, label_col: QColor, icon_col: Optional[QColor],
             max_w: float, bold: bool, font_px: float = 10.5, hide_cut_label: bool = False):
    """Icon with its name under it, centred on (cx, cy). A long name shrinks a little; then it is cut short, or with
    `hide_cut_label` left out (the tooltip under the menu always shows it)."""
    has_icon = item.icon is not None and not item.icon.isNull()
    label = item.label.strip()
    f, fits = _label_font(label, max_w, bold, font_px)
    if label and not fits and hide_cut_label and has_icon:
        label = ""
        icon_px = int(icon_px * 1.25)
    fm = QFontMetrics(f)
    gap = 3
    total = (icon_px if has_icon else 0) + (gap + fm.height() if label and has_icon else fm.height() if label else 0)
    top = cy - total / 2.0
    if has_icon:
        pix = _tinted(item.icon, icon_px, icon_col)
        painter.drawPixmap(int(round(cx - icon_px / 2.0)), int(round(top)), pix)
        top += icon_px + gap
    if label:
        painter.setFont(f)
        painter.setPen(label_col)
        text = label if fits else fm.elidedText(label, Qt.TextElideMode.ElideRight, max(16, int(max_w)))
        painter.drawText(QRectF(cx - max_w / 2.0, top, max_w, fm.height()), Qt.AlignmentFlag.AlignCenter, text)


def _sector_layout(menu, sec, base_icon: float) -> Tuple[float, float, int, float]:
    """Centre, icon size and label width for the content of a sector."""
    mid = math.radians(sec.start_angle + sec.span_angle / 2.0)
    rm = (sec.r_inner + sec.r_outer) / 2.0
    cx = menu.center_pos.x() + rm * math.cos(mid)
    cy = menu.center_pos.y() - rm * math.sin(mid)
    chord = 2 * rm * math.sin(math.radians(min(sec.span_angle, 180)) / 2.0)
    scale = max(0.5, min(2.0, float(get_settings().get("fan_menu_icon_scale", 1.0))))
    radial = (sec.r_outer - sec.r_inner) - 30
    icon_px = int(max(10, min(round(base_icon * scale), radial, chord - 10)))
    return cx, cy, icon_px, max(24.0, chord * 0.9)


def _hub(menu, painter: QPainter, k: _Colours, fill: QColor, shadow: bool):
    c, r = menu.center_pos, menu.HUB_RADIUS - 4
    if menu.hub_action_ok and menu.hub_action_cancel:
        for name, item, start, tint in (("hub_ok", menu.hub_action_ok, 0, QColor(46, 125, 50)),
                                        ("hub_cancel", menu.hub_action_cancel, 180, QColor(198, 40, 40))):
            hover = menu.hovered_hub == name
            path = QPainterPath()
            rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            path.moveTo(c)
            path.arcTo(rect, start, 180)
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint if hover else _with_alpha(tint, 40))
            painter.drawPath(path)
            f = QFont()
            f.setPixelSize(10)
            f.setWeight(QFont.Weight.DemiBold)
            painter.setFont(f)
            painter.setPen(QColor("#FFFFFF") if hover else tint)
            y = c.y() - r * 0.8 if start == 0 else c.y() + r * 0.05
            painter.drawText(QRectF(c.x() - r, y, 2 * r, r * 0.75), Qt.AlignmentFlag.AlignCenter, item.label)
        return
    hover = menu.hovered_hub == "hub_center"
    if shadow:
        _disc_shadow(painter, c, r, k.shadow, 45, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(k.selection if hover else fill)
    painter.drawEllipse(c, r, r)
    label = menu.hub_action_center.label if menu.hub_action_center else "✕"
    f = QFont()
    f.setPixelSize(12)
    f.setWeight(QFont.Weight.DemiBold)
    painter.setFont(f)
    painter.setPen(k.accent if hover else k.muted)
    painter.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, label)


def _tooltip(menu, painter: QPainter, k: _Colours, height: int, glass: bool):
    item = None
    if menu.hovered_sub_idx is not None and 0 <= menu.hovered_sub_idx < len(menu.sub_sectors):
        item = menu.sub_sectors[menu.hovered_sub_idx].item
    elif menu.hovered_outer_idx is not None and 0 <= menu.hovered_outer_idx < len(menu.outer_sectors):
        item = menu.outer_sectors[menu.hovered_outer_idx].item
    elif 0 <= menu.active_category_idx < len(menu.inner_sectors):
        item = menu.inner_sectors[menu.active_category_idx].item
    if item is None:
        return
    bold, light = QFont(), QFont()
    bold.setPixelSize(12)
    bold.setWeight(QFont.Weight.DemiBold)
    light.setPixelSize(12)
    fb, fl = QFontMetrics(bold), QFontMetrics(light)
    title = item.label
    rest = (f"  {item.shortcut}" if item.shortcut else "") + (f" · {item.tooltip}" if item.tooltip else "")
    w = min(560.0, fb.horizontalAdvance(title) + fl.horizontalAdvance(rest) + 32)
    h = 30.0
    outer = menu.SUB_R2 if menu.sub_sectors else menu.OUTER_R2
    x, y = menu.center_pos.x() - w / 2, menu.center_pos.y() + outer + 14
    if y + h > height - 8:
        y = menu.center_pos.y() - outer - 14 - h
    rect = QRectF(x, y, w, h)
    path = QPainterPath()
    path.addRoundedRect(rect, h / 2, h / 2)
    _shadow(painter, path, k.shadow, 6, 40, 2)
    painter.setPen(QPen(_with_alpha(k.surface, 235), 1) if glass else Qt.PenStyle.NoPen)
    painter.setBrush(_with_alpha(k.surface, 205 if glass else 255))
    painter.drawPath(path)
    tw = int(w - 32 - fb.horizontalAdvance(title))
    rest = fl.elidedText(rest, Qt.TextElideMode.ElideRight, max(0, tw))
    total = fb.horizontalAdvance(title) + fl.horizontalAdvance(rest)
    tx = rect.center().x() - total / 2
    base = rect.center().y() + fb.ascent() / 2 - 1
    painter.setFont(bold)
    painter.setPen(k.text)
    painter.drawText(QPointF(tx, base), title)
    painter.setFont(light)
    painter.setPen(k.muted)
    painter.drawText(QPointF(tx + fb.horizontalAdvance(title), base), rest)


def _inner_ring(menu, painter, k: _Colours, style: str):
    c = menu.center_pos
    r2 = menu.INNER_R2 - (6 if style == "tiles" else 0)
    if style == "glass":
        _disc_shadow(painter, c, r2, k.shadow, 40)
        painter.setPen(QPen(_with_alpha(k.surface, 240), 1))
        painter.setBrush(_with_alpha(k.surface, GLASS_ALPHA))
        painter.drawEllipse(c, r2, r2)
    else:
        _disc_shadow(painter, c, r2 + 2, k.shadow, 50)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(k.surface)
        painter.drawEllipse(c, r2 + 2, r2 + 2)
    for i, sec in enumerate(menu.inner_sectors):
        active = i == menu.active_category_idx
        context = sec.item.accent_role
        if style == "glass":
            if active or context:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(_with_alpha(k.selection, 200 if active else 110))
                painter.drawPath(_ring_path(c, menu.INNER_R1, r2, sec.start_angle, sec.span_angle))
            a = math.radians(sec.start_angle)
            painter.setPen(QPen(_with_alpha(k.text, 22), 1))
            painter.drawLine(QPointF(c.x() + (menu.INNER_R1 + 2) * math.cos(a), c.y() - (menu.INNER_R1 + 2) * math.sin(a)),
                             QPointF(c.x() + (r2 - 2) * math.cos(a), c.y() - (r2 - 2) * math.sin(a)))
            if active:
                _arc(painter, c, menu.INNER_R1 + 7, sec.start_angle + 8, sec.span_angle - 16, k.accent)
        else:
            fill = k.selection if active else (_with_alpha(k.selection, 150) if context else
                                               (k.surface if style == "tiles" else k.field))
            _rounded_sector(painter, c, menu.INNER_R1, r2, sec.start_angle, sec.span_angle, fill, 3.5)
        cx, cy, icon_px, max_w = _sector_layout(menu, sec, 20)
        col = k.accent if (active or context) else k.muted
        _content(painter, sec.item, cx, cy, icon_px, col, k.accent if active else None, max_w, active, 10.5)


def _outer_ring(menu, painter, k: _Colours, style: str, sectors, hovered: Optional[int]):
    if not sectors:
        return
    c = menu.center_pos
    r1, r2 = sectors[0].r_inner, sectors[0].r_outer
    if style == "glass":
        # the sectors run clockwise from the first, so the band starts at the last one and goes counter-clockwise
        band = _ring_path(c, r1, r2, sectors[-1].start_angle, sum(s.span_angle for s in sectors))
        _shadow(painter, band, k.shadow, 12, 50)
        painter.setPen(QPen(_with_alpha(k.surface, 240), 1))
        painter.setBrush(_with_alpha(k.surface, GLASS_ALPHA))
        painter.drawPath(band)
    for j, sec in enumerate(sectors):
        hover = j == hovered
        accent = sec.item.accent_role
        cx, cy, icon_px, max_w = _sector_layout(menu, sec, 22)
        if style == "soft":
            path = _ring_path(c, r1, r2, sec.start_angle, sec.span_angle, 3)
            _shadow(painter, path, k.shadow, 5, 30, 2)
            fill = k.accent if hover else (_with_alpha(k.selection, 255) if accent else k.surface)
            _rounded_sector(painter, c, r1, r2, sec.start_angle, sec.span_angle, fill, 3)
            _content(painter, sec.item, cx, cy, icon_px, k.on_accent if hover else (k.accent if accent else k.text),
                     k.on_accent if hover else (k.accent if accent else None), max_w, hover)
        elif style == "glass":
            if hover or accent:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(_with_alpha(k.selection, 215 if hover else 120))
                painter.drawPath(_ring_path(c, r1, r2, sec.start_angle, sec.span_angle))
            if j > 0:
                a = math.radians(sec.start_angle + sec.span_angle)
                painter.setPen(QPen(_with_alpha(k.text, 22), 1))
                painter.drawLine(QPointF(c.x() + (r1 + 4) * math.cos(a), c.y() - (r1 + 4) * math.sin(a)),
                                 QPointF(c.x() + (r2 - 4) * math.cos(a), c.y() - (r2 - 4) * math.sin(a)))
            if hover:
                _arc(painter, c, r2 - 7, sec.start_angle + 5, sec.span_angle - 10, k.accent)
            col = k.accent if (hover or accent) else k.text
            _content(painter, sec.item, cx, cy, icon_px, col, k.accent if (hover or accent) else None, max_w, hover)
        else:   # tiles
            mid = math.radians(sec.start_angle + sec.span_angle / 2.0)
            chord = 2 * ((r1 + r2) / 2) * math.sin(math.radians(min(sec.span_angle, 180)) / 2.0)
            size = max(30.0, min(58.0, chord - 8, r2 - r1 - 30))
            rm = (r1 + r2) / 2 + (4 if hover else 0)
            if hover:
                size *= 1.14
            tx, ty = c.x() + rm * math.cos(mid), c.y() - rm * math.sin(mid)
            rect = QRectF(tx - size / 2, ty - size / 2, size, size)
            path = QPainterPath()
            path.addRoundedRect(rect, size * 0.27, size * 0.27)
            _shadow(painter, path, k.accent if hover else k.shadow, 8 if hover else 5, 70 if hover else 35, 3 if hover else 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(k.accent if hover else (k.selection if accent else k.surface))
            painter.drawPath(path)
            icon = int(max(10, min(icon_px, size * 0.42)))
            label = k.on_accent if hover else (k.accent if accent else k.text)
            _content(painter, sec.item, tx, ty, icon, label, k.on_accent if hover else (k.accent if accent else None),
                     size - 6, hover, 10.0 if hover else 9.5, hide_cut_label=True)


def open_progress(menu) -> float:
    """0..1 of the opening animation (1 when it is off or done)."""
    timer = getattr(menu, "_open_timer", None)
    if timer is None or not timer.isValid():
        return 1.0
    return min(1.0, timer.elapsed() / OPEN_MS)


def draw_soft(menu, painter: QPainter, width: int, height: int, style: str):
    k = _Colours()
    t = open_progress(menu)
    if t < 1.0:
        ease = 1 - (1 - t) ** 3
        c = menu.center_pos
        painter.setOpacity(ease)
        painter.translate(c)
        painter.scale(0.9 + 0.1 * ease, 0.9 + 0.1 * ease)
        painter.translate(-c)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(16, menu.viewport.update)
    _inner_ring(menu, painter, k, style)
    _outer_ring(menu, painter, k, style, menu.outer_sectors, menu.hovered_outer_idx)
    _outer_ring(menu, painter, k, style, menu.sub_sectors, menu.hovered_sub_idx)
    hub_fill = _with_alpha(k.surface, 220) if style == "glass" else (k.field if style == "tiles" else k.surface)
    _hub(menu, painter, k, hub_fill, style == "soft")
    _tooltip(menu, painter, k, height, style == "glass")
