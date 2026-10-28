"""Rotate and move handles on the selected body, like Layerling. A small curved arrow per axis (X red, Y green,
Z blue) beside the body turns it about its centre in 15° steps (Björn #107); a straight double arrow per axis off a
side of the body slides it along that axis in whole millimetres (#111); pointing at a flat face of another body
across that axis while sliding lines the body up with it, flush on either side. Shift: free. The release makes one
Move step."""
import math
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPen, QPolygonF, QFont
from PySide6.QtWidgets import QApplication

from omacad.ui import theme
from omacad.ui.math3d import ray_from_screen
from omacad.ui.viewport.body_dims import box_corners

AXES = {"X": np.array([1.0, 0.0, 0.0]), "Y": np.array([0.0, 1.0, 0.0]), "Z": np.array([0.0, 0.0, 1.0])}
COLOURS = {"X": (232, 96, 96), "Y": (92, 200, 118), "Z": (92, 150, 240)}
OUT = 26.0          # px from the box edge out to the handle
HALF = 20.0         # px, half the arrow's chord
HIT = 20.0          # px pick radius
SNAP_DEG = 15.0
SNAP_MM = 1.0
MOVES = {"MX": "X", "MY": "Y", "MZ": "Z"}   # move handle -> its axis


class RotateHandles:
    def __init__(self, viewport):
        self.vp = viewport
        self.hover: Optional[str] = None
        self.drag: Optional[dict] = None

    # --- where -------------------------------------------------------------------------------------------------------
    def body(self):
        """The one selected, visible body the handles turn, or None when they are not shown."""
        vp, doc = self.vp, self.vp.doc
        if (doc.active_sketch is not None or getattr(vp, "move_gizmo", None) or getattr(vp, "primitive_handles", None)
                or getattr(vp, "measure", None) is not None or getattr(vp, "edge_pick_mode", False)
                or getattr(vp, "extrude_handle", None)):
            return None
        ids = [b for b in doc.selected_body_ids if b in doc.bodies]
        if len(ids) != 1:
            return None
        body = doc.bodies[ids[0]]
        if not body.visible or body.render_mesh is None or len(body.render_mesh.vertices) == 0:
            return None
        return body

    def handles(self):
        """{axis: (screen position, screen tangent unit, outward unit)} for the selected body, or {}."""
        body = self.body()
        if body is None:
            return {}
        lo = np.asarray(body.render_mesh.bounds_min, float)
        hi = np.asarray(body.render_mesh.bounds_max, float)
        corners = box_corners(lo, hi)
        screen, front = self.vp.project_points(corners)
        if not front.all():
            return {}
        centre_w = (lo + hi) / 2.0
        centre_s = screen.mean(axis=0)
        out = {}
        for k, (name, axis) in enumerate(AXES.items()):
            bit = 1 << k
            # the edges along this axis: corner i (bit clear) to i | bit. X and Y sit on a top edge furthest out on
            # screen, Z on the upright edge furthest left: clear of the size labels on the floor edges and the right
            edges = [(i, i | bit) for i in range(8) if not i & bit]
            if name == "Z":
                a, b = min(edges, key=lambda e: screen[e[0]][0] + screen[e[1]][0])
            else:
                top = [e for e in edges if e[0] & 4]
                a, b = max(top, key=lambda e: np.linalg.norm((screen[e[0]] + screen[e[1]]) / 2 - centre_s))
            mid_s = (screen[a] + screen[b]) / 2
            outward = mid_s - centre_s
            n = float(np.linalg.norm(outward))
            if n < 1e-6:
                continue
            outward /= n
            mid_w = (corners[a] + corners[b]) / 2
            move = np.cross(axis, mid_w - centre_w)          # where turning about the axis carries that edge
            if np.linalg.norm(move) < 1e-9:
                continue
            step = mid_w + move / np.linalg.norm(move) * max(1e-3, float(np.linalg.norm(hi - lo)) * 0.05)
            s2, ok = self.vp.project_points(np.array([mid_w, step]))
            tangent = s2[1] - s2[0]
            if not ok.all() or np.linalg.norm(tangent) < 1e-6:
                tangent = np.array([-outward[1], outward[0]])
            out[name] = (mid_s + outward * OUT, tangent / np.linalg.norm(tangent), outward)
        out.update(self._move_handles(lo, hi, centre_w, centre_s, screen))
        return out

    def _move_handles(self, lo, hi, centre_w, centre_s, screen):
        """{"MX"/"MY"/"MZ": (position, arrow direction, same)}: a straight arrow along each axis, just off the side of
        the box it points out of: the front sides (lowest on screen) for X and Y, the top (highest) for Z. Left out
        when the axis points at the viewer and the arrow would be a dot."""
        from shapely.geometry import MultiPoint, Point
        outline = MultiPoint([tuple(p) for p in screen]).convex_hull
        ends, _ok = self.vp.project_points(np.array([centre_w, *(centre_w + a for a in AXES.values())]))
        per_mm = {name: float(np.linalg.norm(ends[1 + i] - ends[0])) for i, name in enumerate(AXES)}
        out = {}
        for name, axis_name in MOVES.items():
            axis = AXES[axis_name]
            half = (hi - lo) / 2.0 * axis
            faces = [centre_w + half, centre_w - half]
            pts, ok = self.vp.project_points(np.array([*faces, faces[0] + axis, faces[1] - axis]))
            if not ok.all():
                continue
            pick = (min if axis_name == "Z" else max)((0, 1), key=lambda i: pts[i][1])
            face_s = pts[pick]
            along = pts[2 + pick] - face_s                      # the axis on screen, pointing out of that side
            if np.linalg.norm(along) < 1e-6 or np.linalg.norm(face_s - centre_s) < 1e-6:
                continue
            along /= np.linalg.norm(along)
            if per_mm[axis_name] < 0.3 * max(per_mm.values()):  # the axis points at the viewer: nothing to drag along
                continue
            # from the side's centre out along the arrow until clear of the body's outline on screen
            t = 0.0
            while t < 4000 and outline.contains(Point(*(face_s + along * t))):
                t += 4.0
            out[name] = (face_s + along * (t + OUT + 10 + HALF), along, along)   # past the size labels too
        return out

    def hit(self, x: float, y: float) -> Optional[str]:
        best, best_d = None, HIT
        for name, (pos, _t, _o) in self.handles().items():
            d = math.hypot(x - pos[0], y - pos[1])
            if d < best_d:
                best, best_d = name, d
        return best

    # --- dragging ----------------------------------------------------------------------------------------------------
    def _plane_angle(self, x, y, axis, centre) -> Optional[float]:
        """Angle (degrees) of the mouse about the axis through `centre`, read in the plane across the axis; None when
        that plane is seen edge-on."""
        proj, view, _ = self.vp.get_matrices()
        r0, rd = ray_from_screen(x, y, self.vp.width(), self.vp.height(), view, proj)
        r0, rd = np.asarray(r0, float), np.asarray(rd, float)
        denom = float(rd @ axis)
        if abs(denom) < 0.15:
            return None
        t = float((centre - r0) @ axis) / denom
        if t <= 0:
            return None
        p = r0 + rd * t - centre
        u = np.cross(axis, [0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        return math.degrees(math.atan2(float(p @ v), float(p @ u)))

    def _along(self, x, y, axis, through) -> Optional[float]:
        """Where the mouse ray passes the axis line through `through`, as a distance along the axis (mm)."""
        proj, view, _ = self.vp.get_matrices()
        r0, rd = ray_from_screen(x, y, self.vp.width(), self.vp.height(), view, proj)
        r0, rd = np.asarray(r0, float), np.asarray(rd, float)
        rd /= np.linalg.norm(rd)
        w = through - r0
        b, d1, e = float(axis @ rd), float(axis @ w), float(rd @ w)
        denom = 1.0 - b * b
        if abs(denom) < 1e-6:
            return None
        return (b * e - d1) / denom

    def press(self, x: float, y: float) -> bool:
        name = self.hit(x, y)
        if name is None:
            return False
        body = self.body()
        lo, hi = np.asarray(body.render_mesh.bounds_min, float), np.asarray(body.render_mesh.bounds_max, float)
        pos, tangent, _o = self.handles()[name]
        centre = (lo + hi) / 2.0
        self.drag = {"axis": name, "body_id": body.body_id, "centre": centre, "start": (x, y), "tangent": tangent,
                     "angle": 0.0, "dist": 0.0, "pos": pos, "lo": lo, "hi": hi, "snap": None}
        if name in MOVES:
            self.drag["start_along"] = self._along(x, y, AXES[MOVES[name]], centre)
        else:
            self.drag["start_angle"] = self._plane_angle(x, y, AXES[name], centre)
        self.vp.setCursor(Qt.CursorShape.ClosedHandCursor)
        return True

    def angle_at(self, x: float, y: float) -> float:
        d = self.drag
        a = None
        if d["start_angle"] is not None:
            now = self._plane_angle(x, y, AXES[d["axis"]], d["centre"])
            if now is not None:
                a = (now - d["start_angle"] + 180.0) % 360.0 - 180.0
        if a is None:     # plane seen edge-on: along the arrow, 2 px a degree
            a = float(np.dot(np.array([x, y]) - d["start"], d["tangent"])) / 2.0
        if not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            a = round(a / SNAP_DEG) * SNAP_DEG
        return a

    def dist_at(self, x: float, y: float) -> float:
        d = self.drag
        now = self._along(x, y, AXES[MOVES[d["axis"]]], d["centre"])
        if now is None or d["start_along"] is None:
            return d["dist"]
        dist = now - d["start_along"]
        snap = self._face_snap(x, y, d, dist)
        d["snap"] = snap[1] if snap else None
        if snap:
            return snap[0]
        step = 0.1 if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier else SNAP_MM
        return round(dist / step) * step + 0.0

    def _face_snap(self, x, y, d, free):
        """(shift, face) when the mouse is on a flat face of another body that lies across the drag axis: the shift
        that puts the body's near or far side in that face's plane (whichever is closer to where the mouse took it)."""
        from omacad.model.faces import ray_hit_faces
        k = "XYZ".index(MOVES[d["axis"]])
        axis = AXES[MOVES[d["axis"]]]
        proj, view, _ = self.vp.get_matrices()
        r0, rd = ray_from_screen(x, y, self.vp.width(), self.vp.height(), view, proj)
        best, best_t = None, float("inf")
        for body in self.vp.doc.bodies.values():
            if body.body_id == d["body_id"] or not body.visible or not len(body.faces):
                continue
            hits = ray_hit_faces(body.faces, r0, rd, bary_tol=2e-4)
            for i in np.flatnonzero(np.isfinite(hits)):
                if hits[i] < best_t:
                    best, best_t = body.faces[i], float(hits[i])
        if best is None or abs(float(np.asarray(best.normal, float) @ axis)) < 0.999:
            return None
        plane = float(np.asarray(best.origin, float) @ axis)
        shift = min((plane - d["lo"][k], plane - d["hi"][k]), key=lambda s: abs(s - free))
        return shift, best

    def move(self, x: float, y: float) -> bool:
        if self.drag is None:
            name = self.hit(x, y)
            if name != self.hover:
                self.hover = name
                self.vp.setCursor(Qt.CursorShape.OpenHandCursor if name else Qt.CursorShape.ArrowCursor)
                self.vp.update()
            return False
        d = self.drag
        key, value = ("dist", self.dist_at(x, y)) if d["axis"] in MOVES else ("angle", self.angle_at(x, y))
        if value != d[key]:
            d[key] = value
            body = self.vp.doc.bodies.get(d["body_id"])
            if body is not None:
                self.vp.set_display_override({d["body_id"]: self._turned(body.manifold, d)})
        return True

    def shift(self, d):
        """(dx, dy, dz) of a move drag."""
        return tuple(d["dist"] if a == MOVES.get(d["axis"]) else 0.0 for a in AXES)

    @staticmethod
    def rotation(axis: str, angle: float):
        return tuple(angle if a == axis else 0.0 for a in AXES)

    def _turned(self, manifold, d):
        from omacad.model.features.transform import MoveFeature
        if d["axis"] in MOVES:
            return manifold.translate(list(self.shift(d)))
        return MoveFeature.transform(manifold, (0.0, 0.0, 0.0), self.rotation(d["axis"], d["angle"]), d["centre"])

    def release(self) -> bool:
        d, self.drag = self.drag, None
        if d is None:
            return False
        self.vp.set_display_override(None)
        self.vp.setCursor(Qt.CursorShape.OpenHandCursor if self.hover else Qt.CursorShape.ArrowCursor)
        doc = self.vp.doc
        if d["axis"] in MOVES:
            if abs(d["dist"]) > 1e-9 and d["body_id"] in doc.bodies:
                name = doc.bodies[d["body_id"]].name
                dx, dy, dz = self.shift(d)
                doc.move_body(d["body_id"], dx=dx, dy=dy, dz=dz)
                doc.selected_body_ids = [d["body_id"]] if d["body_id"] in doc.bodies else []
                self.vp.status_message.emit(f"Moved {name} {d['dist']:g} mm along {MOVES[d['axis']]} "
                                            "(one Move step; Ctrl+Z undoes).")
            return True
        if abs(d["angle"]) > 1e-9 and d["body_id"] in doc.bodies:
            name = doc.bodies[d["body_id"]].name
            rx, ry, rz = self.rotation(d["axis"], d["angle"])
            doc.move_body(d["body_id"], rx=rx, ry=ry, rz=rz, pivot="center")
            doc.selected_body_ids = [d["body_id"]] if d["body_id"] in doc.bodies else []
            self.vp.status_message.emit(f"Rotated {name} {d['angle']:g}° about {d['axis']} (one Move step; Ctrl+Z undoes).")
        return True

    def cancel(self) -> bool:
        if self.drag is None:
            return False
        self.drag = None
        self.vp.set_display_override(None)
        return True

    # --- drawing -----------------------------------------------------------------------------------------------------
    def draw(self, painter: QPainter) -> None:
        handles = self.handles()
        if not handles:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        active = self.drag["axis"] if self.drag else None
        for name, (pos, tangent, outward) in handles.items():
            if active and name != active:
                continue
            lit = name in (active, self.hover)
            r, g, b = COLOURS[MOVES.get(name, name)]
            colour = theme.qcolor(r, g, b, 255 if lit else 200)
            if name in MOVES:
                _straight_arrow(painter, pos, tangent, colour, 4.0 if lit else 3.0)
            else:
                _curved_arrow(painter, pos, tangent, outward, colour, 4.0 if lit else 3.0)
        snap = self.drag.get("snap") if self.drag else None
        if snap is not None:                         # the face it lines up with
            r, g, b = COLOURS[MOVES[self.drag["axis"]]]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qcolor(r, g, b, 90))
            tris = np.asarray(snap.tris, float)
            pts, ok = self.vp.project_points(tris.reshape(-1, 3))
            for tri in pts.reshape(-1, 3, 2)[ok.reshape(-1, 3).all(axis=1)]:
                painter.drawPolygon(QPolygonF([QPointF(*p) for p in tri]))
        if self.drag:
            label = f"{self.drag['dist']:g} mm" if self.drag["axis"] in MOVES else f"{self.drag['angle']:g}°"
            if snap is not None:
                label += " · flush"
            font = QFont(painter.font())
            font.setPixelSize(13)
            painter.setFont(font)
            fm = painter.fontMetrics()
            w, h = fm.horizontalAdvance(label) + 16, fm.height() + 8
            pos = self.drag["pos"]
            rect = QRectF(pos[0] - w / 2, pos[1] + 14, w, h)
            painter.setPen(QPen(theme.qcolor(90, 96, 104), 1))
            painter.setBrush(theme.qcolor(37, 40, 44, 240))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(theme.qcolor(224, 227, 231))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()


def _curved_arrow(painter: QPainter, pos, tangent, outward, colour, width: float) -> None:
    """A shallow arc across `tangent`, bulging outwards, with an arrow head at both ends."""
    def at(t):
        return pos + tangent * HALF * t + outward * 8.0 * (1.0 - t * t)

    path = QPainterPath(QPointF(*at(-1.0)))
    for t in np.linspace(-1.0, 1.0, 13)[1:]:
        path.lineTo(QPointF(*at(t)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(colour, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    for t in (-1.0, 1.0):
        tip = at(t)
        back = at(t * 0.7)
        d = tip - back
        d /= max(np.linalg.norm(d), 1e-9)
        n = np.array([-d[1], d[0]])
        tip = tip + d * 4.0
        base = tip - d * 9.0
        painter.drawPolygon(QPolygonF([QPointF(*tip), QPointF(*(base + n * 6.0)), QPointF(*(base - n * 6.0))]))


def _straight_arrow(painter: QPainter, pos, along, colour, width: float) -> None:
    """A short straight line along `along` with an arrow head at both ends."""
    a, b = pos - along * HALF, pos + along * HALF
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(colour, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(*a), QPointF(*b))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    n = np.array([-along[1], along[0]])
    for tip, d in ((b, along), (a, -along)):
        tip = tip + d * 4.0
        base = tip - d * 9.0
        painter.drawPolygon(QPolygonF([QPointF(*tip), QPointF(*(base + n * 6.0)), QPointF(*(base - n * 6.0))]))
