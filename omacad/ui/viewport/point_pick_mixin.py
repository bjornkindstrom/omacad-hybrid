"""Picking a point on a body in the 3D view (Move / Rotate from a point, point to point).

While picking, the snap points of the bodies near the cursor show as dots: green for the end of a straight
edge, orange for the sharp corner a rounding hides, with dashed guide lines from the rounding to that
corner, blue for the centre of a flat face or a circle. Points hidden behind a body are left out, and the
dots are projected again on every repaint so they stay on the body while the camera moves. The world
origin can be picked too. A click emits `point_picked` with {"body", "kind", "xyz"}."""

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
        self._hole_place_hover(0, 0)
        self.setFocus()
        self.update()

    def end_hole_place(self):
        self.hole_place_mode = False
        self.hole_place_hover = None
        self.update()

    def clear_hole_place(self):
        self.end_hole_place()
        self.hole_place_plane = None
        self.hole_place_points = []
        self.update()

    def _hole_place_at(self, x, y):
        proj, view, _ = self.get_matrices()
        origin, direction = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        p = self.hole_place_plane
        return ray_plane_intersect(origin, direction, p.origin, p.normal)

    def _hole_place_hover(self, x, y):
        self.hole_place_hover = self._hole_place_at(x, y) if self.hole_place_plane is not None else None
        self.update()

    def _hole_place_press(self, x, y):
        point = self._hole_place_at(x, y)
        if point is None:
            return False
        point = np.asarray(point, dtype=float)
        self.hole_place_points.append(point.tolist())
        self.hole_point_picked.emit(point.tolist())
        self.update()
        return True

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
