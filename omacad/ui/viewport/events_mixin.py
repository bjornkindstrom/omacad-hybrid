"""Qt input event handlers for the viewport."""

from PySide6.QtCore import Qt
from omacad.model import quality
from omacad.model.faces import tangent_chain
from omacad.model.sketch import SketchText

# Single keys the sketch tools use (keyPressEvent below). In a sketch they win over the window's menu shortcuts
# with the same letter (M = Move Body, F = Fit View), see SketchToolsMixin.event.
SKETCH_KEYS = {Qt.Key.Key_L, Qt.Key.Key_R, Qt.Key.Key_C, Qt.Key.Key_P, Qt.Key.Key_A, Qt.Key.Key_X, Qt.Key.Key_D,
               Qt.Key.Key_M, Qt.Key.Key_O, Qt.Key.Key_F, Qt.Key.Key_T, Qt.Key.Key_I}
# Face picking that lasts as long as its tool panel (Shell, Offset Face, Honeycomb, Move): Esc ends the tool,
# not just the picking, which would leave an open panel that can no longer pick.
SESSION_PICKS = {"shell_face", "offset_face", "move_body"}


class ViewportEventsMixin:
    """Keyboard and discrete mouse event behavior for :class:`Viewport3D`."""

    def mouseDoubleClickEvent(self, event):
        x = event.position().x()
        y = event.position().y()
        if (self.doc.active_sketch and self.sketch_tool == "SPLINE"
                and event.button() == Qt.MouseButton.LeftButton):
            if self.sketch_current_uv is not None:
                self._commit_sketch_point(self.sketch_current_uv)
            self._finish_spline()
            return
        if self.doc.active_sketch and event.button() == Qt.MouseButton.LeftButton:
            for dim_id, (rect, s_id, d_id, val) in list(self.dim_badges.items()):
                if rect.contains(x, y):
                    self.prompt_edit_dimension(s_id, d_id, val)
                    return
        if event.button() == Qt.MouseButton.LeftButton and self.edge_pick_mode:
            e = self._pick_edge(x, y)
            if e is not None:
                for c in self._edge_loop(e, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                    if not any(self._same_edge(c, k) for k in self.selected_edges):
                        self.selected_edges.append(c)
                self.edges_selection_changed.emit()
                self.update()
            else:
                hit = self._pick_face(x, y)
                if hit is not None:
                    body, face = hit
                    face_edges = self._edges_of_face(face, body)
                    for fe in face_edges:
                        if not any(self._same_edge(fe, k) for k in self.selected_edges):
                            self.selected_edges.append(fe)
                    self.edges_selection_changed.emit()
                    self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._can_select_sketch_entities():
            ent = self._pick_entity(x, y)
            if ent is not None:
                self._drag = None
                from omacad.model.sketch_entities import SketchSpline
                if isinstance(ent, SketchSpline) and not getattr(ent, "projected", False):
                    # Double-click on a spline inserts a point at cursor position
                    uv = self.get_sketch_plane_uv(x, y)
                    if uv is not None:
                        sk = self.doc.active_sketch
                        before = sk.to_dict()
                        try:
                            idx = sk.insert_spline_point(ent.entity_id, uv)
                            if self.doc.record_sketch_change(sk, before):
                                self.doc.timeline.recompute(self.doc)
                            self.selected_entities = {ent.entity_id}
                            self.selection_changed.emit()
                            self.status_message.emit(f"Inserted spline point #{idx + 1}")
                            self.update()
                            return
                        except Exception:
                            pass
                if isinstance(ent, SketchText):
                    self.selected_entities = {ent.entity_id}
                    self.selection_changed.emit()
                    self.update()
                    self.text_edit_requested.emit(ent.entity_id)
                    return
                # Double-click selects everything joined to this element (e.g. a whole rectangle)
                self.selected_entities = self.doc.active_sketch.connected_entities(ent.entity_id)
                self.selection_changed.emit()
                self.update()
                return
        super().mouseDoubleClickEvent(event)
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        from omacad.ui.settings import get_settings
        if get_settings().get("invert_zoom", False):
            delta = -delta
        factor = 0.9 if delta > 0 else 1.1
        self.distance = max(5.0, min(2000.0, self.distance * factor))
        if self.point_pick:   # other points come within reach (or behind the body) at the new zoom
            self._point_pick_hover(event.position().x(), event.position().y())
        self.update()
    def _typing_panel(self):
        """The open tool panel whose main field takes what is typed in the 3D view (outside a sketch), else None."""
        if self.doc.active_sketch:
            return None
        from omacad.ui import dialogs as _dialogs
        host = _dialogs.SIDE_HOST
        tool_dlg = getattr(host, "_extrude_dlg", None) or getattr(getattr(host, "inspector", None), "current_tool_dlg", None)
        if tool_dlg is not None and hasattr(tool_dlg, "primary_field") and tool_dlg.isVisible():
            return tool_dlg
        return None

    def _types_into_panel(self, event) -> bool:
        """A character that belongs in the panel's field: a number, a formula sign, or a letter of a parameter name
        (X stays see-through while edges are picked)."""
        txt = event.text()
        if not txt or len(txt) != 1 or event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            return False
        if self.edge_pick_mode and txt in "xX":
            return False
        return txt in "0123456789+-/*().,_" or txt.isalpha()

    def _owns_key(self, event) -> bool:
        """Keys the view handles itself even though a menu shortcut uses the same letter: the sketch tools' keys,
        every letter while a value is typed into a drawing's dimension fields (a parameter name such as 'depth'
        must not start Extrude at its 'e'), and letters typed for an open tool panel's field."""
        no_mods = not event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        txt = event.text()
        if self.doc.active_sketch:
            if no_mods and len(txt) == 1 and (txt.isalnum() or txt == "_") and self._dyn_can_start() and self.dyn.active:
                return True                 # the dimension fields are open: letters may be a parameter name
            return no_mods and event.key() in SKETCH_KEYS
        return self._typing_panel() is not None and self._types_into_panel(event)

    def toggle_profile_in_selection(self, picked) -> None:
        """Shift+click: add a profile to the selection or remove it again. Normally only profiles of one sketch or of
        sketches in the same plane go together (Extrude); in `profile_chain_mode` (Loft) every click adds a profile
        from any plane, in click order."""
        doc = self.doc
        chosen = ([doc.selected_profile] if doc.selected_profile else []) + list(doc.selected_extra)
        if picked in chosen:
            chosen.remove(picked)
        elif (getattr(self, "profile_chain_mode", False) or not chosen or chosen[0][0] == picked[0]
              or self._sketches_share_plane(chosen[0][0], picked[0])):
            chosen.append(picked)
        doc.selected_profile = chosen[0] if chosen else None
        doc.selected_extra = chosen[1:]
        self.profile_picked.emit()
        self.update()

    def keyPressEvent(self, event):
        # A tool panel is open (Extrude, Fillet, Chamfer, Shell, ...): typing a number or a parameter name in the 3D
        # view goes straight into its main field, Enter is OK. Backspace stays "undo last edge" while edges are picked.
        tool_dlg = self._typing_panel()
        if tool_dlg is not None:
            txt = event.text()
            edit_key = event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not self.edge_pick_mode
            if (self._types_into_panel(event) or edit_key) and tool_dlg.focus_primary():
                if txt:
                    field = tool_dlg.primary_field()
                    field.lineEdit().event(event)
                    if hasattr(field, "suggest"):
                        field.suggest()         # the parameter list, as when typed in the field itself
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                tool_dlg.accept()
                return

        if (self._constraint_guide is not None or self.constraint_help.isVisible()) and event.key() == Qt.Key.Key_Escape:
            guide_active = self._constraint_guide is not None
            self.constraint_help.dismiss()
            if guide_active:
                self.selected_entities.clear()
                self.selection_changed.emit()
                self.update()
            return

        if self.measure is not None and event.key() == Qt.Key.Key_Escape:
            self.end_measure()
            return
        if self.hole_place_mode and event.key() == Qt.Key.Key_Escape:
            self.end_hole_place()
            return
        if self.point_pick and event.key() == Qt.Key.Key_Escape:
            self.end_point_pick()
            self.point_picked.emit(None)     # the tool keeps what was picked so far
            return
        if self.measure is not None and self.measure["mode"] == "model" and event.key() == Qt.Key.Key_D:
            self._measure_set_distance()
            return
        if self.doc.active_sketch and self.sketch_tool == "FILLET" and self.fillet_picked:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._fillet_apply_picked()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.fillet_picked = []
                self.status_message.emit("Fillet: picked corners cleared.")
                self.update()
                return
        if self.doc.active_sketch and self.sketch_tool == "ROTATE":
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._rotate_finish(True)
                return
        if (self.doc.active_sketch and self.sketch_tool == "MOVE" and self._move_phase == "pick"
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
            self._move_next()
            return
        if self.doc.active_sketch and self.sketch_tool == "OFFSET":
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._offset_go()
                return
            if event.key() == Qt.Key.Key_Escape:
                self.set_sketch_tool("NONE")
                return
        if self.doc.active_sketch and self.sketch_tool == "MIRROR":
            k = event.key()
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self._mirror_phase == "pick":
                self._mirror_next()
                return
            if k == Qt.Key.Key_Escape:
                self.fillet_preview = None
                self.set_sketch_tool("NONE")
                return
        if self.doc.active_sketch and self.sketch_tool == "SMART_CIRCLE" and self._smart_key(event):
            return
        if self._handle_dyn_key(event):
            return
        if (event.key() == Qt.Key.Key_Escape and self.sketch_tool == "DIMENSION"
                and (self._dim_pending or self._dim_place)):
            self._dim_pending, self._dim_place = [], None
            self.status_message.emit("Dimension cancelled.")
            self.update()
            return
        if self._can_select_sketch_entities():
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_entities:
                self.delete_selected_entities()
                return
            if event.key() == Qt.Key.Key_Delete and self.dimension_to_delete():
                self.delete_dimension(*self.dimension_to_delete())
                return
            if event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.selected_entities = {e.entity_id for e in self.doc.active_sketch.entities}
                self.update()
                return
            if event.key() == Qt.Key.Key_Escape and self.selected_entities:
                self.selected_entities.clear()
                self.update()
                return
        if self.doc.active_sketch:
            if event.key() == Qt.Key.Key_L:
                self.set_sketch_tool("LINE")
                return
            elif event.key() == Qt.Key.Key_R and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.set_sketch_tool("ROTATE")
                return
            elif event.key() == Qt.Key.Key_R:
                self.set_sketch_tool("RECT")
                return
            elif event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.set_sketch_tool("SMART_CIRCLE")
                return
            elif event.key() == Qt.Key.Key_C:
                self.set_sketch_tool("CIRCLE")
                return
            elif event.key() == Qt.Key.Key_P:
                self.set_sketch_tool("POLYGON")
                return
            elif event.key() == Qt.Key.Key_A:
                self.set_sketch_tool("ARC")
                return
            elif event.key() == Qt.Key.Key_X:
                self.toggle_construction_mode()
                return
            elif event.key() == Qt.Key.Key_D:
                self.set_sketch_tool("DIMENSION")
                return
            elif event.key() == Qt.Key.Key_M and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.set_sketch_tool("MIRROR")
                return
            elif event.key() == Qt.Key.Key_M:
                self.set_sketch_tool("MOVE")
                return
            elif event.key() == Qt.Key.Key_O:
                self.set_sketch_tool("OFFSET")
                return
            elif event.key() == Qt.Key.Key_F:
                self.set_sketch_tool("FILLET")
                return
            elif event.key() == Qt.Key.Key_T:
                self.set_sketch_tool("TRIM")
                return
            elif event.key() == Qt.Key.Key_I:
                self.begin_measure()
                return

        if self.edge_pick_mode and event.key() == Qt.Key.Key_X:
            self.edge_xray = not self.edge_xray
            self.status_message.emit("Edges: see-through " + ("ON - hidden edges can be picked too (X again to turn off, or hold Alt)." if self.edge_xray else "off."))
            self.update()
            return
        if self.edge_pick_mode and event.key() == Qt.Key.Key_Backspace and self.selected_edges:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.selected_edges = []   # Ctrl+Backspace: clear everything
            else:
                self.selected_edges.pop()   # undo the last picked edge
            self.edges_selection_changed.emit()
            self.update()
            return
        if event.key() == Qt.Key.Key_Escape and self.edge_pick_mode:
            self.end_edge_pick(cancelled=True)
            return
        if event.key() == Qt.Key.Key_Escape and self.plane_pick_mode:
            if self.plane_pick_purpose in SESSION_PICKS and self.active_tool_title():
                self.menu_command.emit("tool_cancel")   # the picking is the tool itself: Esc cancels the tool
            else:
                self.end_plane_pick(cancelled=True)
            return
        if event.key() == Qt.Key.Key_Escape and self.rotate_handles.cancel():
            self.update()
            return
        if event.key() == Qt.Key.Key_Escape and self.primitive_handles:
            handles = self.primitive_handles
            if handles.drag:
                handles.cancel_drag()
                self.update()
            else:
                handles.dialog.reject()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self.sketch_second_uv is not None:
                self.sketch_second_uv = None
            elif self.sketch_start_uv is not None:
                if self._move:
                    self._end_move(False)
                self.sketch_start_uv = None
                if self.sketch_tool == "SPLINE":
                    self._spline_points = []
                self.dyn.reset()
                self.update()
            elif self.sketch_tool != "NONE":
                self.set_sketch_tool("NONE")
            elif self.active_tool_title():   # Esc always leaves the current function, also an open tool panel
                self.menu_command.emit("tool_cancel")
            elif self.doc.selected_profile or self.doc.selected_extra:
                self.doc.selected_profile = None
                self.doc.selected_extra = []
                self.profile_picked.emit()
            elif self.selected_entities or self.picked_dim_entities[1]:
                self.selected_entities.clear()
                self.picked_dim = None
                self.picked_dim_entities = (None, set())
                self.selection_changed.emit()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
        elif event.key() == Qt.Key.Key_F:
            self.zoom_fit()

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton and self.primitive_handles
                and self.primitive_handles.release()):
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.rotate_handles.release():
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.viewcube.handle_mouse_release():
            self.update()
            return
        if self._rubber is not None and event.button() == Qt.MouseButton.LeftButton:
            self._finish_rubber(event)
            return
        if self.sketch_tool == "ROTATE" and self._rotate_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._rotate_release(event.position().x(), event.position().y())
            return
        if (self.measure is not None and self.measure["mode"] == "model" and event.button() == Qt.MouseButton.LeftButton
                and self._press_pos is not None and (event.position() - self._press_pos).manhattanLength() < 4):
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            self._measure_click(event.position().x(), event.position().y())
            return
        if self.move_gizmo and self.move_gizmo.get("dragging") and event.button() == Qt.MouseButton.LeftButton:
            self.move_gizmo["dragging"] = False
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.move_gizmo.get("hover_axis") else Qt.CursorShape.ArrowCursor)
            self.move_gizmo_finished.emit()
            self.update()
            return
        if self._handle_drag and event.button() == Qt.MouseButton.LeftButton:
            self._handle_drag = False
            quality.set_interactive_mode(False)
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._handle_hover else Qt.CursorShape.ArrowCursor)
            self.extrude_handle_drag_finished.emit()
            self.update()
            return
        if event.button() == Qt.MouseButton.RightButton and self._rpress is not None:
            moved = (event.position() - self._rpress).manhattanLength()
            self._rpress = None
            self.is_panning = False
            if moved < 4 and self.plane_pick_mode and self.plane_pick_purpose == "move_body":
                body_id = self.pick_body(event.position().x(), event.position().y())
                if body_id is not None:
                    self.doc.select_body(body_id)
                    self.body_clicked.emit(body_id)
                    self.update()
                return
            if moved < 4 and not self.plane_pick_mode and not self.edge_pick_mode:
                if not self.doc.active_sketch and self.move_gizmo:
                    self._show_axis_menu(event)
                elif not self.doc.active_sketch and self.pick_profile(event.position().x(), event.position().y()) is not None:
                    self._show_profile_menu(event, self.pick_profile(event.position().x(), event.position().y()))
                elif not self.doc.active_sketch and self._sketch_line_at(event.position().x(), event.position().y()) is not None:
                    self._show_sketch_menu(event, self._sketch_line_at(event.position().x(), event.position().y()))
                elif not self.doc.active_sketch and not self.active_tool_title() and self._pick_edge(event.position().x(), event.position().y()) is not None:
                    self._show_edge_menu(event, self._pick_edge(event.position().x(), event.position().y()))
                elif not self.doc.active_sketch:
                    target = self._pick_plane_target(event.position().x(), event.position().y())
                    if target is not None and target[0] == "face":
                        self._show_face_menu(event)
                    elif target is not None:
                        self._show_plane_menu(event, target)
                    else:
                        self._show_general_menu(event)
                elif self.dim_badge_at(event.position().x(), event.position().y()) is not None:
                    self._show_dimension_menu(event, *self.dim_badge_at(event.position().x(), event.position().y()))
                elif self.sketch_tool in ("NONE", "DIMENSION") and not self._move:
                    ent = self._pick_entity(event.position().x(), event.position().y())
                    if ent is not None:
                        self._show_element_menu(event, ent)
                    else:
                        self._show_general_menu(event)
            return
        if self._endpoint_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._endpoint_drag_release()
            return
        if self._spline_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._spline_drag_release()
            return
        if self._dim_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._dim_drag_release()
            return
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_release(event)
            return
        was_click = (
            event.button() == Qt.MouseButton.LeftButton
            and self._press_pos is not None
            and not self.doc.active_sketch
            and (event.position() - self._press_pos).manhattanLength() < 4
        )
        if (event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None
                and self._can_select_sketch_entities()
                and (event.position() - self._press_pos).manhattanLength() < 4):
            additive = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            self.select_entity_at(event.position().x(), event.position().y(), additive)
            return
        if was_click and self.pick_step_mode and not self.plane_pick_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            hit = self._pick_surface(event.position().x(), event.position().y())
            if hit is not None:
                self.step_point_clicked.emit(hit["point"])
            return
        if was_click and self.edge_pick_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            if getattr(self, "path_pick_mode", False):    # a Sweep / Pipe path: sketch curves count as well as edges
                curve = self.pick_sketch_curve(event.position().x(), event.position().y())
                if curve is not None:
                    self.sketch_curve_picked.emit(*curve)
                    return
            e = self._pick_edge(event.position().x(), event.position().y())
            if e is not None:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:   # Ctrl+click only removes
                    chain = tangent_chain(e, self._visible_edges()) if getattr(self, "edge_tangent_chain", True) else [e]
                    self.selected_edges = [k for k in self.selected_edges if not any(self._same_edge(k, c) for c in chain)]
                    self.edges_selection_changed.emit()
                    self.update()
                else:
                    self._toggle_edge(e)
            else:
                hit = self._pick_face(event.position().x(), event.position().y())
                if hit is not None:
                    body, face = hit
                    face_edges = self._edges_of_face(face, body)
                    if face_edges:
                        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                            # Ctrl+click removes all edges of this face
                            self.selected_edges = [k for k in self.selected_edges if not any(self._same_edge(k, fe) for fe in face_edges)]
                        else:
                            # If all edges of this face are already selected, toggle them off; otherwise select all
                            all_selected = all(any(self._same_edge(k, fe) for k in self.selected_edges) for fe in face_edges)
                            if all_selected:
                                self.selected_edges = [k for k in self.selected_edges if not any(self._same_edge(k, fe) for fe in face_edges)]
                            else:
                                for fe in face_edges:
                                    if not any(self._same_edge(k, fe) for k in self.selected_edges):
                                        self.selected_edges.append(fe)
                        self.edges_selection_changed.emit()
                        self.update()
                if self._hidden_edge_at(event.position().x(), event.position().y()) is not None:   # said last: stays shown
                    self.status_message.emit("An edge hidden behind the model is here (inside a jar, under a shoulder...): "
                                             "press X or hold Alt to pick through the model (Ctrl+Backspace clears the selection).")
            return
        if was_click and self.plane_pick_mode:
            self._press_pos = None
            self.is_orbiting = False
            self.is_panning = False
            if self.plane_pick_purpose == "offset_surface":
                hit = self._pick_surface(event.position().x(), event.position().y())
                if hit is not None:
                    self.end_plane_pick()
                    self.surface_picked.emit(hit)
                return
            if self.plane_pick_purpose == "hole_point":
                hit = self._pick_surface(event.position().x(), event.position().y())
                if hit is not None:
                    self.surface_picked.emit(hit)
                return
            if self.plane_pick_purpose == "offset_face":
                self._offset_face_click(event.position().x(), event.position().y())
                return
            if self.plane_pick_purpose == "pattern_axis":
                edge = self._pick_edge(event.position().x(), event.position().y())
                if edge is not None and edge.kind == "circle":
                    cylinder = {"origin": edge.center, "axis": edge.axis}
                else:
                    cylinder = self._pick_cylinder_surface(event.position().x(), event.position().y())
                if cylinder is not None:
                    self.end_plane_pick()
                    self.cylinder_picked.emit(cylinder)
                return
            if self.plane_pick_purpose == "thread_surface":
                cyl = self._pick_cylinder_surface(event.position().x(), event.position().y())
                if cyl is not None:
                    self.cylinder_picked.emit(cyl)
                    return
            target = self._pick_plane_target(event.position().x(), event.position().y())
            if target is not None:
                plane = self.plane_from_target(target)
                purpose = self.plane_pick_purpose
                if purpose not in ("move_body", "shell_face", "thread_surface", "offset_face"):
                    self.end_plane_pick()
                if purpose == "offset_base":
                    self.offset_base_picked.emit(plane)
                elif purpose == "section_base":
                    self.section_base_picked.emit(plane)
                elif purpose == "extrude_target":
                    self.target_plane_picked.emit(plane)
                elif purpose == "primitive_face":
                    self.primitive_face_picked.emit(plane)
                elif purpose == "shell_face":
                    self.shell_face_picked.emit(plane)
                elif purpose == "move_body":
                    self.move_body_picked.emit(plane)
                elif purpose == "lay_target":
                    self.lay_target_picked.emit(plane)
                else:
                    self.plane_picked.emit(plane)
            return
        self._press_pos = None
        self.is_orbiting = False
        self.is_panning = False
        if was_click and getattr(self, "path_pick_mode", False):
            curve = self.pick_sketch_curve(event.position().x(), event.position().y())
            if curve is not None:                 # a Sweep / Pipe path: the clicked curve and what joins it
                self.sketch_curve_picked.emit(*curve)
                return
        if was_click:
            picked = self.pick_profile(event.position().x(), event.position().y())
            doc = self.doc
            if picked is not None and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                                       or getattr(self, "profile_chain_mode", False)):
                self.toggle_profile_in_selection(picked)
            elif picked != doc.selected_profile or doc.selected_extra:
                doc.selected_profile = picked
                doc.selected_extra = []
                self.profile_picked.emit()
                self.update()
            if picked is None:
                clicked_body_id = self.pick_body(event.position().x(), event.position().y())
                if clicked_body_id is not None:
                    multi = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    doc.select_body(clicked_body_id, multi=multi)
                    self.body_clicked.emit(clicked_body_id)
                    self.update()
                else:
                    target = self._pick_plane_target(event.position().x(), event.position().y())
                    if target is not None and target[0] in ("origin", "cplane"):
                        self.plane_clicked.emit(target[1])     # e.g. Split Body takes it as its splitting plane
                    if doc.selected_body_ids:
                        doc.select_body(None)    # a click in empty space clears the body selection
                        self.update()
