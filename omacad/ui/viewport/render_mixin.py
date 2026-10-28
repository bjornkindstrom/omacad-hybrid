"""OpenGL rendering methods mixin for Viewport3D."""

import ctypes
import math
from typing import Optional, List, Dict
import numpy as np
from PySide6.QtCore import Qt, QTimer
from OpenGL import GL
from omacad.ui import theme
from omacad.ui.viewport.sketch_rotate_mixin import INFO as ROTATE_INFO
from omacad.model.timeline import profile_cross_section
from omacad.model.sketch import Sketch, SketchArc, SketchSlot, SketchSpline



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
        """Translucent fills for the hovered and selected sketch profiles."""
        if not self.prog_flat or self.doc.active_sketch:
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
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        inside = op in ("cut", "intersect")   # these sit inside the body: show them through its surface
        if inside:
            GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glUniform4f(loc_col, r, g, b, 0.50 if inside else 0.38)
        self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, mesh.vertices)
        GL.glDepthMask(GL.GL_TRUE)
        if len(mesh.sharp_lines) > 0:
            GL.glUniform4f(loc_col, r, g, b, 1.0)
            self.set_line_width(2.0)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, mesh.sharp_lines)
        if inside:
            GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(0)


















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

    def render_plane_grid(self, mvp: np.ndarray, plane):
        """Grid on the sketch plane itself, centred on its origin (the face centre) and sized to the
        face, drawn a hair above it so it shows on the face."""
        if not self.prog_flat:
            return
        step = 10.0
        ref = self._reference_segments()
        half = float(np.abs(ref).max()) if len(ref) else 50.0
        n = max(5, int(math.ceil(half * 1.2 / step)))
        ext = n * step
        pts = []
        for i in range(-n, n + 1):
            c = i * step
            pts += [(-ext, c), (ext, c), (c, -ext), (c, ext)]
        lift = np.asarray(plane.normal, dtype=np.float64) * 0.05
        data = np.array([plane.uv_to_world(u, v) + lift for u, v in pts], dtype=np.float32)
        GL.glUseProgram(self.prog_flat)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.prog_flat, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
        GL.glUniform4f(GL.glGetUniformLocation(self.prog_flat, "u_color"), *theme.palette().grid_rgb01(), 0.72)
        self.set_line_width(1.0)
        self.draw_buffer_arrays(GL.GL_LINES, GL.glGetAttribLocation(self.prog_flat, "in_pos"), data.reshape(-1))
        GL.glUseProgram(0)

    def render_ground_grid(self, mvp: np.ndarray):
        """Renders concentric grid and colored X/Y/Z coordinate axes."""
        if not self.prog_flat:
            return

        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")

        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

        # Draw Grid Lines
        grid_lines = []
        grid_extent = 150.0
        step_minor = 10.0

        num_steps = int(grid_extent / step_minor)
        for i in range(-num_steps, num_steps + 1):
            coord = i * step_minor
            # lines parallel to X
            grid_lines.extend([-grid_extent, coord, 0.0, grid_extent, coord, 0.0])
            # lines parallel to Y
            grid_lines.extend([coord, -grid_extent, 0.0, coord, grid_extent, 0.0])

        grid_data = np.array(grid_lines, dtype=np.float32)

        GL.glUniform4f(loc_col, *theme.palette().grid_rgb01(), 0.72)
        self.set_line_width(1.0)
        # The ground grid is a backdrop. It must not reject body fragments when the camera is below XY.
        GL.glDepthMask(GL.GL_FALSE)
        self.draw_buffer_arrays(GL.GL_LINES, loc_pos, grid_data)
        GL.glDepthMask(GL.GL_TRUE)

        GL.glUseProgram(0)

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
        except Exception:
            pass

    def render_bodies(self, mvp: np.ndarray):
        """Renders shaded CAD bodies with sharp silhouette edges."""
        if not self.prog_solid or not self.prog_flat:
            return

        gpu_cache = getattr(self, "_body_gpu_cache", None)
        if gpu_cache is not None:
            live_bids = set(self.doc.bodies.keys())
            for k in list(gpu_cache.keys()):
                if k[0] not in live_bids:
                    self._delete_gpu_cache_entry(gpu_cache.pop(k))
        from omacad.ui.settings import get_settings
        tangent = bool(get_settings().get("show_tangent_edges", False))

        for body in self.doc.bodies.values():
            if not body.visible or not body.render_mesh:
                continue

            mesh = body.render_mesh
            override = getattr(self, "display_override", None)
            if self.section is not None and body.body_id in self.section["meshes"]:
                mesh = self.section["meshes"][body.body_id]   # the part left after the cut (of a tool's result too)
            elif override and body.body_id in override:
                mesh = override[body.body_id]   # a tool shows its finished result in place of the body (Fillet)
            if len(mesh.vertices) == 0:
                continue

            is_selected = body.selected
            edge_lines = np.vstack([mesh.sharp_lines, mesh.tangent_lines()]) if tangent else mesh.sharp_lines

            # Fetch or build GPU VAO/VBO for this body mesh
            cache_entry = None
            mesh_key = (body.body_id, id(mesh), len(mesh.vertices), len(edge_lines))
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


                    pos_data = np.ascontiguousarray(mesh.vertices, dtype=np.float32)
                    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo_pos)
                    GL.glBufferData(GL.GL_ARRAY_BUFFER, pos_data.nbytes, pos_data, GL.GL_STATIC_DRAW)
                    loc_pos_solid = GL.glGetAttribLocation(self.prog_solid, "in_pos")
                    GL.glEnableVertexAttribArray(loc_pos_solid)
                    GL.glVertexAttribPointer(loc_pos_solid, 3, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

                    norm_data = np.ascontiguousarray(mesh.normals, dtype=np.float32)
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

                # Color: Orange tint if selected, else body color
                if is_selected:
                    GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 1.0)
                else:
                    c = body.color
                    GL.glUniform4f(loc_col, c[0], c[1], c[2], c[3])

                # Push depth back slightly so crisp edges render cleanly on top
                GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
                GL.glPolygonOffset(1.0, 1.0)

                if cache_entry and cache_entry.get("vao_solid"):
                    GL.glBindVertexArray(cache_entry["vao_solid"])
                    GL.glDrawArrays(GL.GL_TRIANGLES, 0, cache_entry["vert_count"])
                    GL.glBindVertexArray(0)
                else:
                    loc_pos = GL.glGetAttribLocation(self.prog_solid, "in_pos")
                    loc_norm = GL.glGetAttribLocation(self.prog_solid, "in_normal")
                    self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, mesh.vertices, loc_norm, mesh.normals)

                GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
                GL.glUseProgram(0)

            # 2. Crisp Sharp Feature Edges
            if (self.show_edges or self.wireframe_only) and len(edge_lines) > 0:
                GL.glUseProgram(self.prog_flat)
                loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
                loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")

                GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())

                if is_selected:
                    GL.glUniform4f(loc_col, *theme.palette().highlight01(), 1.0)  # theme highlight
                    self.set_line_width(2.2)
                else:
                    GL.glUniform4f(loc_col, 0.12, 0.13, 0.15, 1.0)  # Dark CAD Edge
                    self.set_line_width(1.6)

                if cache_entry and cache_entry.get("vao_lines"):
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
            if normal_lines:
                if is_active:
                    is_fully_constrained = (sketch.dof == 0)
                    if is_fully_constrained:
                        scol = get_settings().sketch_fully_constrained_color_rgb01()
                        # On dark background or canvas, a subtle lighter rim keeps black lines visible
                        halo_col = (0.75, 0.78, 0.82, 0.75) if sum(theme.palette().canvas_rgb01()) / 3 < 0.5 else (0.03, 0.04, 0.06, 0.85)
                    else:
                        scol = get_settings().sketch_line_color_rgb01()
                        halo_col = (0.03, 0.04, 0.06, 0.85)
                    self.draw_thick_lines(mvp, normal_lines, (*scol, 1.0), line_w, halo_px=halo_px, halo_color=halo_col)
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
            if self.sketch_tool == "SPLINE":
                points = list(getattr(self, "_spline_points", []))
                if points:
                    if math.hypot(u2 - points[-1][0], v2 - points[-1][1]) > 1e-4:
                        points.append((u2, v2))
                    spline_preview = SketchSpline("preview", points)
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
