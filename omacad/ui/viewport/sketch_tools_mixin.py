"""Sketch entity editing, dynamic input, and Smart Circle behavior."""

import math
from typing import Dict, Tuple
import numpy as np
from PySide6.QtCore import Qt, QEvent, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QFont, QPolygonF
from omacad.model.hover_info import describe_entity
from omacad.model.sketch_solver import solve_sketch
from omacad.model.sketch import Sketch, SketchLine, SketchSpline, ref_id
from omacad.model import expr as expr_lib
from omacad.ui import dyn_input, smart_circle, theme
from omacad.ui.viewport.events_mixin import SKETCH_KEYS
from omacad.ui.theme import qcolor


class SketchToolsMixin:
    """Sketch editing and tool helpers used by :class:`Viewport3D`."""

    def _entity_tolerance(self) -> float:
        """8 screen pixels expressed in sketch units."""
        mm_per_px = self.distance * 2.0 * math.tan(math.radians(self.fovy) / 2.0) / max(1, self.height())
        return 8.0 * mm_per_px
    def _can_select_sketch_entities(self) -> bool:
        return bool(self.doc.active_sketch and self.sketch_tool == "NONE" and not self.plane_pick_mode)
    def _pick_entity(self, x: float, y: float):
        uv = self.get_sketch_plane_uv(x, y)
        if uv is None:
            return None
        show_const = self.sketch_palette.chk_show_construction.isChecked()
        return self.doc.active_sketch.hit_test(uv[0], uv[1], self._entity_tolerance(), include_construction=show_const)

    def _pick_spline_handle(self, x: float, y: float):
        """Checks if (x, y) hits a fit point or tangent handle on a selected spline.
        Returns dict(entity, kind: 'point'|'tangent', index: int, handle_sign: float) or None."""
        if not self._can_select_sketch_entities() or not self.doc.active_sketch:
            return None
        sk = self.doc.active_sketch
        plane = sk.plane
        sel_splines = [e for e in sk.entities if e.entity_id in self.selected_entities and isinstance(e, SketchSpline)]
        if not sel_splines:
            return None

        # Search tangent handles first (tip circles), then fit points
        tol_px = 9.0
        for spline in sel_splines:
            # 1. Tangent handles
            for i in range(len(spline.points)):
                pt = spline.points[i]
                t_vec = spline.tangent_at(i)
                # Show handle in positive and (if not start) negative direction
                for sign in (1.0, -1.0) if (0 < i < len(spline.points) - 1) else (1.0 if i == 0 else -1.0,):
                    tip_uv = (pt[0] + sign * t_vec[0], pt[1] + sign * t_vec[1])
                    scr = self.world_to_screen(plane.uv_to_world(*tip_uv))
                    if scr and math.hypot(scr[0] - x, scr[1] - y) <= tol_px:
                        return {"entity": spline, "kind": "tangent", "index": i, "handle_sign": sign}

            # 2. Fit points
            for i, pt in enumerate(spline.points):
                scr = self.world_to_screen(plane.uv_to_world(*pt))
                if scr and math.hypot(scr[0] - x, scr[1] - y) <= tol_px:
                    return {"entity": spline, "kind": "point", "index": i, "handle_sign": 1.0}

        return None

    def _free_endpoints(self):
        """Returns list of (entity, point_name, (u, v)) for endpoints of lines and arcs not connected to anything."""
        if not self.doc.active_sketch:
            return []
        sk = self.doc.active_sketch
        tol = 1e-4
        ends = []
        for e in sk.entities:
            if e.is_construction or getattr(e, "projected", False):
                continue
            if getattr(e, "entity_type", "") == "line":
                ends.append((e, "p1", e.p1))
                ends.append((e, "p2", e.p2))
            elif getattr(e, "entity_type", "") == "arc":
                ends.append((e, "p_start", e.p_start))
                ends.append((e, "p_end", e.p_end))
            elif getattr(e, "entity_type", "") == "spline" and len(getattr(e, "points", [])) >= 2:
                ends.append((e, 0, e.points[0]))
                ends.append((e, len(e.points) - 1, e.points[-1]))

        free = []
        for i, (e, name, pt) in enumerate(ends):
            coincident = False
            for j, (oe, oname, opt) in enumerate(ends):
                if i != j and abs(pt[0] - opt[0]) < tol and abs(pt[1] - opt[1]) < tol:
                    coincident = True
                    break
            if not coincident:
                free.append((e, name, pt))
        return free

    def _pick_free_endpoint(self, x: float, y: float):
        """Checks if (x, y) hits a free endpoint dot."""
        if not self._can_select_sketch_entities() or not self.doc.active_sketch:
            return None
        sk = self.doc.active_sketch
        plane = sk.plane
        tol_px = 9.0
        for e, name, pt in self._free_endpoints():
            scr = self.world_to_screen(plane.uv_to_world(*pt))
            if scr and math.hypot(scr[0] - x, scr[1] - y) <= tol_px:
                return {"entity": e, "point_name": name, "uv": pt}
        return None
    def _update_entity_hover(self, x: float, y: float):
        active = self._can_select_sketch_entities() or (self.doc.active_sketch is not None and (self.sketch_tool in ("DIMENSION", "OFFSET") or self.measure is not None))
        if self.sketch_tool == "TEXT":
            return                                  # the Text tool lights up its own path curve
        ent = self._pick_entity(x, y) if active else None
        hid = ent.entity_id if ent else None
        if hid != self.hover_entity_id:
            self.hover_entity_id = hid
            self.hover_info_changed.emit(describe_entity(ent) if ent else None)
            self.update()
    def select_entity_at(self, x: float, y: float, additive: bool):
        ent = self._pick_entity(x, y)
        if ent is None:
            if not additive:
                self.selected_entities.clear()
        elif additive:
            self.selected_entities ^= {ent.entity_id}
        else:
            self.selected_entities = {ent.entity_id}
        self.selection_changed.emit()
        self.update()
    def _offset_status(self):
        n = len(self.selected_entities)
        self.status_message.emit(f"Offset: click a curve for its whole chain (Shift/Ctrl/Alt+click = add or drop single line). "
                                 f"{n} selected. Press Enter or right-click to set the distance. Esc cancels.")
    def _offset_go(self):
        if not self.selected_entities:
            self.status_message.emit("Offset: click the curves to offset first.")
            return
        self.offset_selected()
        self.set_sketch_tool("NONE")
    def offset_selected(self):
        """Offset (O): parallel copies of the selected sketch elements at a typed distance."""
        sk = self.doc.active_sketch
        if not sk:
            return
        if not self.selected_entities:
            self.status_message.emit("Offset: select the sketch elements first (click, Ctrl+click, double-click for a whole shape), then press O.")
            return
        ids = set(self.selected_entities)

        def preview(value):
            segs = []
            if abs(value) > 1e-9:
                from omacad.model.sketch import Sketch
                tmp = Sketch.from_dict(sk.to_dict())
                n0 = len(tmp.entities)
                try:
                    tmp.offset_entities(ids, value)
                except Exception:
                    tmp.entities = tmp.entities[:n0]
                for ent in tmp.entities[n0:]:
                    for a, b in ent.to_lines():
                        segs += [*sk.plane.uv_to_world(*a), *sk.plane.uv_to_world(*b)]
            self.offset_preview = np.array(segs, dtype=np.float32) if segs else None
            self.update()

        try:
            res = self.prompt_dimension_value("Offset", "Distance (negative = inward for a closed shape, positive = outward; for an open curve: positive = left of its direction):",
                                              5.0, lo=-5000.0, hi=5000.0, on_change=preview)
        finally:
            self.offset_preview = None
            self.update()
        if res is None or abs(res[0]) < 1e-9:
            return
        before = sk.to_dict()
        new = sk.offset_entities(self.selected_entities, res[0])
        if not new:
            self.status_message.emit("Offset: nothing could be offset by that distance (a shape can't shrink past its own size).")
            return
        self.doc.record_sketch_change(sk, before)
        self.selected_entities = {e.entity_id for e in new}
        self.selection_changed.emit()
        self.doc.timeline.recompute(self.doc)
        self.doc.notify_changed()
        self.status_message.emit(f"Offset: {len(new)} element(s) created {res[0]:g} mm away.")
        self.update()
    def delete_selected_entities(self) -> int:
        sk = self.doc.active_sketch
        if not sk or not self.selected_entities:
            return 0
        ids = set(self.selected_entities)
        self.selected_entities.clear()
        self.sketch_start_uv = None
        n = self.doc.delete_sketch_entities(sk.sketch_id, ids)
        self.selection_changed.emit()
        return n

    def _finish_spline(self):
        sketch = self.doc.active_sketch
        points = list(getattr(self, "_spline_points", []))
        if sketch is not None and len(points) >= 2:
            before = sketch.to_dict()
            sketch.add_spline(points, is_construction=self.construction_mode)
            self.doc.record_sketch_change(sketch, before)
            self.doc.timeline.recompute(self.doc)
            self.doc.notify_changed()
            self.status_message.emit(f"Spline: created through {len(points)} points.")
        elif points:
            self.status_message.emit("Spline: add another point, or Esc to cancel.")
        self._spline_points = []
        self.sketch_start_uv = None
        self.dyn.reset()
        self.dyn_live = {}
        self.update()

    def _commit_sketch_point(self, p2: Tuple[float, float]):
        """Second (or later) click of the active tool: create/advance the shape."""
        sketch = self.doc.active_sketch
        p1 = self.sketch_start_uv
        if self.sketch_tool == "SPLINE":
            points = getattr(self, "_spline_points", [])
            if points and math.hypot(p2[0] - points[-1][0], p2[1] - points[-1][1]) > 1e-4:
                points.append(tuple(p2))
                self.sketch_start_uv = tuple(p2)
                self.status_message.emit(f"Spline: {len(points)} points; Enter or right-click finishes.")
            self.update()
            return
        if self.sketch_tool == "MOVE":
            if self._move:
                self._apply_move(p2[0] - p1[0], p2[1] - p1[1])   # Move only translates; Rotate is its own tool
                self._end_move(True)
            self.sketch_start_uv = None
            self.dyn.reset()
            self.dyn_live = {}
            self.set_sketch_tool("NONE")
            return
        before = sketch.to_dict()
        is_const = self.construction_mode
        created = None
        typed_formulas = {name: text for name, text in zip(self.dyn.names, self.dyn.texts)
                          if text.strip() and not expr_lib.is_plain_number(text)} if self.dyn.active else {}
        dims_before = len(sketch.dimensions)

        if self.sketch_tool == "LINE":
            if p1 != p2:
                created = sketch.add_line(p1, p2, is_construction=is_const)
                self.sketch_start_uv = p2  # continue chaining line
        elif self.sketch_tool == "RECT":
            if p1 != p2:
                created = sketch.add_rect(p1, p2, is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "ROUNDED_RECT":
            if p1 != p2:
                created = sketch.add_rounded_rect(p1, p2, self._corner_radius(), is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "CENTER_RECT":
            if p1 != p2:
                created = sketch.add_center_rect(p1, p2, is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "CENTER_ROUNDED_RECT":
            if p1 != p2:
                created = sketch.add_center_rounded_rect(p1, p2, self._corner_radius(), is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "POLYGON":
            if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) > 0.5:
                sketch.add_polygon(p1, p2, self._polygon_sides(), is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "CIRCLE":
            r = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if r > 0.5:
                created = sketch.add_circle(p1, r, is_construction=is_const)
            self.sketch_start_uv = None
        elif self.sketch_tool == "ARC":
            if self.sketch_second_uv is None:
                self.sketch_second_uv = p2
            else:
                sketch.add_arc(p1, p2, self.sketch_second_uv, is_construction=is_const)
                self.sketch_start_uv = None
                self.sketch_second_uv = None
        elif self.sketch_tool == "SLOT":
            if self.sketch_second_uv is None:
                self.sketch_second_uv = p2
            else:
                d = self._point_to_segment_dist(p2, p1, self.sketch_second_uv)
                r = max(2.0, d)
                sketch.add_slot(p1, self.sketch_second_uv, r, is_construction=is_const)
                self.sketch_start_uv = None
                self.sketch_second_uv = None

        for d_new in sketch.dimensions[dims_before:]:  # a typed "width/2" stays a formula on its dimension
            if d_new.name in typed_formulas:
                d_new.expr = typed_formulas[d_new.name]
        if isinstance(created, list):
            solve_sketch(sketch)  # rectangle: refresh the degrees-of-freedom status
        if created is not None and isinstance(created, SketchLine) and self.sketch_palette.chk_auto_constraints.isChecked():
            self._auto_constrain_line(sketch, created)
        self.doc.record_sketch_change(sketch, before)
        self.dyn.reset()
        self.dyn_live = {}
        self._arm_dyn()  # chained line: next segment starts with its first field active
        self.doc.notify_changed()
    def _arm_dyn(self):
        """After a start point exists the first dimension field is active so numbers can be typed at once."""
        self.dyn.reset()
        self.dyn_live = {}
        if self._dyn_can_start():
            self.dyn.start(self.sketch_tool)
            self.dyn.focus = 0
            self._apply_panel_locks()

    # ---- tool panel (Björn #76): the tool's numbers as fields with sliders in the sketch palette ----------------
    def _init_tool_panel(self):
        from omacad.ui.sketch_tool_panel import SketchToolPanel
        self.tool_panel = SketchToolPanel(self.sketch_palette.content_widget)
        self.sketch_palette.content_widget.layout().insertWidget(0, self.tool_panel)
        self.tool_panel.hide()
        self.tool_panel.locked.connect(self._panel_locked)
        self.tool_panel.unlocked.connect(self._panel_unlocked)
        self.tool_panel.default_changed.connect(self._panel_default)

    def _show_tool_panel(self, tool: str):
        sk = self.doc.active_sketch
        axis_names = sk.plane.axis_names() if sk is not None else ("X", "Y")
        self.tool_panel.show_tool(tool, axis_names=axis_names)
        if self.tool_panel.chk_copy is not None:
            self.tool_panel.chk_copy.toggled.connect(lambda _on: self.update())   # originals shown / hidden
        self.tool_panel.set_values({"Sides": float(self.sketch_palette.spn_sides.value()),
                                    "Radius": self.sketch_palette.spn_corner_radius.value()})
        self.sketch_palette.adjustSize()

    def _apply_panel_locks(self):
        """Values set in the panel go into the matching Tab fields that were not typed in."""
        if not self.dyn.active:
            return
        for name, v in self.tool_panel.locks.items():
            if name in self.dyn.names:
                i = self.dyn.names.index(name)
                if not self.dyn.texts[i]:
                    self.dyn.texts[i] = repr(float(v))

    def _panel_locked(self, name: str, value: float):
        if self.sketch_tool == "MOVE" and self.sketch_start_uv is None and self.selected_entities:
            self._move_auto_base()          # move straight away from the selection's centre, like Move for bodies
        if self.dyn.active and name in self.dyn.names:
            self.dyn.texts[self.dyn.names.index(name)] = repr(float(value))
            self._refresh_dyn()
        self.update()

    def _panel_unlocked(self):
        if self.dyn.active:
            self.dyn.texts = [""] * len(self.dyn.names)
            self._refresh_dyn()
        self.update()

    def _panel_default(self, name: str, value: float):
        spin = {"Sides": self.sketch_palette.spn_sides, "Radius": self.sketch_palette.spn_corner_radius}[name]
        spin.setValue(int(round(value)) if name == "Sides" else value)
        self._refresh_dyn()
        self.update()

    def _move_auto_base(self):
        """Move: the base point is the centre of the picked elements (a click in the view picks another)."""
        if self._move_phase == "pick":
            self._move_phase = "base"
        self._begin_move(self.selected_entities)
        self.sketch_start_uv = tuple(self._move["pivot"])
        self._raw_mouse_uv = self.sketch_start_uv
        self._arm_dyn()
    def _auto_constrain_line(self, sketch, line):
        """Fusion-style inference: horizontal/vertical lines and end points that meet other lines."""
        eid = line.entity_id
        specs = []
        dx, dy = line.p2[0] - line.p1[0], line.p2[1] - line.p1[1]
        if abs(dy) < 1e-6 * max(1.0, abs(dx)):
            specs.append(("HORIZONTAL", [eid], []))
        elif abs(dx) < 1e-6 * max(1.0, abs(dy)):
            specs.append(("VERTICAL", [eid], []))
        for pname in ("p1", "p2"):
            mine = getattr(line, pname)
            for other in sketch.entities:
                if other is line or not isinstance(other, SketchLine):
                    continue
                for oname in ("p1", "p2"):
                    o = getattr(other, oname)
                    if math.hypot(mine[0] - o[0], mine[1] - o[1]) < 1e-6:
                        specs.append(("COINCIDENT", [eid, other.entity_id], [pname, oname]))
                        break
                else:
                    continue
                break
        if specs:
            self.doc.auto_constrain(sketch, specs)
    def _dyn_can_start(self) -> bool:
        return bool(
            self.doc.active_sketch
            and self.sketch_start_uv is not None
            and self.sketch_second_uv is None
            and dyn_input.supports(self.sketch_tool)
        )
    def _corner_radius(self) -> float:
        """Corner radius of the rounded rectangles: a typed Radius wins over the palette spinner."""
        if self.dyn.active and "Radius" in self.dyn.names:
            v = self.dyn.locked_values().get("Radius")
            if v is not None:
                return max(0.1, abs(v))
        return self.sketch_palette.spn_corner_radius.value()
    def _polygon_sides(self) -> int:
        """Sides for the Polygon tool: a typed value wins over the palette spinner."""
        n = self.sketch_palette.spn_sides.value()
        if self.dyn.active and self.dyn.tool == "POLYGON":
            v = self.dyn.locked_values().get("Sides")
            if v is not None:
                n = max(3, min(200, int(round(v))))
        return n
    def _refresh_dyn(self):
        """Re-resolves the pending end point from mouse + typed values."""
        if not (self.dyn.active and self._dyn_can_start()):
            return
        mouse = self._raw_mouse_uv or self.sketch_start_uv
        self.dyn.default_sides = self.sketch_palette.spn_sides.value()
        self.dyn.default_radius = self.sketch_palette.spn_corner_radius.value()
        end, live = self.dyn.resolve(self.sketch_start_uv, mouse)
        self.sketch_current_uv = end
        self.dyn_live = live
        self.tool_panel.set_values(live)
        if self.sketch_tool == "MOVE" and self._move:
            self._apply_move(end[0] - self.sketch_start_uv[0], end[1] - self.sketch_start_uv[1])
        self.update()
    _dyn_list = None          # ParameterList under the focused dimension field while a name is typed
    _dyn_focus_rect = None    # where the focused field was drawn last

    def _dyn_suggest(self):
        """List the parameters starting with the name being typed in the focused field (as in the panels' fields)."""
        from omacad.ui.expr_spin import ParameterList, formula_hint, matching_parameters, name_before
        from PySide6.QtCore import QPoint
        i = self.dyn.focus
        token = name_before(self.dyn.texts[i])[0] if self.dyn.active and i >= 0 else None
        names, values = matching_parameters(token)
        if names:
            hint = formula_hint(names[0])
        elif token in values:
            hint = f"{token} = {values[token]:g} · {formula_hint(token)}"
        else:
            if self._dyn_list is not None:
                self._dyn_list.hide()
            return
        if self._dyn_list is None:
            self._dyn_list = ParameterList(self)
            self._dyn_list.itemClicked.connect(lambda _item: self._dyn_take_suggestion())
        r = self._dyn_focus_rect
        x, y, w = (int(r.left()), int(r.bottom()) + 4, int(r.width())) if r is not None else (20, 20, 170)
        self._dyn_list.show_at(QPoint(x, y), w, [(n, values[n]) for n in names], hint)

    def _dyn_take_suggestion(self):
        from omacad.ui.expr_spin import name_before
        name = self._dyn_list.chosen() if self._dyn_list is not None else None
        if self._dyn_list is not None:
            self._dyn_list.hide()
        i = self.dyn.focus
        if not name or i < 0:
            return
        _token, start = name_before(self.dyn.texts[i])
        self.dyn.texts[i] = self.dyn.texts[i][:start] + name
        self._refresh_dyn()
        self.update()

    def _handle_dyn_key(self, event) -> bool:
        key = event.key()
        if (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.doc.active_sketch
                and self.sketch_start_uv is not None and self.sketch_tool != "NONE"
                and not dyn_input.supports(self.sketch_tool)):
            if self.sketch_tool == "SPLINE":
                self._finish_spline()
                return True
            if self.sketch_current_uv is not None:  # ARC / SLOT: Enter confirms the current step
                self._commit_sketch_point(self.sketch_current_uv)
                self.update()
            return True
        if not self._dyn_can_start():
            return False
        text = event.text()
        if self._dyn_list is not None and self._dyn_list.has_choices():   # the parameter list under the field
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._dyn_list.step(-1 if key == Qt.Key.Key_Up else 1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self._dyn_take_suggestion()
                return True
            if key == Qt.Key.Key_Escape:
                self._dyn_list.hide()
                return True
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.dyn.editing = True  # from now on letters go into the field (parameter names)
            self.dyn.start(self.sketch_tool)
            if not self._raw_mouse_uv:
                self._raw_mouse_uv = self.sketch_current_uv
            self.dyn.tab(backwards=(key == Qt.Key.Key_Backtab))
            self._refresh_dyn()
            return True
        cur = self.dyn.texts[self.dyn.focus] if (self.dyn.active and self.dyn.focus >= 0) else ""
        if text == "=" and self.dyn.active and self._dyn_can_start():
            self.dyn.editing = True  # "=" starts a formula/parameter name even for names that begin with a hotkey letter
            return True
        starts_name = text.isupper() or text.lower() not in "lrcaxdm"  # not a tool hotkey
        if (text and len(text) == 1 and (text.isalpha() or text == "_") and self.dyn.active
                and (cur or getattr(self.dyn, "editing", False) or starts_name)
                and not (text in "xX" and cur[-1:].isdigit())):
            self.dyn.type_char(text)  # a parameter name such as width or Height
            self._refresh_dyn()
            self._dyn_suggest()
            return True
        formula_char = text in ("+", "*", "/", "(", ")", "^", "×") or (text in ("x", "X") and cur[-1:].isdigit() or text in ("x", "X") and cur[-1:] == ")")
        if text and len(text) == 1 and (text in "0123456789.,-" or (formula_char and (cur or text == "("))):
            self.dyn.start(self.sketch_tool)
            self.dyn.type_char(text)
            self._refresh_dyn()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.dyn.active:
            # Enter = OK: finish the shape currently being drawn at the cursor
            if self.sketch_current_uv is not None:
                self._commit_sketch_point(self.sketch_current_uv)
                self.update()
            return True
        if not self.dyn.active:
            return False
        if key == Qt.Key.Key_Backspace:
            self.dyn.backspace()
            self._refresh_dyn()
            self._dyn_suggest()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._refresh_dyn()
            i = self.dyn.focus
            if self.dyn.invalid(i):
                self.status_message.emit(f"'{self.dyn.texts[i]}' is not a valid number or formula.")
                return True
            if i >= 0 and self.dyn.locked(i) is not None:
                # Enter locks the typed value and moves to the next open field; last one commits
                n = len(self.dyn.names)
                for step in range(1, n):
                    j = (i + step) % n
                    if self.dyn.locked(j) is None:
                        self.dyn.focus = j
                        self.update()
                        return True
            if self.sketch_current_uv is not None:
                self._commit_sketch_point(self.sketch_current_uv)
                self.update()
            return True
        if key == Qt.Key.Key_Escape:
            if any(self.dyn.texts):
                self.dyn.texts = [""] * len(self.dyn.names)
                self.dyn.focus = 0
                self._refresh_dyn()
                self.update()
                return True
            return False  # nothing typed: Esc cancels the shape as usual
        return False
    def _smart_segments(self):
        """Straight lines a circle can be measured from: the sketch's own lines and the edges of the faces."""
        sk = self.doc.active_sketch
        segs = []
        guides = sk.corner_guide_walls()   # a rounded corner's guide lies on its wall: measure from the wall
        for e in sk.entities:
            if isinstance(e, SketchLine) and e.entity_id not in guides:
                segs.append((tuple(e.p1), tuple(e.p2), e.entity_id))
        for a, b in self._reference_segments():
            a, b = (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))
            segs.append((a, b, ref_id((a, b))))
        return segs
    def _smart_key(self, event) -> bool:
        sc, key, text = self.smart, event.key(), event.text()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._smart_accept()
            return True
        if key == Qt.Key.Key_Backspace:
            if sc.text:
                sc.text = sc.text[:-1]
            else:
                sc.back()
            self.update()
            return True
        if key == Qt.Key.Key_Escape:
            if sc.text or sc.stage != smart_circle.SIZE:
                sc.reset()
                sc.mouse = self._raw_mouse_uv
                self.update()
                return True
            return False
        if text and len(text) == 1 and (text in "0123456789.,-+*/()^×" or (text.isalpha() and (sc.text or text == "="))):
            if text != "=":
                sc.text += text
            self.update()
            return True
        return False
    def _smart_accept(self):
        sc = self.smart
        if sc.mouse is None and self._raw_mouse_uv is not None:
            sc.mouse = self._raw_mouse_uv
        res = sc.accept()
        if res == "invalid":
            self.status_message.emit(f"'{sc.text}' is not a valid number or formula.")
        elif res == "need_size":
            self.status_message.emit("Smart Circle: type the diameter first.")
        elif res == "no_line":
            self.status_message.emit("Smart Circle: no straight line to measure from here (step 3 needs one that is not parallel to the first). Clear the field to use the cursor.")
        elif res == "next":
            self.status_message.emit("Smart Circle: distance from the circle's centre (at right angles) to "
                                     + ("the nearest line, any angle" if sc.stage == smart_circle.ACROSS
                                        else "the nearest line that is not parallel to the first")
                                     + ", Enter (empty = cursor).")
        elif res == "done":
            self._smart_create()
        self.update()
    def _smart_create(self):
        sc, sk = self.smart, self.doc.active_sketch
        centre, d = sc.centre(), sc.diameter
        dims = dict(sc.dimension)
        before = sk.to_dict()
        circle = sk.add_circle(centre, d / 2.0, is_construction=self.construction_mode)
        solve_sketch(sk)
        self.doc.record_sketch_change(sk, before)
        for stage in (smart_circle.ACROSS, smart_circle.DOWN):
            if stage in dims:
                seg, dist = dims[stage]
                self.doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", circle.entity_id, dist, refs=[seg[2]], pts=["center"])
        sc.reset()
        sc.mouse = self._raw_mouse_uv
        self.status_message.emit("Smart Circle: placed. Type the next diameter for another one, or Esc.")
        self.doc.notify_changed()
    def _draw_smart_dimensions(self, painter: QPainter, sc, scr, c, d, colour):
        """The numbers typed so far show up on screen as dimensions: the diameter on the circle and the distance
        from each wall to the centre, each with a value badge, before the circle is even created."""
        painter.setFont(QFont(theme.font_family(), 9))
        fm = painter.fontMetrics()

        def badge(at: QPointF, text: str):
            rect = QRectF(at.x() - (fm.horizontalAdvance(text) + 16) / 2, at.y() - 11, fm.horizontalAdvance(text) + 16, 22)
            painter.setBrush(QBrush(qcolor(37, 40, 44, 240)))
            painter.setPen(QPen(colour, 1.5))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(qcolor(224, 227, 231))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

        def line(a: QPointF, b: QPointF, text: str):
            painter.setPen(QPen(colour, 1.5))
            painter.drawLine(a, b)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln * 5.0, dx / ln * 5.0
            for p in (a, b):                       # end ticks
                painter.drawLine(QPointF(p.x() - nx, p.y() - ny), QPointF(p.x() + nx, p.y() + ny))
            badge(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2), text)

        sc_c = scr(c)
        if d and sc.diameter is not None and sc_c is not None:       # diameter, once Enter was pressed
            r = sc.diameter / 2.0
            a, b = scr((c[0] - r * 0.7071, c[1] - r * 0.7071)), scr((c[0] + r * 0.7071, c[1] + r * 0.7071))
            if a is not None and b is not None:
                line(a, b, f"\u00d8 {sc.diameter:g} mm")
        for stage, (seg, dist) in sc.dimension.items():
            sf = scr(smart_circle.foot_on_line(seg, c))
            if sf is not None and sc_c is not None:
                line(sf, sc_c, f"{dist:g} mm")
    def draw_smart_circle(self, painter: QPainter):
        sc = self.smart
        if self.sketch_tool != "SMART_CIRCLE" or not self.doc.active_sketch or sc.mouse is None:
            return
        plane = self.doc.active_sketch.plane

        def scr(uv):
            p = self.world_to_screen(plane.uv_to_world(uv[0], uv[1]))
            return None if p is None else QPointF(p[0], p[1])

        orange, cyan = qcolor(226, 109, 40), qcolor(60, 190, 255)
        g = sc.guide()
        if g is not None:
            a, b = scr(g[0]), scr(g[1])
            if a is not None and b is not None:
                painter.setPen(QPen(cyan, 3))
                painter.drawLine(a, b)
        c = sc.centre()
        d = sc.diameter if sc.diameter is not None else (sc.typed() if sc.stage == smart_circle.SIZE else None)
        if c is not None and d:
            r = abs(d) / 2.0
            pts = [scr((c[0] + r * math.cos(2 * math.pi * i / 48), c[1] + r * math.sin(2 * math.pi * i / 48))) for i in range(49)]
            if all(p is not None for p in pts):
                painter.setPen(QPen(orange, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(QPolygonF(pts))
            sc_c = scr(c)
            if sc_c is not None and g is not None:   # dotted measure line from the guide to the centre
                sf = scr(smart_circle.foot_on_line(g, c))
                if sf is not None:
                    painter.setPen(QPen(cyan, 1, Qt.PenStyle.DashLine))
                    painter.drawLine(sf, sc_c)
        anchor = scr(c) if c is not None else None
        if anchor is None:
            return
        self._draw_smart_dimensions(painter, sc, scr, c, d, cyan)
        if not d:   # no size yet: a small shadow circle on the cursor shows that Smart Circle is the active tool
            painter.setPen(QPen(orange, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(qcolor(226, 109, 40, 55)))
            painter.drawEllipse(anchor, 14.0, 14.0)
            painter.drawPoint(anchor)
        painter.setFont(QFont(theme.font_family(), 9))
        label = smart_circle.LABELS[sc.stage]
        if sc.text:
            txt = sc.text + "|"
            v = sc.typed()
            if v is not None and not sc.text.replace(".", "", 1).lstrip("-").isdigit():
                txt += f" = {v:g}"
        else:
            txt = "type a value" if sc.stage == smart_circle.SIZE else "cursor"
        txt = f"{label}  {txt} mm"
        fm = painter.fontMetrics()
        rect = QRectF(anchor.x() + 18, anchor.y() - 36, fm.horizontalAdvance(txt) + 20, 24)
        painter.setBrush(QBrush(qcolor(37, 40, 44, 235)))
        painter.setPen(QPen(orange, 2))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(qcolor(224, 227, 231))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)
    def event(self, e):
        if e.type() == QEvent.Type.ShortcutOverride and self._owns_key(e):
            e.accept()              # the view gets the key, not a menu shortcut with the same letter (E, M, F, I)
            return True
        # Tab would otherwise move Qt focus; route it to dimension entry while drawing
        if e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            if self._dyn_can_start():
                self.keyPressEvent(e)
                return True
            panel = self._typing_panel()
            if panel is not None and panel.focus_primary():   # Tab from the view goes to the open panel's numbers (#47)
                return True
        return super().event(e)
    def draw_dyn_fields(self, painter: QPainter):
        """Floating value boxes next to the shape being drawn."""
        if not (self.dyn.active and self._dyn_can_start() and self.sketch_current_uv):
            if self._dyn_list is not None and self._dyn_list.isVisible():
                self._dyn_list.hide()             # the shape was finished or cancelled
            return
        plane = self.doc.active_sketch.plane
        a = self.sketch_start_uv
        b = self.sketch_current_uv

        def scr(uv):
            p = self.world_to_screen(plane.uv_to_world(uv[0], uv[1]))
            return None if p is None else QPointF(p[0], p[1])

        sa, sb = scr(a), scr(b)
        if sa is None or sb is None:
            return
        anchors: Dict[str, QPointF] = {}
        tool = self.dyn.tool
        if tool == "LINE":
            mid = (sa + sb) / 2.0
            d = sb - sa
            n = math.hypot(d.x(), d.y()) or 1.0
            anchors["Length"] = QPointF(mid.x() - d.y() / n * 26, mid.y() + d.x() / n * 26)
            anchors["Angle"] = QPointF(sa.x() + 30, sa.y() - 22)
        elif tool in ("RECT", "ROUNDED_RECT", "CENTER_RECT", "CENTER_ROUNDED_RECT"):
            if tool not in ("CENTER_RECT", "CENTER_ROUNDED_RECT"):
                c1, c2 = a, b
            else:
                c1, c2 = (2 * a[0] - b[0], 2 * a[1] - b[1]), b
            p_bl, p_br = scr((c1[0], c1[1])), scr((c2[0], c1[1]))
            p_tr = scr((c2[0], c2[1]))
            if p_bl and p_br and p_tr:
                anchors["Width"] = QPointF((p_bl.x() + p_br.x()) / 2, (p_bl.y() + p_br.y()) / 2 + 22)
                anchors["Height"] = QPointF((p_br.x() + p_tr.x()) / 2 + 48, (p_br.y() + p_tr.y()) / 2)
                anchors["Radius"] = QPointF(p_bl.x() + 62, p_bl.y() - 26)   # inside, by the corner it rounds
        elif tool == "MOVE":
            anchors["X"] = QPointF((sa.x() + sb.x()) / 2, (sa.y() + sb.y()) / 2 + 24)
            anchors["Y"] = QPointF(sb.x() + 52, sb.y())
        elif tool == "CIRCLE":
            anchors["Diameter"] = QPointF(sb.x() + 46, sb.y() - 16)
        elif tool == "POLYGON":
            anchors["Side"] = QPointF(sb.x() + 46, sb.y() - 16)
            anchors["Sides"] = QPointF(sa.x() + 38, sa.y() - 24)

        font = QFont(theme.font_family(), 9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        for i, name in enumerate(self.dyn.names):
            pt = anchors.get(name)
            if pt is None:
                continue
            locked = self.dyn.locked(i) is not None
            focused = (i == self.dyn.focus)
            if self.dyn.texts[i]:
                txt = self.dyn.texts[i] + ("|" if focused else "")
                result = self.dyn.locked(i)
                if result is not None and not self.dyn.texts[i].replace(".", "", 1).lstrip("-").isdigit():
                    txt += f" = {result:g}"  # a formula: show what it evaluates to
            else:
                val = self.dyn_live.get(name, 0.0)
                txt = f"{val:.0f}" if name == "Sides" else f"{val:.2f}"
            txt += {"Angle": "°", "Sides": ""}.get(name, " mm")
            if name == "Diameter" and not self.dyn.texts[i] and name in self.dyn_live:
                txt += f"  (R {self.dyn_live[name] / 2.0:.2f})"
            if tool == "MOVE":
                u_lbl, v_lbl = plane.axis_names()
                lbl = {"X": u_lbl, "Y": v_lbl}.get(name, name)
                txt = f"{lbl}  {txt}"
            wbox = max(64, fm.horizontalAdvance(txt) + 18)
            rect = QRectF(pt.x() - wbox / 2, pt.y() - 12, wbox, 24)
            if focused:
                self._dyn_focus_rect = rect
            painter.setBrush(QBrush(qcolor(37, 40, 44, 235)))
            painter.setPen(QPen(qcolor(226, 109, 40) if focused else qcolor(110, 118, 128), 2 if focused else 1))
            painter.drawRoundedRect(rect, 4, 4)
            if focused and not self.dyn.texts[i]:
                # Ready for typing: value shown as selected text that the first digit replaces
                painter.setBrush(QBrush(qcolor(226, 109, 40, 200)))
                painter.setPen(QPen(qcolor(226, 109, 40), 2))
                painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(qcolor(224, 227, 231) if locked or focused else qcolor(142, 149, 160))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)
