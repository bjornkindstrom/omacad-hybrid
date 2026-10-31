"""
Radial / Fan Menu for Omacad Viewport.
Rendered directly via QPainter inside Viewport3D overlay pass (like ViewCube and RotateHandles).
- Inner arc: categories (Context, Create, Modify, Constraints, Inspect, View, History)
- Outer arc: tools for the active/hovered category
- Hub: Finish / Cancel / Undo quick actions
Supports both regular click/hover navigation and hold-and-drag gesture (marking menu).
"""

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QObject, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QBrush
)

from omacad.ui import theme


@dataclass
class FanItem:
    id: str
    label: str
    icon: Optional[QIcon] = None
    shortcut: str = ""
    tooltip: str = ""
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    callback: Optional[Callable[[], None]] = None
    children: List["FanItem"] = field(default_factory=list)
    accent_role: bool = False  # True for Context / Suggested items


@dataclass
class SectorGeom:
    item: FanItem
    start_angle: float   # degrees (Qt 3 o'clock = 0, counter-clockwise)
    span_angle: float
    r_inner: float
    r_outer: float
    path: QPainterPath


class FanMenu(QObject):
    """
    Direct QPainter overlay controller for the Viewport Fan Menu.
    """

    action_triggered = Signal(object)
    dismissed = Signal()

    # Dimensions (pixels)
    HUB_RADIUS = 34.0
    INNER_R1 = 38.0
    INNER_R2 = 110.0
    OUTER_R1 = 116.0
    OUTER_R2 = 216.0
    SUB_R1 = 222.0
    SUB_R2 = 300.0

    def __init__(self, viewport):
        super().__init__()
        self.viewport = viewport

        self.is_open = False
        self.categories: List[FanItem] = []
        self.center_pos = QPointF(0, 0)
        self.cursor_pos = QPointF(0, 0)
        self.active_category_idx = 0
        self.expanded_group_item: Optional[FanItem] = None
        self.hovered_outer_idx: Optional[int] = None
        self.hovered_sub_idx: Optional[int] = None
        self.hovered_hub: Optional[str] = None  # "hub_ok", "hub_cancel", "hub_center"
        self.gesture_mode = False

        # Quick hub items
        self.hub_action_ok: Optional[FanItem] = None
        self.hub_action_cancel: Optional[FanItem] = None
        self.hub_action_center: Optional[FanItem] = None
        self.on_close_cb: Optional[Callable[[], None]] = None

        # Pre-calculated geometry
        self.inner_sectors: List[SectorGeom] = []
        self.outer_sectors: List[SectorGeom] = []
        self.sub_sectors: List[SectorGeom] = []

    def isVisible(self) -> bool:
        return self.is_open

    def isHidden(self) -> bool:
        return not self.is_open

    def popup(
        self,
        center: QPoint,
        categories: List[FanItem],
        hub_ok: Optional[FanItem] = None,
        hub_cancel: Optional[FanItem] = None,
        hub_center: Optional[FanItem] = None,
        gesture_mode: bool = False,
        default_category_idx: int = 0,
        on_close: Optional[Callable[[], None]] = None
    ):
        """Open the fan menu centered at the given viewport coordinate."""
        self.categories = [c for c in categories if c.enabled]
        self.hub_action_ok = hub_ok
        self.hub_action_cancel = hub_cancel
        self.hub_action_center = hub_center
        self.gesture_mode = gesture_mode
        self.on_close_cb = on_close

        max_r = self.OUTER_R2 + 12.0
        pw = self.viewport.width()
        ph = self.viewport.height()
        raw_x = float(center.x())
        raw_y = float(center.y())
        cx = max(max_r, min(pw - max_r, raw_x)) if pw > 2 * max_r else raw_x
        cy = max(max_r, min(ph - max_r, raw_y)) if ph > 2 * max_r else raw_y
        self.center_pos = QPointF(cx, cy)
        self.open_cursor_pos = QPointF(raw_x, raw_y)
        self.cursor_pos = QPointF(raw_x, raw_y)

        self.active_category_idx = min(max(0, default_category_idx), max(0, len(self.categories) - 1))
        self.expanded_group_item = None
        self.hovered_outer_idx = None
        self.hovered_sub_idx = None
        self.hovered_hub = None

        self._rebuild_geometry()
        self.is_open = True
        self.viewport.update()

    def update_cursor_pos(self, pt: QPointF):
        self.cursor_pos = pt
        self._update_hover()
        self.viewport.update()

    def dismiss(self):
        """Close the menu."""
        if not self.is_open:
            return
        self.is_open = False
        cb = self.on_close_cb
        self.on_close_cb = None
        if cb:
            cb()
        self.dismissed.emit()
        self.viewport.update()


    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Process mouse movement while fan menu is active. Returns True if handled."""
        if not self.is_open:
            return False
        self.cursor_pos = QPointF(x, y)
        self._update_hover()
        self.viewport.update()
        return True

    def handle_mouse_release(self, x: float, y: float, button: Qt.MouseButton) -> bool:
        """Process mouse release. Returns True if handled."""
        if not self.is_open:
            return False
        self.cursor_pos = QPointF(x, y)
        self._update_hover()

        if button in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            triggered = self._execute_hovered()
            if not triggered:
                # Keep menu open if user clicked an inner category or an outer group with children
                on_category = any(sec.path.contains(self.cursor_pos) for sec in self.inner_sectors)
                on_parent_outer = (
                    self.hovered_outer_idx is not None
                    and 0 <= self.hovered_outer_idx < len(self.outer_sectors)
                    and bool(self.outer_sectors[self.hovered_outer_idx].item.children)
                    and self.outer_sectors[self.hovered_outer_idx].path.contains(self.cursor_pos)
                )
                if on_parent_outer:
                    # Clicking a group item (Primitives, Pattern, Rectangle) expands its children into the main outer ring
                    self.expanded_group_item = self.outer_sectors[self.hovered_outer_idx].item
                    self.hovered_outer_idx = None
                    self.hovered_sub_idx = None
                    self._rebuild_geometry()
                    self._update_hover()
                    self.viewport.update()
                elif on_category:
                    self.viewport.update()
                else:
                    self.dismiss()
            return True
        return False

    def finish_gesture(self):
        """Called on right-button release when in gesture mode."""
        if not self.is_open:
            return
        open_pt = getattr(self, "open_cursor_pos", self.center_pos)
        drag_dist = math.hypot(self.cursor_pos.x() - open_pt.x(), self.cursor_pos.y() - open_pt.y())
        dx = self.cursor_pos.x() - self.center_pos.x()
        dy = -(self.cursor_pos.y() - self.center_pos.y())
        r = math.hypot(dx, dy)
        if drag_dist < 16.0 or r < self.OUTER_R1:
            self.gesture_mode = False
            self.hovered_hub = None
            self.viewport.update()
            return
        if self._execute_hovered():
            return
        if (
            self.hovered_outer_idx is not None
            and 0 <= self.hovered_outer_idx < len(self.outer_sectors)
            and bool(self.outer_sectors[self.hovered_outer_idx].item.children)
        ):
            self.gesture_mode = False
            self.viewport.update()
            return
        self.dismiss()

    def _rebuild_geometry(self):
        """Rebuild sector shapes for inner and outer arcs."""
        self.inner_sectors.clear()
        self.outer_sectors.clear()
        self.sub_sectors.clear()

        n_cat = len(self.categories)
        if n_cat == 0:
            return

        span_each = 360.0 / n_cat
        start_base = 90.0 - (span_each / 2.0)

        for i, cat in enumerate(self.categories):
            a_start = (start_base - i * span_each) % 360.0
            p = self._make_annular_path(self.center_pos, self.INNER_R1, self.INNER_R2, a_start, span_each)
            self.inner_sectors.append(SectorGeom(cat, a_start, span_each, self.INNER_R1, self.INNER_R2, p))

        # Build outer sectors for the active category (or expanded group item)
        if 0 <= self.active_category_idx < n_cat:
            cat_sec = self.inner_sectors[self.active_category_idx]
            source_items = (
                self.expanded_group_item.children
                if self.expanded_group_item is not None
                else cat_sec.item.children
            )
            tools = [t for t in source_items if t.enabled]
            n_tools = len(tools)
            if n_tools > 0:
                mid_angle = (cat_sec.start_angle + cat_sec.span_angle / 2.0) % 360.0
                tool_span = min(40.0, max(18.0, 180.0 / max(1, n_tools)))
                total_span = min(280.0, tool_span * n_tools)
                fan_start = mid_angle + (total_span / 2.0)

                for j, tool in enumerate(tools):
                    a_s = (fan_start - (j + 1) * (total_span / n_tools)) % 360.0
                    a_span = total_span / n_tools
                    p = self._make_annular_path(self.center_pos, self.OUTER_R1, self.OUTER_R2, a_s, a_span)
                    self.outer_sectors.append(SectorGeom(tool, a_s, a_span, self.OUTER_R1, self.OUTER_R2, p))

        # Build sub sectors if an outer tool has children
        if self.hovered_outer_idx is not None and 0 <= self.hovered_outer_idx < len(self.outer_sectors):
            out_sec = self.outer_sectors[self.hovered_outer_idx]
            sub_tools = [st for st in out_sec.item.children if st.enabled]
            n_sub = len(sub_tools)
            if n_sub > 0:
                mid_angle = (out_sec.start_angle + out_sec.span_angle / 2.0) % 360.0
                sub_span = min(36.0, max(16.0, 160.0 / n_sub))
                total_sub_span = min(260.0, sub_span * n_sub)
                sub_start = mid_angle + (total_sub_span / 2.0)

                for k, sub_t in enumerate(sub_tools):
                    a_s = (sub_start - (k + 1) * (total_sub_span / n_sub)) % 360.0
                    a_span = total_sub_span / n_sub
                    p = self._make_annular_path(self.center_pos, self.SUB_R1, self.SUB_R2, a_s, a_span)
                    self.sub_sectors.append(SectorGeom(sub_t, a_s, a_span, self.SUB_R1, self.SUB_R2, p))

    @staticmethod
    def _make_annular_path(center: QPointF, r1: float, r2: float, start_deg: float, span_deg: float) -> QPainterPath:
        gap = 1.2
        a0 = start_deg + gap / 2.0
        da = max(0.5, span_deg - gap)

        path = QPainterPath()
        rect2 = QRectF(center.x() - r2, center.y() - r2, r2 * 2, r2 * 2)
        rect1 = QRectF(center.x() - r1, center.y() - r1, r1 * 2, r1 * 2)

        rad0 = math.radians(a0)
        path.moveTo(center.x() + r2 * math.cos(rad0), center.y() - r2 * math.sin(rad0))
        path.arcTo(rect2, a0, da)

        rad1 = math.radians(a0 + da)
        path.lineTo(center.x() + r1 * math.cos(rad1), center.y() - r1 * math.sin(rad1))
        path.arcTo(rect1, a0 + da, -da)
        path.closeSubpath()
        return path

    def _update_hover(self):
        dx = self.cursor_pos.x() - self.center_pos.x()
        dy = -(self.cursor_pos.y() - self.center_pos.y())
        r = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx)) % 360.0

        self.hovered_hub = None
        self.hovered_sub_idx = None

        if r <= self.HUB_RADIUS:
            self.hovered_outer_idx = None
            if self.hub_action_ok and self.hub_action_cancel:
                self.hovered_hub = "hub_ok" if dy >= 0 else "hub_cancel"
            else:
                self.hovered_hub = "hub_center"
            return

        # 1. Check Sub-sectors first (including the small gap between OUTER_R2 and SUB_R1)
        for k, sec in enumerate(self.sub_sectors):
            if sec.path.contains(self.cursor_pos) or (
                self.SUB_R1 - 8.0 <= r <= self.SUB_R2 + 10.0
                and self._angle_in_span(ang, sec.start_angle, sec.span_angle)
            ):
                self.hovered_sub_idx = k
                return

        # Safe-corridor: when sub_sectors is open and cursor is in the outer part of the 2nd ring
        # within the angular span of sub_sectors, keep sub_sectors open so diagonal movement reaches them!
        if self.sub_sectors and self.OUTER_R1 + 26.0 <= r <= self.SUB_R1:
            if any(self._angle_in_span(ang, s.start_angle, s.span_angle) for s in self.sub_sectors):
                return

        # 2. Check Outer sectors
        outer_hit = None
        for j, sec in enumerate(self.outer_sectors):
            if sec.path.contains(self.cursor_pos):
                outer_hit = j
                break
        if outer_hit is not None:
            if self.hovered_outer_idx != outer_hit:
                self.hovered_outer_idx = outer_hit
                self._rebuild_geometry()
            return

        # 3. Check Inner categories
        for i, sec in enumerate(self.inner_sectors):
            if sec.path.contains(self.cursor_pos):
                if i != self.active_category_idx or self.expanded_group_item is not None:
                    self.active_category_idx = i
                    self.expanded_group_item = None
                    self.hovered_outer_idx = None
                    self._rebuild_geometry()
                return

        if r > self.OUTER_R2 and not self.sub_sectors:
            self.hovered_outer_idx = None


    @staticmethod
    def _angle_in_span(ang: float, start: float, span: float) -> bool:
        diff = (ang - start) % 360.0
        return diff <= span

    def _execute_hovered(self) -> bool:
        item: Optional[FanItem] = None

        if self.hovered_sub_idx is not None and 0 <= self.hovered_sub_idx < len(self.sub_sectors):
            item = self.sub_sectors[self.hovered_sub_idx].item
        elif self.hovered_outer_idx is not None and 0 <= self.hovered_outer_idx < len(self.outer_sectors):
            cand = self.outer_sectors[self.hovered_outer_idx].item
            if not cand.children:
                item = cand
        elif self.hovered_hub == "hub_ok":
            item = self.hub_action_ok
        elif self.hovered_hub == "hub_cancel":
            item = self.hub_action_cancel
        elif self.hovered_hub == "hub_center":
            item = self.hub_action_center

        if item:
            self.dismiss()
            if item.callback:
                self.viewport._fan_dispatching = True
                try:
                    item.callback()
                finally:
                    self.viewport._fan_dispatching = False
            self.action_triggered.emit(item)
            return True
        return False


    # -- Direct Rendering on Viewport QPainter ---------------------------------
    @staticmethod
    def _qc(rgb, alpha: int = 255) -> QColor:
        if isinstance(rgb, QColor):
            c = QColor(rgb)
            c.setAlpha(alpha)
            return c
        return QColor(int(round(rgb[0])), int(round(rgb[1])), int(round(rgb[2])), alpha)

    def draw(self, painter: QPainter, width: int, height: int):
        """Draws the entire fan menu onto the viewport."""
        if not self.is_open or not self.categories:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        pal = theme.palette()

        bg_card = self._qc(pal.surfaces.get("surface", (38, 41, 46)), 235)
        bg_card_alt = self._qc(pal.surfaces.get("field", (28, 30, 34)), 245)
        border_col = self._qc(pal.surfaces.get("border", (70, 75, 84)), 255)
        text_col = self._qc(pal.foreground, 255)
        muted_col = self._qc(pal.muted, 255)
        accent_col = self._qc(pal.accent, 255)
        highlight_col = self._qc(pal.highlight, 255)

        # 1. Semi-transparent backdrop shadow
        painter.setPen(Qt.PenStyle.NoPen)
        dim_brush = QBrush(QColor(0, 0, 0, 50))
        painter.setBrush(dim_brush)
        painter.drawEllipse(self.center_pos, self.OUTER_R2 + 18, self.OUTER_R2 + 18)

        # 2. Draw Inner Categories
        for i, sec in enumerate(self.inner_sectors):
            is_active = (i == self.active_category_idx)
            is_context = sec.item.accent_role

            if is_active:
                fill = QColor(accent_col)
                fill.setAlpha(210 if not is_context else 240)
                pen = QPen(highlight_col if is_context else QColor(255, 255, 255, 220), 1.8)
            elif is_context:
                fill = QColor(accent_col)
                fill.setAlpha(95)
                pen = QPen(accent_col, 1.4)
            else:
                fill = bg_card_alt
                pen = QPen(border_col, 1.0)

            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawPath(sec.path)

            self._draw_sector_content(
                painter, sec,
                text_col=QColor("#FFFFFF") if is_active else text_col,
                muted_col=muted_col
            )

        # 3. Draw Outer Tools
        for j, sec in enumerate(self.outer_sectors):
            is_hover = (j == self.hovered_outer_idx)
            is_accent = sec.item.accent_role

            if is_hover:
                fill = QColor(accent_col)
                fill.setAlpha(235)
                pen = QPen(QColor(255, 255, 255, 245), 1.6)
            elif is_accent:
                fill = QColor(accent_col)
                fill.setAlpha(75)
                pen = QPen(accent_col, 1.2)
            else:
                fill = bg_card
                pen = QPen(border_col, 1.0)

            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawPath(sec.path)

            self._draw_sector_content(
                painter, sec,
                text_col=QColor("#FFFFFF") if is_hover else text_col,
                muted_col=muted_col
            )

        # 4. Draw Sub Sectors
        for k, sec in enumerate(self.sub_sectors):
            is_hover = (k == self.hovered_sub_idx)
            fill = QColor(accent_col) if is_hover else bg_card
            fill.setAlpha(235 if is_hover else 210)
            pen = QPen(QColor(255, 255, 255, 240) if is_hover else border_col, 1.4 if is_hover else 1.0)

            painter.setPen(pen)
            painter.setBrush(fill)
            painter.drawPath(sec.path)

            self._draw_sector_content(
                painter, sec,
                text_col=QColor("#FFFFFF") if is_hover else text_col,
                muted_col=muted_col
            )

        # 5. Hub
        self._draw_hub(painter, bg_card_alt, border_col, text_col, accent_col)

        # 6. Tooltip pill
        self._draw_tooltip_pill(painter, bg_card_alt, border_col, text_col, muted_col, width, height)

        painter.restore()

    def _draw_hub(self, painter: QPainter, bg_col, border_col, text_col, accent_col):
        c = self.center_pos
        r = self.HUB_RADIUS

        if self.hub_action_ok and self.hub_action_cancel:
            ok_hover = (self.hovered_hub == "hub_ok")
            p_ok = QPainterPath()
            p_ok.arcMoveTo(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), 0)
            p_ok.arcTo(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), 0, 180)
            p_ok.closeSubpath()

            painter.setPen(QPen(QColor("#4CAF50"), 1.5 if ok_hover else 1.0))
            painter.setBrush(QColor(46, 125, 50, 230 if ok_hover else 170))
            painter.drawPath(p_ok)

            cancel_hover = (self.hovered_hub == "hub_cancel")
            p_cancel = QPainterPath()
            p_cancel.arcMoveTo(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), 180)
            p_cancel.arcTo(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), 180, 180)
            p_cancel.closeSubpath()

            painter.setPen(QPen(QColor("#F44336"), 1.5 if cancel_hover else 1.0))
            painter.setBrush(QColor(180, 40, 40, 230 if cancel_hover else 160))
            painter.drawPath(p_cancel)

            painter.setPen(QPen(border_col, 1.2))
            painter.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))

            f = QFont()
            f.setPixelSize(10)
            f.setBold(True)
            painter.setFont(f)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(QRectF(c.x() - r, c.y() - r * 0.85, r * 2, r * 0.75), Qt.AlignmentFlag.AlignCenter, "Finish ✔")
            painter.drawText(QRectF(c.x() - r, c.y() + r * 0.1, r * 2, r * 0.75), Qt.AlignmentFlag.AlignCenter, "Cancel ✖")
        else:
            is_hover = (self.hovered_hub == "hub_center")
            painter.setPen(QPen(accent_col if is_hover else border_col, 1.6 if is_hover else 1.2))
            painter.setBrush(QColor(accent_col if is_hover else bg_col))
            painter.drawEllipse(c, r, r)

            label = self.hub_action_center.label if self.hub_action_center else "✖"
            f = QFont()
            f.setPixelSize(11)
            f.setBold(True)
            painter.setFont(f)
            painter.setPen(QColor("#FFFFFF") if is_hover else text_col)
            painter.drawText(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), Qt.AlignmentFlag.AlignCenter, label)

    def _draw_sector_content(self, painter: QPainter, sec: SectorGeom, text_col, muted_col):
        """Draws the curved label along the outer arc of the sector, with the icon placed below it."""
        item = sec.item
        has_icon = item.icon is not None and not item.icon.isNull()
        mid_deg = sec.start_angle + sec.span_angle / 2.0
        mid_rad = math.radians(mid_deg)

        # 1. Place icon slightly inward from center radius
        if has_icon:
            icon_size = 22
            r_icon = sec.r_inner + (sec.r_outer - sec.r_inner) * 0.38
            icx = self.center_pos.x() + r_icon * math.cos(mid_rad)
            icy = self.center_pos.y() - r_icon * math.sin(mid_rad)
            pix = item.icon.pixmap(icon_size, icon_size)
            painter.drawPixmap(int(round(icx - icon_size / 2.0)), int(round(icy - icon_size / 2.0)), pix)

        # 2. Draw curved text along the outer arc (above the icon)
        label = item.label.strip()
        if not label:
            return

        f = QFont()
        f.setPixelSize(10)
        f.setWeight(QFont.Weight.DemiBold)
        painter.setFont(f)
        painter.setPen(text_col)
        fm = QFontMetrics(f)

        # Radius for baseline of curved text: positioned near the top of the sector
        r_text = sec.r_outer - 11.0 if has_icon else (sec.r_inner + sec.r_outer) * 0.5

        # Check total angular width required
        char_widths = [fm.horizontalAdvance(ch) for ch in label]
        total_text_width = sum(char_widths)
        max_arc_len = (sec.r_outer * math.radians(sec.span_angle)) * 0.88

        # If text is too wide, elide it
        if total_text_width > max_arc_len:
            label = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(max_arc_len))
            char_widths = [fm.horizontalAdvance(ch) for ch in label]
            total_text_width = sum(char_widths)

        total_arc_deg = math.degrees(total_text_width / r_text) if r_text > 0 else 0.0

        # In Qt coordinate system (Y down), standard angle increases counter-clockwise (math).
        # To read left-to-right along the arc:
        # For the top half / upper quadrants, reading L-to-R means sweeping clockwise (decreasing math degrees).
        # Characters are centered around mid_deg.
        current_deg = mid_deg + (total_arc_deg / 2.0)

        for ch, ch_w in zip(label, char_widths):
            half_w_deg = math.degrees((ch_w / 2.0) / r_text)
            char_center_deg = current_deg - half_w_deg
            rad = math.radians(char_center_deg)

            px = self.center_pos.x() + r_text * math.cos(rad)
            py = self.center_pos.y() - r_text * math.sin(rad)

            # Rotation angle: tangent to circle at char_center_deg.
            # Angle of radial vector in Qt screen coords: atan2(dy_screen, dx_screen) = -char_center_deg
            # Tangent pointing clockwise is perpendicular: rotation = 90 - char_center_deg
            rot_deg = 90.0 - char_center_deg

            painter.save()
            painter.translate(px, py)
            painter.rotate(rot_deg)
            # Draw character centered at (0, 0)
            painter.drawText(QRectF(-ch_w / 2.0, -fm.ascent(), ch_w + 2, fm.height()), Qt.AlignmentFlag.AlignCenter, ch)
            painter.restore()

            current_deg -= math.degrees(ch_w / r_text)

    def _draw_label_and_icon(self, painter: QPainter, item: FanItem, cx: float, cy: float, text_col, muted_col, max_width: float):
        pass

    def _draw_tooltip_pill(self, painter: QPainter, bg_col, border_col, text_col, muted_col, width: int, height: int):
        hovered_item: Optional[FanItem] = None
        if self.hovered_sub_idx is not None and 0 <= self.hovered_sub_idx < len(self.sub_sectors):
            hovered_item = self.sub_sectors[self.hovered_sub_idx].item
        elif self.hovered_outer_idx is not None and 0 <= self.hovered_outer_idx < len(self.outer_sectors):
            hovered_item = self.outer_sectors[self.hovered_outer_idx].item
        elif 0 <= self.active_category_idx < len(self.inner_sectors):
            hovered_item = self.inner_sectors[self.active_category_idx].item

        if not hovered_item:
            return

        title = hovered_item.label
        if hovered_item.shortcut:
            title += f"  [{hovered_item.shortcut}]"
        tip = hovered_item.tooltip or ""

        pill_text = f"{title}: {tip}" if tip else title

        f = QFont()
        f.setPixelSize(11)
        fm = QFontMetrics(f)
        w = min(440, max(140, fm.horizontalAdvance(pill_text) + 24))
        h = 24

        px = self.center_pos.x() - w / 2.0
        py = self.center_pos.y() + self.OUTER_R2 + 16

        if py + h > height - 8:
            py = self.center_pos.y() - self.OUTER_R2 - 16 - h

        pill_rect = QRectF(px, py, w, h)
        painter.setPen(QPen(border_col, 1.0))
        painter.setBrush(bg_col)
        painter.drawRoundedRect(pill_rect, 12, 12)

        painter.setFont(f)
        painter.setPen(text_col)
        display_str = fm.elidedText(pill_text, Qt.TextElideMode.ElideRight, int(w - 16))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, display_str)


# Backward compatibility
FanMenuOverlay = FanMenu
