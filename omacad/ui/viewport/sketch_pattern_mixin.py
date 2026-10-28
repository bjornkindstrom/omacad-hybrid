"""Sketch Pattern tool (Björn #75): live copies of the selection while the panel's numbers change; OK is one undo
step, Cancel / Esc / another tool puts the sketch back."""

from omacad.model.sketch_pattern import circular_copies, default_spacing, rectangular_copies, selection_centre
from omacad.model.sketch_rotate import sketch_face_pivot
from omacad.ui.sketch_pattern_panel import SketchPatternPanel


class SketchPatternMixin:
    def _init_sketch_pattern(self):
        self.pattern_panel = SketchPatternPanel(self.sketch_palette.content_widget)
        self.sketch_palette.content_widget.layout().insertWidget(0, self.pattern_panel)
        self.pattern_panel.hide()
        self.pattern_panel.changed.connect(self._pattern_preview)
        self.pattern_panel.accepted.connect(lambda: self._pattern_finish(True))
        self.pattern_panel.cancelled.connect(lambda: self.set_sketch_tool("NONE"))
        self._pattern = None

    def _pattern_begin(self) -> bool:
        sk = self.doc.active_sketch
        ents = [e for e in sk.entities if e.entity_id in self.selected_entities and not getattr(e, "projected", False)]
        if not ents:
            self.status_message.emit("Pattern: select sketch elements first (click, Ctrl+click, or double-click a figure).")
            return False
        centres = {"selection": selection_centre(ents), "origin": (0.0, 0.0)}
        face = sketch_face_pivot(self.doc, sk)
        if face is not None:
            centres["face"] = tuple(face)
        self._pattern = {"before": sk.to_dict(), "ids": [e.entity_id for e in ents], "centres": centres}
        labels = {"selection": "Selection centre", "origin": "Sketch origin", "face": "Face centre"}
        self.pattern_panel.configure(default_spacing(ents), [(k, labels[k]) for k in centres])
        self.pattern_panel.show()
        self.sketch_palette.adjustSize()
        self._pattern_preview()
        return True

    def _pattern_preview(self):
        p = self._pattern
        if self.sketch_tool != "PATTERN" or not p:
            return
        sk = self.doc.active_sketch
        sk.restore_from_dict(p["before"])
        ents = [sk.get_entity(i) for i in p["ids"]]
        panel = self.pattern_panel
        if panel.kind.currentData() == "circular":
            copies = circular_copies(sk, ents, int(panel.count.value()), p["centres"][panel.centre.currentData()],
                                     panel.angle.value())
        else:
            copies = rectangular_copies(sk, ents, int(panel.count_x.value()), panel.spacing_x.value(),
                                        int(panel.count_y.value()), panel.spacing_y.value())
        sk._bind_texts()
        sk.solve_profiles()
        p["copies"] = [c.entity_id for c in copies]
        if panel.kind.currentData() == "rectangular":
            p["spacing"] = (panel.spacing_x.value(), panel.spacing_y.value())
            p["rectangular"] = True
        else:
            p["spacing"] = None
            p["rectangular"] = False
        self.status_message.emit(f"Pattern: {len(copies)} new element(s). OK keeps them.")
        self.update()

    def draw_sketch_pattern_dimensions(self, painter):
        """Show the live first-copy spacing from the selected original geometry."""
        p = self._pattern
        sk = self.doc.active_sketch
        if not p or not p.get("rectangular") or sk is None:
            return
        spacing_x, spacing_y = p["spacing"]
        ids = p["ids"]
        originals = [sk.get_entity(i) for i in ids]
        originals = [e for e in originals if e is not None]
        if not originals:
            return
        points = [pt for entity in originals for segment in entity.to_lines() for pt in segment]
        if not points:
            return
        left, right = min(pt[0] for pt in points), max(pt[0] for pt in points)
        bottom, top = min(pt[1] for pt in points), max(pt[1] for pt in points)
        plane = sk.plane
        if int(self.pattern_panel.count_x.value()) > 1 and abs(spacing_x) > 1e-9:
            self._draw_pattern_spacing_dimension(painter, plane, (right, (bottom + top) / 2),
                                                 (right + spacing_x, (bottom + top) / 2),
                                                 f"{abs(spacing_x):g} mm", (0, -1))
        if int(self.pattern_panel.count_y.value()) > 1 and abs(spacing_y) > 1e-9:
            self._draw_pattern_spacing_dimension(painter, plane, ((left + right) / 2, top),
                                                 ((left + right) / 2, top + spacing_y),
                                                 f"{abs(spacing_y):g} mm", (1, 0))

    def _draw_pattern_spacing_dimension(self, painter, plane, a, b, label, text_direction):
        from PySide6.QtCore import QPointF, QRectF, Qt
        from PySide6.QtGui import QColor, QFont, QPen

        sa = self.world_to_screen(plane.uv_to_world(*a))
        sb = self.world_to_screen(plane.uv_to_world(*b))
        if sa is None or sb is None:
            return
        ax, ay = sa
        bx, by = sb
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(255, 183, 77, 220), 1.5))
        painter.drawLine(QPointF(ax, ay), QPointF(bx, by))
        for x, y in ((ax, ay), (bx, by)):
            painter.drawLine(QPointF(x - nx * 5, y - ny * 5), QPointF(x + nx * 5, y + ny * 5))
        font = QFont(painter.font())
        font.setPixelSize(12)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        w, h = fm.horizontalAdvance(label) + 14, fm.height() + 6
        tx = (ax + bx) / 2 + text_direction[0] * (w / 2 + 7)
        ty = (ay + by) / 2 + text_direction[1] * (h / 2 + 7)
        rect = QRectF(tx - w / 2, ty - h / 2, w, h)
        painter.setPen(QPen(QColor(255, 183, 77), 1))
        painter.setBrush(QColor(22, 25, 30, 235))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(255, 240, 210))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _pattern_finish(self, commit: bool):
        p, self._pattern = self._pattern, None
        self.pattern_panel.hide()
        sk = self.doc.active_sketch
        if not p or sk is None:
            return
        if commit and p.get("copies"):
            self.doc.record_sketch_change(sk, p["before"])
            self.doc.timeline.recompute(self.doc)
            self.selected_entities = set(p["ids"]) | set(p["copies"])
            self.selection_changed.emit()
        else:
            sk.restore_from_dict(p["before"])
        self.doc.notify_changed()
        if commit and self.sketch_tool == "PATTERN":
            self.set_sketch_tool("NONE")
        self.update()
