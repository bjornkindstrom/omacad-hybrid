"""Selection and picking mixin for Viewport3D: bodies, edges, planes, surfaces."""

from typing import Optional, List, Tuple
import math
import time
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from OpenGL import GL
import omacad.ui.viewport as _vp_pkg
from omacad.model.hover_info import describe_edge
from omacad.ui import theme
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect
from omacad.model.faces import ray_hit_face, ray_hit_faces, tangent_chain
from omacad.model.faces_edges import loop_contains


class PickerMixin:
    """Mixin providing body, edge, and plane picking operations for Viewport3D."""

    @staticmethod
    def _ray_hits_body_aabb(body, origin: np.ndarray, ray_dir: np.ndarray, max_t: float = float("inf"), margin: float = 1e-3) -> bool:
        """Fast slab test against a body's 3D bounding box to skip all faces/triangles when the ray misses the body."""
        mesh = getattr(body, "render_mesh", None)
        if mesh is None or getattr(mesh, "bounds_min", None) is None or getattr(mesh, "bounds_max", None) is None:
            return True
        bmin = np.asarray(mesh.bounds_min, dtype=float) - margin
        bmax = np.asarray(mesh.bounds_max, dtype=float) + margin
        inv_d = np.where(np.abs(ray_dir) > 1e-12, 1.0 / np.where(np.abs(ray_dir) > 1e-12, ray_dir, 1.0), np.inf)
        t1 = (bmin - origin) * inv_d
        t2 = (bmax - origin) * inv_d
        tmin = float(np.max(np.minimum(t1, t2)))
        tmax = float(np.min(np.maximum(t1, t2)))
        return tmax >= max(0.0, tmin) and tmin <= max_t

    def pick_body(self, x: float, y: float) -> Optional[str]:
        """Returns the body_id of the nearest 3D solid body under the cursor."""
        from omacad.model.faces import ray_mesh_hit
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best_t, best_id = float("inf"), None
        for bid, body in self.doc.bodies.items():
            if not self._ray_hits_body_aabb(body, origin, ray_dir, best_t):
                continue
            mesh = body.render_mesh
            if mesh is not None and len(mesh.vertices) > 0:
                hit = ray_mesh_hit(mesh, origin, ray_dir)
                if hit is not None and hit[0] < best_t:
                    best_t = hit[0]
                    best_id = bid
            faces = getattr(body, "faces", [])
            if len(faces):
                t = float(ray_hit_faces(faces, origin, ray_dir).min())
                if t < best_t:
                    best_t = t
                    best_id = bid
        return best_id

    # ---- Edge selection (fillet / chamfer) ------------------------------------------
    def begin_edge_pick(self):
        self.edge_pick_mode = True
        self.edge_xray = False
        self.hover_edge = None
        self.hover_face = self.hover_surface = None
        self.selected_edges = []
        self.setFocus()
        self.update()

    def end_edge_pick(self, cancelled: bool = False):
        self.edge_pick_mode = False
        self.hover_edge = None
        self.hover_face = self.hover_surface = None
        self.selected_edges = []
        if cancelled:
            self.edge_pick_cancelled.emit()
        self.update()

    @staticmethod
    def _same_edge(a, b) -> bool:
        return a.same_as(b)

    def _pick_edge(self, x: float, y: float):
        """The straight edge between two flat faces nearest the cursor (within 8 px, and not hidden)."""
        proj, view, _ = self.get_matrices()
        origin, _ = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        xray = self.edge_xray or bool(QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)
        best, best_d, best_eye = None, 8.0, 1e18
        for body in self.doc.bodies.values():
            if not body.visible:
                continue
            edges, pts, seg_edge, seg_start = self._edge_segments(body)
            if not edges:
                continue
            # every segment of every edge at once; only edges within reach go on to the (slow) hidden test
            seg_d = self._screen_segment_dists(pts, seg_start, x, y)
            edge_d = np.full(len(edges), np.inf)
            np.minimum.at(edge_d, seg_edge, seg_d)
            for k in np.flatnonzero(edge_d < best_d):
                d = float(edge_d[k])
                if d >= best_d:
                    continue
                e = edges[k]
                s = int(np.flatnonzero((seg_edge == k) & (seg_d == d))[0])
                mid = (pts[seg_start[s]] + pts[seg_start[s] + 1]) / 2.0
                direction = mid - origin
                dist = float(np.linalg.norm(direction))
                direction = direction / dist if dist > 1e-9 else direction
                blocked = (not xray) and any(
                    self._ray_hits_body_aabb(bd, origin, direction, dist + 1e-3)
                    and bool((ray_hit_faces(bd.faces, origin, direction) < dist - 2e-2).any())
                    for bd in self.doc.bodies.values() if bd.visible and len(bd.faces)
                )
                if not blocked:
                    # near-ties: a single piece (line or arc) beats the whole outline it belongs to, so a click
                    # takes one piece and a double-click the outline (Björn #104); otherwise the closer edge
                    piece = lambda a: getattr(a, "kind", "") in ("line", "circle")
                    piece_beats_loop = piece(e) and getattr(best, "kind", "") == "loop"
                    loop_loses = getattr(e, "kind", "") == "loop" and piece(best)
                    if d < best_d - 1.0 or (d <= best_d + 1.0 and (piece_beats_loop or (not loop_loses and dist < best_eye))):
                        best, best_d, best_eye = e, min(d, best_d), dist
        return best

    def _hidden_edge_at(self, x: float, y: float):
        """The edge under the cursor that only see-through picking reaches (None when see-through is on already)."""
        if self.edge_xray:
            return None
        self.edge_xray = True
        try:
            return self._pick_edge(x, y)
        finally:
            self.edge_xray = False

    def _edge_segments(self, body):
        """A body's edges as one flat set of segments, built once per rebuild of the body (its edge list is
        replaced then): (edges, points, edge index per segment, index of each segment's first point)."""
        cache = self.__dict__.setdefault("_edge_segment_cache", {})
        hit = cache.get(body.body_id)
        if hit is None or hit[0] is not body.edges:
            edges, polys = [], []
            for e in body.edges:
                p = np.asarray(e.polyline(), dtype=float).reshape(-1, 3)
                if len(p) >= 2:
                    edges.append(e)
                    polys.append(p)
            counts = np.array([len(p) for p in polys], dtype=int)
            firsts = np.concatenate([[0], np.cumsum(counts)[:-1]]) if polys else np.zeros(0, dtype=int)
            seg_edge = np.repeat(np.arange(len(polys)), np.maximum(counts - 1, 0))
            seg_start = np.concatenate([f + np.arange(c - 1) for f, c in zip(firsts, counts)]) if polys else np.zeros(0, dtype=int)
            pts = np.concatenate(polys) if polys else np.zeros((0, 3))
            hit = cache[body.body_id] = (body.edges, (edges, pts, seg_edge, seg_start.astype(int)))
        return hit[1]

    def project_points(self, pts: np.ndarray):
        """Screen x/y of many world points in one go, and which of them lie in front of the camera."""
        proj, view, _ = self.get_matrices()
        pv = np.asarray(proj, dtype=float) @ np.asarray(view, dtype=float)
        p = np.asarray(pts, dtype=float).reshape(-1, 3)
        clip = np.c_[p, np.ones(len(p))] @ pv.T
        front = clip[:, 3] > 0.001
        w = np.where(front, clip[:, 3], 1.0)
        screen = np.c_[(clip[:, 0] / w + 1.0) * 0.5 * self.width(), (1.0 - clip[:, 1] / w) * 0.5 * self.height()]
        return screen, front

    def _screen_segment_dists(self, pts: np.ndarray, seg_start: np.ndarray, x: float, y: float) -> np.ndarray:
        """Pixel distance from the cursor to each segment pts[i]-pts[i+1] (i in seg_start); inf behind the camera."""
        screen, front = self.project_points(pts)
        a, b = screen[seg_start], screen[seg_start + 1]
        ab = b - a
        length2 = np.einsum("ij,ij->i", ab, ab)
        t = np.clip(np.einsum("ij,ij->i", np.array([x, y]) - a, ab) / np.where(length2 > 1e-12, length2, 1.0), 0.0, 1.0)
        dist = np.hypot(*(a + t[:, None] * ab - (x, y)).T)
        dist[~(front[seg_start] & front[seg_start + 1])] = np.inf
        return dist

    def _edge_loop(self, e, other_face: bool = False):
        """Double-click: the edges joined end to end around one flat face (e.g. the whole top of a box).
        Of the two faces an edge borders, the one facing the camera is used."""
        outline = next((c for c in self._visible_edges() if c.kind == "loop" and loop_contains(c, e)), None)
        if outline is not None and not other_face:     # a piece of a rounded outline: the whole outline (Björn #104)
            return [outline]
        if e.kind in ("circle", "loop", "wrapped", "curve"):
            return [e]
        proj, view, _ = self.get_matrices()
        eye = np.linalg.inv(view)[:3, 3]
        mid = (e.p0 + e.p1) / 2.0
        to_eye = eye - mid
        n = e.n1 if float(e.n1 @ to_eye) >= float(e.n2 @ to_eye) else e.n2
        if other_face:   # Shift: the face on the other side of the edge (e.g. the riser instead of the tread)
            n = e.n2 if n is e.n1 else e.n1
        d = float(n @ e.p0)
        candidates = [c for b in self.doc.bodies.values() if b.visible for c in b.edges if c.kind == "line"
                      and abs(float(n @ c.p0) - d) < 1e-4 and abs(float(n @ c.p1) - d) < 1e-4]
        chain, frontier = [e], [e]
        while frontier:
            cur = frontier.pop()
            for c in candidates:
                if any(c.same_as(k) for k in chain):
                    continue
                if any(np.linalg.norm(a - b) < 1e-4 for a in (cur.p0, cur.p1) for b in (c.p0, c.p1)):
                    chain.append(c)
                    frontier.append(c)
        return chain

    def _pick_face(self, x: float, y: float):
        """Ray-pick the nearest visible planar body face under the cursor."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = _vp_pkg.ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_t = None, float("inf")
        for body in self.doc.bodies.values():
            if not body.visible or not self._ray_hits_body_aabb(body, origin, ray_dir, best_t):
                continue
            hits = ray_hit_faces(body.faces, origin, ray_dir, bary_tol=2e-4) if len(body.faces) else np.zeros(0)
            candidates = [(body.faces[i], float(hits[i])) for i in np.flatnonzero(np.isfinite(hits))]
            if getattr(self, "edge_pick_mode", False):
                from dataclasses import replace
                patches = {p.index: p for e in body.edges if e.kind == "wrapped" for p in e.patches}
                for p in patches.values():
                    t = ray_hit_face(p, origin, ray_dir)
                    if t is not None:
                        candidates.append((replace(p, body_id=body.body_id), t))
            for face, t in candidates:
                if t < best_t or (face.index < 0 and t <= best_t+1e-6):
                    best, best_t = (body, face), t
        if best is not None and self._surface_in_front(origin, ray_dir, best_t):
            return None                 # a curved surface (only planar faces are faces) hides it
        return best

    def _surface_in_front(self, origin, ray_dir, t: float, tol: float = 2e-2) -> bool:
        """Any visible body surface is hit more than `tol` before `t` along the ray."""
        from omacad.model.faces import ray_mesh_hit
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or not len(mesh.vertices) \
                    or not self._ray_hits_body_aabb(body, origin, ray_dir, t - tol):
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and hit[0] < t - tol:
                return True
        return False


    def _edges_of_face(self, face, body) -> list:
        """All edges forming the boundary and holes of a planar face: closed loops, lines and circles together."""
        if face.index < 0:
            return [e for e in body.edges if e.kind == "wrapped"
                    and any(p.index == face.index for p in e.patches)]
        n = np.asarray(face.normal, dtype=float)
        orig = np.asarray(face.origin, dtype=float)
        res = []
        for e in body.edges:
            kind = getattr(e, "kind", "")
            if kind == "loop":
                ok = abs(float(e.n @ n) - 1.0) < 1e-2 and abs(float((e.centroid - orig) @ n)) < 1e-3
            elif kind == "line":
                ok = abs(float((e.p0 - orig) @ n)) < 1e-3 and abs(float((e.p1 - orig) @ n)) < 1e-3 \
                    and (abs(float(e.n1 @ n) - 1.0) < 1e-2 or abs(float(e.n2 @ n) - 1.0) < 1e-2)
            elif kind == "circle":
                ok = abs(float((e.center - orig) @ n)) < 1e-3 and abs(abs(float(e.axis @ n)) - 1.0) < 1e-2
            else:
                ok = False
            if ok and _on_face_outline(e, face):   # not an edge of another face in the same plane
                res.append(e)
        loops = [e for e in res if e.kind == "loop"]   # an outline already holds its pieces
        return [e for e in res if not any(loop_contains(lp, e) for lp in loops)]

    def _idle_hover_ok(self) -> bool:
        """Nothing is being edited: edges and faces under the cursor light up so a right-click can fillet them."""
        return not (self.edge_pick_mode or self.plane_pick_mode or self.doc.active_sketch or self.move_gizmo
                    or self._move or self.active_tool_title())

    def _update_edge_hover(self, x: float, y: float):
        e = self._pick_edge(x, y)
        face = None
        if e is None:
            hit = self._pick_face(x, y)
            if hit is not None:
                face = hit[1]
        edge_changed = (e is None) != (self.hover_edge is None) or (e is not None and not self._same_edge(e, self.hover_edge))
        # the same triangles, not only the same number: a rebuilt (moved) body numbers its faces the same (Björn #112)
        old_face = self.hover_face
        face_changed = (face is None) != (old_face is None) or (face is not None and (
            face.body_id != old_face.body_id or face.index != old_face.index or face.tris is not old_face.tris))
        surface = self._pick_curved_surface(x, y) if e is None and face is None and not self.edge_pick_mode else None
        old = self.hover_surface
        surface_changed = (surface is None) != (old is None) or (surface is not None and (
            surface[0] != old[0] or surface[1].shape != old[1].shape or not np.array_equal(surface[1][0], old[1][0])))
        if edge_changed or face_changed or surface_changed:
            self.hover_edge = e
            self.hover_face = face
            self.hover_surface = surface
            if edge_changed:
                self.hover_info_changed.emit(describe_edge(e) if e is not None else None)
            self.update()

    def _pick_curved_surface(self, x: float, y: float):
        """(body_id, triangles) of the curved surface (a fillet, a round wall) nearest under the cursor, or None
        when a flat face or nothing is there. Only for the hover highlight: curved surfaces are not faces."""
        from omacad.model.faces import ray_mesh_hit
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best = None
        for body in self.doc.bodies.values():
            mesh = self._pick_mesh(body)
            if not body.visible or mesh is None or not len(mesh.vertices) \
                    or not self._ray_hits_body_aabb(body, origin, ray_dir, best[0] if best else float("inf")):
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], hit[1], mesh, body.body_id)
        if best is None:
            return None
        _, tri, mesh, body_id = best
        tris = mesh.curved_surface(tri) if hasattr(mesh, "curved_surface") else None
        return None if tris is None else (body_id, tris)

    def _visible_edges(self):
        return [c for b in self.doc.bodies.values() if b.visible for c in b.edges]

    def _toggle_edge(self, e):
        """Click: the edge and everything joined to it smoothly is added, or removed if `e` is already picked."""
        chain = tangent_chain(e, self._visible_edges()) if getattr(self, "edge_tangent_chain", True) else [e]
        if any(self._same_edge(sel, e) for sel in self.selected_edges):
            self.selected_edges = [s for s in self.selected_edges if not any(self._same_edge(s, c) for c in chain)]
        else:
            self.selected_edges += [c for c in chain if not any(self._same_edge(c, s) for s in self.selected_edges)]
        self.edges_selection_changed.emit()
        self.update()

    def render_edge_pick(self, mvp: np.ndarray):
        if not (self.edge_pick_mode or self._idle_hover_ok()):
            return
        # If hovering a face, highlight it with translucent flat shading
        if self.hover_face is not None and self.hover_edge is None and self.prog_flat is not None:
            GL.glUseProgram(self.prog_flat)
            loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
            loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
            loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
            GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
            GL.glDepthMask(GL.GL_FALSE)
            GL.glDisable(GL.GL_DEPTH_TEST)
            lift = self.hover_face.normal * 0.05
            tris = (self.hover_face.tris + lift).reshape(-1, 3).astype(np.float32)
            GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 0.35)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
            GL.glDepthMask(GL.GL_TRUE)
            GL.glEnable(GL.GL_DEPTH_TEST)
        if self.hover_surface is not None and self.hover_edge is None and self.prog_flat is not None:
            # depth-tested (the back of a round wall stays hidden), pulled forward so it is not lost in the body
            GL.glUseProgram(self.prog_flat)
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self.prog_flat, "u_mvp"), 1, GL.GL_TRUE, mvp.flatten())
            GL.glUniform4f(GL.glGetUniformLocation(self.prog_flat, "u_color"), *theme.palette().highlight01(0.1), 0.35)
            GL.glDepthMask(GL.GL_FALSE)
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(-2.0, -2.0)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, GL.glGetAttribLocation(self.prog_flat, "in_pos"),
                                    self.hover_surface[1].reshape(-1, 3).astype(np.float32))
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glDepthMask(GL.GL_TRUE)

        if self.prog_thick is None:
            return
        GL.glDisable(GL.GL_DEPTH_TEST)
        def flat(edges):
            out = []
            for e in edges:
                pts = e.polyline()
                for i in range(len(pts) - 1):
                    out += [*pts[i], *pts[i + 1]]
            return out

        if self.edge_xray:   # every pickable edge, also the hidden ones
            self.draw_thick_lines(mvp, flat([e for b in self.doc.bodies.values() if b.visible for e in b.edges]), (0.75, 0.8, 0.9, 0.55), 1.6)
        if self.hover_edge is not None and not any(self._same_edge(self.hover_edge, s) for s in self.selected_edges):
            from omacad.ui.settings import hover_line_style
            hv_col, hv_w = hover_line_style()
            self.draw_thick_lines(mvp, flat([self.hover_edge]), hv_col, hv_w)
        if self.selected_edges:
            self.draw_thick_lines(mvp, flat(self.selected_edges), (*theme.palette().highlight01(), 1.0), 4.0)
        GL.glEnable(GL.GL_DEPTH_TEST)

    def set_step_edges(self, edges):
        self.step_edges = list(edges or [])
        self.update()

    def render_step_edges(self, mvp: np.ndarray):
        """The edges of the Fillet/Chamfer step chosen in the timeline (or open for editing), in dark blue and
        through the material, so you can tell which of several rounds it is."""
        if not self.step_edges or self.prog_thick is None:
            return
        segs = []
        for e in self.step_edges:
            pts = e.polyline()
            for i in range(len(pts) - 1):
                segs += [*pts[i], *pts[i + 1]]
        GL.glDisable(GL.GL_DEPTH_TEST)
        self.draw_thick_lines(mvp, segs, (0.05, 0.22, 0.78, 1.0), 4.5)
        GL.glEnable(GL.GL_DEPTH_TEST)

    # ---- Sketch element selection --------------------------------------------

    def begin_plane_pick(self, purpose: str = "sketch"):
        self.plane_pick_purpose = purpose
        self.plane_pick_mode = True
        self.hover_plane = None
        self.setFocus()
        self.update()

    def end_plane_pick(self, cancelled: bool = False):
        self.plane_pick_mode = False
        self.hover_plane = None
        self.hover_patch = None
        self.highlighted_faces = []
        if cancelled:
            self.plane_pick_cancelled.emit()
        self.plane_pick_purpose = "sketch"
        self.update()

    def _origin_quadrant_size(self) -> float:
        """Side of the marker drawn for each origin plane: only its first quadrant (positive u and v), kept small."""
        ext = 20.0
        for b in self.doc.bodies.values():
            if b.visible and b.render_mesh is not None and len(b.render_mesh.vertices):
                ext = max(ext, float(np.abs(b.render_mesh.bounds_min).max()) * 0.75,
                          float(np.abs(b.render_mesh.bounds_max).max()) * 0.75)
        return ext

    def _plane_rect(self, plane) -> tuple[float, float, float, float]:
        """Plane marker as (u0, u1, v0, v1): the projected bounds of the visible bodies plus a 5 % margin
        (a small square around the plane origin on an empty model), not a square out to the farthest corner."""
        us, vs = [], []
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or not len(mesh.vertices):
                continue
            lo, hi = np.asarray(mesh.bounds_min), np.asarray(mesh.bounds_max)
            for x in (lo[0], hi[0]):
                for y in (lo[1], hi[1]):
                    for z in (lo[2], hi[2]):
                        u, v = plane.world_to_uv(np.array([x, y, z], dtype=float))
                        us.append(float(u))
                        vs.append(float(v))
        if not us:
            return -10.0, 10.0, -10.0, 10.0
        margin = 0.05 * max(max(us) - min(us), max(vs) - min(vs), 20.0)
        return min(us) - margin, max(us) + margin, min(vs) - margin, max(vs) + margin

    @staticmethod
    def _rect_corners(plane, rect):
        u0, u1, v0, v1 = rect
        return [plane.uv_to_world(u0, v0), plane.uv_to_world(u1, v0), plane.uv_to_world(u1, v1), plane.uv_to_world(u0, v1)]

    def _pick_plane_target(self, x: float, y: float):
        """Nearest origin plane (within its drawn quad) or planar body face under the cursor."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = _vp_pkg.ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_t = None, float("inf")
        only_origin = self.plane_pick_mode and self.plane_pick_purpose == "offset_origin_only"
        shell_pick = self.plane_pick_mode and self.plane_pick_purpose in ("shell_face", "offset_face")
        thread_pick = self.plane_pick_mode and self.plane_pick_purpose in ("thread_surface", "pattern_axis")
        if shell_pick or thread_pick:
            candidates = []
        else:
            candidates = [(("origin", n), pl) for n, pl in self.doc.origin_planes.items()
                          if self.plane_pick_mode or self.doc.origin_visible("plane", n)]   # a hidden plane is not there
            if not only_origin:
                candidates += [(("cplane", pid), self.doc.construction_plane(pid))
                               for pid, c in self.doc.construction_planes.items() if c.get("visible", True)]
        for key, plane in candidates:
            hit = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
            if hit is None:
                continue
            u, v = plane.world_to_uv(hit)
            t = float(np.linalg.norm(hit - origin))
            u0, u1, v0, v1 = self._plane_rect(plane)
            inside = u0 <= u <= u1 and v0 <= v <= v1
            if inside and t < best_t:
                best, best_t = key, t
        # Body faces take priority over origin planes (a plane passing through a body
        # would otherwise hide the faces behind it)
        face_best, face_t = None, float("inf")
        for body in ([] if only_origin else self.doc.bodies.values()):
            if shell_pick and self.shell_target_body_id:   # the body is hidden behind its preview; only its faces count
                if body.body_id != self.shell_target_body_id:
                    continue
            elif shell_pick and not body.visible:
                continue
            elif not body.visible:
                continue
            if len(body.faces):
                hits = ray_hit_faces(body.faces, origin, ray_dir, bary_tol=2e-4)
                i = int(np.argmin(hits))
                if hits[i] < face_t:
                    face_best, face_t = ("face", body.faces[i]), float(hits[i])
        if face_best is not None:
            return face_best
        return best

    def _update_plane_hover(self, x: float, y: float):
        hover = self._pick_plane_target(x, y)

        def key(h):
            return None if h is None else (h[0], h[1] if h[0] in ("origin", "cplane") else (h[1].body_id, h[1].index))
        if key(hover) != key(self.hover_plane):
            self.hover_plane = hover
            self.update()

    def _update_idle_plane_hover(self, x: float, y: float):
        """Without a tool, an origin or construction plane under the cursor lights up (a body in front wins)."""
        hit = self._pick_plane_target(x, y)
        key = hit if hit is not None and hit[0] in ("origin", "cplane") else None
        if key != self.hover_plane:
            self.hover_plane = key
            self.update()

    def set_preview_plane(self, plane):
        self.preview_plane = plane
        self.update()

    def _pick_cylinder_surface(self, x: float, y: float) -> Optional[dict]:
        """Detect if clicked/hovered surface is a cylindrical face (bolt or hole) or return hit info."""
        from omacad.model.faces import ray_mesh_hit, detect_cylinder_surface
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best = None
        only = self.shell_target_body_id if self.plane_pick_purpose == "offset_face" else ""
        for body in self.doc.bodies.values():
            mesh = self._pick_mesh(body)
            if (only and body.body_id != only) or (not only and not body.visible) or mesh is None or len(mesh.vertices) == 0:
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], body.body_id, mesh, hit[1])
        if best is None:
            return None
        t, body_id, mesh, tri = best
        cyl_info = detect_cylinder_surface(mesh, tri)
        if cyl_info is not None:
            cyl_info["body_id"] = body_id
            cyl_info["t"] = float(t)
            return cyl_info
        return None

    def _pick_mesh(self, body):
        """The mesh the user sees: the part left of a section view, so clicks reach the cut face, not the half that is cut away."""
        if self.section is not None and body.body_id in self.section["meshes"]:
            return self.section["meshes"][body.body_id]
        return body.render_mesh

    def _section_keeps(self, point) -> bool:
        """False for a point on the side of the section plane that is cut away."""
        sec = self.section
        if sec is None:
            return True
        n = sec["normal"]
        keep = n if sec["flip"] else -n
        return float(keep @ (np.asarray(point, dtype=float) - (sec["origin"] + n * sec["offset"]))) >= -1e-6

    def _update_offset_hover(self, x: float, y: float):
        """Offset Face: the flat face or the curved surface (cylinder, thread...) under the cursor lights up."""
        now = time.monotonic()
        if now - self._hover_patch_time < 0.06:          # finding a smooth patch is not free: at most ~16 times a second
            return
        self._hover_patch_time = now
        surf = self._pick_surface(x, y)
        face, patch = None, None
        if surf is not None:
            target = self._pick_plane_target(x, y)
            if target is not None and target[0] == "face":
                proj, view, _ = self.get_matrices()
                origin, ray_dir = _vp_pkg.ray_from_screen(x, y, self.width(), self.height(), view, proj)
                t_face = ray_hit_face(target[1], origin, ray_dir)
                if t_face is not None and t_face <= surf["t"] + 1e-4:
                    face = target[1]
            if face is None:
                patch = surf["patch"]
        old = self.hover_plane
        new = ("face", face) if face is not None else None
        same_face = (old is None) == (new is None) and (new is None or (old[1].body_id, old[1].index) == (face.body_id, face.index))
        same_patch = (patch is None and self.hover_patch is None) or (
            patch is not None and self.hover_patch is not None and patch.shape == self.hover_patch.shape
            and np.allclose(patch[0], self.hover_patch[0]) and np.allclose(patch[-1], self.hover_patch[-1]))
        if not (same_face and same_patch):
            self.hover_plane, self.hover_patch = new, patch
            self.update()

    def _offset_face_click(self, x: float, y: float):
        """Offset Face: the nearest of a flat face and a cylinder under the cursor is picked."""
        from omacad.model.features.offset_face import cylinder_face_ref, plane_face_ref, surface_face_ref
        surf = self._pick_surface(x, y)     # what the cursor touches first, flat or curved
        if surf is None:
            return
        target = self._pick_plane_target(x, y)
        if target is not None and target[0] == "face":
            face = target[1]
            proj, view, _ = self.get_matrices()
            origin, ray_dir = _vp_pkg.ray_from_screen(x, y, self.width(), self.height(), view, proj)
            t_face = ray_hit_face(face, origin, ray_dir)
            if t_face is not None and t_face <= surf["t"] + 1e-4 and self._section_keeps(origin + t_face * ray_dir):
                self.offset_face_picked.emit(plane_face_ref(face), face.body_id)
                return
        cyl = self._pick_cylinder_surface(x, y)
        if cyl is not None:
            self.offset_face_picked.emit(cylinder_face_ref(cyl), cyl["body_id"])
        else:
            self.offset_face_picked.emit(surface_face_ref(surf), surf["body_id"])

    def _pick_surface(self, x: float, y: float):
        """Any body surface under the cursor (curved ones too): the hit point and its smooth patch of vertices."""
        from omacad.model.faces import ray_mesh_hit, smooth_patch_vertices
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best = None
        only = self.shell_target_body_id if self.plane_pick_purpose == "offset_face" else ""
        for body in self.doc.bodies.values():
            mesh = self._pick_mesh(body)
            if (only and body.body_id != only) or (not only and not body.visible) or mesh is None or len(mesh.vertices) == 0:
                continue
            hit = ray_mesh_hit(mesh, origin, ray_dir)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = (hit[0], mesh, hit[1], body.body_id)
        if best is None:
            return None
        t, mesh, tri, body_id = best
        corner = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3)[tri]
        normal = np.cross(corner[1] - corner[0], corner[2] - corner[0])
        return {"point": np.asarray(origin, dtype=float) + t * np.asarray(ray_dir, dtype=float),
                "patch": smooth_patch_vertices(mesh, tri), "t": float(t), "body_id": body_id,
                "normal": normal / max(float(np.linalg.norm(normal)), 1e-12)}

    def plane_from_target(self, target):
        from omacad.model.sketch import SketchPlane
        kind, payload = target
        if kind == "origin":
            return SketchPlane.create_named(payload)
        if kind == "cplane":
            return self.doc.construction_plane(payload)
        p = SketchPlane.from_face(payload.normal, payload.origin).centered_on(payload.tris)
        p.face = payload
        return p

    PLANE_COLORS = {"XY": (0.30, 0.55, 1.0), "XZ": (0.35, 0.85, 0.40), "YZ": (1.0, 0.40, 0.35)}
    CPLANE_COLOR = (0.75, 0.55, 0.95)

    def _plane_quads(self):
        """The origin and construction planes drawn right now: (key, name, four world corners, rgb).
        Their visible bounds cover the projected bounds of visible bodies."""
        out = []
        picking = self.plane_pick_mode and self.plane_pick_purpose not in ("offset_surface", "shell_face", "thread_surface", "offset_face", "pattern_axis")
        for name, plane in self.doc.origin_planes.items():
            if (picking or (not self.plane_pick_mode and self.doc.origin_visible("plane", name))):
                corners = self._rect_corners(plane, self._plane_rect(plane))
                out.append((("origin", name), f"{name} Plane", corners, self.PLANE_COLORS[name]))
        if not (self.plane_pick_mode and self.plane_pick_purpose in ("offset_surface", "shell_face", "offset_face")):
            for pid, c in self.doc.construction_planes.items():
                if c.get("visible", True):
                    plane = self.doc.construction_plane(pid)
                    corners = self._rect_corners(plane, self._plane_rect(plane))
                    out.append((("cplane", pid), c.get("name", pid), corners, self.CPLANE_COLOR))
        return out

    def render_plane_pick(self, mvp: np.ndarray):
        """Translucent origin-plane quads and hovered face while choosing a sketch plane."""
        quads = self._plane_quads()
        if (not self.plane_pick_mode and self.ctx_face is None and not quads and self.preview_plane is None) or not self.prog_flat:
            return
        GL.glUseProgram(self.prog_flat)
        loc_mvp = GL.glGetUniformLocation(self.prog_flat, "u_mvp")
        loc_col = GL.glGetUniformLocation(self.prog_flat, "u_color")
        loc_pos = GL.glGetAttribLocation(self.prog_flat, "in_pos")
        GL.glUniformMatrix4fv(loc_mvp, 1, GL.GL_TRUE, mvp.flatten())
        GL.glDepthMask(GL.GL_FALSE)
        GL.glDisable(GL.GL_DEPTH_TEST)
        half = self._origin_quadrant_size() / 2
        if self.preview_plane is not None:
            pl = self.preview_plane
            centre = np.asarray(getattr(pl, "display_origin", pl.origin), dtype=float)
            quads = quads + [(None, "", [centre - half * pl.u_axis - half * pl.v_axis,
                                         centre + half * pl.u_axis - half * pl.v_axis,
                                         centre + half * pl.u_axis + half * pl.v_axis,
                                         centre - half * pl.u_axis + half * pl.v_axis], (1.0, 0.65, 0.2))]
        for key, _name, corners, (r, g, b) in quads:
            hovered = key is not None and self.hover_plane == key        # also without a tool: the plane lights up
            fill = 0.25 if key is None else (0.42 if hovered else (0.14 if key[0] == "origin" else 0.10))
            quad = np.array([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, fill)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, quad)
            outline = np.array([c for i in range(4) for c in (corners[i], corners[(i + 1) % 4])], dtype=np.float32)
            GL.glUniform4f(loc_col, r, g, b, 0.95 if (hovered or key is None) else 0.5)
            self.set_line_width(1.5)
            self.draw_buffer_arrays(GL.GL_LINES, loc_pos, outline)
        shown = self.hover_plane if self.plane_pick_mode else (("face", self.ctx_face) if self.ctx_face is not None else None)
        if shown and shown[0] == "face":
            face = shown[1]
            lift = face.normal * 0.05  # avoid z-fighting with the body surface
            tris = (face.tris + lift).reshape(-1, 3).astype(np.float32)
            GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 0.55)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        if self.plane_pick_mode and self.hover_patch is not None and len(self.hover_patch):
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(-1.0, -1.0)               # on top of the surface it covers, hidden behind the model
            GL.glUniform4f(loc_col, *theme.palette().highlight01(0.1), 0.55)
            self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, self.hover_patch.astype(np.float32))
            GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glDisable(GL.GL_DEPTH_TEST)
        for hf in self.highlighted_faces:
            face = getattr(hf, "face", hf) if not isinstance(hf, dict) else None
            if face is not None and hasattr(face, "tris"):
                lift = face.normal * 0.05
                tris = (face.tris + lift).reshape(-1, 3).astype(np.float32)
                GL.glUniform4f(loc_col, 0.95, 0.35, 0.25, 0.6)  # warm red/coral for open faces
                self.draw_buffer_arrays(GL.GL_TRIANGLES, loc_pos, tris)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glUseProgram(0)

    def align_to_plane(self, plane):
        """Orbits the camera so it looks straight at the given sketch plane."""
        n = np.asarray(plane.normal, dtype=np.float64)
        el = math.degrees(math.asin(max(-1.0, min(1.0, float(n[2])))))
        if abs(n[2]) > 0.999:
            self.azimuth = 0.0
            self.elevation = 89.9 if n[2] > 0 else -89.9
        else:
            self.azimuth = math.degrees(math.atan2(n[0], -n[1])) % 360.0
            self.elevation = el
        self.update()

    def look_at_active_plane(self):
        """Aligns camera orthogonally to current active sketch plane."""
        if self.doc.active_sketch:
            self.align_to_plane(self.doc.active_sketch.plane)

    def toggle_construction_mode(self):
        """Toggles construction geometry creation mode (X key)."""
        self.construction_mode = not self.construction_mode
        self.construction_mode_changed.emit(self.construction_mode)
        self.update()

    def world_to_screen(self, world_pt: np.ndarray) -> Optional[Tuple[float, float]]:
        """Projects a 3D point in world space to 2D screen viewport coordinates."""
        screen, front = self.project_points(world_pt)
        return (float(screen[0, 0]), float(screen[0, 1])) if front[0] else None


def _on_face_outline(edge, face, tol: float = 1e-2) -> bool:
    """A point of `edge` lies on a side of one of the face's triangles (the outline runs along them)."""
    pl = edge.polyline()
    p = (pl[0] + pl[1]) / 2 if edge.kind == "line" else pl[0]
    a = face.tris.reshape(-1, 3)
    b = np.roll(face.tris, -1, axis=1).reshape(-1, 3)
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-18), 0.0, 1.0)
    return bool(np.min(np.linalg.norm(a + ab * t[:, None] - p, axis=1)) < tol)
