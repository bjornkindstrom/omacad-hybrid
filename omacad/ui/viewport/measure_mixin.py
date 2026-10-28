"""Measurement tool behavior and its viewport overlay."""

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QFont
from omacad.model.measure import face_outline, is_face
from omacad.ui import theme


class MeasureMixin:
    """Measurement interaction and drawing used by :class:`Viewport3D`."""

    def begin_measure(self):
        """Measure tool: click a line (or edge) for its length, click a second one for the distance/angle between them."""
        self.measure = {"mode": "sketch" if self.doc.active_sketch else "model", "picks": [], "text": [], "segs": []}
        self.selected_entities.clear()
        self.sketch_tool = "NONE" if self.doc.active_sketch else self.sketch_tool
        self.sketch_palette.set_tool(self.sketch_tool)
        from omacad.ui.settings import get_settings
        if self.sketch_palette and get_settings().get("autohide_palette_on_measure", True):
            self.sketch_palette.hide()
        self.status_message.emit("Measure: click a line, circle, edge or face; click a second one to measure between them. Esc ends.")
        self.setFocus()
        self.update()
    def end_measure(self):
        if self.measure is not None:
            self.measure = None
            if self.doc.active_sketch and self.sketch_palette:
                self.sketch_palette.show()
                self.sketch_palette.place_default(self.size())
            self.status_message.emit("Measure closed.")
            self.update()
    def _measure_click(self, x: float, y: float):
        from omacad.model.measure import measure_2d, measure_3d
        m = self.measure
        if m["mode"] == "sketch":
            pick = self._pick_entity(x, y)
        else:   # an edge, else the flat face under the cursor (#102)
            pick = self._pick_edge(x, y)
            if pick is None:
                hit = self._pick_face(x, y)
                pick = hit[1] if hit is not None and hit[1].index >= 0 else None
        if pick is None:
            m["picks"], m["text"], m["segs"] = [], [], []
            self.update()
            return
        same = lambda a, b: (a.entity_id == b.entity_id) if m["mode"] == "sketch" else self._same_pick(a, b)
        if any(same(pick, p) for p in m["picks"]):
            m["picks"] = [p for p in m["picks"] if not same(pick, p)]
        else:
            m["picks"] = (m["picks"] + [pick]) if len(m["picks"]) < 2 else [pick]
        if m["picks"]:
            m["text"], m["segs"] = (measure_2d if m["mode"] == "sketch" else measure_3d)(m["picks"])
        else:
            m["text"], m["segs"] = [], []
        m["set_distance"] = self._measure_set_distance_plan() if m["mode"] == "model" else None
        if m["text"]:
            self.status_message.emit("Measure: " + "  |  ".join(m["text"]) +
                                     ("  |  Press D to set this distance" if m["set_distance"] else ""))
        self.update()
    @staticmethod
    def _face_key(p):
        return (p.body_id, p.index) if is_face(p) else None

    def _same_pick(self, a, b) -> bool:
        if is_face(a) or is_face(b):
            return self._face_key(a) == self._face_key(b)
        return self._same_edge(a, b)

    def _body_of_edge(self, edge):
        if is_face(edge):
            return self.doc.bodies.get(edge.body_id)
        return next((b for b in self.doc.bodies.values() if any(e is edge for e in b.edges)), None)
    def _measure_set_distance_plan(self):
        """Two edges on different bodies: (moving body, unit direction away from the first body, current gap)."""
        m = self.measure
        if m is None or m["mode"] != "model" or len(m["picks"]) != 2 or not m["segs"]:
            return None
        first, second = (self._body_of_edge(p) for p in m["picks"])
        if first is None or second is None or first is second:
            return None
        a, b = (np.asarray(q, dtype=float) for q in m["segs"][0])
        gap = float(np.linalg.norm(b - a))
        if gap < 1e-6:
            return None                          # touching: there is no direction to move in
        return second, (b - a) / gap, gap
    def _measure_set_distance(self):
        """Measure tool, key D: type the wanted distance and the second body moves along the measured line."""
        plan = self._measure_set_distance_plan()
        if plan is None:
            self.status_message.emit("Set distance: measure between edges or faces on two different bodies that are not touching.")
            return
        body, direction, gap = plan
        res = self.prompt_dimension_value("Set distance", f"Distance (mm); {body.name} moves along the measured line:",
                                          gap, 0.0, 50000.0, " mm")
        if res is None:
            return
        target = res[0]
        delta = (target - gap) * direction
        if np.linalg.norm(delta) > 1e-9:
            self.doc.move_body(body.body_id, float(delta[0]), float(delta[1]), float(delta[2]))
            self.status_message.emit(f"Moved {body.name} so the distance is {target:.3f} mm.")
        self.measure["picks"], self.measure["text"], self.measure["segs"], self.measure["set_distance"] = [], [], [], None
        self.update()
    def _draw_measure(self, painter: QPainter):
        m = self.measure
        if m is None:
            return
        sk = self.doc.active_sketch
        to_scr = (lambda q: self.world_to_screen(sk.plane.uv_to_world(q[0], q[1]))) if m["mode"] == "sketch" else \
                 (lambda q: self.world_to_screen(np.asarray(q, dtype=float)))
        from omacad.ui.settings import get_settings
        accent = get_settings().measure_color_qcolor()
        pen = QPen(accent, 3)
        painter.setPen(pen)
        for p in m["picks"]:
            pts = []
            if m["mode"] == "sketch":
                for a, b in p.to_lines():
                    pts.append((a, b))
            elif is_face(p):
                pts = face_outline(p)
            else:
                poly = p.polyline()
                pts = [(poly[i], poly[i + 1]) for i in range(len(poly) - 1)]
            for a, b in pts:
                sa, sb = to_scr(a), to_scr(b)
                if sa is not None and sb is not None:
                    painter.drawLine(QPointF(*sa), QPointF(*sb))
        dash = QPen(accent, 2, Qt.PenStyle.DashLine)
        painter.setPen(dash)
        for a, b in m["segs"]:
            if len(m["picks"]) == 2 or m["mode"] == "model":
                sa, sb = to_scr(a), to_scr(b)
                if sa is not None and sb is not None:
                    painter.drawLine(QPointF(*sa), QPointF(*sb))
                    painter.setBrush(accent)
                    painter.drawEllipse(QPointF(*sa), 3.5, 3.5)
                    painter.drawEllipse(QPointF(*sb), 3.5, 3.5)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
        # result panel
        lines = m["text"] or ["Measure: click a line, circle, edge or face"]
        if m.get("set_distance"):
            lines = lines + [f"D: set the distance (moves {m['set_distance'][0].name})"]
        font = QFont(theme.font_family(), 11)
        painter.setFont(font)
        fm = painter.fontMetrics()
        wbox = max(fm.horizontalAdvance(t) for t in lines) + 28
        hbox = fm.height() * len(lines) + 18
        rect = QRectF((self.width() - wbox) / 2.0, 14, wbox, hbox)
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(theme.qcolor(30, 34, 40, 235))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(theme.qcolor(224, 227, 231))
        for i, t in enumerate(lines):
            painter.drawText(QPointF(rect.x() + 14, rect.y() + 9 + fm.ascent() + i * fm.height()), t)
        painter.setBrush(Qt.BrushStyle.NoBrush)
