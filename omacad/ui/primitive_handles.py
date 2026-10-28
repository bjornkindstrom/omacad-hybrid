"""Direct dimension handles for primitive previews, with no document mutations."""
import math

import numpy as np

from omacad.ui.settings import get_settings
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPen, QFont
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect
from omacad.model.faces import ray_mesh_hit


def primitive_drag_value(field, value):
    """Shared precision for primitive sliders and canvas handles."""
    decimals = max(0, min(2, int(get_settings().get("primitive_drag_decimals", 0))))
    step = 10.0 ** -decimals
    minimum = math.ceil(field.minimum() / step) * step
    maximum = math.floor(field.maximum() / step) * step
    snapped = max(minimum, min(maximum, round(value, decimals)))
    return f"{snapped:.{decimals}f}"


class PrimitiveHandles:
    def __init__(self, viewport, dialog, kind):
        self.viewport = viewport
        self.dialog = dialog
        self.kind = kind
        self.drag = None
        self.hover = None
        self.dialog.placement_offset = np.asarray(getattr(dialog, "placement_offset", (0., 0., 0.)), dtype=float)

    def _ray(self, x, y):
        proj, view, _ = self.viewport.get_matrices()
        return ray_from_screen(x, y, self.viewport.width(), self.viewport.height(), view, proj)

    def _preview_hit(self, x, y):
        mesh = self.viewport.preview_mesh
        if self.viewport.plane_pick_mode or mesh is None or not len(mesh.vertices):
            return None
        origin, direction = self._ray(x, y)
        hit = ray_mesh_hit(mesh, origin, direction)
        return None if hit is None else (origin + direction * hit[0], direction)

    def specs(self):
        """(field, world position, derivative of position per mm, label)."""
        d = self.dialog
        origin, basis = np.zeros(3), np.eye(3)
        mode = d.cmb_placement.currentData() if hasattr(d, "cmb_placement") else "center"
        if mode == "on_face" and d.plane_origin is not None:
            origin = np.asarray(d.plane_origin, dtype=float)
            n = np.asarray(d.plane_normal, dtype=float)
            n /= np.linalg.norm(n)
            if d.plane_u is not None and d.plane_v is not None:
                u, v = np.asarray(d.plane_u, dtype=float), np.asarray(d.plane_v, dtype=float)
                u, v = u / np.linalg.norm(u), v / np.linalg.norm(v)
            else:
                hint = np.array([1., 0., 0.]) if abs(n[0]) < .9 else np.array([0., 1., 0.])
                u = hint - np.dot(hint, n) * n
                u /= np.linalg.norm(u)
                v = np.cross(n, u)
            basis = np.column_stack((u, v, n))
        origin = origin + self.dialog.placement_offset
        if self.kind == "box":
            l, w, h = d.spn_length.value(), d.spn_width.value(), d.spn_height.value()
            middle = np.array([l/2, w/2, h/2]) if mode == "corner" else np.array([0., 0., 0. if mode == "center" else h/2])
            factors = [1. if mode == "corner" else .5, 1. if mode == "corner" else .5,
                       .5 if mode == "center" else 1.]
            entries = [(d.spn_length, 0, l, "Length"), (d.spn_width, 1, w, "Width"),
                       (d.spn_height, 2, h, "Height")]
            positions = [middle + np.eye(3)[a] * size/2 for _, a, size, _ in entries]
        else:
            r = d.spn_radius.value()
            if self.kind == "prism":  # the field is across flats: the handle sits on the +X flat
                entries, positions, factors = [(d.spn_radius, 0, r, "Across flats")], [np.array([r/2, 0., 0.])], [.5]
            else:
                entries, positions, factors = [(d.spn_radius, 0, r, "Radius")], [np.array([r, 0., 0.])], [1.]
            if self.kind != "sphere":
                h = d.spn_height.value()
                z = 0. if mode == "center" else h/2
                positions = [p + [0, 0, z] for p in positions]
                entries.append((d.spn_height, 2, h, "Height"))
                positions.append(np.array([0., 0., h/2 if mode == "center" else h]))
                factors.append(.5 if mode == "center" else 1.)
        if self.kind != "sphere" and hasattr(d, "spn_taper"):
            inset = d.spn_height.value()/2 * math.tan(math.radians(d.spn_taper.value()))
            # Side handles stay on the sloping walls; dimensions refer to the base.
            for i, (_, axis, _, _) in enumerate(entries):
                if axis < 2:
                    positions[i][axis] -= inset
        return [(field, origin + basis @ pos, basis[:, axis] * factor, label)
                for (field, axis, _, label), pos, factor in zip(entries, positions, factors)]

    def geometry(self):
        if self.viewport.plane_pick_mode:
            return []
        result = []
        for field, pos, derivative, label in self.specs():
            p = self.viewport.world_to_screen(pos)
            q = self.viewport.world_to_screen(pos + derivative)
            if p is None or q is None:
                continue
            tangent = np.array(q[:2]) - np.array(p[:2])
            length = np.linalg.norm(tangent)
            if length < .1:  # axis points into the screen; orbit to expose it
                continue
            tip = np.array(p[:2]) + tangent / length * 22
            result.append((field, tip, tangent, label))
        return result

    def hit(self, x, y):
        candidates = [(np.linalg.norm(tip - [x, y]), i) for i, (_, tip, _, _) in enumerate(self.geometry())]
        return min(candidates)[1] if candidates and min(candidates)[0] <= 14 else None

    def press(self, x, y):
        index = self.hit(x, y)
        if index is not None:
            field, _, tangent, _ = self.geometry()[index]
            self._start_expression = field.expression() or str(field.value())
            self.drag = {"kind": "dimension", "field": field, "start": np.array([x, y]),
                         "tangent": tangent, "value": field.value()}
            return True
        hit = self._preview_hit(x, y)
        if hit is None:
            return False
        point, normal = hit
        self.drag = {"kind": "placement", "point": point, "normal": np.array([0., 0., 1.]),
                     "offset": self.dialog.placement_offset.copy()}
        self.viewport.setCursor(Qt.CursorShape.ClosedHandCursor)
        return True

    def move(self, x, y):
        if self.drag is not None:
            if self.drag["kind"] == "dimension":
                field, start, tangent, value = (self.drag[k] for k in ("field", "start", "tangent", "value"))
                delta = np.dot(np.array([x, y]) - start, tangent) / np.dot(tangent, tangent)
                field.set_expression(primitive_drag_value(field, value + delta))
            else:
                origin, direction = self._ray(x, y)
                point = ray_plane_intersect(origin, direction, self.drag["point"], self.drag["normal"])
                if point is not None:
                    self.dialog.placement_offset = self.drag["offset"] + point - self.drag["point"]
                    self.dialog.changed.emit()
                    if hasattr(self, "refresh_preview"):
                        self.refresh_preview()
            return True
        hover = self.hit(x, y)
        if hover is None and self._preview_hit(x, y) is not None:
            hover = "body"
        if hover != self.hover:
            self.hover = hover
            self.viewport.setCursor(Qt.CursorShape.OpenHandCursor if hover == "body" else Qt.CursorShape.ArrowCursor)
            self.viewport.update()
        return hover is not None

    def cancel_drag(self):
        if self.drag is None:
            return
        if self.drag["kind"] == "dimension":
            self.drag["field"].set_expression(self._start_expression)
        else:
            self.dialog.placement_offset = self.drag["offset"].copy()
            self.dialog.changed.emit()
        self.release()

    def release(self):
        if self.drag is None:
            return False
        self.drag = None
        self.viewport.setCursor(Qt.CursorShape.ArrowCursor)
        return True

    def draw(self, painter):
        painter.save()
        painter.setFont(QFont("sans-serif", 9))
        for i, (field, tip, tangent, label) in enumerate(self.geometry()):
            color = QColor("#ffad42") if i == self.hover or (self.drag and self.drag.get("field") is field) else QColor("#43b7ff")
            painter.setPen(QPen(color, 2))
            painter.drawLine(int(tip[0] - tangent[0]/np.linalg.norm(tangent)*22),
                             int(tip[1] - tangent[1]/np.linalg.norm(tangent)*22), int(tip[0]), int(tip[1]))
            painter.setBrush(color)
            painter.drawRect(QRectF(tip[0]-5, tip[1]-5, 10, 10))
            text = f"{label}: {field.value():g} mm"
            width = painter.fontMetrics().horizontalAdvance(text) + 12
            rect = QRectF(tip[0]+10, tip[1]-12, width, 24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 24, 30, 225))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("white"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


def attach_primitive_handles(viewport, dialog, kind, preview=None):
    handles = PrimitiveHandles(viewport, dialog, kind)
    if preview is not None:
        handles.refresh_preview = preview
    for field, *_ in handles.specs():
        field.setProperty("primitive_dimension", True)
    viewport.primitive_handles = handles

    def clear(*_):
        if viewport.primitive_handles is handles:
            viewport.primitive_handles = None
            viewport.update()

    dialog.finished.connect(clear)
    dialog.destroyed.connect(clear)
    return handles
