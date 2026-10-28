"""Sketch dimension drawing, picking, editing, and inline input."""

import math
from typing import Optional, List, Tuple
import numpy as np
from PySide6.QtCore import Qt, QPoint, QRectF, QPointF, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QFontMetrics
from omacad.ui import theme, dyn_input
from omacad.ui.theme import qcolor
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.model.dim_layout import pt_line_base_shift, PT_LINE_DEFAULT_OFFSET, lines_are_parallel, line_distance
from omacad.model.sketch import (
    SketchLine, SketchRect, SketchCircle, SketchCenterRect, SketchArc, SketchSlot,
    point_of, arm_vector, arm_angle_deg, nearest_ends_to_vertex, ref_id, ref_segment, EDGE_PTS
)


class DimensionOverlayMixin:
    """Dimension rendering and interaction methods used by :class:`Viewport3D`."""

    def draw_dimensions(self, painter: QPainter):
        """Renders dimension extension lines, arrows, and interactive value badges."""
        if not self.doc.active_sketch or not self.sketch_palette.chk_show_dims.isChecked():
            self.dim_badges.clear()
            return

        sketch = self.doc.active_sketch
        plane = sketch.plane
        self.dim_badges.clear()

        font_dim = QFont(theme.font_family(), 9, QFont.Weight.Bold)
        painter.setFont(font_dim)
        fm = painter.fontMetrics()

        pen_ext = QPen(qcolor(160, 180, 205, 180), 1, Qt.PenStyle.DashLine)
        pen_dim_line = QPen(qcolor(200, 225, 255, 230), 1.2, Qt.PenStyle.SolidLine)

        for dim in sketch.dimensions:
            ent = sketch.get_entity(dim.target_entity_id)
            if not ent:
                continue

            lines_to_draw = []
            badge_pos_uv = None
            dim_p1_uv = None
            dim_p2_uv = None
            badge_text = f"{dim.dim_id}: {dim.value:.1f} mm"

            if dim.dim_type == "RECT_WIDTH":
                if isinstance(ent, SketchRect):
                    x1 = min(ent.p1[0], ent.p2[0])
                    x2 = max(ent.p1[0], ent.p2[0])
                    y_base = min(ent.p1[1], ent.p2[1])
                elif isinstance(ent, SketchCenterRect):
                    c1, c2, _, _ = ent.get_corners()
                    x1, x2 = c1[0], c2[0]
                    y_base = c1[1]
                else:
                    continue
                y_dim = y_base - dim.offset_distance
                ext1 = ((x1, y_base), (x1, y_dim - 2.0))
                ext2 = ((x2, y_base), (x2, y_dim - 2.0))
                dim_line = ((x1, y_dim), (x2, y_dim))
                lines_to_draw = [ext1, ext2, dim_line]
                dim_p1_uv = (x1, y_dim)
                dim_p2_uv = (x2, y_dim)
                badge_pos_uv = ((x1 + x2) * 0.5, y_dim)

            elif dim.dim_type == "RECT_HEIGHT":
                if isinstance(ent, SketchRect):
                    x_base = max(ent.p1[0], ent.p2[0])
                    y1 = min(ent.p1[1], ent.p2[1])
                    y2 = max(ent.p1[1], ent.p2[1])
                elif isinstance(ent, SketchCenterRect):
                    c1, c2, c3, _ = ent.get_corners()
                    x_base = c2[0]
                    y1, y2 = c1[1], c3[1]
                else:
                    continue
                x_dim = x_base + dim.offset_distance
                ext1 = ((x_base, y1), (x_dim + 2.0, y1))
                ext2 = ((x_base, y2), (x_dim + 2.0, y2))
                dim_line = ((x_dim, y1), (x_dim, y2))
                lines_to_draw = [ext1, ext2, dim_line]
                dim_p1_uv = (x_dim, y1)
                dim_p2_uv = (x_dim, y2)
                badge_pos_uv = (x_dim, (y1 + y2) * 0.5)

            elif dim.dim_type == "LENGTH":
                if isinstance(ent, SketchLine):
                    p1, p2 = ent.p1, ent.p2
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    length = math.hypot(dx, dy)
                    if length > 1e-4:
                        nx = -dy / length
                        ny = dx / length
                        off = dim.offset_distance
                        p1_off = (p1[0] + nx * off, p1[1] + ny * off)
                        p2_off = (p2[0] + nx * off, p2[1] + ny * off)
                        over = 2.0 if off >= 0 else -2.0   # extension lines run a little past the dimension line
                        ext1 = (p1, (p1_off[0] + nx * over, p1_off[1] + ny * over))
                        ext2 = (p2, (p2_off[0] + nx * over, p2_off[1] + ny * over))
                        dim_line = (p1_off, p2_off)
                        lines_to_draw = [ext1, ext2, dim_line]
                        dim_p1_uv = p1_off
                        dim_p2_uv = p2_off
                        badge_pos_uv = ((p1_off[0] + p2_off[0]) * 0.5, (p1_off[1] + p2_off[1]) * 0.5)
                elif isinstance(ent, SketchSlot):
                    c1, c2 = ent.center1, ent.center2
                    dx = c2[0] - c1[0]
                    dy = c2[1] - c1[1]
                    length = math.hypot(dx, dy)
                    if length > 1e-4:
                        nx = -dy / length
                        ny = dx / length
                        off = dim.offset_distance + ent.radius
                        p1_off = (c1[0] + nx * off, c1[1] + ny * off)
                        p2_off = (c2[0] + nx * off, c2[1] + ny * off)
                        ext1 = (c1, p1_off)
                        ext2 = (c2, p2_off)
                        dim_line = (p1_off, p2_off)
                        lines_to_draw = [ext1, ext2, dim_line]
                        dim_p1_uv = p1_off
                        dim_p2_uv = p2_off
                        badge_pos_uv = ((p1_off[0] + p2_off[0]) * 0.5, (p1_off[1] + p2_off[1]) * 0.5)

            elif dim.dim_type in ("DIAMETER", "RADIUS") and isinstance(ent, (SketchCircle, SketchSlot)):
                cx, cy = ent.center if isinstance(ent, SketchCircle) else ent.center2
                r = ent.radius
                ang = math.pi * 0.25
                edge_pt = (cx + r * math.cos(ang), cy + r * math.sin(ang))
                leader_pt = (cx + (r + dim.offset_distance) * math.cos(ang), cy + (r + dim.offset_distance) * math.sin(ang))
                leader_ext = (edge_pt, leader_pt)
                lines_to_draw = [leader_ext]
                dim_p1_uv = edge_pt
                dim_p2_uv = leader_pt
                badge_pos_uv = leader_pt
                symbol = "Ø" if dim.dim_type == "DIAMETER" else "R"
                badge_text = f"{symbol} {dim.value:.1f} mm ({dim.dim_id})"

            elif dim.dim_type == "RADIUS" and isinstance(ent, SketchArc):
                params = ent.get_circle_params()
                if params:
                    cx, cy = params[0]
                    r = params[1]
                    mid = ent.p_mid
                    ang = math.atan2(mid[1] - cy, mid[0] - cx)
                    leader_pt = (cx + (r + dim.offset_distance) * math.cos(ang), cy + (r + dim.offset_distance) * math.sin(ang))
                    lines_to_draw = [(mid, leader_pt)]
                    dim_p1_uv = mid
                    dim_p2_uv = leader_pt
                    badge_pos_uv = leader_pt
                    badge_text = f"R {dim.value:.1f} mm ({dim.dim_id})"

            elif dim.dim_type == "ANGLE":
                other = sketch.get_entity(dim.refs[0]) if dim.refs else None
                if isinstance(ent, SketchLine) and isinstance(other, SketchLine) and len(dim.pts) == 2:
                    ua, ub = arm_vector(ent, dim.pts[0]), arm_vector(other, dim.pts[1])
                    na, nb = math.hypot(*ua), math.hypot(*ub)
                    if na > 1e-6 and nb > 1e-6:
                        # vertex: where the two lines (extended) meet, else the nearest ends' midpoint
                        pa, pb = point_of(ent, dim.pts[0]), point_of(other, dim.pts[1])
                        det = ua[0] * ub[1] - ua[1] * ub[0]
                        if abs(det) > 1e-9 * na * nb:
                            t = ((pb[0] - pa[0]) * ub[1] - (pb[1] - pa[1]) * ub[0]) / det
                            vtx = (pa[0] + ua[0] * t, pa[1] + ua[1] * t)
                        else:
                            vtx = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)
                        a0 = math.atan2(ua[1], ua[0])
                        sweep = math.atan2(ua[0] * ub[1] - ua[1] * ub[0], ua[0] * ub[0] + ua[1] * ub[1])
                        radius = 8.0 + dim.offset_distance * 0.6
                        arc = [(vtx[0] + radius * math.cos(a0 + sweep * k / 24.0),
                                vtx[1] + radius * math.sin(a0 + sweep * k / 24.0)) for k in range(25)]
                        painter.setPen(pen_dim_line)
                        for q1, q2 in zip(arc, arc[1:]):
                            s1 = self.world_to_screen(plane.uv_to_world(q1[0], q1[1]))
                            s2 = self.world_to_screen(plane.uv_to_world(q2[0], q2[1]))
                            if s1 and s2:
                                painter.drawLine(QPointF(s1[0], s1[1]), QPointF(s2[0], s2[1]))
                        mid = a0 + sweep / 2.0
                        badge_pos_uv = (vtx[0] + (radius + 6.0) * math.cos(mid), vtx[1] + (radius + 6.0) * math.sin(mid))
                        badge_text = f"∠ {dim.value:.1f}° ({dim.dim_id})"

            elif dim.dim_type in ("DISTANCE", "HORIZ_DIST", "VERT_DIST", "PT_LINE_DIST"):
                other = sketch.get_entity(dim.refs[0]) if dim.refs else None
                edge = ref_segment(dim.refs[0]) if dim.refs else None
                if edge is not None:  # measured to a fixed face edge
                    other = SketchLine("edge", edge[0], edge[1])
                if other is not None and dim.pts:
                    if (dim.dim_type == "PT_LINE_DIST" and isinstance(other, SketchLine)
                            and dim.pts[0] in EDGE_PTS and isinstance(ent, SketchCircle)):
                        (x1, y1), (x2, y2) = other.p1, other.p2
                        L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
                        if L2 > 1e-12:
                            cx, cy = ent.center
                            t = ((cx - x1) * (x2 - x1) + (cy - y1) * (y2 - y1)) / L2
                            foot = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
                            dx, dy = cx - foot[0], cy - foot[1]
                            dl = math.hypot(dx, dy) or 1.0
                            sgn = -1.0 if dim.pts[0] == "edge_near" else 1.0
                            edge_pt = (cx + sgn * ent.radius * dx / dl, cy + sgn * ent.radius * dy / dl)
                            lines_to_draw = [(foot, edge_pt)]
                            dim_p1_uv, dim_p2_uv = foot, edge_pt
                            badge_pos_uv = ((foot[0] + edge_pt[0]) / 2.0, (foot[1] + edge_pt[1]) / 2.0)
                    elif dim.dim_type == "PT_LINE_DIST" and isinstance(other, SketchLine):
                        P = point_of(ent, dim.pts[0])
                        (x1, y1), (x2, y2) = other.p1, other.p2
                        L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
                        if P and L2 > 1e-12:
                            t = ((P[0] - x1) * (x2 - x1) + (P[1] - y1) * (y2 - y1)) / L2
                            foot = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
                            dx, dy = P[0] - foot[0], P[1] - foot[1]
                            dl = math.hypot(dx, dy) or 1.0
                            # Offset perpendicular to dimension line so the badge doesn't cover circle or lines
                            line_dir = ((x2 - x1) / math.sqrt(L2), (y2 - y1) / math.sqrt(L2))
                            # Determine offset shift: for circle, shift outside the circle radius
                            r_shift = pt_line_base_shift(ent) + dim.offset_distance - PT_LINE_DEFAULT_OFFSET
                            # Choose shift direction along the reference line
                            off_vec = (line_dir[0] * r_shift, line_dir[1] * r_shift)
                            p_off = (P[0] + off_vec[0], P[1] + off_vec[1])
                            foot_off = (foot[0] + off_vec[0], foot[1] + off_vec[1])
                            lines_to_draw = [(P, p_off), (foot, foot_off), (foot_off, p_off)]
                            dim_p1_uv, dim_p2_uv = foot_off, p_off
                            badge_pos_uv = ((p_off[0] + foot_off[0]) / 2.0, (p_off[1] + foot_off[1]) / 2.0)
                    elif len(dim.pts) == 2:
                        A, B = point_of(ent, dim.pts[0]), point_of(other, dim.pts[1])
                        off = dim.offset_distance
                        if A and B and dim.dim_type == "HORIZ_DIST":
                            y_dim = max(A[1], B[1]) + off
                            lines_to_draw = [((A[0], A[1]), (A[0], y_dim)), ((B[0], B[1]), (B[0], y_dim)),
                                             ((A[0], y_dim), (B[0], y_dim))]
                            dim_p1_uv, dim_p2_uv = (A[0], y_dim), (B[0], y_dim)
                            badge_pos_uv = ((A[0] + B[0]) / 2.0, y_dim)
                        elif A and B and dim.dim_type == "VERT_DIST":
                            x_dim = max(A[0], B[0]) + off
                            lines_to_draw = [((A[0], A[1]), (x_dim, A[1])), ((B[0], B[1]), (x_dim, B[1])),
                                             ((x_dim, A[1]), (x_dim, B[1]))]
                            dim_p1_uv, dim_p2_uv = (x_dim, A[1]), (x_dim, B[1])
                            badge_pos_uv = (x_dim, (A[1] + B[1]) / 2.0)
                        elif A and B:
                            L = math.hypot(B[0] - A[0], B[1] - A[1])
                            if L > 1e-6:
                                nx, ny = -(B[1] - A[1]) / L, (B[0] - A[0]) / L
                                a_off = (A[0] + nx * off, A[1] + ny * off)
                                b_off = (B[0] + nx * off, B[1] + ny * off)
                                lines_to_draw = [(A, a_off), (B, b_off), (a_off, b_off)]
                                dim_p1_uv, dim_p2_uv = a_off, b_off
                                badge_pos_uv = ((a_off[0] + b_off[0]) / 2.0, (a_off[1] + b_off[1]) / 2.0)

            if dim.expr and badge_text:     # driven by a parameter or formula: say so first (Fusion: "fx:")
                badge_text = f"ƒx {dim.expr} = {badge_text}"

            # Draw lines
            for idx, (u_a, u_b) in enumerate(lines_to_draw):
                w_a = plane.uv_to_world(u_a[0], u_a[1])
                w_b = plane.uv_to_world(u_b[0], u_b[1])
                s_a = self.world_to_screen(w_a)
                s_b = self.world_to_screen(w_b)
                if s_a and s_b:
                    if idx < 2 and len(lines_to_draw) >= 3:
                        painter.setPen(pen_ext)
                    else:
                        painter.setPen(pen_dim_line)
                    painter.drawLine(QPointF(s_a[0], s_a[1]), QPointF(s_b[0], s_b[1]))

            # Draw Arrowheads on dimension line
            if dim_p1_uv and dim_p2_uv:
                w1 = plane.uv_to_world(dim_p1_uv[0], dim_p1_uv[1])
                w2 = plane.uv_to_world(dim_p2_uv[0], dim_p2_uv[1])
                s1 = self.world_to_screen(w1)
                s2 = self.world_to_screen(w2)
                if s1 and s2:
                    if dim.dim_type in ("DIAMETER", "RADIUS"):
                        self._draw_single_arrowhead(painter, s1, s2)
                    else:
                        self._draw_arrowheads(painter, s1, s2)

            # Draw Dimension Badge
            if badge_pos_uv:
                w_badge = plane.uv_to_world(badge_pos_uv[0], badge_pos_uv[1])
                s_badge = self.world_to_screen(w_badge)
                if s_badge:
                    bw = fm.horizontalAdvance(badge_text) + 20
                    bh = 22
                    bx = s_badge[0] - bw * 0.5
                    by = s_badge[1] - bh * 0.5
                    badge_rect = QRectF(bx, by, bw, bh)

                    self.dim_badges[dim.dim_id] = (badge_rect, sketch.sketch_id, dim.dim_id, dim.value)

                    is_hovered = (self.hovered_dim_id == dim.dim_id)
                    if is_hovered:
                        painter.setPen(QPen(qcolor(255, 255, 255), 1.5))
                        painter.setBrush(QBrush(qcolor(226, 109, 40, 245)))
                        painter.drawRoundedRect(badge_rect, 4, 4)
                        painter.setPen(QPen(qcolor(255, 255, 255)))
                        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, f"✏️ {badge_text}")
                    elif dim.expr:                   # parameter-driven: blue frame and text
                        painter.setPen(QPen(qcolor(56, 189, 248, 240), 1.6))
                        painter.setBrush(QBrush(qcolor(12, 38, 56, 235)))
                        painter.drawRoundedRect(badge_rect, 4, 4)
                        painter.setPen(QPen(qcolor(125, 211, 252)))
                        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
                    else:
                        painter.setPen(QPen(qcolor(70, 115, 160, 210), 1.0))
                        painter.setBrush(QBrush(qcolor(22, 26, 32, 230)))
                        painter.drawRoundedRect(badge_rect, 4, 4)
                        painter.setPen(QPen(qcolor(215, 230, 250)))
                        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

    def _draw_arrowheads(self, painter: QPainter, s1: Tuple[float, float], s2: Tuple[float, float]):
        """Draws small CAD arrowheads at the endpoints of a dimension line."""
        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        dist = math.hypot(dx, dy)
        if dist < 12.0:
            return

        ux = dx / dist
        uy = dy / dist
        px = -uy
        py = ux

        arrow_len = 7.0
        arrow_half_w = 3.0

        painter.setPen(QPen(qcolor(200, 225, 255, 240), 1.0))
        painter.setBrush(QBrush(qcolor(200, 225, 255, 240)))

        # Arrowhead at s1 pointing towards s2
        a1_tip = QPointF(s1[0], s1[1])
        a1_b1 = QPointF(s1[0] + ux * arrow_len + px * arrow_half_w, s1[1] + uy * arrow_len + py * arrow_half_w)
        a1_b2 = QPointF(s1[0] + ux * arrow_len - px * arrow_half_w, s1[1] + uy * arrow_len - py * arrow_half_w)
        painter.drawPolygon(QPolygonF([a1_tip, a1_b1, a1_b2]))

        # Arrowhead at s2 pointing towards s1
        a2_tip = QPointF(s2[0], s2[1])
        a2_b1 = QPointF(s2[0] - ux * arrow_len + px * arrow_half_w, s2[1] - uy * arrow_len + py * arrow_half_w)
        a2_b2 = QPointF(s2[0] - ux * arrow_len - px * arrow_half_w, s2[1] - uy * arrow_len - py * arrow_half_w)
        painter.drawPolygon(QPolygonF([a2_tip, a2_b1, a2_b2]))

    def _draw_single_arrowhead(self, painter: QPainter, s1: Tuple[float, float], s2: Tuple[float, float]):
        """Draws a single arrowhead at s1 pointing towards s2 (for leader lines)."""
        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        dist = math.hypot(dx, dy)
        if dist < 6.0:
            return

        ux = dx / dist
        uy = dy / dist
        px = -uy
        py = ux

        arrow_len = 7.0
        arrow_half_w = 3.0

        painter.setPen(QPen(qcolor(200, 225, 255, 240), 1.0))
        painter.setBrush(QBrush(qcolor(200, 225, 255, 240)))

        a_tip = QPointF(s1[0], s1[1])
        a_b1 = QPointF(s1[0] + ux * arrow_len + px * arrow_half_w, s1[1] + uy * arrow_len + py * arrow_half_w)
        a_b2 = QPointF(s1[0] + ux * arrow_len - px * arrow_half_w, s1[1] + uy * arrow_len - py * arrow_half_w)
        painter.drawPolygon(QPolygonF([a_tip, a_b1, a_b2]))

    def prompt_edit_dimension(self, sketch_id: str, dim_id: str, current_value: float):
        """Edit a dimension value (type the number, press Enter); the solver updates the geometry."""
        sk = self.doc.sketches.get(sketch_id)
        dim = next((d for d in sk.dimensions if d.dim_id == dim_id), None) if sk else None
        is_angle = dim is not None and dim.dim_type == "ANGLE"
        res = self.prompt_dimension_value(
            f"Parametric Dimension ({dim_id})",
            f"Enter new value for {dim_id} ({'degrees' if is_angle else 'mm'}); a formula or parameter name works too:",
            current_value, 0.1, 179.9 if is_angle else 50000.0, " °" if is_angle else " mm",
            expr=dim.expr if dim is not None else None, inline=True)
        val, ex = res if res is not None else (None, None)
        if val is not None and val > 0.001:
            if not self.doc.update_dimension(sketch_id, dim_id, val, expr=ex):
                self.status_message.emit(self.doc.last_message)
            self.update()

    def show_dimension_entities(self, sketch_id: str, dim_id: str):
        """Lights up the entities a dimension measures (picked in the browser); empty ids clear it."""
        sk = self.doc.sketches.get(sketch_id) if sketch_id else None
        dim = next((d for d in sk.dimensions if d.dim_id == dim_id), None) if sk else None
        self.picked_dim_entities = (sketch_id, {dim.target_entity_id, *dim.refs}) if dim else (None, set())
        self.picked_dim = (sketch_id, dim_id) if dim else None
        self.update()

    def _dim_highlight_ids(self) -> set:
        ids = {p[1].entity_id for p in self._dim_pending if p[0] in ("ent", "pt")}  # "ref" picks are edges, not entities
        if self._dim_place:
            ids |= {self._dim_place["a"][1].entity_id, self._dim_place["b"][1].entity_id}
        return ids

    def _dim_pick(self, u: float, v: float):
        """('pt', entity, point name) near an end point/centre, else ('ent', entity), else None."""
        sk = self.doc.active_sketch
        tol = self._entity_tolerance()
        best = None
        for e in sk.entities:
            names = ("p1", "p2") if isinstance(e, SketchLine) else ("center",) if isinstance(e, SketchCircle) else ()
            for n in names:
                pt = point_of(e, n)
                d = math.hypot(u - pt[0], v - pt[1])
                if d <= tol * 1.3 and (best is None or d < best[0]):
                    best = (d, e, n)
        if best:
            return ("pt", best[1], best[2])
        ent = sk.hit_test(u, v, tol)
        if ent:
            return ("ent", ent)
        # the outline of the face the sketch is on (and other in-plane body edges)
        near = None
        for seg in sk.reference_segments:
            d = self._point_to_segment_dist((u, v), seg[0], seg[1])
            if d <= tol and (near is None or d < near[0]):
                near = (d, seg)
        return ("ref", near[1]) if near else None

    def prompt_dimension_inline(self, label: str, value: float, lo: float, hi: float, suffix: str, expr: str = None):
        """The value box floating in the 3D view next to the cursor; waits for Enter (value) or Esc (None)."""
        from PySide6.QtCore import QEventLoop
        from PySide6.QtGui import QCursor
        from omacad.ui.inline_value import InlineValueBox
        box = InlineValueBox(self, label, value, lo, hi, suffix, expr)
        loop = QEventLoop(self)
        outcome = []
        box.committed.connect(lambda: (outcome.append(True), loop.quit()))
        box.cancelled.connect(lambda: (outcome.append(False), loop.quit()))

        def focus_moved(_old, new):
            # A click elsewhere in Omacad takes the value, as in Fusion. Before, the box only listened for Enter and
            # Esc while it had the focus, so after a click outside it stayed in the view for good (Björn #77).
            if new is not None and new is not box and not box.isAncestorOf(new) and not outcome:
                outcome.append(True)
                loop.quit()

        from PySide6.QtWidgets import QApplication
        QApplication.instance().focusChanged.connect(focus_moved)
        pos = self.mapFromGlobal(QCursor.pos())
        box.place_near(pos.x(), pos.y())
        box.show()
        box.focus_value()
        try:
            loop.exec()
        finally:
            QApplication.instance().focusChanged.disconnect(focus_moved)
        result = box.result() if outcome and outcome[0] else None
        box.hide()
        box.deleteLater()
        self.setFocus()
        return result

    def prompt_dimension_value(self, title: str, label: str, value: float, lo: float = 0.1,
                               hi: float = 50000.0, suffix: str = " mm", expr: str = None, on_change=None,
                               inline: bool = False):
        """Value dialog with the number pre-selected: type it and press Enter. Returns None on cancel.
        `inline`: a small box in the 3D view instead of the side panel (used for sketch dimensions)."""
        if inline and on_change is None:
            return self.prompt_dimension_inline(label, value, lo, hi, suffix, expr)
        dlg = QDialog(self)
        dlg._nested = True          # asked from inside a tool: the tool stays open and comes back afterwards
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        lbl = QLabel(label)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        spin = ExprDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(2)
        spin.setSuffix(suffix)
        spin.setValue(max(lo, min(hi, float(value))))
        if expr:
            spin.set_expression(expr)  # keep showing the formula that drives this dimension
        spin.setToolTip("Type a value, a formula (10-1, 2x(3+5)) or a parameter name (width/2)")
        lay.addWidget(spin)
        if on_change is not None:
            spin.valueChanged.connect(lambda *_: on_change(spin.value()))
            QTimer.singleShot(0, lambda: on_change(spin.value()))   # show the first preview at once
        row = QHBoxLayout()
        row.addStretch()
        cancel, ok = QPushButton("Cancel"), QPushButton("OK")
        ok.setDefault(True)
        cancel.clicked.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        QTimer.singleShot(0, lambda: (spin.setFocus(), spin.selectAll()))
        from omacad.ui.dialogs import run_docked
        if run_docked(dlg) != QDialog.DialogCode.Accepted:
            return None
        spin.interpretText()  # evaluates a formula that was typed but not yet committed
        return spin.value(), spin.expression()

    def _dim_create(self, dim_type, target, measured, refs=(), pts=(), offset=12.0, label="", lo=0.1, hi=50000.0, suffix=" mm"):
        sk = self.doc.active_sketch
        res = self.prompt_dimension_value(f"New dimension", label, measured, lo, hi, suffix, inline=True)
        if res is None:
            return
        val, ex = res
        self.doc.add_dimension_constraint(sk.sketch_id, dim_type, target, val, refs=refs, pts=pts, offset=offset, expr=ex)
        self.status_message.emit(self.doc.last_message)
        self.update()

    def _dim_existing(self, dim_type, target, refs=(), pts=()):
        sk = self.doc.active_sketch
        refs = list(refs)
        for d in sk.dimensions:
            if d.dim_type != dim_type:
                continue
            same = d.target_entity_id == target and d.refs == refs and (not pts or d.pts == list(pts))
            swapped = dim_type == "ANGLE" and refs and d.target_entity_id == refs[0] and d.refs == [target]
            if same or swapped:
                return d
        return None

    def _dim_circle(self, circ):
        sk = self.doc.active_sketch
        existing = next((d for d in sk.dimensions
                         if d.target_entity_id == circ.entity_id and d.dim_type in ("DIAMETER", "RADIUS")), None)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
        else:
            self._dim_create("DIAMETER", circ.entity_id, circ.radius * 2.0, label="Diameter (mm):")

    def _dim_arc(self, arc):
        sk = self.doc.active_sketch
        existing = next((d for d in sk.dimensions
                         if d.target_entity_id == arc.entity_id and d.dim_type in ("RADIUS", "DIAMETER")), None)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
            return
        params = arc.get_circle_params()
        if params:
            self._dim_create("RADIUS", arc.entity_id, float(params[1]), label="Radius (mm):")

    def _dim_slot_length(self, slot):
        sk = self.doc.active_sketch
        existing = self._dim_existing("LENGTH", slot.entity_id)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
        else:
            L = math.hypot(slot.center2[0] - slot.center1[0], slot.center2[1] - slot.center1[1])
            self._dim_create("LENGTH", slot.entity_id, L, label="Slot center-to-center length (mm):")

    def _dim_slot_width(self, slot):
        sk = self.doc.active_sketch
        existing = next((d for d in sk.dimensions
                         if d.target_entity_id == slot.entity_id and d.dim_type in ("DIAMETER", "RADIUS")), None)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
        else:
            self._dim_create("DIAMETER", slot.entity_id, slot.radius * 2.0, label="Slot width / diameter (mm):")

    def _dim_length(self, line):
        sk = self.doc.active_sketch
        existing = self._dim_existing("LENGTH", line.entity_id)
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
        else:
            L = math.hypot(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1])
            self._dim_create("LENGTH", line.entity_id, L, label="Length (mm):")

    def _dim_angle(self, a, b):
        sk = self.doc.active_sketch
        ea, eb = nearest_ends_to_vertex(a, b)
        existing = self._dim_existing("ANGLE", a.entity_id, refs=[b.entity_id])
        if existing:
            self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("ANGLE", a.entity_id, arm_angle_deg(a, ea, b, eb), refs=[b.entity_id], pts=[ea, eb],
                         offset=12.0, label="Angle (degrees):", lo=0.1, hi=179.9, suffix=" °")

    def _dim_parallel(self, a, b):
        """Two parallel lines: the distance between them (the lines are kept parallel by a constraint)."""
        sk = self.doc.active_sketch
        for x, y in ((a, b), (b, a)):
            existing = self._dim_existing("PT_LINE_DIST", x.entity_id, refs=[y.entity_id], pts=["p1"])
            if existing:
                self.prompt_edit_dimension(sk.sketch_id, existing.dim_id, existing.value)
                return
        dist = line_distance(a, b)
        res = self.prompt_dimension_value("New dimension", "Distance between the lines (mm):", dist, 0.0, 50000.0, " mm", inline=True)
        if res is None:
            return
        val, ex = res
        if not any(c.ctype == "PARALLEL" and set(c.refs) == {a.entity_id, b.entity_id} for c in sk.constraints):
            self.doc.add_constraints(sk.sketch_id, [("PARALLEL", [a.entity_id, b.entity_id], [])])
        self.doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", a.entity_id, val, refs=[b.entity_id], pts=["p1"],
                                          offset=PT_LINE_DEFAULT_OFFSET, expr=ex)
        self.status_message.emit(self.doc.last_message)
        self.update()

    def _dim_pt_line(self, pt_pick, line):
        ent, pname = pt_pick[1], pt_pick[2]
        if ent is line:
            return
        P = point_of(ent, pname)
        (x1, y1), (x2, y2) = line.p1, line.p2
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        dist = abs((P[0] - x1) * (y2 - y1) - (P[1] - y1) * (x2 - x1)) / L
        existing = self._dim_existing("PT_LINE_DIST", ent.entity_id, refs=[line.entity_id], pts=[pname])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("PT_LINE_DIST", ent.entity_id, dist, refs=[line.entity_id], pts=[pname], label="Distance to line (mm):", lo=0.0)

    def _dim_edge_to_circle(self, line_pick, circ, u: float, v: float):
        """Distance from a face edge / line to the near or far edge of a circle. Which one is decided
        by where on the circle you clicked: the side facing the line is the near edge."""
        if line_pick[0] == "ref":
            seg, line_ref, line_ent = line_pick[1], ref_id(line_pick[1]), None
        else:
            line_ent = line_pick[1]
            seg, line_ref = (line_ent.p1, line_ent.p2), line_ent.entity_id
        (x1, y1), (x2, y2) = seg
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        dist = lambda px, py: abs((px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)) / L
        dc = dist(*circ.center)
        near = dist(u, v) < dc
        if self._dim_side in ("near", "far"):  # chosen explicitly from the right-click menu
            near = self._dim_side == "near"
        self._dim_side = None
        pname = "edge_near" if near else "edge_far"
        measured = max(0.0, dc - circ.radius) if near else dc + circ.radius
        existing = self._dim_existing("PT_LINE_DIST", circ.entity_id, refs=[line_ref], pts=[pname])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("PT_LINE_DIST", circ.entity_id, measured, refs=[line_ref], pts=[pname],
                         label=f"Distance to the circle's {'near' if near else 'far'} edge (mm):", lo=0.0)

    def _dim_pt_ref(self, pt_pick, seg):
        """Distance from a point (or circle centre) to a face edge, which stays fixed."""
        ent, pname = pt_pick[1], pt_pick[2]
        P = point_of(ent, pname)
        (x1, y1), (x2, y2) = seg
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        dist = abs((P[0] - x1) * (y2 - y1) - (P[1] - y1) * (x2 - x1)) / L
        existing = self._dim_existing("PT_LINE_DIST", ent.entity_id, refs=[ref_id(seg)], pts=[pname])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        self._dim_create("PT_LINE_DIST", ent.entity_id, dist, refs=[ref_id(seg)], pts=[pname],
                         label="Distance to edge (mm):", lo=0.0)

    def _dim_finish_points(self, u: float, v: float):
        """Placement click for a point-to-point distance: the side you click on picks the kind
        (above/below = horizontal, left/right = vertical, diagonal = aligned)."""
        place = self._dim_place
        box = self._dim_box
        typed = box.result() if box is not None and box.edited else None
        self._dim_place = None           # (this also closes the floating box)
        (ea, na), (eb, nb) = (place["a"][1], place["a"][2]), (place["b"][1], place["b"][2])
        dim_type, measured, _label, offset = self._dim_points_kind(place, u, v, with_offset=True)
        existing = self._dim_existing(dim_type, ea.entity_id, refs=[eb.entity_id], pts=[na, nb])
        if existing:
            self.prompt_edit_dimension(self.doc.active_sketch.sketch_id, existing.dim_id, existing.value)
            return
        sk = self.doc.active_sketch
        value, expr_text = typed if typed is not None else (measured, None)
        self.doc.add_dimension_constraint(sk.sketch_id, dim_type, ea.entity_id, value, refs=[eb.entity_id], pts=[na, nb],
                                          offset=offset, expr=expr_text)
        self.status_message.emit(self.doc.last_message)
        self.update()

    def _dim_points_kind(self, place, u: float, v: float, with_offset: bool = False):
        """What a point pair measures for a cursor at (u, v): above/below = horizontal, left/right = vertical,
        diagonal = aligned. Returns (type, measured value, label[, offset])."""
        (ea, na), (eb, nb) = (place["a"][1], place["a"][2]), (place["b"][1], place["b"][2])
        A, B = point_of(ea, na), point_of(eb, nb)
        xmin, xmax = sorted((A[0], B[0]))
        ymin, ymax = sorted((A[1], B[1]))
        inside_x, inside_y = xmin <= u <= xmax, ymin <= v <= ymax
        if inside_x and not inside_y:
            dim_type, measured, offset = "HORIZ_DIST", abs(A[0] - B[0]), v - ymax
        elif inside_y and not inside_x:
            dim_type, measured, offset = "VERT_DIST", abs(A[1] - B[1]), u - xmax
        else:
            dim_type = "DISTANCE"
            measured = math.hypot(A[0] - B[0], A[1] - B[1])
            L = measured or 1.0
            nx, ny = -(B[1] - A[1]) / L, (B[0] - A[0]) / L
            offset = (u - A[0]) * nx + (v - A[1]) * ny
        label = self.DIM_POINT_LABELS[dim_type] + " (mm) - type a value, Enter or click to place"
        return (dim_type, measured, label, offset) if with_offset else (dim_type, measured, label)

    def _show_dim_box(self):
        """Floating value box for the point pair that just got picked: shows the distance, type to change it."""
        from omacad.ui.inline_value import InlineValueBox
        self._hide_dim_box()
        place = self._dim_place
        (ea, na), (eb, nb) = (place["a"][1], place["a"][2]), (place["b"][1], place["b"][2])
        A, B = point_of(ea, na), point_of(eb, nb)
        mid = ((A[0] + B[0]) / 2.0, (A[1] + B[1]) / 2.0)
        _kind, measured, label = self._dim_points_kind(place, mid[0] + 1e6, mid[1] + 1e6)   # aligned until the cursor says otherwise
        box = InlineValueBox(self, label, measured, 0.0)
        box.committed.connect(self._dim_commit_from_box)
        box.cancelled.connect(self._dim_cancel_from_box)
        scr = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(mid[0], mid[1]))
        box.place_near(*(scr if scr else (self.width() / 2, self.height() / 2)))
        box.show()
        box.focus_value()
        self._dim_box = box
        self._dim_hover_uv = None

    def _dim_commit_from_box(self):
        """Enter in the box: place the dimension where the cursor was last seen (or at the default side)."""
        if not self._dim_place:
            return
        uv = self._dim_hover_uv
        if uv is None:
            place = self._dim_place
            A, B = point_of(place["a"][1], place["a"][2]), point_of(place["b"][1], place["b"][2])
            uv = ((A[0] + B[0]) / 2.0, max(A[1], B[1]) + 12.0)
        self._dim_finish_points(*uv)
        self.setFocus()
        self.update()

    def _dim_cancel_from_box(self):
        self._dim_pending, self._dim_place = [], None
        self.status_message.emit("Dimension cancelled.")
        self.setFocus()
        self.update()

    def handle_dimension_tool_click(self, u: float, v: float) -> bool:
        """Dimension tool: circle = diameter; arc = radius; slot = length/width; line + click away = length;
        line + line = angle; point + point = distance (click again to place); point + line = distance to line.
        Clicking a dimension that already exists edits it. Always consumes the click."""
        if not self.doc.active_sketch:
            return False
        if self._dim_place:
            self._dim_finish_points(u, v)
            self.update()
            return True
        pick = self._dim_pick(u, v)
        pend = self._dim_pending
        if not pend:
            if pick is None:
                self.status_message.emit("Dimension: click a line, circle, arc, slot or end point.")
            elif pick[0] == "ent" and isinstance(pick[1], SketchCircle):
                pend.append(pick)
                self.status_message.emit(
                    "Dimension: click away for the diameter, or click an edge/line to measure to the circle's edge "
                    "(click the centre point instead to measure from the centre).")
            elif pick[0] == "ent" and isinstance(pick[1], SketchArc):
                self._dim_arc(pick[1])
            elif pick[0] == "ent" and isinstance(pick[1], SketchSlot):
                slot = pick[1]
                # Clicking near the rounded ends edits width/diameter; clicking along the middle edits center-to-center length
                d1 = math.hypot(u - slot.center1[0], v - slot.center1[1])
                d2 = math.hypot(u - slot.center2[0], v - slot.center2[1])
                if min(d1, d2) < slot.radius * 1.15:
                    self._dim_slot_width(slot)
                else:
                    self._dim_slot_length(slot)
            elif pick[0] == "ent" and not isinstance(pick[1], SketchLine):
                self.status_message.emit("Dimension: this element type can't be dimensioned here yet.")
            elif pick[0] == "ref":
                pend.append(pick)
                self.status_message.emit("Dimension: now click the point or circle centre to measure from this edge.")
            else:
                pend.append(pick)
                self.status_message.emit(
                    "Dimension: click another line for an angle, an end point for a distance, or click away to dimension the length."
                    if pick[0] == "ent" else
                    "Dimension: click a second end point (distance) or a line (distance to line).")
            self.update()
            return True


        first = pend[0]
        self._dim_pending = []
        circle_pick = lambda p_: p_ and p_[0] == "ent" and isinstance(p_[1], SketchCircle)
        if first[0] == "ent" and isinstance(first[1], SketchCircle):  # a circle is waiting
            if pick and (pick[0] == "ref" or (pick[0] == "ent" and isinstance(pick[1], SketchLine))):
                self._dim_edge_to_circle(pick, first[1], u, v)
            else:
                self._dim_circle(first[1])
        elif first[0] == "ref" and circle_pick(pick):
            self._dim_edge_to_circle(first, pick[1], u, v)
        elif first[0] == "ent" and isinstance(first[1], SketchLine) and circle_pick(pick):
            self._dim_edge_to_circle(first, pick[1], u, v)
        elif first[0] == "ref":  # a face edge is waiting
            if pick and pick[0] == "pt":
                self._dim_pt_ref(pick, first[1])
            else:
                self.status_message.emit("Dimension: click an end point or a circle centre.")
        elif first[0] == "pt" and pick and pick[0] == "ref":
            self._dim_pt_ref(first, pick[1])
        elif first[0] == "ent":  # a line is waiting
            line = first[1]
            if pick and pick[0] == "ref":
                self.status_message.emit("Dimension: to measure from a face edge, click the point or circle centre first.")
            elif pick and pick[0] == "ent" and isinstance(pick[1], SketchLine) and pick[1] is not line:
                if lines_are_parallel(line, pick[1]):
                    self._dim_parallel(line, pick[1])
                else:
                    self._dim_angle(line, pick[1])
            elif pick and pick[0] == "pt" and pick[1] is not line:
                self._dim_pt_line(pick, line)
            else:
                self._dim_length(line)
        else:                  # a point is waiting
            if pick and pick[0] == "pt" and (pick[1].entity_id, pick[2]) != (first[1].entity_id, first[2]):
                self._dim_place = {"a": first, "b": pick}
                self._show_dim_box()
                self.status_message.emit("Dimension: click where to place it (above/below = horizontal, beside = vertical, diagonal = aligned).")
            elif pick and pick[0] == "ent" and isinstance(pick[1], SketchLine):
                self._dim_pt_line(first, pick[1])
            else:
                self.status_message.emit("Dimension cancelled.")
        self.update()
        return True
