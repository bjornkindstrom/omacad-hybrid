"""Pointer press and drag handling for the viewport."""

import math
import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QToolTip
from omacad.model.dim_layout import describe_dimension
from omacad.model import quality
from omacad.model.sketch import SketchLine
from omacad.model.sketch_snap import SketchSnapper, SnapResult
from omacad.model.sketch_tangent import snap_tangent_arc


class PointerMixin:
    """Mouse press and move handlers used by :class:`Viewport3D`."""

    def mousePressEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        if self._constraint_guide is not None:
            if event.button() == Qt.MouseButton.RightButton:
                self.constraint_help.dismiss()
                return
            if event.button() == Qt.MouseButton.LeftButton:
                self._constraint_guide_pick(x, y)
                return
        if event.button() == Qt.MouseButton.LeftButton and self.picked_dim_entities[1]:
            self.picked_dim = None
            self.picked_dim_entities = (None, set())

        if (event.button() == Qt.MouseButton.LeftButton and self.primitive_handles
                and self.primitive_handles.press(x, y)):
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.rotate_handles.press(x, y):
            self.update()
            return

        # Check ViewCube click first
        if (event.button() == Qt.MouseButton.LeftButton
                and self.viewcube.handle_mouse_press(int(x), int(y), self.width())):
            self.update()
            return

        if self.hole_place_mode and event.button() == Qt.MouseButton.LeftButton:
            if self._hole_place_press(x, y):
                return

        if self.measure is not None and event.button() == Qt.MouseButton.LeftButton and self.measure["mode"] == "sketch":
            self._measure_click(x, y)
            return
        if event.button() == Qt.MouseButton.LeftButton and self.move_gizmo:
            hit_ax = self._gizmo_hit(x, y)
            if hit_ax:
                g = self.move_gizmo
                g["dragging"] = True
                g["active_axis"] = hit_ax
                g["start_proj"] = self._gizmo_project_mouse(x, y, hit_ax)
                self.move_gizmo_axis_selected.emit(hit_ax)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()
                return
        if event.button() == Qt.MouseButton.LeftButton and self.extrude_handle and self._handle_hit(x, y):
            self._handle_drag = True
            quality.set_interactive_mode(True)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        # Check HUD clicks
        h = self.height()
        w = self.width()
        hud_w, hud_h = 260, 36
        hud_rect = QRectF((w - hud_w) / 2.0, h - 50, hud_w, hud_h)
        if hud_rect.contains(x, y):
            rel_x = x - hud_rect.x()
            if rel_x < 65:
                self.nav_mode = "ORBIT"
            elif rel_x < 130:
                self.nav_mode = "PAN"
            elif rel_x < 195:
                self.zoom_fit()
            else:
                self.show_grid = not self.show_grid
            self.update()
            return

        if self.point_pick and event.button() == Qt.MouseButton.LeftButton and self._point_pick_press():
            return

        if self.doc.active_sketch and self.sketch_tool == "ROTATE":
            if event.button() == Qt.MouseButton.LeftButton:
                self._rotate_press(event, x, y)
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.set_sketch_tool("NONE")
                return

        # Dimension badge: a click edits the value, dragging it moves the dimension line out of the way
        if self.doc.active_sketch and event.button() == Qt.MouseButton.LeftButton:
            for dim_id, (rect, s_id, d_id, val) in list(self.dim_badges.items()):
                if rect.contains(x, y):
                    sk = self.doc.sketches.get(s_id)
                    dim = next((d for d in sk.dimensions if d.dim_id == d_id), None) if sk else None
                    self._dim_drag = {"sketch": sk, "dim": dim, "press": event.position(), "moved": False,
                                      "before": sk.to_dict() if sk else None, "value": val}
                    return

        # Handle Dimension Tool Click near geometry
        if self.doc.active_sketch and self.sketch_tool == "DIMENSION" and event.button() == Qt.MouseButton.LeftButton:
            uv = self.get_sketch_plane_uv(x, y)
            if uv and self.handle_dimension_tool_click(uv[0], uv[1]):
                return

        self.last_mouse_pos = event.position().toPoint()

        # Handle Offset Tool Click (Fusion style: a click takes the whole connected chain)
        if self.doc.active_sketch and self.sketch_tool == "OFFSET":
            if event.button() == Qt.MouseButton.RightButton:
                if self.selected_entities:
                    self._offset_go()
                else:
                    self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                ent = self._pick_entity(x, y)
                if ent is not None:
                    mods = event.modifiers()
                    single = bool(mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
                    if single:
                        # Toggle or deselect just this single entity
                        if ent.entity_id in self.selected_entities:
                            self.selected_entities.remove(ent.entity_id)
                        else:
                            self.selected_entities.add(ent.entity_id)
                    else:
                        ids = self.doc.active_sketch.connected_entities(ent.entity_id)
                        if ids <= self.selected_entities:
                            self.selected_entities -= ids
                        else:
                            self.selected_entities |= ids   # clicks add; click a picked chain again to drop it
                    self.selection_changed.emit()
                    self._offset_status()
                    self.update()
                    return
                if self._start_rubber(event):
                    return
                return

        if self.doc.active_sketch and self.sketch_tool == "TEXT" and self._text_press(event, x, y):
            return

        # Handle Mirror Tool Click
        if self.doc.active_sketch and self.sketch_tool == "MIRROR":
            if event.button() == Qt.MouseButton.RightButton:   # right-click: next step / back / cancel
                self.fillet_preview = None
                if self._mirror_phase == "pick" and self.selected_entities:
                    self._mirror_next()
                elif self._mirror_phase == "axis":
                    self._mirror_phase = "pick"
                    self._mirror_status()
                    self.update()
                else:
                    self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                if self._mirror_phase == "pick":
                    if self._toggle_pick(event, x, y):
                        self._mirror_status()
                else:
                    self._mirror_at(x, y)
                return

        # Move, step 1: click what to move (several things), Enter goes on to the base point
        if self.doc.active_sketch and self.sketch_tool == "MOVE" and self._move_phase == "pick":
            if event.button() == Qt.MouseButton.LeftButton:
                if self._toggle_pick(event, x, y):
                    self._move_status()
            elif event.button() == Qt.MouseButton.RightButton:
                self._move_next()
            return

        # Handle Trim Tool Click
        if self.doc.active_sketch and self.sketch_tool == "TRIM":
            if event.button() == Qt.MouseButton.RightButton:
                self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                self._trim_at(x, y)
                return

        # Handle Fillet Tool Click
        if self.doc.active_sketch and self.sketch_tool == "FILLET":
            if event.button() == Qt.MouseButton.RightButton:
                if self.fillet_first_line:
                    self.fillet_first_line = None
                    self.status_message.emit("Fillet: click a corner between lines or arcs, or click two of them (Esc cancels).")
                    self.update()
                    return
                self.set_sketch_tool("NONE")
                return
            if event.button() == Qt.MouseButton.LeftButton:
                if self.fillet_hover_corner:
                    pt, la, lb = self.fillet_hover_corner
                    item = (pt, la.entity_id, lb.entity_id)
                    here = next((c for c in self.fillet_picked if math.hypot(c[0][0] - pt[0], c[0][1] - pt[1]) < 1e-3), None)
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        # Shift+click collects corners; Enter (or a plain click on one more corner) rounds them all
                        if here is not None:
                            self.fillet_picked.remove(here)
                        else:
                            self.fillet_picked.append(item)
                        n = len(self.fillet_picked)
                        self.status_message.emit(f"Fillet: {n} corner(s) picked. Shift+click more, then press Enter (or click one more corner) to set the radius.")
                        self.update()
                        return
                    if self.fillet_picked:
                        if here is None:
                            self.fillet_picked.append(item)
                        self._fillet_apply_picked()
                        return
                    self.prompt_fillet_radius(la, lb, pt)
                    return
                ent = self._pick_entity(x, y)
                from omacad.model.sketch import SketchArc, SketchLine
                if ent and isinstance(ent, (SketchLine, SketchArc)):
                    if self.fillet_first_line is None:
                        self.fillet_first_line = ent
                        self.status_message.emit("Fillet: now click the second line or arc to round the corner between them.")
                    else:
                        first = self.fillet_first_line
                        self.fillet_first_line = None
                        if first.entity_id != ent.entity_id:
                            self.prompt_fillet_radius(first, ent)
                        else:
                            self.status_message.emit("Fillet: pick two different lines or arcs.")
                    self.update()
                    return
                if self._start_rubber(event):
                    return
                return

        # Handle Sketch Drawing Click
        if self.doc.active_sketch and self.sketch_tool != "NONE":
            # Right click finishes current line chain or cancels step
            if event.button() == Qt.MouseButton.RightButton:
                if self.sketch_tool == "SPLINE":
                    self._finish_spline()
                    return
                if self.sketch_tool == "DIMENSION":
                    self._rpress = event.position()  # a plain right-click still opens the element menu
                    self._dim_pending, self._dim_place = [], None
                    self.update()
                    return
                if self._move:
                    self._end_move(False)
                self.sketch_start_uv = None
                self.sketch_second_uv = None
                self.dyn.reset()
                self.smart.reset()
                self.update()
                return

            if event.button() == Qt.MouseButton.LeftButton and self.sketch_tool == "SMART_CIRCLE":
                self._smart_accept()
                return

            if event.button() == Qt.MouseButton.LeftButton and self.sketch_current_uv is not None:
                snapped_u, snapped_v = self.sketch_current_uv

                if self.sketch_start_uv is None:
                    # First click
                    self.sketch_start_uv = (snapped_u, snapped_v)
                    if self.sketch_tool == "SPLINE":
                        self._spline_points = [self.sketch_start_uv]
                        self.status_message.emit("Spline: click through-points; Enter or right-click finishes, Esc cancels.")
                    if self.sketch_tool == "MOVE":
                        self._begin_move(self.selected_entities)
                    self._arm_dyn()
                else:
                    self._commit_sketch_point((snapped_u, snapped_v))
                self.update()
                return

        # Click on a constraint glyph removes that constraint
        if event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities():
            for rect, cid in self.constraint_badges:
                if rect.contains(x, y):
                    if self.doc.remove_constraint(self.doc.active_sketch.sketch_id, cid):
                        self.status_message.emit(self.doc.last_message)
                    return

        # Press on a sketch element: select it and prepare a drag-move
        if event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities():
            # Check free endpoint dot first (to stretch and connect lines/arcs)
            free_end = self._pick_free_endpoint(x, y)
            if free_end is not None:
                sk = self.doc.active_sketch
                ent = free_end["entity"]
                self._endpoint_drag = {
                    "sketch_id": sk.sketch_id,
                    "entity_id": ent.entity_id,
                    "point_name": free_end["point_name"],
                    "before": sk.to_dict(),
                    "press_uv": self.get_sketch_plane_uv(x, y),
                    "moved": False,
                }
                self.selected_entities = {ent.entity_id}
                self.selection_changed.emit()
                self._press_pos = None
                return

            # Check spline point or tangent handle next
            handle = self._pick_spline_handle(x, y)
            if handle is not None:
                sk = self.doc.active_sketch
                ent = handle["entity"]
                if not getattr(ent, "projected", False):
                    self._spline_drag = {
                        "sketch_id": sk.sketch_id,
                        "entity_id": ent.entity_id,
                        "kind": handle["kind"],
                        "index": handle["index"],
                        "handle_sign": handle["handle_sign"],
                        "before": sk.to_dict(),
                        "press_uv": self.get_sketch_plane_uv(x, y),
                        "moved": False,
                    }
                    self._press_pos = None
                    return

            ent = self._pick_entity(x, y)
            if ent is not None:
                if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
                    self.selected_entities ^= {ent.entity_id}   # Shift/Ctrl+click: add or remove one element
                    self._press_pos = None
                    self.selection_changed.emit()
                    self.update()
                    return
                if ent.entity_id not in self.selected_entities:
                    self.selected_entities = {ent.entity_id}
                    self.selection_changed.emit()
                uv = self.get_sketch_plane_uv(x, y)
                if uv is not None and not getattr(ent, "projected", False):   # edges of the body can't be dragged away
                    self._drag = {"press_uv": uv, "press_pos": event.position(), "moved": False, "ent_id": ent.entity_id}
                self.update()
                return

        # Box selection on empty sketch space (Alt+drag orbits instead)
        if (event.button() == Qt.MouseButton.LeftButton and self.doc.active_sketch and self.sketch_tool == "NONE"
                and not self.plane_pick_mode and self.measure is None and self._pick_entity(x, y) is None
                and self._start_rubber(event)):
            return

        # Standard Navigation
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.is_panning = True
            if event.button() == Qt.MouseButton.LeftButton and not self.doc.active_sketch:
                self._press_pos = event.position()   # Shift+click without moving selects (adds a profile); dragging still pans
        elif event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position()
            if self.nav_mode == "PAN":
                self.is_panning = True
            else:
                self.is_orbiting = True
        elif event.button() == Qt.MouseButton.RightButton:
            self._rpress = event.position()
            self.is_panning = True
    def mouseMoveEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        if self.hole_place_mode:
            if not self.is_orbiting and not self.is_panning:
                self._hole_place_hover(x, y)
            return
        if (self.primitive_handles and not self.is_orbiting and not self.is_panning
                and self.primitive_handles.move(x, y)):
            self.update()
            return
        if not self.is_orbiting and not self.is_panning and self.rotate_handles.move(x, y):
            self.update()
            return
        if self._rubber is not None:
            self._rubber["p1"] = event.position()
            self.update()
            return
        if self.sketch_tool == "ROTATE" and self._rotate_drag is not None:
            self._rotate_drag_to(event, x, y)
            self.update()
            return

        if self.viewcube._press is not None:
            self.viewcube.handle_mouse_move(int(x), int(y), self.width())
            self.update()
            return

        # Check ViewCube hover
        if self.viewcube.handle_mouse_move(int(x), int(y), self.width()):
            self.update()

        if self.move_gizmo:
            g = self.move_gizmo
            if g.get("dragging"):
                cur_proj = self._gizmo_project_mouse(x, y, g["active_axis"])
                delta = self.gizmo_snapped_delta(x, y, g["active_axis"], cur_proj - g["start_proj"])
                self.move_gizmo_dragged.emit(g["active_axis"], delta)
                self.update()
                return
            else:
                hover_ax = self._gizmo_hit(x, y)
                if hover_ax != g.get("hover_axis"):
                    g["hover_axis"] = hover_ax
                    self.setCursor(Qt.CursorShape.OpenHandCursor if hover_ax else Qt.CursorShape.ArrowCursor)
                    self.update()

        if self._handle_drag:
            val = self._handle_value(x, y)
            if val is not None:
                self.extrude_handle["dist"] = val
                self.extrude_handle_dragged.emit(val)
                self.update()
            return
        if self.extrude_handle:
            hover = self._handle_hit(x, y)
            if hover != self._handle_hover:
                self._handle_hover = hover
                self.setCursor(Qt.CursorShape.OpenHandCursor if hover else Qt.CursorShape.ArrowCursor)
                self.update()
        if self._dim_place and self._dim_box is not None:
            uv = self.get_sketch_plane_uv(x, y)
            if uv is not None:
                self._dim_hover_uv = uv
                _kind, measured, label = self._dim_points_kind(self._dim_place, uv[0], uv[1])
                self._dim_box.set_measure(label, measured)
        if self._endpoint_drag is not None:
            self._endpoint_drag_move(event)
            return
        if self._spline_drag is not None:
            self._spline_drag_move(event)
            return
        if self._dim_drag is not None:
            self._dim_drag_move(event)
            return
        if self._drag is not None:
            self._drag_move(event)
            return
        if self.point_pick:
            if not self.is_orbiting and not self.is_panning:
                self._point_pick_hover(x, y)
        elif self.edge_pick_mode:
            if not self.is_orbiting and not self.is_panning:
                self._update_edge_hover(x, y)
        elif self.plane_pick_mode:
            if not self.is_orbiting and not self.is_panning:
                if self.plane_pick_purpose == "offset_surface":
                    self.surface_hover.emit(self._pick_surface(x, y))
                elif self.plane_pick_purpose == "offset_face":
                    self._update_offset_hover(x, y)
                else:
                    self._update_plane_hover(x, y)
        else:
            self._update_profile_hover(x, y)
            if not self.is_orbiting and not self.is_panning:
                self._update_entity_hover(x, y)
                if self._idle_hover_ok():
                    self._update_edge_hover(x, y)
                    if self.hover_edge is None and self.hover_face is None and self.hover_surface is None:
                        self._update_idle_plane_hover(x, y)
                    elif self.hover_plane is not None:
                        self.hover_plane = None
                        self.update()
                elif self.hover_edge is not None or self.hover_face is not None or self.hover_surface is not None:
                    if self.hover_edge is not None:
                        self.hover_info_changed.emit(None)
                    self.hover_edge = self.hover_face = self.hover_surface = None
                    self.update()

        # Check Dimension Badge Hover
        prev_hovered = self.hovered_dim_id
        hovered = None
        if self.doc.active_sketch:
            for dim_id, (rect, s_id, d_id, val) in self.dim_badges.items():
                if rect.contains(x, y):
                    hovered = dim_id
                    break

        self.hovered_dim_id = hovered
        if hovered != prev_hovered:      # say what the dimension measures (Björn #72)
            dim = next((d for d in self.doc.active_sketch.dimensions if d.dim_id == hovered), None) if hovered else None
            if dim is not None:
                QToolTip.showText(event.globalPosition().toPoint(), describe_dimension(dim), self)
            else:
                QToolTip.hideText()
        if hovered:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self.sketch_tool in ("LINE", "RECT", "ROUNDED_RECT", "CENTER_RECT", "CENTER_ROUNDED_RECT", "CIRCLE", "SMART_CIRCLE", "POLYGON", "ARC", "SPLINE", "SLOT", "FILLET", "TRIM", "MIRROR", "OFFSET", "DIMENSION", "MOVE", "TEXT"):
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if hovered != prev_hovered:
            self.update()

        if self.doc.active_sketch and self.sketch_tool == "TEXT":
            self._text_hover(x, y)
        if self.doc.active_sketch and self.sketch_tool == "TRIM":
            self._trim_hover(x, y)
        if self.doc.active_sketch and self.sketch_tool == "MIRROR":
            self._mirror_hover(x, y)

        if self.doc.active_sketch and self.sketch_tool == "FILLET":
            sk = self.doc.active_sketch
            best_c = None
            corners = sk.find_corners()
            best_d = 16.0  # pixels
            for pt, la, lb, ea, eb in corners:
                scr = self.world_to_screen(sk.plane.uv_to_world(*pt))
                if scr:
                    d = math.hypot(x - scr[0], y - scr[1])
                    if d < best_d:
                        best_d = d
                        best_c = (pt, la, lb)
            if best_c != self.fillet_hover_corner:
                self.fillet_hover_corner = best_c
                self.update()

        # Active sketch snapping and preview tracking
        if self.doc.active_sketch and self.sketch_tool != "NONE":
            uv = self.get_sketch_plane_uv(x, y)
            if uv is not None:
                enable_grid = self.sketch_palette.chk_snap_grid.isChecked()
                enable_pts = self.sketch_palette.chk_snap_points.isChecked()
                grid_step = 5.0 if enable_grid else 0.0

                snap_res = SketchSnapper.snap(
                    raw_uv=uv,
                    sketch=self.doc.active_sketch,
                    start_uv=self.sketch_start_uv,
                    snap_distance=max(0.3, min(8.0, self._entity_tolerance() * 1.25)),  # ~10 screen px
                    reference_segments=self._reference_segments(),
                    grid_step=grid_step,
                    enable_grid_snap=enable_grid,
                    enable_geom_snap=enable_pts
                )
                if (self.sketch_tool == "ARC" and self.sketch_start_uv is not None and self.sketch_second_uv is not None
                        and snap_res.snap_type in ("NONE", "GRID")):   # a real snap point wins over the magnet
                    mid = snap_tangent_arc(self.sketch_start_uv, self.sketch_second_uv, snap_res.uv,
                                           self.doc.active_sketch.entities, self._reference_segments())
                    if mid is not None:
                        snap_res = SnapResult(uv=mid, snap_type="TANGENT")
                self.active_snap = snap_res
                if self.sketch_tool == "SMART_CIRCLE":
                    if not self.hasFocus():
                        self.setFocus()
                    self.smart.mouse = uv
                    self.smart.segments = self._smart_segments()
                self.sketch_current_uv = snap_res.uv
                self._raw_mouse_uv = snap_res.uv
                self._refresh_dyn()
                self.update()
        else:
            if self.active_snap is not None:
                self.active_snap = None
                self.update()

        dx = x - self.last_mouse_pos.x()
        dy = y - self.last_mouse_pos.y()
        self.last_mouse_pos = event.position().toPoint()

        if self.is_orbiting:
            self.azimuth = (self.azimuth - dx * 0.5) % 360.0
            self.elevation = max(-89.9, min(89.9, self.elevation + dy * 0.5))
            self.update()
        elif self.is_panning:
            # Move target along camera's right and up vectors
            proj, view, _ = self.get_matrices()
            inv_view = np.linalg.inv(view)
            right = inv_view[:3, 0]
            up = inv_view[:3, 1]

            pan_speed = self.distance * 0.0018
            self.target -= right * (dx * pan_speed)
            self.target += up * (dy * pan_speed)
            self.update()
