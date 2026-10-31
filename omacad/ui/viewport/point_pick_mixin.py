"""Picking a point on a body in the 3D view (Move / Rotate from a point, point to point).

While picking, the snap points of the bodies near the cursor show as dots: green for the end of a straight
edge, orange for the sharp corner a rounding hides, with dashed guide lines from the rounding to that
corner, blue for the centre of a flat face or a circle. Points hidden behind a body are left out, and the
dots are projected again on every repaint so they stay on the body while the camera moves. The world
origin can be picked too. A click emits `point_picked` with {"body", "kind", "xyz"}."""

import math
import numpy as np
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPen

from omacad.model.body_points import body_points
from omacad.model.faces import ray_mesh_hit
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect

SNAP_PX = 12.0       # the cursor catches a point this close
SHOW_PX = 90.0       # points (and hidden corners' guide lines) this close are shown


class PointPickMixin:
    def begin_hole_place(self, plane, points=()):
        self.hole_place_mode = True
        self.hole_place_plane = plane
        self.hole_place_points = list(points)
        self.hole_place_segments = self._hole_reference_segments(plane)
        self.hole_dyn_texts = ["", ""]
        self.hole_dyn_focus = 0
        self._hole_place_hover(0, 0)
        self.setFocus()
        self.update()

    def end_hole_place(self):
        self.hole_place_mode = False
        self.hole_place_hover = None
        self._hole_last_effective_world = None
        self._hole_badge_rects = []
        self.hole_place_segments = []
        self.hole_dyn_texts = ["", ""]
        self.hole_dyn_focus = 0
        self.update()

    def clear_hole_place(self):
        self.end_hole_place()
        self.hole_place_plane = None
        self.hole_place_points = []
        self.hole_place_segments = []
        self.hole_dyn_texts = ["", ""]
        self.hole_dyn_focus = 0
        self.update()

    def _hole_reference_segments(self, plane):
        """Straight edge segments on or projected to `plane`, for measuring placement like Smart Circle."""
        if plane is None or not self.doc.bodies:
            return []
        o = np.asarray(plane.origin, dtype=np.float64)
        n = np.asarray(plane.normal, dtype=np.float64)
        ua = np.asarray(plane.u_axis, dtype=np.float64)
        va = np.asarray(plane.v_axis, dtype=np.float64)
        segs = []
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or len(mesh.sharp_lines) == 0:
                continue
            lines = np.asarray(mesh.sharp_lines, dtype=np.float64).reshape(-1, 2, 3)
            d0 = np.abs((lines[:, 0, :] - o) @ n)
            d1 = np.abs((lines[:, 1, :] - o) @ n)
            coplanar = (d0 < 1e-4) & (d1 < 1e-4)
            use_lines = lines[coplanar] if coplanar.any() else lines
            pts = use_lines - o
            uv = np.stack([pts @ ua, pts @ va], axis=-1)
            segs.append(uv)
        if not segs:
            return []
        allseg = np.concatenate(segs)
        r = np.round(allseg, 3)
        swap = (r[:, 0, 0] > r[:, 1, 0]) | ((r[:, 0, 0] == r[:, 1, 0]) & (r[:, 0, 1] > r[:, 1, 1]))
        r[swap] = r[swap][:, ::-1]
        key = r.reshape(len(r), 4)
        _, idx = np.unique(key, axis=0, return_index=True)
        segs = allseg[np.sort(idx)]
        out = []
        for s in segs:
            p1, p2 = (float(s[0, 0]), float(s[0, 1])), (float(s[1, 0]), float(s[1, 1]))
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 1e-4:
                out.append((p1, p2, None))
        return out

    def _hole_place_at(self, x, y):
        proj, view, _ = self.get_matrices()
        origin, direction = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        p = self.hole_place_plane
        return ray_plane_intersect(origin, direction, p.origin, p.normal)

    def _hole_place_hover(self, x, y):
        self.hole_place_hover = self._hole_place_at(x, y) if self.hole_place_plane is not None else None
        self.update()

    def _hole_place_press(self, x, y):
        plane = self.hole_place_plane
        if plane is None:
            return False
        point_data = self._hole_place_resolve_point(x, y)
        if point_data is None:
            return False
        self.hole_place_points.append(point_data["origin"])
        self.hole_point_picked.emit(point_data)
        self.hole_dyn_texts = ["", ""]
        self.hole_dyn_focus = 0
        self.update()
        return True

    def _hole_place_resolve_point(self, x=None, y=None):
        plane = self.hole_place_plane
        if plane is None:
            return None
        if x is not None and y is not None:
            point = self._hole_place_at(x, y)
        else:
            point = self.hole_place_hover
        if point is None:
            return None
        hp = np.asarray(point, dtype=float)
        try:
            cur_uv = np.asarray(plane.world_to_uv(hp), dtype=float)
        except Exception:
            rel = hp - np.asarray(plane.origin, dtype=float)
            cur_uv = np.array([float(rel @ np.asarray(plane.u_axis, dtype=float)),
                               float(rel @ np.asarray(plane.v_axis, dtype=float))])
        from omacad.ui import smart_circle
        from omacad.model import expr
        segs = getattr(self, "hole_place_segments", None)
        texts = getattr(self, "hole_dyn_texts", ["", ""])
        seg1, seg2 = None, None
        d1_val, d2_val = None, None
        d1_expr, d2_expr = None, None
        refs = []

        if segs:
            seg1 = smart_circle.nearest_line(segs, (float(cur_uv[0]), float(cur_uv[1])))
            if seg1 is not None:
                n1 = smart_circle.line_normal(seg1)
                seg2 = smart_circle.nearest_line(segs, (float(cur_uv[0]), float(cur_uv[1])), not_parallel_to=n1)

        if seg1 is not None:
            raw_d1 = abs(smart_circle.signed_distance(seg1, (float(cur_uv[0]), float(cur_uv[1]))))
            if texts[0].strip():
                try:
                    d1_val = abs(float(expr.evaluate(texts[0].strip(), self.doc.parameter_values())))
                    d1_expr = None if expr.is_plain_number(texts[0].strip()) else texts[0].strip()
                except Exception:
                    d1_val = raw_d1
            else:
                d1_val = raw_d1

        if seg2 is not None:
            raw_d2 = abs(smart_circle.signed_distance(seg2, (float(cur_uv[0]), float(cur_uv[1]))))
            if texts[1].strip():
                try:
                    d2_val = abs(float(expr.evaluate(texts[1].strip(), self.doc.parameter_values())))
                    d2_expr = None if expr.is_plain_number(texts[1].strip()) else texts[1].strip()
                except Exception:
                    d2_val = raw_d2
            else:
                d2_val = raw_d2

        final_uv = cur_uv.copy()
        if seg1 is not None and d1_val is not None and seg2 is not None and d2_val is not None:
            try:
                p1, p2 = np.array(seg1[0]), np.array(seg1[1])
                v1 = p2 - p1
                dir1 = v1 / max(float(np.linalg.norm(v1)), 1e-12)
                norm1 = np.array([-dir1[1], dir1[0]])
                side1 = 1.0 if (cur_uv - p1) @ norm1 >= 0 else -1.0
                k1 = p1 @ norm1 + side1 * d1_val

                p3, p4 = np.array(seg2[0]), np.array(seg2[1])
                v2 = p4 - p3
                dir2 = v2 / max(float(np.linalg.norm(v2)), 1e-12)
                norm2 = np.array([-dir2[1], dir2[0]])
                side2 = 1.0 if (cur_uv - p3) @ norm2 >= 0 else -1.0
                k2 = p3 @ norm2 + side2 * d2_val

                A = np.vstack([norm1, norm2])
                b = np.array([k1, k2])
                final_uv = np.linalg.solve(A, b)
            except Exception:
                final_uv = cur_uv
        elif seg1 is not None and d1_val is not None:
            try:
                p1, p2 = np.array(seg1[0]), np.array(seg1[1])
                v1 = p2 - p1
                dir1 = v1 / max(float(np.linalg.norm(v1)), 1e-12)
                norm1 = np.array([-dir1[1], dir1[0]])
                side1 = 1.0 if (cur_uv - p1) @ norm1 >= 0 else -1.0
                k1 = p1 @ norm1 + side1 * d1_val
                t = float((cur_uv - p1) @ dir1)
                final_uv = p1 + t * dir1 + norm1 * (side1 * d1_val)
            except Exception:
                final_uv = cur_uv

        if hasattr(plane, "uv_to_world"):
            w = plane.uv_to_world(float(final_uv[0]), float(final_uv[1]))
        else:
            w = (np.asarray(plane.origin, dtype=float) + np.asarray(plane.u_axis, dtype=float) * float(final_uv[0])
                 + np.asarray(plane.v_axis, dtype=float) * float(final_uv[1]))
        final_world = np.asarray(w, dtype=float).tolist()

        if seg1 is not None and d1_val is not None:
            refs.append({
                "p1": [float(seg1[0][0]), float(seg1[0][1])],
                "p2": [float(seg1[1][0]), float(seg1[1][1])],
                "dist": float(d1_val),
                "expr": d1_expr,
            })
        if seg2 is not None and d2_val is not None:
            refs.append({
                "p1": [float(seg2[0][0]), float(seg2[0][1])],
                "p2": [float(seg2[1][0]), float(seg2[1][1])],
                "dist": float(d2_val),
                "expr": d2_expr,
            })

        plane_info = {
            "origin": [float(x) for x in plane.origin],
            "normal": [float(x) for x in plane.normal],
            "u_axis": [float(x) for x in getattr(plane, "u_axis", [1, 0, 0])],
            "v_axis": [float(x) for x in getattr(plane, "v_axis", [0, 1, 0])],
        }
        return {
            "origin": final_world,
            "normal": [float(x) for x in plane.normal],
            "plane": plane_info,
            "refs": refs,
            "final_uv": (float(final_uv[0]), float(final_uv[1])),
            "seg1": seg1,
            "d1_val": d1_val,
            "seg2": seg2,
            "d2_val": d2_val,
        }

    def _hole_key(self, event) -> bool:
        """Handle keyboard typing for hole smart dimension boxes."""
        key = event.key()
        txt = event.text()
        texts = getattr(self, "hole_dyn_texts", ["", ""])
        focus = getattr(self, "hole_dyn_focus", 0)

        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.hole_dyn_focus = 1 - focus
            self.update()
            return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            plane = getattr(self, "hole_place_plane", None)
            if plane is not None and getattr(self, "hole_place_hover", None) is not None:
                pt_data = self._hole_place_resolve_point()
                if pt_data is not None:
                    self.hole_place_points.append(pt_data["origin"])
                    self.hole_point_picked.emit(pt_data)
                    self.hole_dyn_texts = ["", ""]
                    self.hole_dyn_focus = 0
                    self.update()
                    return True
            return False

        if key == Qt.Key.Key_Backspace:
            if texts[focus]:
                texts[focus] = texts[focus][:-1]
                self.update()
                return True
            elif focus > 0:
                self.hole_dyn_focus = 0
                self.update()
                return True
            return False

        if key == Qt.Key.Key_Escape:
            if any(texts):
                self.hole_dyn_texts = ["", ""]
                self.hole_dyn_focus = 0
                self.update()
                return True
            self.end_hole_place()
            return True

        if txt and len(txt) == 1 and (txt in "0123456789.,-+*/()^" or txt.isalpha() or txt == "_"):
            texts[focus] += txt
            self.update()
            return True

        return False

    def begin_point_pick(self):
        self.point_pick = True
        self.hover_point = None
        self._near_points = []
        self.setFocus()
        self.update()

    def end_point_pick(self):
        self.point_pick = False
        self.hover_point = None
        self._near_points = []
        self.update()

    def _snap_points(self, body):
        """A body's snap points, worked out once per rebuild of the body (its edge list is replaced then)."""
        cache = self.__dict__.setdefault("_snap_point_cache", {})
        hit = cache.get(body.body_id)
        if hit is None or hit[0] is not body.edges:
            hit = cache[body.body_id] = (body.edges, body_points(body))
        return hit[1]

    def _point_pick_shows(self, body) -> bool:
        """Visible, or the body being moved (hidden behind its preview while its points are picked)."""
        return body.visible or body.body_id == getattr(self, "point_pick_hidden_ok", None)

    def _candidate_points(self):
        """(body_id or None, kind, xyz, guides) of everything that can be picked: body points and the origin."""
        out = [(None, "fixed", np.zeros(3), ())]
        for body in self.doc.bodies.values():
            if self._point_pick_shows(body):
                out += [(body.body_id, p.kind, p.xyz, p.guides) for p in self._snap_points(body)]
        return out

    def _point_hidden(self, scr, xyz) -> bool:
        """True when a visible body surface lies between the camera and the point (seen at screen spot `scr`).
        The ray starts on the near plane at the point's own pixel, so this holds for an orthographic view too."""
        proj, view, _ = self.get_matrices()
        origin, _ = ray_from_screen(float(scr[0]), float(scr[1]), self.width(), self.height(), view, proj)
        direction = np.asarray(xyz, float) - origin
        dist = float(np.linalg.norm(direction))
        if dist < 1e-9:
            return False
        direction = direction / dist
        for body in self.doc.bodies.values():
            mesh = self._pick_mesh(body)
            if not self._point_pick_shows(body) or mesh is None or len(mesh.vertices) == 0 \
                    or not self._ray_hits_body_aabb(body, origin, direction, dist):
                continue
            hit = ray_mesh_hit(mesh, origin, direction)
            if hit is not None and hit[0] < dist - max(1e-3, 1e-5 * dist):
                return True
        return False

    def _point_pick_hover(self, x: float, y: float) -> None:
        cands = self._candidate_points()
        screen, front = self.project_points(np.array([c[2] for c in cands]))
        dist = np.hypot(screen[:, 0] - x, screen[:, 1] - y)
        dist[~front] = np.inf
        near = [i for i in np.flatnonzero(dist < SHOW_PX) if not self._point_hidden(screen[i], cands[i][2])]
        self._near_points = [cands[i] for i in near]
        i = min(near, key=lambda k: dist[k], default=None)
        hover = cands[i] if i is not None and dist[i] < SNAP_PX else None
        if (hover is None) != (self.hover_point is None) or (hover is not None and hover[2] is not self.hover_point[2]):
            self.hover_point = hover
            if hover is not None:
                what = {"end": "end of an edge", "corner": "hidden corner", "center": "centre of a circle",
                        "quadrant": "quarter point of a circle",
                        "face_center": "centre of a face", "top_center": "centre of top face",
                        "bottom_center": "centre of bottom face", "fixed": "origin"}[hover[1]]
                self.status_message.emit(f"Point: {what} at ({hover[2][0]:.2f}, {hover[2][1]:.2f}, {hover[2][2]:.2f}). Click to pick it.")
        self.update()

    def _point_pick_press(self) -> bool:
        if self.hover_point is None:
            return False
        body_id, kind, xyz, _ = self.hover_point
        self.point_picked.emit({"body": body_id, "kind": kind, "xyz": [float(c) for c in xyz]})
        return True

    def _draw_point_pick(self, painter) -> None:
        if not getattr(self, "point_pick", False):
            return
        painter.save()
        centre = QColor(80, 190, 255)
        colours = {"end": QColor(80, 220, 120), "corner": QColor(255, 150, 40), "center": centre,
                   "quadrant": QColor(200, 230, 90),
                   "face_center": centre, "top_center": centre, "bottom_center": centre,
                   "fixed": QColor(120, 180, 255)}
        near = self._near_points
        # projected now, not at the last mouse move: the camera may have moved since
        screen, front = self.project_points(np.array([c[2] for c in near])) if near else ((), ())
        for (body_id, kind, xyz, guides), scr, ok in zip(near, screen, front):
            if not ok:
                continue
            colour = colours[kind]
            if kind == "corner":
                ends = self.project_points(np.array(guides))
                pen = QPen(colour, 1.5, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                for g, g_ok in zip(*ends):
                    if g_ok:
                        painter.drawLine(QPointF(*g), QPointF(*scr))
            hovered = self.hover_point is not None and self.hover_point[2] is xyz
            painter.setPen(QPen(QColor(255, 255, 255), 2 if hovered else 1))
            painter.setBrush(colour if hovered else QColor(colour.red(), colour.green(), colour.blue(), 110))
            painter.drawEllipse(QPointF(*scr), 7.0 if hovered else 4.0, 7.0 if hovered else 4.0)
        painter.restore()
