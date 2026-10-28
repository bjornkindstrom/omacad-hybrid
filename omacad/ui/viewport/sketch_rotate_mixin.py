"""Sketch rotation: click sets the pivot, drag around it turns the selection (Shift = 15° steps).

Uses the viewport's move transaction, so Esc/Cancel restores everything and OK is one undo step."""

import math

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPen, QColor
from omacad.model.sketch_rotate import selection_pivots, sketch_face_pivot, rotate_axis_constraints, validate_axis_dimensions
from omacad.ui.sketch_rotation import SketchRotationPanel


class SketchRotateMixin:
    def _init_sketch_rotation(self):
        self.rotation_panel = SketchRotationPanel(self.sketch_palette.content_widget)
        self.sketch_palette.content_widget.layout().insertWidget(0, self.rotation_panel)
        self.rotation_panel.hide()
        self.rotation_panel.changed.connect(self._rotate_preview)
        self.rotation_panel.accepted.connect(lambda: self._rotate_finish(True))
        self.rotation_panel.cancelled.connect(lambda: self.set_sketch_tool("NONE"))
        self._rotate_drag = None

    def _rotate_begin(self):
        self._begin_move(self.selected_entities)
        if not self._move["orig"]:
            self._end_move(False)
            self.status_message.emit("Rotate: select editable sketch elements first. Projected edges cannot be rotated.")
            return False
        self.selected_entities = set(self._move["ids"])
        self.selection_changed.emit()
        self._rotate_pivots = selection_pivots(self._move["orig"].values())
        self._rotate_pivots["origin"] = (0.0, 0.0)
        face = sketch_face_pivot(self.doc, self.doc.active_sketch)
        if face is not None:
            self._rotate_pivots["face"] = face
        self.rotation_panel.configure(self._rotate_pivots)
        self.rotation_panel.set_coordinates(self._move["pivot"], True)
        self.rotation_panel.show()
        self.sketch_palette.adjustSize()
        self._rotate_preview()
        QTimer.singleShot(0, self.rotation_panel.angle.setFocus)
        self.rotation_panel.angle.selectAll()
        return True

    def _rotate_preview(self):
        if self.sketch_tool != "ROTATE" or not self._move:
            return
        panel = self.rotation_panel
        key = panel.pivot.currentData()
        pivot = (panel.x.value(), panel.y.value()) if key == "custom" else self._rotate_pivots[key]
        panel.set_coordinates(pivot, key == "custom")
        self._move["pivot"] = pivot
        sk = self.doc.active_sketch
        # Every preview starts at the transaction snapshot; changing the pivot never
        # compounds a previous rotation or progressively removes constraints.
        sk.constraints = self._rotate_original_constraints()
        angle = panel.angle.value()
        self._apply_move(0, 0, angle)
        try:
            rotate_axis_constraints(sk, self._move["ids"], angle)
            validate_axis_dimensions(sk, self._move["ids"])
        except ValueError as exc:
            panel.info.setText(str(exc))
            panel.ok.setEnabled(False)
        else:
            panel.info.setText(INFO)
            panel.ok.setEnabled(True)
        self.update()

    def _rotate_original_constraints(self):
        from omacad.model.sketch import SketchConstraint
        return [SketchConstraint.from_dict(c) for c in self._move["before"]["constraints"]]

    def _rotate_snap_uv(self, x, y):
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None:
            return None
        from omacad.model.sketch_snap import SketchSnapper
        return SketchSnapper.snap(
            raw_uv=uv, sketch=self.doc.active_sketch,
            snap_distance=max(0.3, min(8.0, self._entity_tolerance() * 1.25)),
            reference_segments=self._reference_segments(), grid_step=5.0,
            enable_grid_snap=self.sketch_palette.chk_snap_grid.isChecked(),
            enable_geom_snap=self.sketch_palette.chk_snap_points.isChecked()).uv

    def _rotate_press(self, event, x, y):
        """Left press: remember it; release without moving = new pivot, dragging = rotate."""
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None or not self._move:
            return
        self._rotate_drag = {"pos": event.position(), "uv": uv, "angle": self.rotation_panel.angle.value(),
                             "moved": False, "cursor": uv, "turned": 0.0}

    def _rotate_drag_to(self, event, x, y):
        d = self._rotate_drag
        if (event.position() - d["pos"]).manhattanLength() < 4 and not d["moved"]:
            return
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None:
            return
        d["moved"] = True
        d["turned"] += drag_angle(self._move["pivot"], d["cursor"], uv)   # summed per step: full turns don't jump
        d["cursor"] = uv
        angle = d["angle"] + d["turned"]
        step = 15.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        self.rotation_panel.angle.setValue(round(angle / step) * step)

    def _rotate_release(self, x, y):
        d, self._rotate_drag = self._rotate_drag, None
        if d["moved"]:
            self.status_message.emit(f"Rotate: {self.rotation_panel.angle.value():g}°. Drag again to adjust, Enter applies.")
            self.update()
            return
        uv = self._rotate_snap_uv(x, y)
        if uv is None:
            return
        panel = self.rotation_panel
        panel.pivot.blockSignals(True)
        panel.pivot.setCurrentIndex(panel.pivot.findData("custom"))
        panel.pivot.blockSignals(False)
        panel.set_coordinates(uv, True)
        self._rotate_preview()
        self.status_message.emit("Rotate: pivot set. Drag around it to turn (Shift = 15° steps), Enter applies.")

    def _rotate_finish(self, commit):
        if self.sketch_tool != "ROTATE" or not self._move:
            return
        if commit and not self.rotation_panel.ok.isEnabled():
            return
        self._end_move(commit)
        self.set_sketch_tool("NONE")

    def _draw_rotation_pivot(self, painter):
        if self.sketch_tool != "ROTATE" or not self._move or not self.doc.active_sketch:
            return
        point = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*self._move["pivot"]))
        if point is None:
            return
        painter.save()
        painter.setPen(QPen(QColor(255, 125, 40), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x, y = point[:2]
        painter.drawEllipse(QPointF(x, y), 8, 8)
        painter.drawLine(QPointF(x - 13, y), QPointF(x + 13, y))
        painter.drawLine(QPointF(x, y - 13), QPointF(x, y + 13))
        painter.drawText(QPointF(x + 15, y - 12), "Pivot")
        d = self._rotate_drag
        if d and d["moved"]:
            plane = self.doc.active_sketch.plane
            for uv in (d["uv"], d["cursor"]):
                end = self.world_to_screen(plane.uv_to_world(*uv))
                if end is not None:
                    painter.drawLine(QPointF(x, y), QPointF(end[0], end[1]))
            end = self.world_to_screen(plane.uv_to_world(*d["cursor"]))
            if end is not None:
                painter.drawText(QPointF(end[0] + 12, end[1] - 10), f"{self.rotation_panel.angle.value():g}°")
        painter.restore()


INFO = "Click in the sketch to set the pivot, drag around it to turn (Shift = 15° steps) or type an angle. Enter / OK applies; Esc cancels."


def drag_angle(pivot, start, now):
    """Degrees from the pivot->start direction to the pivot->now direction, in (-180, 180]."""
    a = math.degrees(math.atan2(now[1] - pivot[1], now[0] - pivot[0]) - math.atan2(start[1] - pivot[1], start[0] - pivot[0]))
    return a - 360.0 * math.ceil((a - 180.0) / 360.0)
