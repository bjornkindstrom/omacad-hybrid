"""Sketch operation, trim, mirror, fillet, and rubber band behavior."""

import math
import numpy as np
from PySide6.QtCore import Qt, QTimer
from omacad.ui.viewport.sketch_rotate_mixin import INFO as ROTATE_INFO
from omacad.model.sketch import Sketch


class SketchOperationMixin:
    """Interactive sketch operation methods used by :class:`Viewport3D`."""

    def set_sketch_tool(self, tool_name: str):
        """Sets the active 2D sketching tool and resets temporary anchors."""
        if hasattr(self, "constraint_help") and self.constraint_help.isVisible():
            self.constraint_help.dismiss()
        self._dim_pending = []
        self._dim_place = None
        self._dim_side = None
        self.picked_dim = None
        self.picked_dim_entities = (None, set())
        self.fillet_first_line = None
        self.fillet_hover_corner = None
        self.fillet_preview = None
        self.fillet_picked = []
        self._mirror_phase = "axis" if (tool_name == "MIRROR" and self.selected_entities) else "pick"
        if self._move:
            self._end_move(False)
        self.rotation_panel.hide()
        if getattr(self, "_pattern", None):
            self._pattern_finish(False)     # leaving Pattern without OK puts the sketch back
        self._rotate_drag = None
        self._move_phase = "base" if (tool_name == "MOVE" and self.selected_entities) else "pick"
        if tool_name == "ROTATE" and not self.selected_entities:
            self.status_message.emit("Rotate: select sketch elements first (click, Ctrl+click, or double-click for a whole figure).")
            tool_name = "NONE"
        self.sketch_tool = tool_name
        self.dyn.reset()
        self.smart.reset()
        if tool_name == "SMART_CIRCLE":
            QTimer.singleShot(0, self.setFocus)   # picked from the ribbon: the typed numbers must reach the view, not the button
            self.status_message.emit("Smart Circle: type the diameter, Enter. Then the distance to the nearest vertical line, Enter, "
                                     "then to the nearest horizontal line, Enter. Empty + Enter or a click takes the cursor position. "
                                     "Minus flips the side. Backspace on an empty field goes back.")
        self.sketch_start_uv = None
        self.sketch_second_uv = None
        self._spline_points = []
        self.sketch_current_uv = None
        if tool_name == "ROTATE" and not self._rotate_begin():
            self.sketch_tool = tool_name = "NONE"
        if tool_name == "PATTERN" and not self._pattern_begin():
            self.sketch_tool = tool_name = "NONE"
        self.sketch_palette.set_tool(tool_name)
        self._show_tool_panel(tool_name)
        self.sketch_tool_changed.emit(tool_name)
        if tool_name == "ROTATE":
            self.status_message.emit("Rotate: " + ROTATE_INFO)
        if tool_name == "MOVE":
            self._move_status()
        if tool_name == "OFFSET":
            self._offset_status()
        if tool_name == "MIRROR":
            self._mirror_status()
        if tool_name == "TRIM":
            self.status_message.emit("Trim: click the piece of a line, circle or arc to remove (up to the nearest crossings or the free end).")
        if tool_name == "FILLET":
            if self.selected_entities:
                self.fillet_selected_or_prompt()
            else:
                self.status_message.emit("Fillet: click a corner (Shift+click to pick several corners, then Enter), or click two lines or arcs. Esc cancels.")
        self.update()

    def project_edges(self):
        """Include / Project: the body edges in this sketch plane become sketch elements."""
        sk = self.doc.active_sketch
        if sk is None:
            return
        self.doc.refresh_sketch_references(sk)
        before = sk.to_dict()
        new = sk.include_reference_edges()
        if not new:
            self.status_message.emit("Project: no body edges in this sketch plane (or they are already included).")
            return
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = {e.entity_id for e in new}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.status_message.emit(f"Project: {len(new)} element(s) included from the body. They can be offset, trimmed and drawn on.")
        self.update()

    def _mirror_status(self):
        if self._mirror_phase == "pick":
            n = len(self.selected_entities)
            self.status_message.emit(f"Mirror 1/2: click the shapes to mirror ({n} selected; Ctrl+click = single element), then press Enter or right-click.")
        else:
            self.status_message.emit("Mirror 2/2: click the line (or an origin axis) to mirror across. Right-click = back.")

    def _mirror_next(self):
        if not self.selected_entities:
            self.status_message.emit("Mirror: click something to mirror first.")
            return
        self._mirror_phase = "axis"
        self._mirror_status()
        self.update()

    def _mirror_axis_at(self, x, y):
        """The mirror line under the cursor: a sketch line that is not itself selected, else an origin axis."""
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None:
            return None
        from omacad.model.sketch import SketchLine
        sk = self.doc.active_sketch
        tol = self._entity_tolerance()
        ent = sk.hit_test(uv[0], uv[1], tol)
        if isinstance(ent, SketchLine) and ent.entity_id not in self.selected_entities:
            return ent.p1, ent.p2
        if abs(uv[1]) <= tol:
            return (0.0, 0.0), (1.0, 0.0)
        if abs(uv[0]) <= tol:
            return (0.0, 0.0), (0.0, 1.0)
        return None

    def _mirror_hover(self, x, y):
        axis = self._mirror_axis_at(x, y) if self._mirror_phase == "axis" else None
        segs = []
        if axis:
            sk = self.doc.active_sketch
            from omacad.model.sketch import Sketch
            tmp = Sketch.from_dict(sk.to_dict())
            n0 = len(tmp.entities)
            try:
                tmp.mirror_entities(self.selected_entities, *axis)
            except Exception:
                tmp.entities = tmp.entities[:n0]
            for ent in tmp.entities[n0:]:
                for a, b in ent.to_lines():
                    segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
        arr = np.array(segs, dtype=np.float32) if segs else None
        if arr is not None or self.fillet_preview is not None:
            self.fillet_preview = arr
            self.update()

    def _mirror_at(self, x, y):
        axis = self._mirror_axis_at(x, y)
        if not axis:
            self.status_message.emit("Mirror: click a line (not one of the selected) or an origin axis.")
            return
        sk = self.doc.active_sketch
        before = sk.to_dict()
        new = sk.mirror_entities(self.selected_entities, *axis)
        self.fillet_preview = None
        if not new:
            self.status_message.emit("Mirror: nothing to mirror (lines, circles, arcs and slots are supported).")
            return
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = {e.entity_id for e in new}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.set_sketch_tool("NONE")
        self.status_message.emit(f"Mirror: {len(new)} element(s) mirrored.")
        self.update()

    def _trim_plan_at(self, x, y):
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None:
            return None
        from omacad.model.sketch_trim import trim_plan
        return trim_plan(self.doc.active_sketch, uv[0], uv[1], self._entity_tolerance())

    def _trim_hover(self, x, y):
        """Shows the piece a click would remove."""
        plan = self._trim_plan_at(x, y)
        segs = []
        if plan:
            sk = self.doc.active_sketch
            pts = [sk.plane.uv_to_world(*p) for p in plan[1]]
            for a, b in zip(pts, pts[1:]):
                segs += [*a, *b]
        arr = np.array(segs, dtype=np.float32) if segs else None
        if (arr is None) != (self.fillet_preview is None) or arr is not None:
            self.fillet_preview = arr
            self.update()

    def _trim_at(self, x, y):
        plan = self._trim_plan_at(x, y)
        if not plan:
            self.status_message.emit("Trim: click a line, circle or arc segment to remove (it ends at the nearest crossings).")
            return
        from omacad.model.sketch_trim import apply_trim
        sk = self.doc.active_sketch
        before = sk.to_dict()
        apply_trim(sk, plan)
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = set()
        self.fillet_preview = None
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.status_message.emit("Trim: removed. Click more pieces, or press Esc / right-click to finish.")
        self.update()

    def prompt_fillet_radius(self, line_a, line_b, corner_pt=None):
        """Interactive fillet creation with live OpenGL preview."""
        sk = self.doc.active_sketch
        if not sk:
            return
        from omacad.ui.settings import get_settings
        default_r = float(get_settings().get("fillet_default_radius", 2.0))

        def preview(radius):
            segs = []
            if radius > 0.05:
                from omacad.model.sketch import Sketch
                tmp = Sketch.from_dict(sk.to_dict())
                la = tmp.get_entity(line_a.entity_id)
                lb = tmp.get_entity(line_b.entity_id)
                if la and lb:
                    try:
                        arc, _ = tmp.fillet_corner(la, lb, radius, corner_pt)
                        if arc:
                            for a, b in arc.to_lines(24):
                                segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
                            for a, b in la.to_lines():
                                segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
                            for a, b in lb.to_lines():
                                segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
                    except Exception:
                        pass
            self.fillet_preview = np.array(segs, dtype=np.float32) if segs else None
            self.update()

        try:
            res = self.prompt_dimension_value("Fillet", "Radius:", default_r, lo=0.1, hi=2000.0, on_change=preview)
        finally:
            self.fillet_preview = None
            self.update()

        if res is None or res[0] <= 0.001:
            return

        radius = res[0]
        before = sk.to_dict()
        arc, msg = sk.fillet_corner(line_a, line_b, radius, corner_pt)
        if not arc:
            self.status_message.emit(f"Fillet: {msg}")
            return

        get_settings().set("fillet_default_radius", radius)
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = {arc.entity_id}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.status_message.emit(f"Fillet: corner rounded with radius {radius:g} mm.")
        self.update()

    def _start_rubber(self, event) -> bool:
        """Begin a box selection on empty sketch space (not while Alt is held: Alt+drag orbits)."""
        if event.modifiers() & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier):
            return False
        self._rubber = {"p0": event.position(), "p1": event.position(),
                        "additive": bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)}
        self.setCursor(Qt.CursorShape.CrossCursor)
        return True

    @staticmethod
    def _seg_hits_rect(a, b, r) -> bool:
        """Does the 2D segment a-b touch the rectangle r = (x0, y0, x1, y1)? (Liang-Barsky)"""
        x0, y0, x1, y1 = r
        dx, dy = b[0] - a[0], b[1] - a[1]
        t0, t1 = 0.0, 1.0
        for p_, q_ in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
            if abs(p_) < 1e-12:
                if q_ < 0:
                    return False
            else:
                t = q_ / p_
                if p_ < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
                if t0 > t1:
                    return False
        return True

    def _finish_rubber(self, event):
        rb = self._rubber
        self._rubber = None
        self.unsetCursor()
        self.update()
        if rb is None:
            return
        sk = self.doc.active_sketch
        p0, p1 = rb["p0"], rb["p1"]
        if sk is None:
            return
        if (p1 - p0).manhattanLength() < 5:   # a plain click on empty space
            if self.sketch_tool == "NONE" and not rb["additive"]:
                self.selected_entities.clear()
                self.selection_changed.emit()
            return
        crossing = p1.x() < p0.x()               # right to left: everything the box touches; left to right: only what is inside
        r = (min(p0.x(), p1.x()), min(p0.y(), p1.y()), max(p0.x(), p1.x()), max(p0.y(), p1.y()))
        inside = lambda q: q is not None and r[0] <= q[0] <= r[2] and r[1] <= q[1] <= r[3]

        def screen_lines(ent):
            out = []
            for a, b in ent.to_lines():
                sa, sb = self.world_to_screen(sk.plane.uv_to_world(*a)), self.world_to_screen(sk.plane.uv_to_world(*b))
                if sa is not None and sb is not None:
                    out.append((sa, sb))
            return out

        def hit(ent):
            segs = screen_lines(ent)
            if not segs:
                return False
            if crossing:
                return any(self._seg_hits_rect(a, b, r) for a, b in segs)
            return all(inside(a) and inside(b) for a, b in segs)

        if self.sketch_tool == "FILLET":
            added = 0
            for pt, la, lb, _ea, _eb in sk.find_corners():
                if inside(self.world_to_screen(sk.plane.uv_to_world(*pt))) and not any(
                        math.hypot(c[0][0] - pt[0], c[0][1] - pt[1]) < 1e-3 for c in self.fillet_picked):
                    self.fillet_picked.append((pt, la.entity_id, lb.entity_id))
                    added += 1
            self.status_message.emit(f"Fillet: {len(self.fillet_picked)} corner(s) picked ({added} new). Press Enter to set the radius, "
                                     "or drag/Shift+click for more.")
            self.update()
            return
        found = {e.entity_id for e in sk.entities if hit(e)}
        if self.sketch_tool == "OFFSET":
            chain = set()
            for eid in found:
                chain |= sk.connected_entities(eid)
            found = chain
            self.selected_entities |= found
            self._offset_status()
        elif rb["additive"]:
            self.selected_entities |= found
        else:
            self.selected_entities = found
        self.selection_changed.emit()
        self.update()

    def is_busy(self) -> bool:
        """True while a gesture or pick mode is in progress (undo must not interleave with it)."""
        if self._handle_drag or self._move or self._rubber is not None or self.edge_pick_mode or self.plane_pick_mode:
            return True
        if self.move_gizmo and self.move_gizmo.get("dragging"):
            return True
        return bool(self._drag and self._drag.get("moved"))

    def _fillet_apply_picked(self):
        """One radius for all corners picked with Shift (live preview, one undo step)."""
        sk = self.doc.active_sketch
        picks = list(self.fillet_picked)
        if not sk or not picks:
            return
        from omacad.model.sketch import Sketch
        from omacad.ui.settings import get_settings
        default_r = float(get_settings().get("fillet_default_radius", 2.0))

        def run(target, radius):
            arcs = []
            for pt, ida, idb in picks:
                la, lb = target.get_entity(ida), target.get_entity(idb)
                if la is None or lb is None:
                    continue
                try:
                    arc, _ = target.fillet_corner(la, lb, radius, pt)
                except Exception:
                    arc = None
                if arc:
                    arcs.append(arc)
            return arcs

        def preview(radius):
            segs = []
            if radius > 0.05:
                tmp = Sketch.from_dict(sk.to_dict())
                for arc in run(tmp, radius):
                    for a, b in arc.to_lines(24):
                        segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
            self.fillet_preview = np.array(segs, dtype=np.float32) if segs else None
            self.update()

        try:
            res = self.prompt_dimension_value("Fillet", f"Radius for {len(picks)} corner(s):", default_r, lo=0.1, hi=2000.0, on_change=preview)
        finally:
            self.fillet_preview = None
        if res is None or res[0] <= 0.001:
            self.update()
            return
        before = sk.to_dict()
        arcs = run(sk, res[0])
        if not arcs:
            self.status_message.emit("Fillet: none of the corners could be rounded with that radius.")
            self.update()
            return
        get_settings().set("fillet_default_radius", res[0])
        self.doc.record_sketch_change(sk, before)
        self.fillet_picked = []
        self.selected_entities = {a.entity_id for a in arcs}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        skipped = len(picks) - len(arcs)
        self.status_message.emit(f"Fillet: {len(arcs)} corner(s) rounded with radius {res[0]:g} mm" + (f" ({skipped} could not be rounded)." if skipped else "."))
        self.update()

    def fillet_selected_or_prompt(self):
        """Fillet corner(s) from current selection (2 lines or a shape like rectangle/polygon)."""
        sk = self.doc.active_sketch
        if not sk or not self.selected_entities:
            return
        from omacad.model.sketch import SketchArc, SketchLine
        cands = [sk.get_entity(eid) for eid in self.selected_entities if isinstance(sk.get_entity(eid), (SketchLine, SketchArc))]
        if len(cands) == 2:
            self.prompt_fillet_radius(cands[0], cands[1])
            return
        elif len(cands) > 2:
            corners = sk.find_corners(cands)
            if corners:
                from omacad.ui.settings import get_settings
                default_r = float(get_settings().get("fillet_default_radius", 2.0))
                res = self.prompt_dimension_value("Fillet", f"Radius for {len(corners)} corners:", default_r, lo=0.1, hi=2000.0)
                if res and res[0] > 0.001:
                    radius = res[0]
                    before = sk.to_dict()
                    created_arcs = []
                    for pt, la, lb, ea, eb in corners:
                        arc, msg = sk.fillet_corner(la, lb, radius, pt)
                        if arc:
                            created_arcs.append(arc)
                    if created_arcs:
                        get_settings().set("fillet_default_radius", radius)
                        self.doc.record_sketch_change(sk, before)
                        self.selected_entities = {a.entity_id for a in created_arcs}
                        self.selection_changed.emit()
                        self.doc.timeline.recompute(self.doc)
                        self.doc.notify_changed()
                        self.status_message.emit(f"Fillet: {len(created_arcs)} corners rounded with radius {radius:g} mm.")
                        self.update()
                    return
        self.status_message.emit("Fillet: click a corner between lines or arcs, or click two of them (Esc cancels).")
