"""Gizmo, arrow handle, and section view rendering mixin for Viewport3D."""

import math
from typing import Optional
import numpy as np
import manifold3d as m3d
from OpenGL import GL
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from omacad.ui import theme
from omacad.ui.theme import qcolor
from omacad.model.kernel import CadKernel
from omacad.ui.math3d import ray_from_screen


class GizmoMixin:
    """Mixin providing gizmos (extrude arrow, move gizmo) and section planes."""
    # ---- Section view -------------------------------------------------------------------
    def set_section(self, origin, normal, offset: float, flip: bool = False, show_plane: bool = True):
        """Cuts every body along a plane (base origin + normal * offset) and shows the cut face. View only."""
        from omacad.model.sketch import SketchPlane
        n = np.asarray(normal, dtype=float)
        n = n / np.linalg.norm(n)
        p = np.asarray(origin, dtype=float) + n * float(offset)
        plane = SketchPlane.from_face(n, p)
        self.section = {"origin": np.asarray(origin, dtype=float), "normal": n, "offset": float(offset), "flip": flip,
                        "meshes": {}, "caps": [], "mat": plane.get_transform_matrix_3x4()}
        for bid, body in self.doc.bodies.items():
            if not body.visible:
                continue
            try:
                self._cut_into_section(bid, (getattr(self, "display_solids", None) or {}).get(bid, body.manifold))
            except Exception:
                continue
        self.set_preview_plane(plane if show_plane else None)
        self.update()

    def _cut_into_section(self, bid, manifold):
        """Puts the kept part of this solid and its cut face into the shown section, in place of the body's own."""
        sec = self.section
        flip, mat = sec["flip"], np.asarray(sec["mat"], dtype=float)
        sec["meshes"][bid] = CadKernel.extract_render_mesh(self.section_trim(manifold))   # empty when all is cut away
        inv = np.linalg.inv(np.vstack([mat, [0, 0, 0, 1]]))[:3]
        polys = manifold.transform(inv).slice(1e-4 if not flip else -1e-4).to_polygons()
        index = next((i for i, c in enumerate(sec["caps"]) if c["body_id"] == bid), len(sec["caps"]))
        sec["caps"][index:index + 1] = []
        if polys:
            cs = m3d.CrossSection(polys)
            slab = m3d.Manifold.extrude(cs, 0.08).translate((0, 0, -0.04)).transform(mat)
            # each body's cut has its own tint, so touching bodies can be told apart
            sec["caps"].insert(index, {"body_id": bid, "fill": self.SECTION_FILLS[index % len(self.SECTION_FILLS)],
                                       "cap": CadKernel.extract_render_mesh(slab), "polys": cs.to_polygons(),
                                       "hatch": None})

    def section_trim(self, manifold):
        """The part of a solid a section view keeps (the solid itself when no section is shown)."""
        sec = getattr(self, "section", None)
        if sec is None or manifold is None:
            return manifold
        n = sec["normal"]
        p = sec["origin"] + n * sec["offset"]
        keep = n if sec["flip"] else -n
        return manifold.trim_by_plane(tuple(keep), float(keep @ p))

    def clear_section(self):
        self.section = None
        self.set_preview_plane(None)
        self.clear_extrude_handle()
        self.update()

    def sync_section(self):
        """Shows the document's active saved section (if any); not while one is being edited."""
        if getattr(self, "section_editing", False):
            return
        act = self.doc.active_section()
        if act is None:
            if self.section is not None:
                self.section = None
                self.update()
            return
        sec = act[1]
        self.set_section(sec["origin"], sec["normal"], sec["offset"], sec["flip"], show_plane=False)

    # the cut face of each body: a pale tint (the first is Fusion's yellow) with darker diagonal hatching, black outline
    SECTION_FILLS = ((1.0, 0.91, 0.69), (0.70, 0.87, 1.0), (0.74, 0.95, 0.72), (1.0, 0.76, 0.82),
                     (0.85, 0.78, 1.0), (1.0, 0.82, 0.62))

    def _section_hatch(self, sec, cap):
        """Hatch and outline of the cut in world coordinates, rebuilt when the zoom changes the line spacing."""
        from omacad.model.section_hatch import hatch_and_outline
        spacing = max(0.15, self.distance * 0.009)
        cached = cap.get("hatch")
        if cached is not None and 0.7 <= spacing / cached[0] <= 1.4:
            return cached[1], cached[2]
        hatch2d, outline2d = hatch_and_outline(cap["polys"] or [], spacing)
        mat = np.asarray(sec["mat"], dtype=float)

        def to_world(seg):
            if len(seg) == 0:
                return np.zeros((0, 3), dtype=np.float32)
            pts = seg.reshape(-1, 2)
            world = pts[:, 0:1] * mat[:, 0] + pts[:, 1:2] * mat[:, 1] + mat[:, 3]
            return world.astype(np.float32)

        hatch, outline = to_world(hatch2d), to_world(outline2d)
        cap["hatch"] = (spacing, hatch, outline)
        return hatch, outline

    def render_section_cap(self, mvp: np.ndarray):
        """The cut face as Fusion 360 draws it: pale yellow, diagonal hatching and a black outline."""
        sec = self.section
        if not sec or not sec["caps"] or not self.prog_flat:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        for cap in sec["caps"]:
            if len(cap["cap"].vertices) == 0:
                continue
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(1.0, 1.0)                # the fill sits a hair behind, so the lines are never swallowed by it
            GL.glUniform4f(loc_col, *cap["fill"], 1.0)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, cap["cap"].vertices)
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            try:
                hatch, outline = self._section_hatch(sec, cap)
            except Exception:
                hatch = outline = np.zeros((0, 3), dtype=np.float32)
            self.set_line_width(1.0)
            if len(hatch):
                GL.glUniform4f(loc_col, *(0.33 * c for c in cap["fill"]), 0.9)
                self.draw_buffer_arrays(GL.GL_LINES, loc_pos, hatch)
            if len(outline):
                GL.glUniform4f(loc_col, 0.0, 0.0, 0.0, 1.0)
                self.draw_buffer_arrays(GL.GL_LINES, loc_pos, outline)
        GL.glUseProgram(0)

    # ---- Extrude arrow ------------------------------------------------------------------
    def set_extrude_handle(self, origin, axis, dist: float, color=None, show_value: bool = False, value_scale: float = 1.0):
        """Draggable arrow. `color` (r, g, b) overrides the theme highlight, e.g. when that would blend into the scene.
        `show_value` writes the distance (times `value_scale`) beside the shaft, also after the mouse is released."""
        self.extrude_handle = {"origin": np.asarray(origin, dtype=float), "axis": np.asarray(axis, dtype=float), "dist": float(dist),
                               "color": color, "show_value": show_value, "value_scale": value_scale}
        self.update()

    def clear_extrude_handle(self):
        self.extrude_handle = None
        self._handle_drag = False
        self._handle_hover = False
        self.update()

    def _arrow_size(self) -> float:
        """Size of the extrude arrow's head in mm (the Arrow size setting scales it)."""
        from omacad.ui.settings import get_settings
        return self.distance * 0.04 * float(get_settings().get("arrow_size", 1.0))

    def _arrow_lift(self, dist: float) -> float:
        """The arrow is drawn a couple of mm off the surface, in the direction it points, so it never
        starts inside the material (the Arrow distance setting)."""
        from omacad.ui.settings import get_settings
        return (1.0 if dist >= 0 else -1.0) * float(get_settings().get("arrow_gap", 2.0))

    def _handle_screen(self):
        h = self.extrude_handle
        tip = h["origin"] + h["axis"] * h["dist"]
        return self.world_to_screen(h["origin"]), self.world_to_screen(tip), tip

    def _handle_geometry(self):
        """Screen-space shape of the drawn arrow: (origin, apex, head centre, head radius in px) or None."""
        h = self.extrude_handle
        if not h:
            return None
        origin, axis, dist = h["origin"], h["axis"], h["dist"]
        sign = 1.0 if dist >= 0 else -1.0
        lift = self._arrow_lift(dist)
        origin = origin + axis * lift
        tip = origin + axis * dist
        size = self._arrow_size()
        so = self.world_to_screen(origin)
        apex = self.world_to_screen(tip + axis * sign * size * 0.4)
        base = tip - axis * sign * size * 0.8
        centre = self.world_to_screen(tip - axis * sign * size * 0.2)
        if so is None or apex is None or centre is None:
            return None
        u = np.cross(axis, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(axis, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        edge = self.world_to_screen(base + u * size * 0.5)
        bs = self.world_to_screen(base)
        radius = math.hypot(edge[0] - bs[0], edge[1] - bs[1]) if edge is not None and bs is not None else 14.0
        return so, apex, centre, radius

    def _draw_handle_value(self, painter: QPainter):
        """The distance of the extrude arrow as a label beside the middle of the shaft (stays after release)."""
        h = self.extrude_handle
        g = self._handle_geometry() if h and h.get("show_value") else None
        if g is None:
            return
        so, apex, _centre, _radius = g
        dx, dy = apex[0] - so[0], apex[1] - so[1]
        n = math.hypot(dx, dy)
        nx, ny = (-dy / n, dx / n) if n > 1e-6 else (0.0, -1.0)
        if ny > 0:   # keep the label above the line rather than below
            nx, ny = -nx, -ny
        text = f"{h['dist'] * h.get('value_scale', 1.0):.2f} mm"
        font = QFont(theme.font_family(), 10, QFont.Weight.Bold)
        painter.setFont(font)
        tw = painter.fontMetrics().horizontalAdvance(text) + 16
        th = painter.fontMetrics().height() + 8
        cx = (so[0] + apex[0]) / 2 + nx * (th / 2 + 12 + abs(nx) * tw / 2)
        cy = (so[1] + apex[1]) / 2 + ny * (th / 2 + 12)
        rect = QRectF(cx - tw / 2, cy - th / 2, tw, th)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
        painter.setBrush(QColor(20, 24, 30, 225))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _handle_hit(self, x: float, y: float) -> bool:
        """Generous: anywhere on the head (plus a margin, so it is easy to catch when it sits behind or inside
        a body) or along the shaft."""
        g = self._handle_geometry()
        if g is None:
            return False
        so, apex, centre, radius = g
        if math.hypot(x - centre[0], y - centre[1]) < max(26.0, radius * 1.3 + 8.0):
            return True
        return self._point_to_segment_dist((x, y), so, apex) < 12

    def _handle_value(self, x: float, y: float):
        """Distance along the arrow's axis that is closest to the mouse ray."""
        h = self.extrude_handle
        proj, view, _ = self.get_matrices()
        r0, rd = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        r0, rd = np.asarray(r0, dtype=float), np.asarray(rd, dtype=float)
        a, w = h["axis"], h["origin"] - r0
        b, d1, e = float(a @ rd), float(a @ w), float(rd @ w)
        denom = 1.0 - b * b
        if abs(denom) < 1e-6:
            return None
        t = (b * e - d1) / denom
        t -= self._arrow_lift(h["dist"])   # the arrow is drawn lifted off the surface
        step = 0.1 if abs(t) < 10 else 0.5 if abs(t) < 50 else 1.0
        return round(t / step) * step

    def render_extrude_handle(self, mvp: np.ndarray):
        h = self.extrude_handle
        if not h or self.prog_flat is None or self.prog_thick is None:
            return
        origin, axis, dist = h["origin"], h["axis"], h["dist"]
        sign = 1.0 if dist >= 0 else -1.0
        origin = origin + axis * self._arrow_lift(dist)
        tip = origin + axis * dist
        size = self._arrow_size()
        lit = self._handle_hover or self._handle_drag
        from omacad.ui.settings import get_settings
        custom_arrow = get_settings().arrow_color_rgb01()
        if h.get("color"):
            col = (*(min(1.0, c + (0.2 if lit else 0.0)) for c in h["color"]), 1.0)
        elif custom_arrow is not None:
            col = (*(min(1.0, c + (0.2 if lit else 0.0)) for c in custom_arrow), 1.0)
        else:
            col = (*theme.palette().highlight01(0.15 if lit else 0.0), 1.0)
        GL.glDisable(GL.GL_DEPTH_TEST)
        shaft_end = tip - axis * sign * size * 0.8
        self.draw_thick_lines(mvp, [*origin, *shaft_end], col, 4.0, halo=True)
        # arrow head: a cone around the axis
        u = np.cross(axis, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(axis, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        v_ = np.cross(axis, u)
        apex, base = tip + axis * sign * size * 0.4, tip - axis * sign * size * 0.8
        ring = [base + size * 0.5 * (math.cos(t) * u + math.sin(t) * v_) for t in np.linspace(0, 2 * math.pi, 17)]
        tris = []
        for i in range(16):
            tris += [*apex, *ring[i], *ring[i + 1], *base, *ring[i + 1], *ring[i]]
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform4f(loc_col, *col)
        self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, np.array(tris, dtype=np.float32))
        GL.glUseProgram(0)
        # a white ring round the head so the grab point stands out also when the arrow sits behind or inside a body
        hub = tip - axis * sign * size * 0.2
        ring_pts = [hub + size * 0.75 * (math.cos(t) * u + math.sin(t) * v_) for t in np.linspace(0, 2 * math.pi, 33)]
        ring = []
        for i in range(32):
            ring += [*ring_pts[i], *ring_pts[i + 1]]
        self.draw_thick_lines(mvp, ring, (1.0, 1.0, 1.0, 0.9 if lit else 0.55), 2.0)
        GL.glEnable(GL.GL_DEPTH_TEST)

    # ---- 3D Translation & Rotation Gizmo (Move / Rotate Body) --------------------
    def set_move_gizmo(self, origin, length=None):
        """Sets the 3D translation & rotation gizmo at the given body/pivot origin."""
        if length is None:
            length = max(14.0, min(45.0, self.distance * 0.11))
        self.move_gizmo = {
            "origin": np.asarray(origin, dtype=float),
            "length": float(length),
            "hover_axis": None,
            "active_axis": "X",
            "dragging": False,
            "start_proj": 0.0,
            "start_mouse_screen": (0.0, 0.0),
        }
        self.update()

    def clear_move_gizmo(self):
        self.move_gizmo = None
        self.update()

    def _gizmo_axis_screen(self, axis_name: str):
        if not self.move_gizmo:
            return None, None
        g = self.move_gizmo
        orig = g["origin"]
        dirs = {
            "X": np.array([1.0, 0.0, 0.0]),
            "Y": np.array([0.0, 1.0, 0.0]),
            "Z": np.array([0.0, 0.0, 1.0])
        }
        tip = orig + dirs[axis_name] * g["length"]
        so = self.world_to_screen(orig)
        st = self.world_to_screen(tip)
        return so, st

    def _gizmo_ring_screen_points(self, rot_axis: str, n_samples: int = 36):
        """Returns sampled 2D screen points along the circular rotation ring for rot_axis (RX, RY, RZ)."""
        if not self.move_gizmo:
            return []
        g = self.move_gizmo
        orig = g["origin"]
        ring_r = g["length"] * 0.72
        basis = {
            "RX": (np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
            "RY": (np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0])),
            "RZ": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
        }
        u, v_ = basis[rot_axis]
        pts = []
        for a in np.linspace(0, 2 * math.pi, n_samples, endpoint=False):
            w_pt = orig + ring_r * (math.cos(a) * u + math.sin(a) * v_)
            s_pt = self.world_to_screen(w_pt)
            if s_pt is not None:
                pts.append(s_pt)
        return pts

    def _gizmo_hit(self, x: float, y: float) -> Optional[str]:
        if not self.move_gizmo:
            return None
        best_ax, best_dist = None, 18.0

        # 1. Linear translation axes (X, Y, Z)
        for ax in ("X", "Y", "Z"):
            so, st = self._gizmo_axis_screen(ax)
            if so is None or st is None:
                continue
            d_tip = math.hypot(x - st[0], y - st[1])
            if d_tip < best_dist:
                best_dist = d_tip
                best_ax = ax
            d_shaft = self._point_to_segment_dist((x, y), so, st)
            if d_shaft < 9.0 and d_shaft < best_dist:
                best_dist = d_shaft
                best_ax = ax

        # 2. Rotation rings (RX, RY, RZ)
        for rot_ax in ("RX", "RY", "RZ"):
            s_pts = self._gizmo_ring_screen_points(rot_ax, n_samples=36)
            if len(s_pts) < 4:
                continue
            for i in range(len(s_pts)):
                p1 = s_pts[i]
                p2 = s_pts[(i + 1) % len(s_pts)]
                d_seg = self._point_to_segment_dist((x, y), p1, p2)
                if d_seg < 10.0 and d_seg < best_dist:
                    best_dist = d_seg
                    best_ax = rot_ax

        return best_ax

    def _gizmo_project_mouse(self, x: float, y: float, axis_name: str) -> float:
        if not self.move_gizmo:
            return 0.0
        g = self.move_gizmo
        proj, view, _ = self.get_matrices()
        r0, rd = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        r0, rd = np.asarray(r0, dtype=float), np.asarray(rd, dtype=float)

        if axis_name in ("RX", "RY", "RZ"):
            # Angular rotation projection around normal axis plane
            norm_map = {
                "RX": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
                "RY": (np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0])),
                "RZ": (np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
            }
            n, u, v_ = norm_map[axis_name]
            orig = g["origin"]
            denom = float(rd @ n)
            if abs(denom) > 1e-6:
                t = float((orig - r0) @ n) / denom
                if t > 0:
                    hit = r0 + rd * t - orig
                    ang = math.degrees(math.atan2(float(hit @ v_), float(hit @ u)))
                    return ang

            # Fallback to screen-space angle from gizmo center
            so = self.world_to_screen(orig)
            if so is not None:
                return math.degrees(math.atan2(y - so[1], x - so[0]))
            return 0.0

        # Linear axis projection
        dirs = {
            "X": np.array([1.0, 0.0, 0.0]),
            "Y": np.array([0.0, 1.0, 0.0]),
            "Z": np.array([0.0, 0.0, 1.0])
        }
        a = dirs.get(axis_name, np.array([1.0, 0.0, 0.0]))
        w = g["origin"] - r0
        b, d1, e = float(a @ rd), float(a @ w), float(rd @ w)
        denom = 1.0 - b * b
        if abs(denom) < 1e-6:
            return 0.0
        t = (b * e - d1) / denom
        step = 0.1 if abs(t) < 10 else 0.5 if abs(t) < 50 else 1.0
        return round(t / step) * step

    GIZMO_SNAP_DEG = 15.0        # ticks and snapping step on the rotation rings
    GIZMO_SNAP_RADIUS = 1.12     # dragging beyond this x the ring radius snaps; inside it turns freely

    @staticmethod
    def _gizmo_color(base_col, lit: bool, boost: float):
        """Gizmo colours are pale and translucent until the mouse is on them."""
        if lit:
            return (*(min(1.0, c + boost) for c in base_col), 1.0)
        return (*(0.55 * c + 0.45 * 0.7 for c in base_col), 0.55)

    def gizmo_snapped_delta(self, x: float, y: float, axis_name: str, delta: float) -> float:
        """Rotation delta, rounded to the tick step when the mouse is outside the ring (free inside it)."""
        if axis_name not in ("RX", "RY", "RZ") or not self.move_gizmo:
            return delta
        g = self.move_gizmo
        n = {"RX": (1, 0, 0), "RY": (0, 1, 0), "RZ": (0, 0, 1)}[axis_name]
        proj, view, _ = self.get_matrices()
        r0, rd = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        r0, rd, n = np.asarray(r0, dtype=float), np.asarray(rd, dtype=float), np.asarray(n, dtype=float)
        denom = float(rd @ n)
        if abs(denom) < 1e-6:
            return delta
        t = float((g["origin"] - r0) @ n) / denom
        if t <= 0 or np.linalg.norm(r0 + rd * t - g["origin"]) < g["length"] * 0.72 * self.GIZMO_SNAP_RADIUS:
            return delta
        return round(delta / self.GIZMO_SNAP_DEG) * self.GIZMO_SNAP_DEG

    def render_move_gizmo(self, mvp: np.ndarray):
        g = self.move_gizmo
        if not g or self.prog_flat is None or self.prog_thick is None:
            return
        origin = g["origin"]
        length = g["length"]
        size = self.distance * 0.024
        dirs = {
            "X": (np.array([1.0, 0.0, 0.0]), (0.95, 0.25, 0.25)),
            "Y": (np.array([0.0, 1.0, 0.0]), (0.25, 0.85, 0.35)),
            "Z": (np.array([0.0, 0.0, 1.0]), (0.25, 0.55, 0.95)),
        }
        GL.glDisable(GL.GL_DEPTH_TEST)

        # 1. Linear Translation Arrows (X, Y, Z)
        for ax, (axis_vec, base_col) in dirs.items():
            is_hover = (g.get("hover_axis") == ax)
            is_active = (g.get("active_axis") == ax and g.get("dragging"))
            lit = is_hover or is_active
            col = self._gizmo_color(base_col, lit, 0.3)
            tip = origin + axis_vec * length
            shaft_end = tip - axis_vec * size * 0.8
            self.draw_thick_lines(mvp, [*origin, *shaft_end], col, 4.0 if lit else 2.5, halo=lit)

            # 3D Arrowhead cone
            u = np.cross(axis_vec, [1.0, 0.0, 0.0])
            if np.linalg.norm(u) < 1e-6:
                u = np.cross(axis_vec, [0.0, 1.0, 0.0])
            u = u / np.linalg.norm(u)
            v_ = np.cross(axis_vec, u)
            apex = tip + axis_vec * size * 0.4
            base = tip - axis_vec * size * 0.8
            ring = [base + size * 0.5 * (math.cos(t) * u + math.sin(t) * v_) for t in np.linspace(0, 2 * math.pi, 17)]
            tris = []
            for i in range(16):
                tris += [*apex, *ring[i], *ring[i + 1], *base, *ring[i + 1], *ring[i]]
            GL.glUseProgram(self.prog_flat)
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.prog_flat, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
            GL.glUniform4f(GL.glGetUniformLocation(self.prog_flat, "u_color"), *col)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, GL.glGetAttribLocation(self.prog_flat, "in_pos"), np.array(tris, dtype=np.float32))

        # 2. Circular Rotation Rings (RX, RY, RZ) - Fusion 360 Style
        ring_r = length * 0.72
        rot_configs = {
            "RX": ((np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])), (0.95, 0.25, 0.25)),
            "RY": ((np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0])), (0.25, 0.85, 0.35)),
            "RZ": ((np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])), (0.25, 0.55, 0.95)),
        }
        for rot_ax, ((u, v_), base_col) in rot_configs.items():
            is_hover = (g.get("hover_axis") == rot_ax)
            is_active = (g.get("active_axis") == rot_ax and g.get("dragging"))
            lit = is_hover or is_active
            col = self._gizmo_color(base_col, lit, 0.35)
            angles = np.linspace(0, 2 * math.pi, 49)
            ring_pts = [origin + ring_r * (math.cos(a) * u + math.sin(a) * v_) for a in angles]
            ring_segs = []
            for p0, p1 in zip(ring_pts[:-1], ring_pts[1:]):
                ring_segs.extend([*p0, *p1])
            self.draw_thick_lines(mvp, ring_segs, col, 3.5 if lit else 2.0, halo=lit)

            if lit:   # degree ticks outside the ring; dragging out there snaps to them
                ref = math.radians(g["start_proj"]) if g.get("dragging") else 0.0
                tick_pts = []
                for k in range(int(360 / self.GIZMO_SNAP_DEG)):
                    deg = k * self.GIZMO_SNAP_DEG
                    a = ref + math.radians(deg)
                    r1 = ring_r * (1.14 if deg % 90 == 0 else 1.10 if deg % 45 == 0 else 1.05)
                    c, sn = math.cos(a), math.sin(a)
                    tick_pts.extend([*(origin + ring_r * 1.02 * (c * u + sn * v_)), *(origin + r1 * (c * u + sn * v_))])
                self.draw_thick_lines(mvp, tick_pts, col, 2.0, halo=False)

        GL.glUseProgram(0)
        GL.glEnable(GL.GL_DEPTH_TEST)

