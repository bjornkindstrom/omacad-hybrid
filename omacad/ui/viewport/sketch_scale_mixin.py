"""Sketch scaling: click sets the pivot, drag or spinbox scales the selection.

Uses the viewport's move transaction, so Esc/Cancel restores everything and OK is one undo step.
"""

import copy
import math

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPen, QColor
from omacad.model.sketch_rotate import selection_pivots, sketch_face_pivot
from omacad.model.sketch import scale_entity
from omacad.ui.sketch_scale import SketchScalePanel

SCALE_INFO = "Click in the sketch to set the pivot, drag or enter a scale factor. Enter / OK applies; Esc cancels."


class SketchScaleMixin:
    def _init_sketch_scale(self):
        self.scale_panel = SketchScalePanel(self.sketch_palette.content_widget)
        self.sketch_palette.content_widget.layout().insertWidget(0, self.scale_panel)
        self.scale_panel.hide()
        self.scale_panel.changed.connect(self._scale_preview)
        self.scale_panel.accepted.connect(lambda: self._scale_finish(True))
        self.scale_panel.cancelled.connect(lambda: self.set_sketch_tool("NONE"))
        self._scale_drag = None

    def _scale_begin(self):
        self._begin_move(self.selected_entities)
        if not self._move or not self._move["orig"]:
            self._end_move(False)
            self.status_message.emit("Scale: select editable sketch elements first. Projected edges cannot be scaled.")
            return False
        self.selected_entities = set(self._move["ids"])
        self.selection_changed.emit()
        self._scale_pivots = selection_pivots(self._move["orig"].values())
        self._scale_pivots["origin"] = (0.0, 0.0)
        face = sketch_face_pivot(self.doc, self.doc.active_sketch)
        if face is not None:
            self._scale_pivots["face"] = face
        self.scale_panel.configure(self._scale_pivots)
        self.scale_panel.set_coordinates(self._move["pivot"], True)
        self.scale_panel.show()
        self.sketch_palette.adjustSize()
        self._scale_preview()
        QTimer.singleShot(0, self.scale_panel.scale.setFocus)
        self.scale_panel.scale.selectAll()
        return True

    def _scale_preview(self):
        if self.sketch_tool != "SCALE" or not self._move:
            return
        panel = self.scale_panel
        key = panel.pivot.currentData()
        pivot = (panel.x.value(), panel.y.value()) if key == "custom" else self._scale_pivots.get(key, (0.0, 0.0))
        panel.set_coordinates(pivot, key == "custom")
        self._move["pivot"] = pivot
        sk = self.doc.active_sketch
        sk.restore_from_dict(self._move["before"])
        scale_val = panel.scale.value()
        if scale_val <= 0.0001:
            panel.info.setText("Scale factor must be greater than zero.")
            panel.ok.setEnabled(False)
            return

        for i, ent in enumerate(sk.entities):
            orig = self._move["orig"].get(ent.entity_id)
            if orig is not None:
                scaled = copy.deepcopy(orig)
                scale_entity(scaled, scale_val, pivot)
                sk.entities[i] = scaled

        for dim in sk.dimensions:
            if dim.target_entity_id in self._move["ids"]:
                if dim.dim_type in ("LENGTH", "DIAMETER", "RADIUS", "DISTANCE", "HORIZ_DIST", "VERT_DIST"):
                    dim.value = float(dim.value) * scale_val

        sk._bind_texts()
        sk.solve_profiles()
        panel.info.setText(SCALE_INFO)
        panel.ok.setEnabled(True)
        self.update()

    def _scale_finish(self, commit: bool):
        if self.sketch_tool != "SCALE" or not self._move:
            return
        if commit and not self.scale_panel.ok.isEnabled():
            return
        sk = self.doc.active_sketch
        m = self._move
        self._move = None
        self._scale_drag = None
        if not commit or sk is None or not m:
            if sk and m:
                sk.restore_from_dict(m["before"])
        else:
            self.doc.record_sketch_change(sk, m["before"])
            self.doc.timeline.recompute(self.doc)
            self.doc.notify_changed()
        self.scale_panel.hide()
        self.set_sketch_tool("NONE")
        self.update()

    def _draw_scale_pivot(self, painter):
        if self.sketch_tool != "SCALE" or not self._move or not self.doc.active_sketch:
            return
        point = self.world_to_screen(self.doc.active_sketch.plane.uv_to_world(*self._move["pivot"]))
        if point is None:
            return
        painter.save()
        painter.setPen(QPen(QColor(40, 180, 255), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        x, y = point[:2]
        painter.drawEllipse(QPointF(x, y), 8, 8)
        painter.drawLine(QPointF(x - 13, y), QPointF(x + 13, y))
        painter.drawLine(QPointF(x, y - 13), QPointF(x, y + 13))
        painter.drawText(QPointF(x + 15, y - 12), f"Scale Pivot ({self.scale_panel.scale.value():g}x)")
        painter.restore()
