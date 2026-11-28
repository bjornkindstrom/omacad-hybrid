"""OpenGL rendering methods mixin for Viewport3D."""

import ctypes
import math
from typing import Optional, List, Dict
import numpy as np
import manifold3d as m3d
from PySide6.QtCore import Qt, QTimer
from OpenGL import GL
from omacad.ui import theme
from omacad.ui.viewport.sketch_rotate_mixin import INFO as ROTATE_INFO
from omacad.model.timeline import profile_cross_section
from omacad.model.sketch import Sketch, SketchArc, SketchSlot, SketchSpline
from omacad.model.sketch_solver import entity_defined



def dash_lines(flat_segments, project, dash_px: float = 9.0, gap_px: float = 6.0):
    """Cuts consecutive segments [x1,y1,z1,x2,y2,z2,...] into dashes of a constant screen size.
    `project` maps a world point to screen pixels (or None). The dash phase carries on across
    segments, so a circle or arc made of many short pieces dashes evenly."""
    segs = np.asarray(flat_segments, dtype=float).reshape(-1, 2, 3)
    out = []
    period = dash_px + gap_px
    pos = 0.0                           # distance into the current dash+gap period (px)
    for a, b in segs:
        sa, sb = project(a), project(b)
        length = float(np.hypot(sb[0] - sa[0], sb[1] - sa[1])) if sa and sb else 0.0
        if length < 1e-6:
            out.extend([*a, *b])        # off screen or degenerate: keep it solid
            continue
        d = 0.0
        while d < length:
            boundary = dash_px if pos < dash_px else period
            remaining = boundary - pos
            step = min(length - d, remaining)
            end = d + step
            if pos < dash_px:
                out.extend([*(a + (b - a) * (d / length)), *(a + (b - a) * (end / length))])
            # Snap to the boundary: float cancellation must never stall the loop.
            pos = (0.0 if boundary == period else dash_px) if step == remaining else pos + step
            d = end
    return out

class RenderGLMixin:
    """Mixin providing 3D OpenGL drawing methods for Viewport3D."""
    def render_profile_fills(self, mvp: np.ndarray):
        """Translucent fills for the hovered and selected sketch profiles; in an open sketch, a faint tint on every
        closed profile so it shows what an extrude could take (sketch plan step 7)."""
        if not self.prog_flat:
            return
        if self.doc.active_sketch:
            self._render_live_profile_fills(mvp)
            return
        entries = []
        if self.hover_profile and self.hover_profile != self.doc.selected_profile:
            entries.append((self.hover_profile, (*theme.palette().highlight01(0.35), 0.30)))
        selected_col = (*theme.palette().highlight01(0.1), 0.50)
        selection_tris = self._selection_fill() if self.doc.selected_profile else None
        if self.doc.selected_profile and selection_tris is None:
            entries.append((self.doc.selected_profile, selected_col))
        if selection_tris is None:
            for key in self.doc.selected_extra:
                entries.append((key, selected_col))
        if not entries and selection_tris is None:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(-1.0, -1.0)
        if selection_tris is not None:
            GL.glUniform4f(loc_col, *selected_col)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, selection_tris)
        for key, col in entries:
            tris = self._profile_fill(key)
            if tris is not None:
                GL.glUniform4f(loc_col, *col)
                self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    LIVE_FILL_ALPHA = 0.08            # closed profiles of the open sketch: a tint, the lines stay what you look at
    LIVE_FILL_ALPHA_DARK = 0.16       # the same tint needs about twice the cover to show on a dark canvas

    def live_profile_fill(self) -> Optional[np.ndarray]:
        """World triangles of every closed profile of the active sketch, rebuilt only when the profiles change (the
        solver hands out new profile objects whenever the geometry moves)."""
        sketch = self.doc.active_sketch
        if sketch is None or not sketch.profiles:
            return None
        profiles = list(sketch.profiles)
        cached = getattr(self, "_live_fill", None)
        if cached is not None and cached[0] is sketch and len(cached[1]) == len(profiles) \
                and all(a is b for a, b in zip(cached[1], profiles)):
            return cached[2]
        parts = []
        for prof in profiles:
            try:
                solid = m3d.Manifold.extrude(profile_cross_section(prof), height=0.02)
            except Exception:
                continue
            mesh = solid.transform(sketch.plane.get_transform_matrix_3x4()).to_mesh()
            if len(mesh.tri_verts):
                parts.append(mesh.vert_properties[:, :3][mesh.tri_verts].reshape(-1, 3))
        tris = np.concatenate(parts).astype(np.float32) if parts else None
        self._live_fill = (sketch, profiles, tris)      # holding the profiles keeps their ids from being reused
        return tris

    def live_fill_alpha(self) -> float:
        r, g, b = theme.palette().canvas_rgb01()
        return self.LIVE_FILL_ALPHA if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else self.LIVE_FILL_ALPHA_DARK

    def _render_live_profile_fills(self, mvp: np.ndarray):
        tris = self.live_profile_fill()
        if tris is None:
            return
        GL.glUseProgram(self.prog_flat)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.prog_flat, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform4f(GL.glGetUniformLocation(self.prog_flat, "u_color"),
                       *theme.palette().highlight01(0.45), self.live_fill_alpha())
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(-1.0, -1.0)
        self.draw_buffer_arrays(GL.GL_TRIANGLES, GL.glGetAttribLocation(self.prog_flat, "in_pos"), tris)
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def render_preview(self, mvp: np.ndarray):
        """Translucent preview of a pending feature (e.g. extrude)."""
        if getattr(self, "preview_extra", None) is not None:
            mesh2, op2 = self.preview_extra
            self._render_preview_mesh(mvp, mesh2, op2)
        self._render_preview_mesh(mvp, self.preview_mesh, self.preview_op)

    def _render_preview_mesh(self, mvp: np.ndarray, mesh, op: str):
        if mesh is None or len(mesh.vertices) == 0 or not self.prog_flat:
            return
        colors = {
            "cut": (0.92, 0.25, 0.20), "intersect": (0.95, 0.80, 0.20),
            "join": (0.30, 0.78, 0.50), "new_body": (0.30, 0.65, 0.95),
        }
        r, g, b = colors.get(op, colors["new_body"])
        inside = op in ("cut", "intersect")   # these sit inside the body: show them through its surface
        # a solid that is added is lit like a body; a cut, seen through the body, stays one clear flat colour
        lit = (not inside and self.prog_solid is not None
               and len(getattr(mesh, "normals", ())) == len(mesh.vertices))
        prog = self.prog_solid if lit else self.prog_flat
        GL.glUseProgram(prog)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(prog, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        loc_col = GL.glGetUniformLocation(prog, "u_color")
        loc_pos = GL.glGetAttribLocation(prog, "in_pos")
        GL.glDepthMask(GL.GL_FALSE)
        if inside:
            GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glUniform4f(loc_col, r, g, b, 0.50 if inside else 0.42)
        if lit:      # shaded like a body (tinted, see-through), so the preview reads as a solid, not a flat blob
            az, el = math.radians(getattr(self, "azimuth", 0.0)), math.radians(getattr(self, "elevation", 0.0))
            GL.glUniform3f(GL.glGetUniformLocation(prog, "u_eye_dir"),
                           math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el))
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, mesh.vertices,
                                    GL.glGetAttribLocation(prog, "in_normal"), mesh.normals)
        else:
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, mesh.vertices)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)
        if len(mesh.sharp_lines) > 0:
            self.draw_thick_lines(mvp, mesh.sharp_lines, (r * 0.8, g * 0.8, b * 0.8, 1.0), 2.0, halo=False)
        if inside:
            GL.glEnable(GL.GL_DEPTH_TEST)


















    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sketch_palette'):
            self.sketch_palette.place_default(self.size())
        if hasattr(self, '_on_viewport_resized') and callable(self._on_viewport_resized):
            self._on_viewport_resized(self.size())

    # ---- Sketch plane picking ---------------------------------------------

    def render_canvases(self, mvp: np.ndarray):
        """Renders calibrated reference images on their respective 3D planes."""
        canvases = getattr(self.doc, "canvases", {})
        if not canvases or not self.prog_tex:
            return

        for cid, c in canvases.items():
            if not c.get("visible", True) or not c.get("image_data"):
                continue

            from omacad.model.canvas import canvas_plane
            plane = canvas_plane(self.doc, c)
            if plane is None:
                continue

            tex_id = self._get_canvas_texture(cid, c["image_data"])
            if not tex_id:
                continue

            w_mm = float(c.get("width_mm", 100.0))
            h_mm = float(c.get("height_mm", 100.0))
            ox, oy = c.get("origin_uv", [-w_mm / 2.0, -h_mm / 2.0])
            rot_deg = float(c.get("rotation_deg", 0.0))
            opacity = float(c.get("opacity", 0.5))

            # 4 Corners in plane UV coordinates with rotation
            cx, cy = ox + w_mm / 2.0, oy + h_mm / 2.0
            rad = math.radians(rot_deg)
            cos_r, sin_r = math.cos(rad), math.sin(rad)

            def rot_pt(u, v):
                du, dv = u - cx, v - cy
                return cx + du * cos_r - dv * sin_r, cy + du * sin_r + dv * cos_r

            uv_corners = [
                rot_pt(ox, oy),
                rot_pt(ox + w_mm, oy),
                rot_pt(ox + w_mm, oy + h_mm),
                rot_pt(ox, oy + h_mm),
            ]
            # Lift face images slightly to avoid depth fighting with the body's triangles.
            lift = plane.normal * (0.01 if c.get("face_plane") else 0.0)
            w_pts = [plane.uv_to_world(u, v) + lift for u, v in uv_corners]

            quad_pos = np.array([
                w_pts[0], w_pts[1], w_pts[2],
                w_pts[0], w_pts[2], w_pts[3]
            ], dtype=np.float32)

            quad_uv = np.array([
                [0.0, 1.0], [1.0, 1.0], [1.0, 0.0],
                [0.0, 1.0], [1.0, 0.0], [0.0, 0.0]
            ], dtype=np.float32)

            GL.glUseProgram(self.prog_tex)
            loc_mvp = GL.glGetUniformLocation(self.prog_tex, "u_mvp")
            loc_op = GL.glGetUniformLocation(self.prog_tex, "u_opacity")
            loc_tex = GL.glGetUniformLocation(self.prog_tex, "u_tex")
            loc_pos = GL.glGetAttribLocation(self.prog_tex, "in_pos")
            loc_uv = GL.glGetAttribLocation(self.prog_tex, "in_uv")

            GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
            GL.glUniform1f(loc_op, opacity)
            GL.glUniform1i(loc_tex, 0)

            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)

            GL.glBindVertexArray(self.vao)
            pos_bytes = np.ascontiguousarray(quad_pos, dtype=np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_pos)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, pos_bytes.nbytes, pos_bytes, GL.GL_DYNAMIC_DRAW)
            GL.glEnableVertexAttribArray(loc_pos)
            GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

            uv_bytes = np.ascontiguousarray(quad_uv, dtype=np.float32)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_norm)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, uv_bytes.nbytes, uv_bytes, GL.GL_DYNAMIC_DRAW)
            GL.glEnableVertexAttribArray(loc_uv)
            GL.glVertexAttribPointer(loc_uv, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

            GL.glDepthMask(GL.GL_FALSE)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
            GL.glDepthMask(GL.GL_TRUE)

            GL.glDisableVertexAttribArray(loc_pos)
            GL.glDisableVertexAttribArray(loc_uv)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glBindVertexArray(0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            GL.glUseProgram(0)

            # Draw canvas boundary border
            if self.prog_flat:
                border_lines = np.array([
                    w_pts[0], w_pts[1],
                    w_pts[1], w_pts[2],
                    w_pts[2], w_pts[3],
                    w_pts[3], w_pts[0]
                ], dtype=np.float32)
                GL.glUseProgram(self.prog_flat)
                loc_m = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
                loc_c = GL.glGetUniformLocation(self.prog_flat, "u_color")
                loc_p = GL.glGetAttribLocation(self.prog_flat, "in_pos")
                GL.glUniformMatrix4fv(loc_m, 1, GL.GL_TRUE, mvp.flatten())
                GL.glUniform4f(loc_c, 0.2, 0.65, 1.0, 0.7)
                self.draw_buffer_arrays(GL.GL_LINES, loc_p, border_lines)
                GL.glUseProgram(0)

    def grid_step(self) -> float:
        """The sketch grid spacing from Settings (also the snap step when Snap to Grid is on)."""
        try:
            from omacad.ui.settings import get_settings
            step = float(get_settings().get("grid_step", 5.0))
        except Exception:
            step = 5.0
        return step if math.isfinite(step) and step > 1e-6 else 5.0

    def _grid_frame(self, plane=None):
        """(origin, u, v, normal) of the plane the grid is drawn on. A sketch draws it on its own plane. Without a
        sketch it lies on XY, unless the camera looks along XY (front/side view, where XY is an edge-on line):
        then the origin plane that faces the camera is used, so a grid is always visible (#226)."""
        if plane is not None:
            return (np.asarray(plane.origin, float), np.asarray(plane.u_axis, float),
                    np.asarray(plane.v_axis, float), np.asarray(plane.normal, float))
        _proj, view, _mvp = self.get_matrices()
        back = np.asarray(view[2, :3], dtype=float)        # world direction from the target towards the eye
        x, y, z = (abs(float(c)) for c in back)
        o = np.zeros(3)
        ex, ey, ez = np.eye(3)
        if z >= 0.25 or z >= max(x, y):
            return o, ex, ey, ez
        if y >= x:
            return o, ex, ez, ey
        return o, ey, ez, ex

    def grid_lines(self, plane=None, step=None):
        """Grid segments in plane (u, v) coordinates: (minor, major). The spacing follows Settings > grid step and
        grows in 5x steps when zoomed out, so lines stay at least ~7 px apart; every 5th line is a major line."""
        o, u, v, n = self._grid_frame(plane)
        step = float(step or self.grid_step())
        h = max(1, self.height())
        visible = 2.0 * float(self.distance) * math.tan(math.radians(15.0))
        while step * h / max(visible, 1e-9) < 7.0:
            step *= 5.0
        # Centre on the camera target projected into the plane, rounded to a major line
        t = np.asarray(self.target, float) - o
        major = step * 5.0
        cu = round(float(t @ u) / major) * major
        cv = round(float(t @ v) / major) * major
        half = max(150.0, visible * 1.6)
        if plane is not None and getattr(plane, "name", "") == "FACE":
            ref = self._reference_segments()
            half = max(half, float(np.abs(ref).max()) * 1.2 if len(ref) else 50.0)
        n_lines = min(400, int(math.ceil(half / step)))
        ext = n_lines * step
        self._grid_info = (step, ext, (cu, cv), step * h / max(visible, 1e-9))
        minor, majors = [], []
        for i in range(-n_lines, n_lines + 1):
            dst = majors if i % 5 == 0 else minor
            dst.append(((cu - ext, cv + i * step), (cu + ext, cv + i * step)))
            dst.append(((cu + i * step, cv - ext), (cu + i * step, cv + ext)))
        return (o, u, v, n), minor, majors

    SELECTED_TINT = 0.72    # share of the highlight colour mixed into a selected body (the rest keeps its own)

    def selected_body_rgb(self, color) -> tuple:
        """A selected body keeps a trace of its own colour under the highlight, so shading and material still read."""
        hi = theme.palette().selected_body01()
        t = self.SELECTED_TINT
        return tuple(float(c) * (1.0 - t) + h * t for c, h in zip(color[:3], hi))

    SHADOW_SPREAD = 1.6         # each shadow reaches this much past its body's footprint
    SHADOW_STRENGTH = 0.30
    SHADOW_MAX_LIFT = 0.15      # a body casts one only when resting on the ground (bottom within this share of its size)

    def contact_shadow_quad(self):
        """(corners, uvs) of the shadows under the visible bodies that rest on the ground (one soft ellipse each),
        or None (in a sketch, the setting off, or nothing resting on the ground)."""
        from omacad.ui.settings import get_settings
        if (self.doc.active_sketch is not None or not get_settings().get("ground_shadow", True)
                or float(getattr(self, "elevation", 30.0)) < 0.0):        # seen from below the ground: none
            return None
        corners, uvs = [], []
        unit = np.array([[-1, -1], [1, -1], [1, 1], [-1, -1], [1, 1], [-1, 1]], dtype=np.float32)
        for body in self.doc.bodies.values():
            rm = body.render_mesh
            if not getattr(body, "visible", True) or getattr(body, "construction", False) or rm is None or not len(rm.vertices):
                continue
            lo, hi = np.asarray(rm.bounds_min, float), np.asarray(rm.bounds_max, float)
            size = max(float(np.max(hi - lo)), 1e-6)
            if abs(lo[2]) > self.SHADOW_MAX_LIFT * size + 1e-6:
                continue
            cx, cy = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
            rx = max((hi[0] - lo[0]) / 2.0, 0.5) * self.SHADOW_SPREAD
            ry = max((hi[1] - lo[1]) / 2.0, 0.5) * self.SHADOW_SPREAD
            z = lo[2] - 0.02
            corners += [[cx + u * rx, cy + v * ry, z] for u, v in unit]
            uvs.append(unit)
        if not corners:
            return None
        return np.asarray(corners, dtype=np.float32), np.concatenate(uvs).astype(np.float32)

    def render_contact_shadow(self, mvp: np.ndarray):
        """A soft shadow on the ground under the model, so it sits on something instead of floating."""
        prog = getattr(self, "prog_shadow", None)
        quad = self.contact_shadow_quad() if prog else None
        if quad is None:
            return
        corners, uvs = quad
        GL.glUseProgram(prog)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(prog, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform1f(GL.glGetUniformLocation(prog, "u_strength"), self.SHADOW_STRENGTH)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDisable(GL.GL_DEPTH_TEST)    # drawn before the bodies (they cover it); origin planes at z 0 must not hide it
        loc_pos, loc_uv = GL.glGetAttribLocation(prog, "in_pos"), GL.glGetAttribLocation(prog, "in_uv")
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_pos)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, corners.nbytes, corners, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(loc_pos)
        GL.glVertexAttribPointer(loc_pos, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_norm)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, uvs.nbytes, uvs, GL.GL_DYNAMIC_DRAW)
        GL.glEnableVertexAttribArray(loc_uv)
        GL.glVertexAttribPointer(loc_uv, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(corners))
        GL.glDisableVertexAttribArray(loc_pos)
        GL.glDisableVertexAttribArray(loc_uv)
        GL.glBindVertexArray(0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def render_backdrop(self):
        """A soft vertical gradient behind everything (theme.Palette.canvas_gradient01), drawn without depth."""
        prog = getattr(self, "prog_backdrop", None)
        if not prog or getattr(self, "vbo_backdrop", None) is None:
            return
        top, bottom = theme.palette().canvas_gradient01()
        quad = np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], dtype=np.float32)
        GL.glUseProgram(prog)
        GL.glUniform3f(GL.glGetUniformLocation(prog, "u_top"), *top)
        GL.glUniform3f(GL.glGetUniformLocation(prog, "u_bottom"), *bottom)
        loc = GL.glGetAttribLocation(prog, "in_xy")
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_backdrop)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, quad.nbytes, quad, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(loc)
        GL.glVertexAttribPointer(loc, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glDisableVertexAttribArray(loc)
        GL.glBindVertexArray(0)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)

    GRID_MINOR_FADE_PX = (7.0, 22.0)    # minor lines fade in between these spacings, so the 5x zoom steps do not pop
    GRID_FADE_START = 0.35              # fraction of the grid's half size where lines start to fade out

    def _render_grid(self, mvp: np.ndarray, plane=None, lift: float = 0.0):
        if not self.prog_flat:
            return
        (o, u, v, n), minor, majors = self.grid_lines(plane)
        off = o + n * lift
        step, ext, (cu, cv), step_px = getattr(self, "_grid_info", (1.0, 0.0, (0.0, 0.0), 30.0))
        prog = getattr(self, "prog_grid", None) or self.prog_flat
        GL.glUseProgram(prog)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(prog, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        loc_col = GL.glGetUniformLocation(prog, "u_color")
        loc_pos = GL.glGetAttribLocation(prog, "in_pos")
        lo, hi = self.GRID_MINOR_FADE_PX
        grow = max(0.0, min(1.0, (step_px - lo) / (hi - lo)))
        grow = grow * grow * (3.0 - 2.0 * grow)
        minor_alpha, major_alpha = 0.45 * grow, 0.45 + 0.40 * grow
        if prog is not self.prog_flat:
            centre = off + cu * u + cv * v
            GL.glUniform3f(GL.glGetUniformLocation(prog, "u_center"), *(float(c) for c in centre))
            GL.glUniform1f(GL.glGetUniformLocation(prog, "u_fade_start"), float(ext * self.GRID_FADE_START))
            GL.glUniform1f(GL.glGetUniformLocation(prog, "u_fade_end"), float(max(ext, 1e-6)))
        else:
            minor_alpha, major_alpha = 0.45, 0.85
        self.set_line_width(1.0)
        # The grid is a backdrop. It must not reject body fragments when the camera is below it.
        GL.glDepthMask(GL.GL_FALSE)
        for segs, alpha in ((minor, minor_alpha), (majors, major_alpha)):
            if alpha <= 0.003:
                continue
            if not segs:
                continue
            uv = np.asarray(segs, dtype=np.float64).reshape(-1, 2)
            data = (off[None, :] + uv[:, :1] * u[None, :] + uv[:, 1:] * v[None, :]).astype(np.float32)
            GL.glUniform4f(loc_col, *theme.palette().grid_rgb01(), alpha)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, data.reshape(-1))
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def render_plane_grid(self, mvp: np.ndarray, plane):
        """Grid on the sketch plane itself (drawn a hair above it so it shows on a face)."""
        self._render_grid(mvp, plane, lift=0.05 if getattr(plane, "name", "") == "FACE" else 0.0)

    def render_ground_grid(self, mvp: np.ndarray):
        """Grid on XY, or on the origin plane facing the camera in a front/side view."""
        self._render_grid(mvp, None)

    ORIGIN_AXES = {"X": ((0.88, 0.22, 0.22), (1.0, 0.0, 0.0)),
                   "Y": ((0.20, 0.72, 0.30), (0.0, 1.0, 0.0)),
                   "Z": ((0.18, 0.50, 0.92), (0.0, 0.0, 1.0))}

    def render_origin_axes(self, mvp: np.ndarray):
        """The coloured X/Y/Z axes through the origin; each one can be hidden (Browser > Origin, View > Origin)."""
        if not self.prog_flat:
            return
        axes = [(c, d) for name, (c, d) in self.ORIGIN_AXES.items() if self.doc.origin_visible("axis", name)]
        if not axes:
            return
        GL.glUseProgram(self.prog_flat)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.prog_flat, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        self.set_line_width(1.0)
        for (r, g, b), d in axes:
            seg = [0.0, 0.0, 0.0, *(150.0 * x for x in d)]
            if self.prog_thick is not None and self.vbo_thick is not None:
                self.draw_thick_lines(mvp, seg, (r, g, b, 0.95), 2.4, halo=False)
            else:
                GL.glUniform4f(loc_col, r, g, b, 0.95)
                self.draw_buffer_arrays(GL.GL_LINES, loc_pos, np.array(seg, dtype=np.float32))
            GL.glUseProgram(self.prog_flat)
            GL.glUniform4f(loc_col, r, g, b, 0.38)
            neg_seg = np.array([0.0, 0.0, 0.0, *(-150.0 * x for x in d)], dtype=np.float32)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, neg_seg)
        GL.glUseProgram(0)

    @staticmethod
    def _delete_gpu_cache_entry(old: dict):
        try:
            GL.glDeleteVertexArrays(1, [old["vao_solid"]])
            GL.glDeleteBuffers(2, [old["vbo_pos"], old["vbo_norm"]])
            if old.get("vao_lines") is not None:
                GL.glDeleteVertexArrays(1, [old["vao_lines"]])
            if old.get("vbo_lines") is not None:
                GL.glDeleteBuffers(1, [old["vbo_lines"]])
            if old.get("vao_thick") is not None:
                GL.glDeleteVertexArrays(1, [old["vao_thick"]])
                GL.glDeleteBuffers(1, [old["vbo_thick"]])
        except Exception:
            pass

    EDGE_WIDTH_PX = 1.5          # body edges, drawn as screen-space quads (Core GL caps glLineWidth at 1 px)
    SELECTED_EDGE_WIDTH_PX = 2.4
    EDGE_DEPTH_BIAS = 2e-5

    @staticmethod
    def thick_line_data(edge_lines) -> np.ndarray:
        """The quad corners `draw_thick_lines` builds for flat line pairs: (pos, other end, side) per vertex."""
        segs = np.asarray(edge_lines, dtype=np.float32).reshape(-1, 2, 3)
        a, b = segs[:, 0], segs[:, 1]
        n = len(segs)
        pos = np.stack([a, a, b, a, b, b], axis=1)
        oth = np.stack([b, b, a, b, a, a], axis=1)
        side = np.tile(np.array([-1, 1, 1, 1, -1, 1], dtype=np.float32), (n, 1))[..., None]
        return np.ascontiguousarray(np.concatenate([pos, oth, side], axis=2).reshape(-1, 7), dtype=np.float32)

    def _draw_cached_thick_edges(self, mvp, entry: dict, edge_lines, rgba, width_px: float) -> bool:
        """Body edges at a real pixel width from a buffer built once per mesh. False: fall back to GL_LINES."""
        prog = self.prog_thick
        if prog is None or not len(edge_lines):
            return False
        if entry.get("vao_thick") is None:
            data = self.thick_line_data(edge_lines)
            vao, vbo = GL.glGenVertexArrays(1), GL.glGenBuffers(1)
            GL.glBindVertexArray(vao)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
            GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
            for name, size, off in (("in_pos", 3, 0), ("in_other", 3, 12), ("in_side", 1, 24)):
                loc = GL.glGetAttribLocation(prog, name)
                if loc >= 0:
                    GL.glEnableVertexAttribArray(loc)
                    GL.glVertexAttribPointer(loc, size, GL.GL_FLOAT, GL.GL_FALSE, 28, ctypes.c_void_p(off))
            GL.glBindVertexArray(0)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            entry.update(vao_thick=vao, vbo_thick=vbo, thick_count=len(data))
        GL.glUseProgram(prog)
        dpr = self.devicePixelRatioF()
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(prog, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform2f(GL.glGetUniformLocation(prog, "u_viewport"), self.width() * dpr, self.height() * dpr)
        GL.glUniform4f(GL.glGetUniformLocation(prog, "u_color"), *rgba)
        GL.glUniform1f(GL.glGetUniformLocation(prog, "u_width"), float(width_px) * dpr)
        GL.glUniform1f(GL.glGetUniformLocation(prog, "u_depth_bias"), self.EDGE_DEPTH_BIAS)
        GL.glBindVertexArray(entry["vao_thick"])
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, entry["thick_count"])
        GL.glBindVertexArray(0)
        GL.glUniform1f(GL.glGetUniformLocation(prog, "u_depth_bias"), 0.0)
        GL.glUseProgram(0)
        return True

    DISPLAY_STYLES = {               # style -> (solids drawn, edges drawn)
        "shaded_edges": ("shaded", True), "shaded": ("shaded", False),
        "wireframe": ("none", True), "hidden_line": ("paper", True),
    }

    @property
    def display_style(self) -> str:
        return getattr(self, "_display_style", "shaded_edges")

    @display_style.setter
    def display_style(self, style: str) -> None:
        """Shaded with edges, shaded, wireframe (every edge, see-through) or hidden line (edges, hidden ones gone)."""
        if style not in self.DISPLAY_STYLES:
            raise ValueError(f"unknown display style {style!r}")
        self._display_style = style
        solids, edges = self.DISPLAY_STYLES[style]
        self.wireframe_only = solids != "shaded"
        self.show_edges = edges
        self.update()

    def render_bodies(self, mvp: np.ndarray):
        """Renders shaded CAD bodies with sharp silhouette edges. Hidden line: the bodies are drawn into the depth
        buffer only (all of them first, so one body hides another's edges too), then their edges."""
        if not self.prog_solid or not self.prog_flat:
            return
        if self.display_style != "hidden_line":
            self._render_bodies_once(mvp)
            return
        # Hidden line: paper-white bodies with their sharp edges, then the silhouettes: the back faces drawn as
        # lines, which only show round the rim of the front faces (the fill is pushed back by the polygon offset)
        saved = (self.wireframe_only, self.show_edges)
        try:
            self.wireframe_only, self.show_edges = False, True
            self._body_pass = "paper"
            self._render_bodies_once(mvp)
            self.show_edges = False
            self._body_pass = "silhouette"
            self._render_bodies_once(mvp)
        finally:
            self._body_pass = None
            self.wireframe_only, self.show_edges = saved

    def _render_bodies_once(self, mvp: np.ndarray):

        gpu_cache = getattr(self, "_body_gpu_cache", None)
        if gpu_cache is not None:
            live_bids = set(self.doc.bodies.keys())
            for k in list(gpu_cache.keys()):
                if k[0] not in live_bids:
                    self._delete_gpu_cache_entry(gpu_cache.pop(k))
        from omacad.ui.settings import get_settings
        tangent = bool(get_settings().get("show_tangent_edges", True))

        # construction bodies last: see-through helpers drawn over what is solid
        for body in sorted(self.doc.bodies.values(), key=lambda b: b.construction or b.body_id in self.cut_tool_ids):
            if not body.visible or not body.render_mesh:
                continue
            cutting = body.body_id in self.cut_tool_ids
            helper = body.construction and not cutting

            mesh = body.render_mesh
            override = getattr(self, "display_override", None)
            if self.section is not None and body.body_id in self.section["meshes"]:
                mesh = self.section["meshes"][body.body_id]   # the part left after the cut (of a tool's result too)
            elif override and body.body_id in override:
                mesh = override[body.body_id]   # a tool shows its finished result in place of the body (Fillet)
            if len(mesh.vertices) == 0:
                continue

            is_selected = body.selected
            edge_lines = mesh.drawn_edges(tangent) if hasattr(mesh, "drawn_edges") else mesh.sharp_lines

            # Fetch or build GPU VAO/VBO for this body mesh
            draw_verts, draw_normals, edge_lines = mesh.display_arrays(edge_lines)   # smoothed in Fast view
            cache_entry = None
            mesh_token = getattr(mesh, "mesh_id", id(mesh))
            mesh_key = (body.body_id, mesh_token, len(draw_verts), len(edge_lines))
            if gpu_cache is not None:
                cache_entry = gpu_cache.get(mesh_key)
                if cache_entry is None:
                    # Clean up old entries for this body
                    for k in list(gpu_cache.keys()):
                        if k[0] == body.body_id:
                            self._delete_gpu_cache_entry(gpu_cache.pop(k))

                    # Build solid VAO/VBO
                    vao_solid = GL.glGenVertexArrays(1)
                    vbo_pos = GL.glGenBuffers(1)
                    vbo_norm = GL.glGenBuffers(1)
                    GL.glBindVertexArray(vao_solid)


                    pos_data = np.ascontiguousarray(draw_verts, dtype=np.float32)
                    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_pos)
                    GL.glBufferData(GL.GL_ARRAY_BUFFER, pos_data.nbytes, pos_data, GL.GL_STATIC_DRAW)
                    loc_pos_solid = GL.glGetAttribLocation(self.prog_solid, "in_pos")
                    GL.glEnableVertexAttribArray(loc_pos_solid)
                    GL.glVertexAttribPointer(loc_pos_solid, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

                    norm_data = np.ascontiguousarray(draw_normals, dtype=np.float32)
                    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_norm)
                    GL.glBufferData(GL.GL_ARRAY_BUFFER, norm_data.nbytes, norm_data, GL.GL_STATIC_DRAW)
                    loc_norm_solid = GL.glGetAttribLocation(self.prog_solid, "in_normal")
                    GL.glEnableVertexAttribArray(loc_norm_solid)
                    GL.glVertexAttribPointer(loc_norm_solid, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

                    GL.glBindVertexArray(0)
                    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

                    # Build sharp lines VAO/VBO
                    vao_lines = None
                    vbo_lines = None
                    line_count = 0
                    if len(edge_lines) > 0 and self.prog_flat:
                        vao_lines = GL.glGenVertexArrays(1)
                        vbo_lines = GL.glGenBuffers(1)
                        GL.glBindVertexArray(vao_lines)
                        lines_data = np.ascontiguousarray(edge_lines, dtype=np.float32)
                        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_lines)
                        GL.glBufferData(GL.GL_ARRAY_BUFFER, lines_data.nbytes, lines_data, GL.GL_STATIC_DRAW)
                        loc_pos_flat = GL.glGetAttribLocation(self.prog_flat, "in_pos")
                        GL.glEnableVertexAttribArray(loc_pos_flat)
                        GL.glVertexAttribPointer(loc_pos_flat, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)
                        GL.glBindVertexArray(0)
                        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
                        line_count = lines_data.size // 3

                    cache_entry = {
                        "vao_solid": vao_solid,
                        "vbo_pos": vbo_pos,
                        "vbo_norm": vbo_norm,
                        "vert_count": pos_data.size // 3,
                        "vao_lines": vao_lines,
                        "vbo_lines": vbo_lines,
                        "line_count": line_count,
                    }
                    gpu_cache[mesh_key] = cache_entry

            # 1. Shaded Surfaces
            if not self.wireframe_only:
                GL.glUseProgram(self.prog_solid)
                loc_mvp = GL.glGetUniformLocation(self.prog_solid, "u_mvp")
                loc_col = GL.glGetUniformLocation(self.prog_solid, "u_color")

                GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
                loc_eye = GL.glGetUniformLocation(self.prog_solid, "u_eye_dir")
                if loc_eye >= 0:
                    az = math.radians(getattr(self, "azimuth", 0.0))
                    el = math.radians(getattr(self, "elevation", 0.0))
                    GL.glUniform3f(loc_eye, math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el))

                # Color: SolidCraft blue if selected, else body color
                if cutting:
                    GL.glDepthMask(GL.GL_FALSE)
                    GL.glUniform4f(loc_col, 0.92, 0.25, 0.20, 0.45)
                elif helper:
                    GL.glDepthMask(GL.GL_FALSE)    # never hides anything, whatever the camera angle
                    grey = 0.55 * (body.color[0] + body.color[1] + body.color[2]) / 3.0
                    mix = [0.5 * c + 0.5 * grey for c in body.color[:3]]   # duller than a real body
                    GL.glUniform4f(loc_col, mix[0], mix[1], mix[2], 0.3)
                elif is_selected:
                    GL.glUniform4f(loc_col, *self.selected_body_rgb(body.color), 1.0)
                else:
                    c = body.color
                    GL.glUniform4f(loc_col, c[0], c[1], c[2], c[3])
                body_pass = getattr(self, "_body_pass", None)
                if body_pass == "paper" and not (cutting or helper):
                    GL.glUniform4f(loc_col, *((0.80, 0.86, 0.98) if is_selected else (0.97, 0.97, 0.96)), 1.0)
                silhouette = body_pass == "silhouette" and not (cutting or helper)
                if silhouette:
                    GL.glUniform4f(loc_col, 0.05, 0.06, 0.08, 1.0)
                    GL.glEnable(GL.GL_CULL_FACE)
                    GL.glCullFace(GL.GL_FRONT)
                    GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_LINE)
                elif body_pass == "silhouette":
                    GL.glUseProgram(0)
                    continue

                # Push depth back slightly so crisp edges render cleanly on top (further for the hidden-line paper,
                # so no back-face line pokes through a flat face as a speck)
                GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
                GL.glPolygonOffset(*((2.0, 4.0) if body_pass == "paper" else (1.0, 1.0)))

                if cache_entry and cache_entry.get("vao_solid"):
                    GL.glBindVertexArray(cache_entry["vao_solid"])
                    GL.glDrawArrays(GL.GL_TRIANGLES, 0, cache_entry["vert_count"])
                    GL.glBindVertexArray(0)
                else:
                    loc_pos = GL.glGetAttribLocation(self.prog_solid, "in_pos")
                    loc_norm = GL.glGetAttribLocation(self.prog_solid, "in_normal")
                    self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, draw_verts, loc_norm, draw_normals)

                GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
                if silhouette:
                    GL.glPolygonMode(GL.GL_FRONT_AND_BACK, GL.GL_FILL)
                    GL.glDisable(GL.GL_CULL_FACE)
                GL.glDepthMask(GL.GL_TRUE)
                GL.glUseProgram(0)

            # 2. Crisp Sharp Feature Edges
            if (self.show_edges or self.wireframe_only) and len(edge_lines) > 0:
                GL.glUseProgram(self.prog_flat)
                loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
                loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")

                GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

                if cutting:
                    rgba, width = (0.75, 0.15, 0.12, 1.0), self.EDGE_WIDTH_PX
                elif is_selected:
                    rgba, width = (*theme.palette().selection_edge01(), 1.0), self.SELECTED_EDGE_WIDTH_PX
                elif helper:
                    rgba, width = (0.45, 0.47, 0.5, 0.45), 1.0       # faint edge on a helper body
                else:
                    rgba, width = (0.157, 0.173, 0.204, 1.0), self.EDGE_WIDTH_PX  # SolidCraft charcoal Rgb(40, 44, 52)
                GL.glUniform4f(loc_col, *rgba)
                self.set_line_width(width)

                if cache_entry and not helper and self._draw_cached_thick_edges(mvp, cache_entry, edge_lines, rgba, width):
                    pass
                elif cache_entry and cache_entry.get("vao_lines"):
                    GL.glBindVertexArray(cache_entry["vao_lines"])
                    GL.glDrawArrays(GL.GL_LINES, 0, cache_entry["line_count"])
                    GL.glBindVertexArray(0)
                else:
                    loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
                    self.draw_buffer_arrays(GL.GL_LINES, loc_pos, edge_lines)
                GL.glUseProgram(0)

    def dash_segments(self, flat_segments, dash_px: float = 9.0, gap_px: Optional[float] = None):
        """Construction lines are dashed: see `dash_lines`."""
        from omacad.ui.settings import get_settings
        if gap_px is None:
            gap_px = float(get_settings().get("guide_line_gap", 6.0))
        return dash_lines(flat_segments, self.world_to_screen, dash_px, gap_px)

    CONFLICT_SHOW_S = 3.0
    CONFLICT_OFFER_S = 12.0     # long enough to click the chip and pick what to replace

    def _recent_conflicts(self, sketch) -> set:
        """Elements of a constraint/dimension just refused as over defining, for a few seconds."""
        import time
        info = getattr(self.doc, "last_conflicts", None)
        if not info or info[0] != sketch.sketch_id:
            return set()
        offer = getattr(self.doc, "conflict_offer", None)
        shown = self.CONFLICT_OFFER_S if offer and offer["sketch_id"] == sketch.sketch_id else self.CONFLICT_SHOW_S
        left = shown - (time.monotonic() - info[2])
        if left <= 0:
            return set()
        if not getattr(self, "_conflict_timer_armed", False):
            from PySide6.QtCore import QTimer
            self._conflict_timer_armed = True

            def _clear():
                self._conflict_timer_armed = False
                self.update()
            QTimer.singleShot(int(left * 1000) + 50, _clear)
        return info[1]

    def draw_thick_lines(self, mvp: np.ndarray, flat_segments, rgba, width_px: float, halo: bool = True,
                         halo_px: float = 3.5, halo_color=None):
        """Draws line segments (flat [x1,y1,z1,x2,y2,z2,...]) as screen-space quads.
        A dark halo under the coloured core keeps them readable on light faces and dark grid alike."""
        if self.prog_thick is None or self.vbo_thick is None:
            return
        segs = np.asarray(flat_segments, dtype=np.float32).reshape(-1, 2, 3)
        if len(segs) == 0:
            return
        a, b = segs[:, 0], segs[:, 1]
        n = len(segs)
        # Vertex order: A(-1) A(+1) B(+1)  |  A(+1) B(-1) B(+1)
        pos = np.stack([a, a, b, a, b, b], axis=1)
        oth = np.stack([b, b, a, b, a, a], axis=1)
        side = np.tile(np.array([-1, 1, 1, 1, -1, 1], dtype=np.float32), (n, 1))[..., None]
        data = np.concatenate([pos, oth, side], axis=2).reshape(-1, 7).astype(np.float32)

        prog = self.prog_thick
        GL.glUseProgram(prog)
        dpr = self.devicePixelRatioF()
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(prog, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform2f(GL.glGetUniformLocation(prog, "u_viewport"), self.width() * dpr, self.height() * dpr)
        loc_col = GL.glGetUniformLocation(prog, "u_color")
        loc_w = GL.glGetUniformLocation(prog, "u_width")
        locs = [GL.glGetAttribLocation(prog, nm) for nm in ("in_pos", "in_other", "in_side")]

        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo_thick)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
        stride = 7 * 4
        for loc, size, off in zip(locs, (3, 3, 1), (0, 12, 24)):
            if loc >= 0:
                GL.glEnableVertexAttribArray(loc)
                GL.glVertexAttribPointer(loc, size, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(off))

        passes = []
        if halo:
            h_col = halo_color if halo_color is not None else (0.03, 0.04, 0.06, 0.85)
            passes.append((h_col, width_px + halo_px))
        passes.append((rgba, width_px))
        for col, w in passes:
            GL.glUniform4f(loc_col, *col)
            GL.glUniform1f(loc_w, w * dpr)
            GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(data))

        for loc in locs:
            if loc >= 0:
                GL.glDisableVertexAttribArray(loc)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)
        GL.glUseProgram(self.prog_flat)

    def render_sketches(self, mvp: np.ndarray):
        """Renders 2D sketch lines, closed profiles, and sketch planes."""
        if not self.prog_flat:
            return

        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")

        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

        # Draw all visible sketches
        for sketch in self.doc.sketches.values():
            flash = sketch.sketch_id == getattr(self, "flash_sketch_id", None)
            picked_sid, picked = getattr(self, "picked_dim_entities", (None, set()))
            picked = picked if (sketch.sketch_id == picked_sid and (sketch.visible or sketch == self.doc.active_sketch)) else set()
            if not sketch.visible and not flash:
                continue

            is_active = (sketch == self.doc.active_sketch)
            # The active sketch is always drawn on top (it may lie on or inside a body);
            # other sketches get a small depth bias so they don't z-fight with faces.
            if is_active:
                GL.glDisable(GL.GL_DEPTH_TEST)
            else:
                GL.glEnable(GL.GL_DEPTH_TEST)
            plane = sketch.plane

            # Render Sketch Entities
            normal_lines = []
            defined_lines = []
            conflict_lines = []
            clash = self._recent_conflicts(sketch) if is_active else set()
            construction_lines = []
            projected_lines = []
            selected_lines = []
            hover_lines = []
            copy_box = getattr(getattr(self, "tool_panel", None), "chk_copy", None)
            if is_active and self._move and copy_box is not None and copy_box.isChecked():
                # Move with Copy: the originals stay where they are, so keep drawing them there (Björn)
                for ent in self._move["orig"].values():
                    dest = construction_lines if ent.is_construction else normal_lines
                    for p1, p2 in ent.to_lines():
                        w1 = plane.uv_to_world(p1[0], p1[1])
                        w2 = plane.uv_to_world(p2[0], p2[1])
                        dest.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            for ent in sketch.entities:
                if flash or ent.entity_id in picked:
                    dest = selected_lines          # lit up in the highlight colour
                elif is_active and (ent.entity_id in self.selected_entities or ent.entity_id in self._dim_highlight_ids()):
                    dest = selected_lines
                elif is_active and ent.entity_id == self.hover_entity_id:
                    dest = hover_lines
                else:
                    dest = projected_lines if getattr(ent, "projected", False) else (construction_lines if ent.is_construction else normal_lines)
                    if dest is normal_lines and is_active and ent.entity_id in clash:
                        dest = conflict_lines      # SolidWorks: over defined geometry in yellow
                    elif dest is normal_lines and is_active and entity_defined(sketch, ent):
                        dest = defined_lines       # SolidWorks: black when it cannot move any more
                for p1, p2 in ent.to_lines():
                    w1 = plane.uv_to_world(p1[0], p1[1])
                    w2 = plane.uv_to_world(p2[0], p2[1])
                    dest.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])

            # a finished sketch of an object that was moved since is drawn where the object is now
            placed = None if is_active else self.doc.sketch_placement(sketch.sketch_id)
            if placed is not None:
                normal_lines, construction_lines, projected_lines, selected_lines, hover_lines = (
                    placed_lines(lines, placed) for lines in
                    (normal_lines, construction_lines, projected_lines, selected_lines, hover_lines))

            from omacad.ui.settings import get_settings, hex_to_rgb01, sketch_line_widths
            line_w, sel_w = sketch_line_widths()     # Björn #74: set in Settings, thinner than before
            halo_px = 0.4 + 0.8 * line_w             # a thin dark rim, not a second line
            if conflict_lines:
                self.draw_thick_lines(mvp, conflict_lines, (1.0, 0.82, 0.10, 1.0), line_w + 0.8, halo_px=halo_px)
            if defined_lines:
                scol = get_settings().sketch_fully_constrained_color_rgb01()
                # On dark background or canvas, a subtle lighter rim keeps black lines visible
                halo_col = (0.75, 0.78, 0.82, 0.75) if sum(theme.palette().canvas_rgb01()) / 3 < 0.5 else (0.03, 0.04, 0.06, 0.85)
                self.draw_thick_lines(mvp, defined_lines, (*scol, 1.0), line_w, halo_px=halo_px, halo_color=halo_col)
            if normal_lines:
                if is_active:
                    scol = get_settings().sketch_line_color_rgb01()
                    self.draw_thick_lines(mvp, normal_lines, (*scol, 1.0), line_w, halo_px=halo_px,
                                          halo_color=(0.03, 0.04, 0.06, 0.85))
                else:
                    fcol = get_settings().sketch_finished_color_rgb01()    # grey by default (Björn #90)
                    self.draw_thick_lines(mvp, normal_lines, (*fcol, 1.0), line_w, halo=False)   # no dark rim

            # edges included from the body: a distinct colour while editing, like Fusion's projected curves;
            # a finished sketch leaves them out, the body's own edges already show there (Björn #92)
            if projected_lines and is_active:
                self.draw_thick_lines(mvp, projected_lines, (0.80, 0.45, 1.0, 1.0), 2.2)
            if hover_lines:
                from omacad.ui.settings import hover_line_style
                hv_col, hv_w = hover_line_style()
                self.draw_thick_lines(mvp, hover_lines, hv_col, max(1.0, hv_w - 0.5))
            if selected_lines:
                hl_col = (hex_to_rgb01(get_settings().get("selected_line_color"))
                          or get_settings().highlight_color_rgb01()
                          or ((0.96, 0.44, 0.08) if theme.palette().studio else theme.palette().highlight01()))
                self.draw_thick_lines(mvp, selected_lines, (*hl_col, 1.0), max(sel_w, line_w + 1.4), halo_px=halo_px + 0.8)

            show_const = getattr(getattr(self, "sketch_palette", None), "chk_show_construction", None)
            if construction_lines and is_active and (show_const is None or show_const.isChecked()):
                ccol = get_settings().sketch_construction_color_rgb01()
                self.draw_thick_lines(mvp, self.dash_segments(construction_lines), (*ccol, 1.0), line_w,
                                      halo_px=halo_px)
            elif construction_lines and not is_active:    # a finished sketch's helper lines: quiet, dashed, in its grey
                fcol = get_settings().sketch_finished_color_rgb01()
                self.draw_thick_lines(mvp, self.dash_segments(construction_lines), (*fcol, 0.6), 1.0, halo=False)

        GL.glEnable(GL.GL_DEPTH_TEST)

        # Render Active Live Drawing Preview
        GL.glDisable(GL.GL_DEPTH_TEST)
        if self.doc.active_sketch and self.sketch_start_uv and self.sketch_current_uv:
            plane = self.doc.active_sketch.plane
            u1, v1 = self.sketch_start_uv
            u2, v2 = self.sketch_current_uv

            preview_lines = []
            if self.sketch_tool in ("SPLINE", "CONTROL_SPLINE"):
                points = list(getattr(self, "_spline_points", []))
                if points:
                    if math.hypot(u2 - points[-1][0], v2 - points[-1][1]) > 1e-4:
                        points.append((u2, v2))
                    spline_preview = SketchSpline("preview", points,
                                                  control_points=self.sketch_tool == "CONTROL_SPLINE")
                    for a, b in spline_preview.to_lines():
                        w1 = plane.uv_to_world(*a)
                        w2 = plane.uv_to_world(*b)
                        preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "LINE":
                w1 = plane.uv_to_world(u1, v1)
                w2 = plane.uv_to_world(u2, v2)
                preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool in ("ROUNDED_RECT", "CENTER_ROUNDED_RECT"):
                c1 = (u1, v1) if self.sketch_tool == "ROUNDED_RECT" else (2 * u1 - u2, 2 * v1 - v2)
                outline = Sketch.rounded_rect_outline(c1, (u2, v2), self._corner_radius())
                for i in range(len(outline)):
                    w1 = plane.uv_to_world(*outline[i])
                    w2 = plane.uv_to_world(*outline[(i + 1) % len(outline)])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "RECT":
                corners = [(min(u1, u2), min(v1, v2)), (max(u1, u2), min(v1, v2)),
                           (max(u1, u2), max(v1, v2)), (min(u1, u2), max(v1, v2))]
                for i in range(4):
                    w1 = plane.uv_to_world(corners[i][0], corners[i][1])
                    w2 = plane.uv_to_world(corners[(i + 1) % 4][0], corners[(i + 1) % 4][1])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "CENTER_RECT":
                cx, cy = u1, v1
                dx, dy = abs(u2 - cx), abs(v2 - cy)
                corners = [(cx - dx, cy - dy), (cx + dx, cy - dy), (cx + dx, cy + dy), (cx - dx, cy + dy)]
                for i in range(4):
                    w1 = plane.uv_to_world(corners[i][0], corners[i][1])
                    w2 = plane.uv_to_world(corners[(i + 1) % 4][0], corners[(i + 1) % 4][1])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                # Diagonals from center to corners
                for i in range(4):
                    w1 = plane.uv_to_world(cx, cy)
                    w2 = plane.uv_to_world(corners[i][0], corners[i][1])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "POLYGON":
                pts = Sketch.polygon_points((u1, v1), (u2, v2), self._polygon_sides())
                for i in range(len(pts)):
                    w1 = plane.uv_to_world(*pts[i])
                    w2 = plane.uv_to_world(*pts[(i + 1) % len(pts)])
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "CIRCLE":
                r = math.hypot(u2 - u1, v2 - v1)
                segs = 36
                for i in range(segs):
                    a1 = 2.0 * math.pi * i / segs
                    a2 = 2.0 * math.pi * (i + 1) / segs
                    w1 = plane.uv_to_world(u1 + r * math.cos(a1), v1 + r * math.sin(a1))
                    w2 = plane.uv_to_world(u1 + r * math.cos(a2), v1 + r * math.sin(a2))
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "CENTER_ARC":
                if self.sketch_second_uv is None:          # the radius line from the centre
                    w1 = plane.uv_to_world(u1, v1)
                    w2 = plane.uv_to_world(u2, v2)
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                else:
                    from omacad.model.sketch_entities import center_arc_points
                    sweep = getattr(self, "_center_arc_sweep", 0.0)
                    if abs(sweep) > 1e-3:
                        arc_temp = SketchArc("temp", *center_arc_points(self.sketch_start_uv, self.sketch_second_uv, sweep))
                        for seg_p1, seg_p2 in arc_temp.to_lines(48):
                            w1 = plane.uv_to_world(seg_p1[0], seg_p1[1])
                            w2 = plane.uv_to_world(seg_p2[0], seg_p2[1])
                            preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "ARC":
                if self.sketch_second_uv is None:
                    w1 = plane.uv_to_world(u1, v1)
                    w2 = plane.uv_to_world(u2, v2)
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                else:
                    p1 = self.sketch_start_uv
                    p2 = self.sketch_second_uv
                    p_mid = (u2, v2)
                    arc_temp = SketchArc("temp", p1, p_mid, p2)
                    for seg_p1, seg_p2 in arc_temp.to_lines(24):
                        w1 = plane.uv_to_world(seg_p1[0], seg_p1[1])
                        w2 = plane.uv_to_world(seg_p2[0], seg_p2[1])
                        preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
            elif self.sketch_tool == "SLOT":
                if self.sketch_second_uv is None:
                    w1 = plane.uv_to_world(u1, v1)
                    w2 = plane.uv_to_world(u2, v2)
                    preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
                else:
                    c1 = self.sketch_start_uv
                    c2 = self.sketch_second_uv
                    d = self._point_to_segment_dist((u2, v2), c1, c2)
                    slot_temp = SketchSlot("temp", c1, c2, max(1.0, d))
                    for seg_p1, seg_p2 in slot_temp.to_lines(16):
                        w1 = plane.uv_to_world(seg_p1[0], seg_p1[1])
                        w2 = plane.uv_to_world(seg_p2[0], seg_p2[1])
                        preview_lines.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])

            if preview_lines:
                col = (1.0, 0.75, 0.25, 1.0) if self.construction_mode else (1.0, 0.92, 0.25, 1.0)
                self.draw_thick_lines(mvp, preview_lines, col, 2.2)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)



def placed_lines(flat, m):
    """A flat [x, y, z, x, y, z, ...] list of line ends moved by the 4x4 matrix `m`."""
    if not flat:
        return flat
    pts = np.asarray(flat, dtype=float).reshape(-1, 3)
    return (pts @ m[:3, :3].T + m[:3, 3]).ravel().tolist()
