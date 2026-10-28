"""Sketch constraints, dimension editing, and dimension menus."""

import math
from typing import Dict
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QCursor, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import QMenu
from omacad.model.sketch import SketchArc, SketchCircle, SketchLine, SketchSlot, SketchText, point_of
from omacad.model.dim_layout import offset_for_point
from omacad.model.sketch_solver import midpoint_spec, symmetric_spec
from omacad.ui import theme
from omacad.ui.theme import qcolor


class SketchDimensionsMixin:
    """Dimension and constraint workflows used by :class:`Viewport3D`."""

    def _reference_segments(self):
        """Body edges lying in the active sketch plane, as 2D (u,v) segments (cached)."""
        sk = self.doc.active_sketch
        if sk is None:
            return np.zeros((0, 2, 2))
        if self._ref_segments_cache and self._ref_segments_cache[0] == sk.sketch_id:
            return self._ref_segments_cache[1]
        plane = sk.plane
        o = np.asarray(plane.origin, dtype=np.float64)
        ua = np.asarray(plane.u_axis, dtype=np.float64)
        va = np.asarray(plane.v_axis, dtype=np.float64)
        segs = []
        for body in self.doc.bodies.values():
            mesh = body.render_mesh
            if not body.visible or mesh is None or len(mesh.sharp_lines) == 0:
                continue
            # Every body edge projected orthogonally onto the sketch plane: edges lying in the
            # plane keep their shape, perpendicular (e.g. vertical) edges collapse to points.
            pts = np.asarray(mesh.sharp_lines, dtype=np.float64).reshape(-1, 2, 3) - o
            uv = np.stack([pts @ ua, pts @ va], axis=-1)  # (N, 2, 2)
            segs.append(uv)
        if segs:
            allseg = np.concatenate(segs)
            # drop duplicates (top/bottom edges of a prism project onto each other)
            r = np.round(allseg, 3)
            swap = (r[:, 0, 0] > r[:, 1, 0]) | ((r[:, 0, 0] == r[:, 1, 0]) & (r[:, 0, 1] > r[:, 1, 1]))
            r[swap] = r[swap][:, ::-1]
            key = r.reshape(len(r), 4)
            _, idx = np.unique(key, axis=0, return_index=True)
            segs = allseg[np.sort(idx)]
        else:
            segs = np.zeros((0, 2, 2))
        self._ref_segments_cache = (sk.sketch_id, segs)
        return segs

    def apply_constraint(self, ctype: str, selected_order=None):
        """Applies a constraint to the selected sketch elements."""
        sk = self.doc.active_sketch
        if not sk:
            return False
        if selected_order:
            by_id = {e.entity_id: e for e in sk.entities}
            sel = [by_id[eid] for eid in selected_order if eid in by_id]
        else:
            sel = [e for e in sk.entities if e.entity_id in self.selected_entities]
        lines = [e for e in sel if isinstance(e, SketchLine)]
        circles = [e for e in sel if isinstance(e, SketchCircle)]
        unsupported = [e for e in sel if not isinstance(e, (SketchLine, SketchCircle))]
        specs = []
        if ctype in ("HORIZONTAL", "VERTICAL"):
            specs = [(ctype, [l.entity_id], []) for l in lines]
        elif ctype in ("PARALLEL", "PERPENDICULAR") and len(lines) >= 2:
            specs = [(ctype, [lines[0].entity_id, l.entity_id], []) for l in lines[1:]]
        elif ctype == "EQUAL":
            group = lines if len(lines) >= 2 else circles if len(circles) >= 2 else []
            specs = [(ctype, [group[0].entity_id, e.entity_id], []) for e in group[1:]]
        elif ctype == "TANGENT" and ((len(lines) == 1 and len(circles) == 1) or (not lines and len(circles) == 2)):
            pair = lines + circles if lines else circles
            specs = [(ctype, [pair[0].entity_id, pair[1].entity_id], [])]
        elif ctype == "CONCENTRIC" and len(circles) == 2 and not lines:
            specs = [(ctype, [circles[0].entity_id, circles[1].entity_id], [])]
        elif ctype == "COINCIDENT" and len(lines) == 2 and not circles:
            a, b = lines
            best = min(((pa, pb) for pa in ("p1", "p2") for pb in ("p1", "p2")),
                       key=lambda t: math.hypot(getattr(a, t[0])[0] - getattr(b, t[1])[0],
                                                getattr(a, t[0])[1] - getattr(b, t[1])[1]))
            specs = [(ctype, [a.entity_id, b.entity_id], list(best))]
        elif ctype == "MIDPOINT" and len(lines) + len(circles) == 2 and lines:
            specs = [midpoint_spec(lines, circles)]
        elif ctype == "SYMMETRIC":
            axis_id = selected_order[-1] if selected_order else None
            # Keep the mirrored pair's reference order stable for duplicate detection; only the
            # mirror-axis identity comes from the guide's final click.
            line_ids = {e.entity_id for e in lines}
            circle_ids = {e.entity_id for e in circles}
            lines = [e for e in sk.entities if e.entity_id in line_ids]
            circles = [e for e in sk.entities if e.entity_id in circle_ids]
            spec = symmetric_spec(lines, circles, axis_id=axis_id)
            specs = [spec] if spec else []
        elif ctype == "CENTER" and len(lines) == 8:
            group_a = self._constraint_rectangle_group(sk, lines[0])
            remaining = [line for line in lines if group_a is None or line.entity_id not in group_a]
            group_b = self._constraint_rectangle_group(sk, remaining[0]) if remaining else None
            selected_ids = {line.entity_id for line in lines}
            if (group_a and group_b and not (set(group_a) & set(group_b))
                    and selected_ids == set(group_a) | set(group_b)):
                specs = [(ctype, group_a + group_b, [])]
        elif ctype == "FIX":
            specs = [(ctype, [e.entity_id], []) for e in lines + circles]

        requested = len(specs)
        if ctype == "CENTER" and specs:
            refs = specs[0][1]
            selected_pair = {frozenset(refs[:4]), frozenset(refs[4:])}
            for constraint in sk.constraints:
                if constraint.ctype == "CENTER" and len(constraint.refs) == 8:
                    existing_pair = {frozenset(constraint.refs[:4]), frozenset(constraint.refs[4:])}
                    if selected_pair == existing_pair:
                        self.status_message.emit("These rectangles are already centred.")
                        return False
        existing = {(c.ctype, tuple(c.refs)) for c in sk.constraints}
        specs = [sp for sp in specs if (sp[0], tuple(sp[1])) not in existing]
        if not specs:
            if requested:
                self.status_message.emit("That constraint is already applied.")
            elif unsupported and not (lines or circles):
                self.status_message.emit("Constraints work on lines and circles for now (not rectangles, arcs or slots).")
            else:
                self.status_message.emit(self.CONSTRAINT_HINTS.get(ctype, ""))
            return False
        applied = self.doc.add_constraints(sk.sketch_id, specs)
        self.status_message.emit(self.doc.last_message)
        return applied

    def draw_dim_picks(self, painter: QPainter):
        """Rings on the end points picked by the dimension tool, and a dashed link while placing."""
        sk = self.doc.active_sketch
        if not sk or self.sketch_tool != "DIMENSION":
            return
        for p in self._dim_pending:
            if p[0] == "ref":
                (a, b) = p[1]
                sa = self.world_to_screen(sk.plane.uv_to_world(a[0], a[1]))
                sb = self.world_to_screen(sk.plane.uv_to_world(b[0], b[1]))
                if sa and sb:
                    painter.setPen(QPen(qcolor(226, 109, 40), 3))
                    painter.drawLine(QPointF(sa[0], sa[1]), QPointF(sb[0], sb[1]))
        picks = [p for p in self._dim_pending if p[0] == "pt"]
        if self._dim_place:
            picks += [self._dim_place["a"], self._dim_place["b"]]
        plane = sk.plane
        screen = []
        for _, ent, name in picks:
            uv = point_of(ent, name)
            scr = self.world_to_screen(plane.uv_to_world(uv[0], uv[1])) if uv else None
            if scr:
                screen.append(QPointF(scr[0], scr[1]))
                painter.setPen(QPen(qcolor(226, 109, 40), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(scr[0], scr[1]), 7, 7)
        if self._dim_place and len(screen) >= 2:
            painter.setPen(QPen(qcolor(226, 109, 40, 200), 1.2, Qt.PenStyle.DashLine))
            painter.drawLine(screen[0], screen[1])

    def draw_constraint_badges(self, painter: QPainter):
        """Small glyphs next to constrained geometry; click one to remove the constraint."""
        self.constraint_badges = []
        sk = self.doc.active_sketch
        if not sk or not sk.constraints:
            return
        plane = sk.plane
        ents = {e.entity_id: e for e in sk.entities}
        stacked: Dict[str, int] = {}
        painter.setFont(QFont(theme.font_family(), 9, QFont.Weight.Bold))
        show_all = self.sketch_palette.chk_show_constraints.isChecked()
        show_const = self.sketch_palette.chk_show_construction.isChecked()
        focus = self.selected_entities | ({self.hover_entity_id} if self.hover_entity_id else set())
        for c in sk.constraints:
            ent = ents.get(c.refs[0]) if c.refs else None
            if ent is None:
                continue
            if not show_const and any(getattr(ents.get(r), "is_construction", False) for r in c.refs):
                continue
            grp = {getattr(ents.get(r), "group", None) for r in c.refs}
            if len(grp) == 1 and None not in grp and c.ctype in ("POINT_ON_CIRCLE", "EQUAL", "COINCIDENT"):
                continue   # the built-in relations of a polygon stay out of sight
            if not show_all and not (set(c.refs) & focus):
                continue
            if c.ctype in ("COINCIDENT", "MIDPOINT") and c.pts:
                uv = getattr(ent, c.pts[0], None) or (0.0, 0.0)
            elif isinstance(ent, SketchLine):
                uv = ((ent.p1[0] + ent.p2[0]) / 2.0, (ent.p1[1] + ent.p2[1]) / 2.0)
            elif isinstance(ent, SketchCircle):
                uv = (ent.center[0] + ent.radius * 0.7071, ent.center[1] + ent.radius * 0.7071)
            else:
                continue
            scr = self.world_to_screen(plane.uv_to_world(uv[0], uv[1]))
            if scr is None:
                continue
            n = stacked.get(c.refs[0], 0)
            stacked[c.refs[0]] = n + 1
            rect = QRectF(scr[0] + 8 + n * 20, scr[1] - 24, 18, 18)
            painter.setBrush(QBrush(qcolor(30, 34, 40, 235)))
            painter.setPen(QPen(qcolor(56, 189, 248), 1.2))
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(qcolor(224, 227, 231))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.CONSTRAINT_GLYPHS.get(c.ctype, "?"))
            self.constraint_badges.append((rect, c.cid))

    @property
    def _dim_place(self):
        return self._dim_place_v

    @_dim_place.setter
    def _dim_place(self, value):
        self._dim_place_v = value
        if value is None:
            self._hide_dim_box()

    def _hide_dim_box(self):
        box, self._dim_box = getattr(self, "_dim_box", None), None
        if box is not None:
            box.hide()
            box.deleteLater()

    def _dim_drag_move(self, event):
        from omacad.model.dim_layout import offset_for_point
        d = self._dim_drag
        if not d["moved"] and (event.position() - d["press"]).manhattanLength() < 5:
            return
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        off = offset_for_point(d["sketch"], d["dim"], uv) if uv is not None and d["dim"] is not None else None
        if off is None:
            return                              # this kind of dimension has nothing to move: a click still edits it
        d["moved"] = True
        d["dim"].offset_distance = float(off)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.update()

    def dim_badge_at(self, x: float, y: float):
        """(sketch_id, dim_id) of the dimension badge under the screen point, or None."""
        for rect, s_id, d_id, _val in list(self.dim_badges.values()):
            if rect.contains(x, y):
                return s_id, d_id
        return None

    def dimension_to_delete(self):
        """Del in a sketch: the badge under the mouse, else the dimension picked in the browser (#101)."""
        pos = self.mapFromGlobal(QCursor.pos())
        hit = self.dim_badge_at(pos.x(), pos.y()) if self.rect().contains(pos) else None
        return hit or self.picked_dim

    def delete_dimension(self, sketch_id: str, dim_id: str) -> bool:
        if self.picked_dim == (sketch_id, dim_id):
            self.show_dimension_entities("", "")
        ok = self.doc.remove_dimension(sketch_id, dim_id)
        if ok:
            self.status_message.emit(self.doc.last_message)
        self.update()
        return ok

    def _show_dimension_menu(self, event, sketch_id: str, dim_id: str):
        """Right-click on a dimension badge: change the value or delete the dimension."""
        sk = self.doc.sketches.get(sketch_id)
        dim = next((d for d in sk.dimensions if d.dim_id == dim_id), None) if sk else None
        if dim is None:
            return
        menu = QMenu(self)
        theme.style_menu(menu)
        edit = theme.action_with_icon(menu, "✏️ Edit value…")
        delete = theme.action_with_icon(menu, "🗑️ Delete dimension\tDel")
        chosen = menu.exec(event.globalPosition().toPoint())
        if chosen is edit:
            self.prompt_edit_dimension(sketch_id, dim_id, dim.value)
        elif chosen is delete:
            self.delete_dimension(sketch_id, dim_id)

    def _dim_drag_release(self):
        d, self._dim_drag = self._dim_drag, None
        self.unsetCursor()
        if d["moved"]:
            self.doc.record_sketch_change(d["sketch"], d["before"])   # one undo step for the whole drag
            self.update()
        elif d["sketch"] is not None:
            self.prompt_edit_dimension(d["sketch"].sketch_id, d["dim"].dim_id, d["value"])

    def _start_guided_dimension(self, pending, hint: str, side=None):
        """Switches to the dimension tool with the first element already picked; the status bar says
        what to click next."""
        self.set_sketch_tool("DIMENSION")
        self._dim_pending = list(pending)
        self._dim_side = side
        self.status_message.emit(hint)
        self.update()

    def _show_element_menu(self, event, ent):
        """Right-click on a line/circle: dimensions and constraints for that element, with help text."""
        sk = self.doc.active_sketch
        self.selected_entities = {ent.entity_id}
        self.selection_changed.emit()
        self.update()
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        acts = {}

        def add(key, label, tip):
            a = theme.action_with_icon(menu, label)
            a.setToolTip(tip)
            a.setStatusTip(tip)
            acts[a] = key
            return a

        def heading(text):
            h = menu.addAction(text)
            h.setEnabled(False)

        members = sk.group_entities(ent)
        poly_circle = next((m for m in members if isinstance(m, SketchCircle)), None)
        poly_line = next((m for m in members if isinstance(m, SketchLine)), None)
        if poly_circle is not None and poly_line is not None:
            heading("Polygon - set a dimension")
            add("p_side", "📏 Side length…", "Type how long each side should be (all sides stay equal).")
            add("p_dia", "Ø Circle through the corners…", "Type the diameter of the circle the corners lie on (corner to corner across the centre).")
            add("p_centre", "◎ Distance from the centre to…", "Then click a point, a line or a face edge to measure from the middle of the polygon.")
            add("p_fix", "🔒 Fix the polygon in place", "Locks the whole polygon so it can't move.")
            menu.addSeparator()
        if isinstance(ent, SketchLine):
            heading("Line - set a dimension")
            add("length", "📏 Length…", "Type how long this line should be.")
            add("angle", "📐 Angle to another line…", "Then click the other line; you get an angle between them.")
            add("p1", "📍 Distance from start point to…", "Then click a point, another line or a face edge to measure to it.")
            add("p2", "📍 Distance from end point to…", "Then click a point, another line or a face edge to measure to it.")
            menu.addSeparator()
            heading("Make it")
            add("horizontal", "━ Horizontal", "Keeps the line level.")
            add("vertical", "┃ Vertical", "Keeps the line upright.")
            add("fix", "🔒 Fixed in place", "Locks the line so it can't move or change.")
        elif isinstance(ent, SketchCircle):
            heading("Circle - set a dimension")
            add("diameter", "Ø Diameter…", "Type the diameter of the circle.")
            add("centre", "◎ Distance from the centre to…", "Then click a point, a line or a face edge to measure from the centre.")
            add("near", "⭕ Distance from the nearest edge to…", "Then click a line or a face edge; measured from the side of the circle facing it.")
            add("far", "⭕ Distance from the far edge to…", "Then click a line or a face edge; measured from the side of the circle facing away.")
            menu.addSeparator()
            heading("Make it")
            add("fix", "🔒 Fixed in place", "Locks the circle so it can't move or change.")
        elif isinstance(ent, SketchArc):
            heading("Arc - set a dimension")
            add("arc_radius", "R Radius…", "Type the radius of the arc.")
        elif isinstance(ent, SketchSlot):
            heading("Slot - set a dimension")
            add("slot_length", "📏 Center-to-center length…", "Type the distance between the two slot centres.")
            add("slot_width", "Ø Width (diameter)…", "Type the width (2 × radius) of the slot.")
        elif isinstance(ent, SketchText):
            heading("Text")
            add("edit_text", "✏️ Edit Text…", "Change the words, the font, the height, the alignment or the path.")
            add("explode_text", "💥 Explode Text", "Turns the text into ordinary lines. It can no longer be edited as text.")
        else:
            from omacad.model.sketch_entities import SketchSpline
            if isinstance(ent, SketchSpline):
                heading("Spline")
                add("insert_point", "➕ Insert Fit Point", "Adds a fit point to the curve at the cursor position.")
        menu.addSeparator()
        add("fillet", "╭ Fillet corner…  (F)", "Rounds a corner between lines with an arc.")
        add("offset", "↔️ Offset…  (O)", "Makes a parallel copy at a distance you type (select several, or double-click, to offset a whole shape).")
        add("delete", "🗑️ Delete", "Removes this element (and its dimensions).")
        menu.addSeparator()
        general: dict = {}
        self._add_history_and_view(menu, general, True)

        chosen = menu.exec(event.globalPosition().toPoint())
        if chosen in general:
            self._run_general(*general[chosen])
            return
        key = acts.get(chosen)
        if key is None:
            return
        pt = lambda name: [("pt", ent, name)]
        if key == "insert_point":
            uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
            if uv is not None:
                before = sk.to_dict()
                try:
                    idx = sk.insert_spline_point(ent.entity_id, uv)
                    if self.doc.record_sketch_change(sk, before):
                        self.doc.timeline.recompute(self.doc)
                    self.selected_entities = {ent.entity_id}
                    self.selection_changed.emit()
                    self.status_message.emit(f"Inserted spline point #{idx + 1}")
                    self.update()
                except Exception as e:
                    self.status_message.emit(f"Could not insert point: {e}")
            return
        if key == "edit_text":
            self.text_edit_requested.emit(ent.entity_id)
            return
        if key == "explode_text":
            before = sk.to_dict()
            sk.explode_text(ent.entity_id)
            self.selected_entities.clear()
            self.doc.record_sketch_change(sk, before)
            self.update()
            return
        if key == "arc_radius":
            self._dim_arc(ent)
            return
        if key == "slot_length":
            self._dim_slot_length(ent)
            return
        if key == "slot_width":
            self._dim_slot_width(ent)
            return
        if key == "p_side":
            self._dim_length(poly_line)
            return
        if key == "p_dia":
            self._dim_circle(poly_circle)
            return
        if key == "p_centre":
            self._start_guided_dimension([("pt", poly_circle, "center")], "Distance from the polygon's centre: click a point, a line or a face edge.")
            return
        if key == "p_fix":
            self.selected_entities = {m.entity_id for m in members}
            self.apply_constraint("FIX")
            return
        if key == "length":
            self._dim_length(ent)
        elif key == "diameter":
            self._dim_circle(ent)
        elif key == "angle":
            self._start_guided_dimension([("ent", ent)], "Angle: click the other line. (Click empty space instead to dimension the length.)")
        elif key in ("p1", "p2"):
            self._start_guided_dimension(pt(key), "Distance: click a point, another line or a face edge to measure to.")
        elif key == "centre":
            self._start_guided_dimension(pt("center"), "Distance from the centre: click a point, a line or a face edge.")
        elif key in ("near", "far"):
            self._start_guided_dimension([("ent", ent)], f"Distance from the {key} edge: click a line or a face edge to measure to.", side=key)
        elif key in ("horizontal", "vertical"):
            self.apply_constraint(key.upper())
        elif key == "fix":
            self.apply_constraint("FIX")
        elif key == "fillet":
            self.set_sketch_tool("FILLET")
        elif key == "offset":
            self.set_sketch_tool("OFFSET")
        elif key == "delete":
            self.delete_selected_entities()
