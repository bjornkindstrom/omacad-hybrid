"""QPainter 2D overlay mixin for Viewport3D: dimensions, HUD, ViewCube, measurements."""

import math
from typing import Optional, List, Tuple
import numpy as np
from PySide6.QtCore import Qt, QPoint, QRectF, QPointF, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QFontMetrics
from omacad.ui import theme, theme_icons
from omacad.ui.theme import qcolor
from omacad.ui import dyn_input
from omacad.ui.viewport.body_dims import draw_body_dimensions
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.model.dim_layout import pt_line_base_shift, PT_LINE_DEFAULT_OFFSET, lines_are_parallel, line_distance
from omacad.model.sketch import (
    SketchLine, SketchRect, SketchCircle, SketchCenterRect, SketchArc, SketchSlot,
    point_of, arm_vector, arm_angle_deg, nearest_ends_to_vertex, ref_id, ref_segment, EDGE_PTS
)


class OverlayMixin:
    """Mixin providing 2D QPainter overlays (dimensions, badges, HUD) for Viewport3D."""
    def _draw_plane_labels(self, painter: QPainter):
        """Each shown plane's name, small, in the corner of the plane that is lowest-right on screen, so it reads
        from wherever the camera looks."""
        painter.save()
        font = QFont(painter.font())
        font.setPixelSize(11)
        painter.setFont(font)
        fm = painter.fontMetrics()
        for key, name, corners, (r, g, b) in self._plane_quads():
            pts = [self.world_to_screen(np.asarray(c, dtype=float)) for c in corners]
            if any(p is None for p in pts):
                continue
            pts = np.array(pts, dtype=float)
            area = 0.5 * abs(float(np.dot(pts[:, 0], np.roll(pts[:, 1], 1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], 1))))
            tw, th = fm.horizontalAdvance(name), fm.height()
            if area < 4.0 * tw * th:            # seen edge-on or tiny: no room for a label
                continue
            # the corner lowest-right on screen; an origin plane skips its corner at the origin, which all three share
            cand = pts[1:] if key[0] == "origin" else pts
            corner = cand[int(np.argmax(cand[:, 0] + cand[:, 1]))]
            inner = corner + 0.22 * (pts.mean(axis=0) - corner)      # inside its own plane, clear of shared edges
            hovered = self.hover_plane == key
            painter.setPen(QColor(int(r * 255), int(g * 255), int(b * 255), 235 if hovered else 150))
            painter.drawText(QRectF(inner[0] - tw - 4, inner[1] - th - 2, tw + 4, th),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)
        painter.restore()

    def draw_painter_overlays(self, painter: QPainter):
        """Draws ViewCube, sketch status banner, and HUD controls."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if getattr(self, "hole_place_plane", None) is not None:
            painter.save()
            painter.setPen(QPen(QColor(40, 170, 255, 210), 1.5))
            painter.setBrush(QColor(40, 170, 255, 150))
            marks = [*getattr(self, "hole_place_points", [])]
            if getattr(self, "hole_place_hover", None) is not None:
                marks.append(self.hole_place_hover)
            for point in marks:
                screen = self.world_to_screen(np.asarray(point, dtype=float))
                if screen is not None:
                    painter.drawEllipse(QPointF(float(screen[0]), float(screen[1])), 5.0, 5.0)
            painter.restore()
        w = self.width()
        h = self.height()

        self._draw_plane_labels(painter)
        # 1. ViewCube
        self.viewcube.draw(painter, w, h, self.azimuth, self.elevation)
        if self.rotate_handles.drag is None:
            draw_body_dimensions(self, painter)
        self.rotate_handles.draw(painter)
        self._draw_measure(painter)
        self._draw_handle_value(painter)
        self._draw_point_pick(painter)
        if self.primitive_handles:
            self.primitive_handles.draw(painter)

        if self.doc.active_sketch and self.sketch_tool == "FILLET" and self.fillet_picked:
            for pt, _a, _b in self.fillet_picked:
                scr = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*pt))
                if scr:
                    painter.setPen(QPen(QColor(255, 255, 255), 2))
                    painter.setBrush(QColor(255, 120, 30, 230))
                    painter.drawEllipse(QPointF(*scr), 7.0, 7.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)

        # Fillet hover corner marker and arrow
        if self.doc.active_sketch and self.sketch_tool == "FILLET" and self.fillet_hover_corner:
            pt, la, lb = self.fillet_hover_corner
            scr = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*pt))
            if scr:
                painter.setPen(QPen(QColor(255, 170, 60), 2))
                painter.setBrush(QColor(255, 170, 60, 160))
                painter.drawEllipse(QPointF(*scr), 6.0, 6.0)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                # Bisector arrow pointing into the corner
                try:
                    from omacad.model.sketch_fillet_curves import end_tangent, ends

                    def line_dir(ent):
                        end = min(ends(ent), key=lambda e: math.hypot(e[1][0] - pt[0], e[1][1] - pt[1]))[0]
                        d = end_tangent(ent, end, pt)
                        return d if d is not None else np.array([1.0, 0.0])

                    da = line_dir(la)
                    db = line_dir(lb)
                    bisect = da + db
                    b_norm = float(np.linalg.norm(bisect))
                    if b_norm > 1e-6:
                        bisect = bisect / b_norm
                        from omacad.ui.settings import get_settings
                        def_r = float(get_settings().get("fillet_default_radius", 2.0))
                        arrow_len = max(6.0, min(30.0, def_r * 2.5))
                        arrow_uv = np.array(pt) + bisect * arrow_len
                        scr_arr = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*arrow_uv))
                        if scr_arr:
                            painter.setPen(QPen(QColor(0, 195, 255), 2.5))
                            painter.drawLine(QPointF(*scr), QPointF(*scr_arr))
                            # Arrow head
                            angle = math.atan2(scr_arr[1] - scr[1], scr_arr[0] - scr[0])
                            head_len = 9.0
                            h1 = QPointF(scr_arr[0] - head_len * math.cos(angle - 0.45), scr_arr[1] - head_len * math.sin(angle - 0.45))
                            h2 = QPointF(scr_arr[0] - head_len * math.cos(angle + 0.45), scr_arr[1] - head_len * math.sin(angle + 0.45))
                            painter.drawLine(QPointF(*scr_arr), h1)
                            painter.drawLine(QPointF(*scr_arr), h2)
                            # Handle circle at tip
                            painter.setBrush(QColor(0, 195, 255, 180))
                            painter.drawEllipse(QPointF(*scr_arr), 4.5, 4.5)
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            # Label
                            painter.setFont(QFont("sans-serif", 9, QFont.Weight.Bold))
                            painter.setPen(QColor(0, 225, 255))
                            painter.drawText(QPointF(scr_arr[0] + 8, scr_arr[1] - 4), f"R {def_r:g} mm")
                except Exception:
                    pass

        # 2. Sketch Profiles Shading (when active or in sketch mode)
        if self.doc.active_sketch and self.sketch_palette.chk_show_profiles.isChecked():
            sketch = self.doc.active_sketch
            plane = sketch.plane
            for prof in sketch.profiles:
                poly_scr = []
                for pu, pv in prof.exterior_pts:
                    wpt = plane.uv_to_world(pu, pv)
                    scr = self.world_to_screen(wpt)
                    if scr:
                        poly_scr.append(QPointF(scr[0], scr[1]))
                if len(poly_scr) >= 3:
                    painter.setPen(QPen(qcolor(226, 109, 40, 200), 1.5))
                    painter.setBrush(QBrush(qcolor(226, 109, 40, 45)))  # Fusion Orange translucent profile fill
                    painter.drawPolygon(QPolygonF(poly_scr))

        # 2b. Selected Spline Fit Points and Tangent Handles (Fusion 360-style)
        if self.doc.active_sketch and self.selected_entities:
            from omacad.model.sketch_entities import SketchSpline
            sk = self.doc.active_sketch
            plane = sk.plane
            for ent_id in self.selected_entities:
                ent = sk.get_entity(ent_id)
                if isinstance(ent, SketchSpline):
                    n_pts = len(ent.points)
                    # Draw tangent handles (lines and green circle endpoints)
                    handle_pen = QPen(QColor(80, 200, 120, 220), 1.6, Qt.PenStyle.DashLine)
                    tip_pen = QPen(QColor(255, 255, 255, 240), 1.5)
                    tip_brush = QBrush(QColor(40, 190, 80, 230))
                    for i in range(n_pts):
                        pt = ent.points[i]
                        scr_pt = self.world_to_screen(plane.uv_to_world(*pt))
                        if not scr_pt:
                            continue
                        t_vec = ent.tangent_at(i)
                        signs = (1.0, -1.0) if (0 < i < n_pts - 1) else (1.0 if i == 0 else -1.0,)
                        for s in signs:
                            tip_uv = (pt[0] + s * t_vec[0], pt[1] + s * t_vec[1])
                            scr_tip = self.world_to_screen(plane.uv_to_world(*tip_uv))
                            if scr_tip:
                                painter.setPen(handle_pen)
                                painter.drawLine(QPointF(*scr_pt), QPointF(*scr_tip))
                                painter.setPen(tip_pen)
                                painter.setBrush(tip_brush)
                                painter.drawEllipse(QPointF(*scr_tip), 4.5, 4.5)

                    # Draw fit points (white circles with dark border)
                    pt_pen = QPen(QColor(30, 30, 30, 240), 1.8)
                    pt_brush = QBrush(QColor(255, 255, 255, 255))
                    painter.setPen(pt_pen)
                    painter.setBrush(pt_brush)
                    for pt in ent.points:
                        scr_pt = self.world_to_screen(plane.uv_to_world(*pt))
                        if scr_pt:
                            painter.drawEllipse(QPointF(*scr_pt), 4.0, 4.0)
                    painter.setBrush(Qt.BrushStyle.NoBrush)

        # 2c. Unconnected Endpoint Dots (free ends of lines/arcs/splines waiting to be joined)
        if self.doc.active_sketch:
            sk = self.doc.active_sketch
            plane = sk.plane
            free_ends = self._free_endpoints()
            if free_ends:
                dot_pen = QPen(QColor(255, 255, 255, 240), 1.6)
                dot_brush = QBrush(QColor(240, 140, 30, 240))  # Vivid orange dot
                painter.setPen(dot_pen)
                painter.setBrush(dot_brush)
                for _ent, _name, pt in free_ends:
                    scr_pt = self.world_to_screen(plane.uv_to_world(*pt))
                    if scr_pt:
                        painter.drawEllipse(QPointF(*scr_pt), 4.5, 4.5)
                painter.setBrush(Qt.BrushStyle.NoBrush)

        self.draw_constraint_badges(painter)
        self.draw_dim_picks(painter)

        # 3. Snapping Indicators & Guide Lines
        if self.doc.active_sketch and self.active_snap and self.active_snap.snap_type != "NONE":
            plane = self.doc.active_sketch.plane
            snap = self.active_snap

            # Orthogonal guide line
            if snap.guide_line is not None:
                g1, g2 = snap.guide_line
                scr1 = self.world_to_screen(plane.uv_to_world(g1[0], g1[1]))
                scr2 = self.world_to_screen(plane.uv_to_world(g2[0], g2[1]))
                if scr1 and scr2:
                    pen_guide = QPen(qcolor(56, 189, 248, 180), 1, Qt.PenStyle.DashLine)
                    painter.setPen(pen_guide)
                    painter.drawLine(QPointF(scr1[0], scr1[1]), QPointF(scr2[0], scr2[1]))

            # Snap Target Marker
            target_uv = snap.target_uv or snap.uv
            tgt_world = plane.uv_to_world(target_uv[0], target_uv[1])
            scr_tgt = self.world_to_screen(tgt_world)
            if scr_tgt:
                sx, sy = scr_tgt
                if snap.snap_type == "ORIGIN":
                    painter.setPen(QPen(qcolor(226, 109, 40), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(sx, sy), 8, 8)
                    painter.drawEllipse(QPointF(sx, sy), 3, 3)
                elif snap.snap_type == "ENDPOINT":
                    painter.setPen(QPen(qcolor(56, 189, 248), 2))
                    painter.setBrush(QBrush(qcolor(56, 189, 248, 60)))
                    painter.drawRect(QRectF(sx - 5, sy - 5, 10, 10))
                elif snap.snap_type == "EDGE":
                    painter.setPen(QPen(qcolor(250, 204, 21), 2))
                    painter.setBrush(QBrush(qcolor(250, 204, 21, 70)))
                    painter.drawPolygon(QPolygonF([QPointF(sx, sy - 6), QPointF(sx + 6, sy),
                                                   QPointF(sx, sy + 6), QPointF(sx - 6, sy)]))
                elif snap.snap_type == "MIDPOINT":
                    painter.setPen(QPen(qcolor(74, 222, 128), 2))
                    painter.setBrush(QBrush(qcolor(74, 222, 128, 60)))
                    tri = QPolygonF([QPointF(sx, sy - 6), QPointF(sx - 6, sy + 5), QPointF(sx + 6, sy + 5)])
                    painter.drawPolygon(tri)
                elif snap.snap_type == "TANGENT":     # the arc sticks smoothly to the line or arc it meets
                    painter.setPen(QPen(qcolor(74, 222, 128), 2))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QPointF(sx, sy), 6, 6)
                    painter.drawLine(QPointF(sx - 10, sy - 6), QPointF(sx + 10, sy - 6))
                elif snap.snap_type in ("ORTHO_H", "ORTHO_V", "ANGLE"):
                    painter.setPen(QPen(qcolor(56, 189, 248), 1.5))
                    painter.setBrush(QBrush(qcolor(24, 28, 34, 220)))
                    badge_rect = QRectF(sx + 10, sy - 20, 30 if snap.label else 20, 16)
                    painter.drawRoundedRect(badge_rect, 3, 3)
                    painter.setPen(QPen(qcolor(224, 227, 231)))
                    font_ortho = QFont(theme.font_family(), 8, QFont.Weight.Bold)
                    painter.setFont(font_ortho)
                    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter,
                                     snap.label or ("H" if snap.snap_type == "ORTHO_H" else "V"))

        # 4. Floating Real-time Dimension Badge (the Tab entry boxes already show these values for
        #    line/rect/circle/move, so showing both only made them cover each other)
        entry_boxes_shown = self.dyn.active and dyn_input.supports(self.sketch_tool) and self._dyn_can_start()
        if (self.doc.active_sketch and self.sketch_start_uv and self.sketch_current_uv
                and self.sketch_palette.chk_show_dims.isChecked() and not entry_boxes_shown):
            u1, v1 = self.sketch_start_uv
            u2, v2 = self.sketch_current_uv
            dim_text = ""

            if self.sketch_tool == "LINE":
                length = math.hypot(u2 - u1, v2 - v1)
                angle = math.degrees(math.atan2(v2 - v1, u2 - u1))
                if angle < 0:
                    angle += 360.0
                dim_text = f"L: {length:.1f} mm  |  ∠ {angle:.1f}°"
            elif self.sketch_tool in ("RECT", "ROUNDED_RECT"):
                w_rect = abs(u2 - u1)
                h_rect = abs(v2 - v1)
                dim_text = f"W: {w_rect:.1f} mm  ×  H: {h_rect:.1f} mm"
            elif self.sketch_tool in ("CENTER_RECT", "CENTER_ROUNDED_RECT"):
                w_rect = 2.0 * abs(u2 - u1)
                h_rect = 2.0 * abs(v2 - v1)
                dim_text = f"W: {w_rect:.1f} mm  ×  H: {h_rect:.1f} mm"
            elif self.sketch_tool == "POLYGON":
                n_p = self._polygon_sides()
                r_p = math.hypot(u2 - u1, v2 - v1)
                dim_text = f"{n_p} sides  ·  side: {2 * r_p * math.sin(math.pi / n_p):.2f} mm  (R: {r_p:.1f} mm)"
            elif self.sketch_tool == "CIRCLE":
                r_circ = math.hypot(u2 - u1, v2 - v1)
                dim_text = f"Ø: {2*r_circ:.1f} mm  (R: {r_circ:.1f} mm)"
            elif self.sketch_tool == "ARC":
                if self.sketch_second_uv is None:
                    chord = math.hypot(u2 - u1, v2 - v1)
                    dim_text = f"Chord: {chord:.1f} mm  (Pick End Point)"
                else:
                    p1 = self.sketch_start_uv
                    p2 = self.sketch_second_uv
                    p_mid = (u2, v2)
                    arc_temp = SketchArc("temp", p1, p_mid, p2)
                    params = arc_temp.get_circle_params()
                    if params:
                        dim_text = f"R: {params[1]:.1f} mm  (Pick Arc Point)"
                    else:
                        dim_text = "Pick Arc Point"
            elif self.sketch_tool == "SPLINE":
                dim_text = f"{len(getattr(self, '_spline_points', []))} points  ·  Enter or double-click to finish"
            elif self.sketch_tool == "SLOT":
                if self.sketch_second_uv is None:
                    length = math.hypot(u2 - u1, v2 - v1)
                    dim_text = f"L: {length:.1f} mm  (Pick Center 2)"
                else:
                    c1 = self.sketch_start_uv
                    c2 = self.sketch_second_uv
                    d = self._point_to_segment_dist((u2, v2), c1, c2)
                    r_slot = max(2.0, d)
                    dim_text = f"Ø: {2*r_slot:.1f} mm  |  R: {r_slot:.1f} mm"

            if dim_text:
                plane = self.doc.active_sketch.plane
                w_cur = plane.uv_to_world(u2, v2)
                scr_cur = self.world_to_screen(w_cur)
                if scr_cur:
                    bx = scr_cur[0] + 16
                    by = scr_cur[1] - 32
                    font_dim = QFont(theme.font_family(), 9, QFont.Weight.Bold)
                    painter.setFont(font_dim)
                    fm = painter.fontMetrics()
                    badge_w = fm.horizontalAdvance(dim_text) + 18
                    badge_h = 24
                    b_rect = QRectF(bx, by, badge_w, badge_h)

                    painter.setPen(QPen(qcolor(226, 109, 40), 1.2))
                    painter.setBrush(QBrush(qcolor(22, 25, 30, 235)))
                    painter.drawRoundedRect(b_rect, 4, 4)

                    painter.setPen(QPen(qcolor(245, 247, 250)))
                    painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

        # 4b. Parametric Dimension Annotations & Interactive Badges
        self.draw_dimensions(painter)
        self.draw_sketch_pattern_dimensions(painter)

        self.draw_dyn_fields(painter)  # on top of everything else
        self.draw_smart_circle(painter)
        self._draw_rotation_pivot(painter)

        # (no sketch-mode banner: it covered the drawing; the sketch name and its solve status are in the status bar)

        if self._rubber is not None:
            a, b = self._rubber["p0"], self._rubber["p1"]
            crossing = b.x() < a.x()
            col = QColor(90, 200, 120) if crossing else QColor(80, 150, 255)
            painter.setPen(QPen(col, 1.5, Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine))
            fill = QColor(col); fill.setAlpha(40)
            painter.setBrush(fill)
            painter.drawRect(QRectF(min(a.x(), b.x()), min(a.y(), b.y()), abs(b.x() - a.x()), abs(b.y() - a.y())))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.doc.active_sketch and self.sketch_tool in ("MIRROR", "TRIM", "OFFSET", "FILLET"):
            hint = {"TRIM": "TRIM: click the piece to remove",
                    "FILLET": f"FILLET: click a corner, or Shift+click / drag a box for several ({len(self.fillet_picked)} picked), then Enter",
                    "OFFSET": f"OFFSET: click curves ({len(self.selected_entities)} picked), then Enter",
                    "MIRROR": ("MIRROR 1/2: click shapes, then Enter" if self._mirror_phase == "pick"
                               else "MIRROR 2/2: click the mirror line / an axis")}[self.sketch_tool]
            self.tool_panel.set_hint(hint.split(": ", 1)[-1])   # in the tool panel, not over the drawing (#76)

        # 6. Bottom HUD Navigation Bar
        hud_w = 260
        hud_h = 36
        hud_rect = QRectF((w - hud_w) / 2.0, h - 50, hud_w, hud_h)
        painter.setPen(QPen(qcolor(60, 65, 75), 1))
        painter.setBrush(QBrush(qcolor(26, 28, 32, 220)))
        painter.drawRoundedRect(hud_rect, 6, 6)

        # HUD Icons / Labels
        font_hud = QFont()
        font_hud.setPointSize(10)
        font_hud.setBold(True)
        painter.setFont(font_hud)

        labels = [("🔄 Orbit", 0), ("✋ Pan", 65), ("🔲 Fit", 130), ("📐 Grid", 195)]
        studio = theme_icons._studio_icons()
        for (text, x_off), name in zip(labels, ("orbit", "pan", "fit", "grid")):
            btn_rect = QRectF(hud_rect.x() + x_off + 4, hud_rect.y() + 4, 60, 28)
            painter.setPen(QPen(qcolor(200, 205, 215)))
            if studio:      # Studio line icon + the word, instead of an emoji in the text
                theme_icons.tool_icon(name, 14).paint(painter, int(btn_rect.x()) + 2, int(btn_rect.y()) + 7, 14, 14)
                painter.drawText(btn_rect.adjusted(18, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text.split(" ", 1)[1])
            else:
                painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, text)

        # 7. Viewport Details (lower left)
        painter.setPen(QPen(qcolor(140, 145, 155)))
        font_small = QFont()
        font_small.setPointSize(9)
        painter.setFont(font_small)
        cam_info = f"Azimuth: {self.azimuth:.1f}° | Elevation: {self.elevation:.1f}° | Zoom: {self.distance:.0f} mm"
        painter.drawText(16, h - 16, cam_info)
        self._draw_status_text(painter, w, h)

    def _draw_status_text(self, painter: QPainter, w: int, h: int):
        """The status message above the camera line (lower left) and the sketch status / units at the lower right."""
        fm = painter.fontMetrics()
        message = self.hud_status.text()
        if self.hud_busy.isVisible():
            message = f"Working…  {message}"
        if message:
            painter.setPen(QPen(qcolor(175, 180, 190)))
            shown = fm.elidedText(message, Qt.TextElideMode.ElideRight, int(w * 0.62))
            painter.drawText(16, h - 16 - fm.height() - 2, shown)
        right = [t for t in (self.hud_sketch.text(), "Units: mm") if t]
        if right:
            painter.setPen(QPen(qcolor(140, 145, 155)))
            text = fm.elidedText("   |   ".join(right), Qt.TextElideMode.ElideLeft, int(w * 0.34))
            painter.drawText(w - 16 - fm.horizontalAdvance(text), h - 16, text)





    # ---- Dimension tool ----------------------------------------------------------

















    DIM_POINT_LABELS = {"HORIZ_DIST": "Horizontal distance", "VERT_DIST": "Vertical distance", "DISTANCE": "Distance"}






    def _point_to_segment_dist(self, pt: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        px, py = pt
        x1, y1 = p1
        x2, y2 = p2
        dx = x2 - x1
        dy = y2 - y1
        l2 = dx*dx + dy*dy
        if l2 == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / l2))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    # ------------------ Mouse & Navigation ------------------

    def _orbit_viewcube(self, dx, dy):
        self.azimuth = (self.azimuth - dx * 0.5) % 360.0
        self.elevation = max(-89.9, min(89.9, self.elevation + dy * 0.5))
        self.update()

    def set_view(self, view_name: str):
        """Snaps camera to preset orthographic or isometric views."""
        v = view_name.upper()
        if v == "HOME":
            self.azimuth = 45.0
            self.elevation = 30.0
        elif v == "TOP":
            self.azimuth = 0.0
            self.elevation = 89.9
        elif v == "BOTTOM":
            self.azimuth = 0.0
            self.elevation = -89.9
        elif v == "FRONT":
            self.azimuth = 0.0
            self.elevation = 0.0
        elif v == "BACK":
            self.azimuth = 180.0
            self.elevation = 0.0
        elif v == "RIGHT":
            self.azimuth = 90.0
            self.elevation = 0.0
        elif v == "LEFT":
            self.azimuth = -90.0
            self.elevation = 0.0
        elif "_" in v:
            directions = {"TOP": (0, 0, 1), "BOTTOM": (0, 0, -1),
                          "FRONT": (0, -1, 0), "BACK": (0, 1, 0),
                          "RIGHT": (1, 0, 0), "LEFT": (-1, 0, 0)}
            parts = v.split("_")
            if all(part in directions for part in parts):
                x, y, z = np.sum([directions[part] for part in parts], axis=0)
                self.azimuth = math.degrees(math.atan2(x, -y))
                self.elevation = math.degrees(math.atan2(z, math.hypot(x, y)))
        self.update()

    def zoom_to_points(self, pts) -> None:
        """Frames the given world points (Find in Window)."""
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        if len(pts) == 0:
            return
        b_min, b_max = pts.min(axis=0), pts.max(axis=0)
        self.target = ((b_min + b_max) * 0.5).astype(np.float32)
        self.distance = max(40.0, float(np.linalg.norm(b_max - b_min)) * 1.8)
        self.update()

    def frame_face(self, plane, tris, fill: float = 0.8) -> None:
        """Centres a face seen straight on (after align_to_plane) and zooms so it fills `fill` of the view's
        shorter side: sketching on a face starts with the face filling the screen."""
        pts = np.asarray(tris, dtype=float).reshape(-1, 3)
        if len(pts) == 0:
            return
        u = pts @ np.asarray(plane.u_axis, dtype=float)
        v = pts @ np.asarray(plane.v_axis, dtype=float)
        size = max(float(np.ptp(u)), float(np.ptp(v)), 1e-3)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        self.target = ((lo + hi) * 0.5).astype(np.float32)
        aspect = min(1.0, self.width() / max(1, self.height()))
        self.distance = max(5.0, min(2000.0, size / (fill * aspect * 2.0 * math.tan(math.radians(self.fovy) / 2.0))))
        self.update()

    def zoom_to_body(self, body_id: str) -> None:
        b = self.doc.bodies.get(body_id)
        if b is not None and b.render_mesh is not None and len(b.render_mesh.vertices):
            self.zoom_to_points([b.render_mesh.bounds_min, b.render_mesh.bounds_max])

    def zoom_to_sketch(self, sketch_id: str) -> None:
        sk = self.doc.sketches.get(sketch_id)
        if sk is None:
            return
        uv = []
        for e in sk.entities:
            for name in ("p1", "p2", "center", "center1", "center2", "p_mid"):
                p = getattr(e, name, None)
                if p is not None:
                    uv.append(tuple(p))
        if uv:
            pts = np.array([sk.plane.uv_to_world(u, v) for u, v in uv], dtype=float)
            placed = None if sk is self.doc.active_sketch else self.doc.sketch_placement(sketch_id)
            if placed is not None:              # where its object has been moved to since
                pts = pts @ placed[:3, :3].T + placed[:3, 3]
            self.zoom_to_points(list(pts))

    def zoom_fit(self):
        """Centers and fits camera to visible bodies or origin."""
        all_pts = []
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                all_pts.append(b.render_mesh.bounds_min)
                all_pts.append(b.render_mesh.bounds_max)

        if all_pts:
            pts = np.vstack(all_pts)
            b_min = pts.min(axis=0)
            b_max = pts.max(axis=0)
            self.target = (b_min + b_max) * 0.5
            diag = float(np.linalg.norm(b_max - b_min))
            self.distance = max(40.0, diag * 1.8)
        else:
            self.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.distance = 140.0
        self.update()

