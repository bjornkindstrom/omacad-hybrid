"""Viewport context menus and their command dispatch."""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from omacad.ui import commands, theme
from omacad.ui.sketch_tools import RECT_TOOLS, SKETCH_TOOLS, rect_icon
from omacad.ui.viewport.shaders import SKETCH_GROUP_ICONS
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect
from omacad.model.faces import tangent_chain


class ContextMenuMixin:
    """Context menu behavior for :class:`Viewport3D`."""

    def _add_tool_entries(self, menu: QMenu, acts: dict):
        """While a tool panel (Extrude, Fillet, ...) is open: finish or cancel it from the menu."""
        title = self.active_tool_title()
        if not title:
            return
        acts[theme.action_with_icon(menu, f"✔️ Finish {title}")] = ("cmd", "tool_ok")
        acts[theme.action_with_icon(menu, f"✖️ Cancel {title}")] = ("cmd", "tool_cancel")
        menu.addSeparator()
    def _add_history_and_view(self, menu: QMenu, acts: dict, sketch: bool):
        """The entries every right-click menu ends with: undo/redo and view options (and Join with 2+ bodies selected)."""
        chosen = [b for b in self.doc.selected_body_ids if b in self.doc.bodies]
        if len(chosen) >= 2 and not sketch and not self.active_tool_title():
            names = ", ".join(self.doc.bodies[b].name for b in chosen)
            acts[theme.action_with_icon(menu, f"🔗 Combine {len(chosen)} Bodies ({names})")] = ("join_bodies", list(chosen))
            menu.addSeparator()
        u, r = self.doc.undo_label(), self.doc.redo_label()
        a = theme.action_with_icon(menu, f"↩️ Undo {u}" if u else "↩️ Undo")
        a.setEnabled(u is not None)
        acts[a] = ("cmd", "undo")
        a = theme.action_with_icon(menu, f"↪️ Redo {r}" if r else "↪️ Redo")
        a.setEnabled(r is not None)
        acts[a] = ("cmd", "redo")
        menu.addSeparator()
        view = menu.addMenu("👁️ View")
        if sketch:
            acts[view.addAction("Look at sketch")] = ("look", None)
        else:
            for name in ("Home", "Top", "Front", "Right"):
                acts[view.addAction(name)] = ("view", name)
        acts[view.addAction("Fit to window")] = ("fit", None)
        view.addSeparator()
        g = view.addAction("Grid")
        g.setCheckable(True)
        g.setChecked(self.show_grid)
        acts[g] = ("grid", None)
        e = view.addAction("Edges")
        e.setCheckable(True)
        e.setChecked(self.show_edges)
        acts[e] = ("edges", None)
    def _run_general(self, kind, arg):
        if kind == "cmd":
            self.menu_command.emit(arg)
        elif kind == "view":
            self.set_view(arg)
        elif kind == "fit":
            self.zoom_fit()
        elif kind == "look" and self.doc.active_sketch:
            self.align_to_plane(self.doc.active_sketch.plane)
        elif kind == "grid":
            self.show_grid = not self.show_grid
            self.update()
        elif kind == "edges":
            self.show_edges = not self.show_edges
            self.update()
        elif kind == "round":
            self.round_requested.emit(*arg)
        elif kind == "offset_face":
            self.offset_face_requested.emit(arg)
        elif kind == "offset_plane":
            self.offset_base_picked.emit(arg)
        elif kind == "body_color":
            self.body_color_requested.emit(arg)
        elif kind == "move_body":
            self.move_body_requested.emit(arg)
        elif kind == "join_bodies":
            self.join_bodies_requested.emit(arg)
        elif kind == "split_plane":
            self.split_plane_requested.emit(arg)
        elif kind == "sketch_plane":
            self.plane_picked.emit(arg)
        elif kind == "hide_plane":
            if arg[0] == "origin":
                self.doc.set_origin_visibility("plane", arg[1], False)
            else:
                self.doc.toggle_construction_plane(arg[1])
            self.hover_plane = None
            self.update()
        elif kind == "tool":
            self.set_sketch_tool(arg)
        elif kind == "construction":
            self.toggle_construction_mode()
        elif kind == "project":
            self.project_edges()
        elif kind == "finish":
            self.finish_sketch_requested.emit()
        elif kind == "sketch":
            self.menu_command.emit(f"sketch:{arg}")
        elif kind == "edit_sketch":
            self.edit_sketch_requested.emit(arg)
        elif kind == "extrude_sketch":
            self.extrude_sketch_requested.emit(arg)
        elif kind == "hide_sketch":
            self.doc.toggle_sketch_visibility(arg)
    def _sketch_line_at(self, x: float, y: float):
        """Id of the visible sketch whose lines or circles are under the cursor (model mode), else None."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        tol, best, best_t = self._entity_tolerance(), None, float("inf")
        for sid, sk in self.doc.sketches.items():
            if not sk.visible:
                continue
            hit = ray_plane_intersect(origin, ray_dir, sk.plane.origin, sk.plane.normal)
            if hit is None:
                continue
            u, v = sk.plane.world_to_uv(hit)
            t = float(np.linalg.norm(hit - origin))
            if t < best_t and sk.hit_test(u, v, tol) is not None:
                best, best_t = sid, t
        return best
    def _show_sketch_menu(self, event, sketch_id: str):
        """Right-click on a sketch (not in sketch mode): Edit Sketch first, as in Fusion 360."""
        sk = self.doc.sketches.get(sketch_id)
        if sk is None:
            return
        menu = QMenu(self)
        acts: dict = {}
        acts[theme.action_with_icon(menu, "✏️ Edit Sketch")] = ("edit_sketch", sketch_id)
        acts[theme.action_with_icon(menu, "⬆️ Extrude\tE")] = ("extrude_sketch", sketch_id)
        acts[theme.action_with_icon(menu, "👁️ Hide Sketch")] = ("hide_sketch", sketch_id)
        acts[theme.action_with_icon(menu, "🗑️ Delete Sketch…")] = ("cmd", f"delete_sketch:{sketch_id}")
        menu.addSeparator()
        self._add_tool_entries(menu, acts)
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)
    def _show_profile_menu(self, event, key):
        """Right-click on a sketch profile (the shaded area inside closed lines): act on that profile only,
        without lighting up the face around it."""
        doc = self.doc
        if key != doc.selected_profile and key not in doc.selected_extra:
            doc.selected_profile, doc.selected_extra = key, []   # right-click selects it, like left-click
            self.profile_picked.emit()
        self.update()
        menu = QMenu(self)
        acts: dict = {}
        acts[theme.action_with_icon(menu, "✏️ Edit Sketch")] = ("edit_sketch", key[0])
        menu.addSeparator()
        self._add_tool_entries(menu, acts)
        n = 1 + len(doc.selected_extra)
        what = "profile" if n == 1 else f"{n} profiles"
        acts[theme.action_with_icon(menu, f"⬆️ Extrude this {what}…")] = ("cmd", "extrude")
        acts[theme.action_with_icon(menu, f"🔄 Revolve this {what}…")] = ("cmd", "revolve")
        acts[theme.action_with_icon(menu, f"🔖 Emboss this {what}…")] = ("cmd", "emboss")
        acts[theme.action_with_icon(menu, "✖️ Deselect")] = ("deselect", None)
        menu.addSeparator()
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen is None:
            return
        if chosen[0] == "deselect":
            doc.selected_profile, doc.selected_extra = None, []
            self.profile_picked.emit()
            self.update()
        else:
            self._run_general(*chosen)
    def _show_axis_menu(self, event):
        """Right-click while the Move arrows are shown: pick the axis to drag along."""
        menu = QMenu(self)
        acts = {}
        for ax, label in (("X", "🔴 Move along X"), ("Y", "🟢 Move along Y"), ("Z", "🔵 Move along Z")):
            acts[theme.action_with_icon(menu, label)] = ax
        menu.addSeparator()
        general: dict = {}
        self._add_tool_entries(menu, general)
        chosen = menu.exec(event.globalPosition().toPoint())
        if chosen in acts:
            self.move_gizmo["active_axis"] = acts[chosen]
            self.move_gizmo_axis_selected.emit(acts[chosen])
            self.update()
        elif chosen in general:
            self._run_general(*general[chosen])
    def _show_general_menu(self, event):
        """Right-click on empty space: what you can do next, depending on whether a sketch is open."""
        menu = QMenu(self)
        acts: dict = {}
        sketch = self.doc.active_sketch is not None
        self._add_tool_entries(menu, acts)
        if sketch:
            acts[theme.action_with_icon(menu, "✔️ Finish Sketch")] = ("finish", None)
            acts[theme.action_with_icon(menu, "🩹 " + commands.label("fix_sketch"))] = ("cmd", "fix_sketch")
            menu.addSeparator()
            groups: dict = {}
            for tool, label, group, sub in SKETCH_TOOLS:
                if group not in groups:
                    if sum(1 for t in SKETCH_TOOLS if t[2] == group) == 1:   # a lone tool needs no submenu
                        groups[group] = (menu, {})
                        label = f"{SKETCH_GROUP_ICONS.get(group, '')} {label}".strip()
                    else:
                        groups[group] = (menu.addMenu(f"{SKETCH_GROUP_ICONS.get(group, '')} {group}".strip()), {})
                parent, subs = groups[group]
                if sub:
                    if sub not in subs:
                        subs[sub] = parent.addMenu(sub)
                    parent = subs[sub]
                act = parent.addAction(rect_icon(tool, 22), label) if tool in RECT_TOOLS else parent.addAction(label)
                acts[act] = ("tool", tool)
            parent = groups.get("Create", (menu,))[0]
            acts[parent.addAction(commands.menu_text("project"))] = ("project", None)
            c = menu.addAction(commands.menu_text("construction"))
            c.setCheckable(True)
            c.setChecked(self.construction_mode)
            acts[c] = ("construction", None)
        else:
            new = menu.addMenu("✏️ New Sketch on")
            for name in ("XY", "XZ", "YZ"):
                acts[new.addAction(f"{name} plane")] = ("sketch", name)
        menu.addSeparator()
        self._add_history_and_view(menu, acts, sketch)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)
    def _round_entries(self, menu, acts: dict, edges: list, what: str):
        """Fillet / Chamfer entries for the edges under the cursor (nothing while a tool panel is open)."""
        if self.active_tool_title():
            return
        for kind, icon in (("fillet", "🔵"), ("chamfer", "📐")):
            acts[theme.action_with_icon(menu, f"{icon} {kind.title()} {what}…")] = ("round", (kind, edges))
        menu.addSeparator()
    def _show_edge_menu(self, event, edge):
        """Right-click on a lit-up edge: fillet or chamfer it (and the edges joined to it smoothly)."""
        menu = QMenu(self)
        acts: dict = {}
        self._round_entries(menu, acts, tangent_chain(edge, self._visible_edges()), "this edge")
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)
    def _show_face_menu(self, event):
        """Right-click on a flat face: offer to sketch on it directly."""
        target = self._pick_plane_target(event.position().x(), event.position().y())
        if target is None or target[0] != "face":
            return
        face = target[1]
        self.ctx_face = face
        self.update()
        menu = QMenu(self)
        act_sketch = theme.action_with_icon(menu, "✏️ Create Sketch on this Face")
        act_canvas = theme.action_with_icon(menu, "🖼️ Insert Canvas on this Face…")
        act_extrude = theme.action_with_icon(menu, "⬆️ Extrude this Face…")
        act_extrude.setToolTip("Pull the face into the body to cut it away, or out to add material.")
        menu.setToolTipsVisible(True)
        acts: dict = {}
        if face.body_id in self.doc.bodies:
            menu.addSeparator()
            acts[theme.action_with_icon(menu, "🎨 Appearance / Färg…")] = ("body_color", face.body_id)
            acts[theme.action_with_icon(menu, "↔️ Move this Body…")] = ("move_body", face.body_id)
            acts[theme.action_with_icon(menu, "⬇️ Lay this face on the ground (XY)")] = ("lay", "ground")
            acts[theme.action_with_icon(menu, "⬇️ Lay this face on a face or plane…")] = ("lay", "pick")
        menu.addSeparator()
        self._add_tool_entries(menu, acts)
        if not self.active_tool_title():
            acts[theme.action_with_icon(menu, "↔️ Offset Face…")] = ("offset_face", face)
            acts[theme.action_with_icon(menu, "📐 Offset Plane from this Face…")] = ("offset_plane", self.plane_from_target(("face", face)))
        body = self.doc.bodies.get(face.body_id)
        if body is not None:
            self._round_entries(menu, acts, self._edges_of_face(face, body), "edges of this face")
        self._add_history_and_view(menu, acts, False)
        chosen = menu.exec(event.globalPosition().toPoint())
        self.ctx_face = None
        self.update()
        if chosen in acts and acts[chosen][0] == "lay":
            self.lay_face_requested.emit(face, acts[chosen][1])
        elif chosen in acts:
            self._run_general(*acts[chosen])
        elif chosen is act_canvas:
            self.canvas_face_requested.emit(face)
        elif chosen is act_sketch:
            self.plane_picked.emit(self.plane_from_target(("face", face)))
        elif chosen is act_extrude:
            self.face_extrude_requested.emit(face)
    def _show_plane_menu(self, event, target):
        """Right-click on an origin or construction plane: split a body with it, offset from it, sketch on it, hide it."""
        menu = QMenu(self)
        acts: dict = {}
        plane = self.plane_from_target(target)
        name = f"{target[1]} plane" if target[0] == "origin" else self.doc.construction_planes[target[1]].get("name", "plane")
        menu.addSection(name)
        if not self.active_tool_title():
            if self.doc.bodies:
                acts[theme.action_with_icon(menu, "✂️ Split Body with this Plane…")] = ("split_plane", target[1])
            acts[theme.action_with_icon(menu, "📐 Offset Plane from this Plane…")] = ("offset_plane", plane)
            acts[theme.action_with_icon(menu, "✏️ Create Sketch on this Plane")] = ("sketch_plane", plane)
            menu.addSeparator()
        acts[theme.action_with_icon(menu, "👁 Hide Plane")] = ("hide_plane", target)
        menu.addSeparator()
        self._add_history_and_view(menu, acts, False)
        chosen = acts.get(menu.exec(event.globalPosition().toPoint()))
        if chosen:
            self._run_general(*chosen)
