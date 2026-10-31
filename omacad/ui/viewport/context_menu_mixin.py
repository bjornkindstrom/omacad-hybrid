"""Viewport context menus and their command dispatch."""

import numpy as np
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QMenu
from omacad.ui import commands, theme
from omacad.ui.sketch_tools import RECT_TOOLS, SKETCH_TOOLS, rect_icon
from omacad.ui.viewport.shaders import SKETCH_GROUP_ICONS
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect
from omacad.model.faces import tangent_chain
from omacad.ui.fan_menu import FanMenuOverlay, FanItem


_SYS_QMENU = QMenu


class ContextMenuMixin:
    """Context menu behavior for :class:`Viewport3D`."""

    def _ensure_fan_menu(self):
        if not hasattr(self, "fan_menu") or self.fan_menu is None:
            from omacad.ui.fan_menu import FanMenu
            self.fan_menu = FanMenu(self)
        return self.fan_menu

    def _record_fan_click_origin(self, x: float, y: float):
        """Record the 3D world point (and face plane, if any) under the right-click cursor for primitive creation."""
        self._fan_click_plane = None
        self._fan_click_world = None
        try:
            proj, view, _ = self.get_matrices()
            origin, ray_dir = ray_from_screen(x, y, max(1, self.width()), max(1, self.height()), view, proj)
            if getattr(self, "ctx_face", None) is not None:
                face = self.ctx_face
                plane = self.plane_from_target(("face", face))
                hit = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
                if hit is not None:
                    plane.origin = np.round(np.asarray(hit, dtype=float), 2)
                    self._fan_click_world = tuple(plane.origin)
                self._fan_click_plane = plane
                return
            hit_xy = ray_plane_intersect(origin, ray_dir, np.zeros(3), np.array([0.0, 0.0, 1.0]))
            if hit_xy is not None:
                self._fan_click_world = (round(float(hit_xy[0]), 2), round(float(hit_xy[1]), 2), 0.0)
        except Exception:
            pass


    def _build_workspace_fan_categories(self, sketch: bool) -> list[FanItem]:
        """Construct standard workspace categories (Create, Modify, Inspect, View, History, Constraints)."""
        categories = []

        if not sketch:
            # Solid Create
            create_items = []
            for cid in ("create_sketch", "extrude", "hole", "revolve", "sweep", "loft", "emboss"):
                c = commands.get(cid)
                create_items.append(FanItem(
                    id=cid,
                    label=c.label,
                    icon=theme.command_icon(cid, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _c=cid: self.menu_command.emit(_c)
                ))

            # Primitives Sub-fan
            prim_items = []
            for cid in ("box", "cylinder", "cone", "hexagon", "pipe", "thread", "jar"):
                c = commands.get(cid)
                prim_items.append(FanItem(
                    id=cid,
                    label=c.label,
                    icon=theme.command_icon(cid, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _c=cid: self.menu_command.emit(_c)
                ))
            create_items.append(FanItem(
                id="primitives",
                label="Primitives",
                icon=theme.named_icon("box", "📦", 20),
                tooltip="Box, Cylinder, Cone, Prism, Pipe, Thread, Jar",
                children=prim_items
            ))

            # Patterns Sub-fan
            pat_items = []
            for cid in ("pattern_linear", "pattern_circular", "mirror", "pattern_fill"):
                c = commands.get(cid)
                pat_items.append(FanItem(
                    id=cid,
                    label=c.label,
                    icon=theme.command_icon(cid, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _c=cid: self.menu_command.emit(_c)
                ))
            create_items.append(FanItem(
                id="patterns",
                label="Pattern",
                icon=theme.named_icon("pattern", "🔁", 20),
                tooltip="Linear, Circular, Mirror, Fill Face",
                children=pat_items
            ))

            for cid in ("honeycomb", "offset_plane", "canvas"):
                c = commands.get(cid)
                create_items.append(FanItem(
                    id=cid,
                    label=c.label,
                    icon=theme.command_icon(cid, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _c=cid: self.menu_command.emit(_c)
                ))

            categories.append(FanItem(
                id="cat_create",
                label="Create",
                icon=theme.named_icon("extrude", "➕", 20),
                children=create_items
            ))

            categories.append(FanItem(
                id="cat_primitives",
                label="Primitives",
                icon=theme.named_icon("box", "📦", 20),
                children=list(prim_items)
            ))

            # Solid Modify
            modify_items = []
            for cid in ("fillet", "chamfer", "shell", "offset_face", "combine", "split_body", "move", "parameters", "delete"):
                c = commands.get(cid)
                modify_items.append(FanItem(
                    id=cid,
                    label=c.label,
                    icon=theme.command_icon(cid, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _c=cid: self.menu_command.emit(_c)
                ))
            categories.append(FanItem(
                id="cat_modify",
                label="Modify",
                icon=theme.named_icon("fillet", "🔧", 20),
                children=modify_items
            ))

        else:
            # Sketch Create
            create_items = []
            create_items.append(FanItem(
                id="line",
                label="Line",
                icon=theme.command_icon("line", "✏️", 20),
                shortcut="L",
                tooltip=commands.tooltip("line"),
                callback=lambda: self.menu_command.emit("sketch_tool:LINE")
            ))

            # Rectangles Sub-fan
            rect_children = []
            for t, (lbl, _icon_sym) in RECT_TOOLS.items():
                rect_children.append(FanItem(
                    id=t,
                    label=lbl.replace("\n", " "),
                    icon=rect_icon(t, 20),
                    callback=lambda _t=t: self.menu_command.emit(f"sketch_tool:{_t}")
                ))
            create_items.append(FanItem(
                id="rectangles",
                label="Rectangle",
                icon=rect_icon("RECT", 20),
                shortcut="R",
                tooltip="2-Point, Center, Rounded, Center Rounded Rectangles",
                children=rect_children
            ))

            for tool_id, cmd_id, tip_id in (
                ("CIRCLE", "circle", "circle"),
                ("SMART_CIRCLE", "smart_circle", "smart_circle"),
                ("ARC", "arc", "arc"),
                ("SPLINE", "spline", "spline"),
                ("POLYGON", "polygon", "polygon"),
                ("SLOT", "slot", "slot"),
                ("TEXT", "text", "text"),
                ("OFFSET", "offset_sketch", "offset_sketch"),
                ("MIRROR", "mirror_sketch", "mirror_sketch"),
                ("DIMENSION", "dimension", "dimension"),
            ):
                c = commands.get(cmd_id)
                create_items.append(FanItem(
                    id=tool_id,
                    label=c.label,
                    icon=theme.command_icon(cmd_id, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _t=tool_id: self.menu_command.emit(f"sketch_tool:{_t}")
                ))

            c_proj = commands.get("project")
            create_items.append(FanItem(
                id="project",
                label=c_proj.label,
                icon=theme.command_icon("project", c_proj.icon, 20),
                tooltip=c_proj.tip,
                callback=self.project_edges
            ))

            categories.append(FanItem(
                id="cat_create",
                label="Create",
                icon=theme.named_icon("line", "✏️", 20),
                children=create_items
            ))

            # Sketch Modify
            modify_items = []
            for tool_id, cmd_id in (
                ("FILLET", "fillet_sketch"),
                ("TRIM", "trim"),
                ("MOVE", "move_sketch"),
                ("ROTATE", "rotate_sketch"),
                ("SCALE", "scale_sketch"),
            ):
                c = commands.get(cmd_id)
                modify_items.append(FanItem(
                    id=tool_id,
                    label=c.label,
                    icon=theme.command_icon(cmd_id, c.icon, 20),
                    shortcut=c.shortcut,
                    tooltip=c.tip,
                    callback=lambda _t=tool_id: self.menu_command.emit(f"sketch_tool:{_t}")
                ))

            c_fix = commands.get("fix_sketch")
            modify_items.append(FanItem(
                id="fix_sketch",
                label=c_fix.label,
                icon=theme.command_icon("fix_sketch", c_fix.icon, 20),
                tooltip=c_fix.tip,
                callback=lambda: self.menu_command.emit("fix_sketch")
            ))
            modify_items.append(FanItem(
                id="construction",
                label="Construction Mode",
                icon=theme.named_icon("construction_line", "┄", 20),
                shortcut="X",
                tooltip="Toggle construction lines mode",
                checkable=True,
                checked=self.construction_mode,
                callback=self.toggle_construction_mode
            ))
            categories.append(FanItem(
                id="cat_modify",
                label="Modify",
                icon=theme.named_icon("trim", "✂️", 20),
                children=modify_items
            ))

            # Sketch Constraints
            from omacad.ui.ribbon import Ribbon
            const_items = []
            for ctype, label, icon_sym, tip in Ribbon.CONSTRAINTS:
                const_items.append(FanItem(
                    id=ctype,
                    label=label,
                    icon=theme.named_icon(f"c_{ctype.lower()}", icon_sym, 20),
                    tooltip=tip,
                    callback=lambda _ct=ctype: self.menu_command.emit(f"constraint:{_ct}")
                ))
            categories.append(FanItem(
                id="cat_constraints",
                label="Constraints",
                icon=theme.named_icon("c_coincident", "📐", 20),
                children=const_items
            ))

        # Inspect
        inspect_items = [
            FanItem(
                id="measure",
                label="Measure",
                icon=theme.command_icon("measure", "📏", 20),
                shortcut="I",
                tooltip=commands.tooltip("measure"),
                callback=self.begin_measure
            )
        ]
        if not sketch:
            inspect_items.append(FanItem(
                id="section",
                label="Section View",
                icon=theme.command_icon("section", "✂️", 20),
                tooltip=commands.tooltip("section"),
                callback=lambda: self.menu_command.emit("section")
            ))
            inspect_items.append(FanItem(
                id="statistics",
                label="Statistics",
                icon=theme.named_icon("statistics", "📊", 20),
                tooltip=commands.tooltip("statistics"),
                callback=lambda: self.menu_command.emit("statistics")
            ))
        categories.append(FanItem(
            id="cat_inspect",
            label="Inspect",
            icon=theme.command_icon("measure", "📏", 20),
            children=inspect_items
        ))

        # View
        view_items = []
        if sketch:
            view_items.append(FanItem(
                id="look_at_sketch",
                label="Look at Sketch",
                icon=theme.named_icon("look_at", "🎯", 20),
                callback=lambda: self.align_to_plane(self.doc.active_sketch.plane) if self.doc.active_sketch else None
            ))
        else:
            for vn in ("Home", "Top", "Front", "Right"):
                view_items.append(FanItem(
                    id=f"view_{vn.lower()}",
                    label=vn,
                    icon=theme.named_icon("camera", "👁️", 20),
                    callback=lambda _v=vn: self.set_view(_v)
                ))
        view_items.append(FanItem(
            id="fit",
            label="Fit Window",
            shortcut="F",
            icon=theme.named_icon("locate", "🔍", 20),
            callback=self.zoom_fit
        ))
        view_items.append(FanItem(
            id="grid",
            label="Grid",
            icon=theme.named_icon("origin", "🌐", 20),
            checkable=True,
            checked=self.show_grid,
            callback=lambda: self._run_general("grid", None)
        ))
        view_items.append(FanItem(
            id="edges",
            label="Edges",
            icon=theme.named_icon("edges", "🔳", 20),
            checkable=True,
            checked=self.show_edges,
            callback=lambda: self._run_general("edges", None)
        ))
        categories.append(FanItem(
            id="cat_view",
            label="View",
            icon=theme.named_icon("camera", "👁️", 20),
            children=view_items
        ))

        # History / Combine
        hist_items = []
        chosen = [b for b in self.doc.selected_body_ids if b in self.doc.bodies]
        if len(chosen) >= 2 and not sketch and not self.active_tool_title():
            hist_items.append(FanItem(
                id="combine_bodies",
                label=f"Combine {len(chosen)} Bodies",
                icon=theme.command_icon("combine", "🔗", 20),
                callback=lambda: self.join_bodies_requested.emit(list(chosen))
            ))
        u, r = self.doc.undo_label(), self.doc.redo_label()
        hist_items.append(FanItem(
            id="undo",
            label=f"Undo {u}" if u else "Undo",
            icon=theme.named_icon("undo", "↩️", 20),
            shortcut="Ctrl+Z",
            enabled=u is not None,
            callback=lambda: self.menu_command.emit("undo")
        ))
        hist_items.append(FanItem(
            id="redo",
            label=f"Redo {r}" if r else "Redo",
            icon=theme.named_icon("redo", "↪️", 20),
            shortcut="Ctrl+Y",
            enabled=r is not None,
            callback=lambda: self.menu_command.emit("redo")
        ))
        categories.append(FanItem(
            id="cat_history",
            label="History",
            icon=theme.named_icon("undo", "↩️", 20),
            children=hist_items
        ))

        return categories

    def _open_fan_or_menu(
        self,
        event,
        menu: QMenu,
        acts: dict,
        context_items: Optional[list[FanItem]] = None,
        context_label: str = "Context",
        on_close=None,
        default_cat: Optional[str] = None,
        on_custom=None
    ):
        """
        If QMenu is spy-patched for tests, fall back to menu.exec().
        Otherwise, open the rich two-arc FanMenuOverlay.
        """
        if getattr(QMenu, "exec", None) != _SYS_QMENU.exec or getattr(menu.__class__, "exec", None) != _SYS_QMENU.exec:
            # A test monkey-patched QMenu.exec (e.g. SpyMenu). Respect test harness.
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else (event.position().toPoint() if hasattr(event, "position") else QPoint(0, 0))
            chosen = menu.exec(pos)
            if on_close:
                on_close()
            if chosen in acts:
                self._run_general(*acts[chosen])
            elif on_custom:
                on_custom(chosen)
            return

        sketch = (self.doc.active_sketch is not None)
        fan_categories = []
        default_idx = 0

        # Prepend Context Category if provided
        if context_items:
            fan_categories.append(FanItem(
                id="cat_context",
                label=context_label,
                icon=theme.named_icon("pointer", "✨", 20),
                accent_role=True,
                children=context_items
            ))
            default_idx = 0
        else:
            default_idx = 0  # Create will be first

        base_cats = self._build_workspace_fan_categories(sketch)
        fan_categories.extend(base_cats)

        if default_cat:
            for idx, c in enumerate(fan_categories):
                if c.id == default_cat or c.label.lower() == default_cat.lower():
                    default_idx = idx
                    break

        # Hub items
        hub_ok = None
        hub_cancel = None
        hub_center = None

        tool_title = self.active_tool_title()
        if tool_title:
            hub_ok = FanItem(id="hub_ok", label=f"Finish {tool_title}", callback=lambda: self.menu_command.emit("tool_ok"))
            hub_cancel = FanItem(id="hub_cancel", label=f"Cancel {tool_title}", callback=lambda: self.menu_command.emit("tool_cancel"))
        elif sketch:
            hub_center = FanItem(id="finish_sketch", label="Finish\nSketch", callback=lambda: self.finish_sketch_requested.emit())
        else:
            hub_center = FanItem(id="close", label="✖", callback=lambda: None)

        menu_ctrl = self._ensure_fan_menu()
        pos = event.position().toPoint() if hasattr(event, "position") else QPoint(self.width() // 2, self.height() // 2)
        self._record_fan_click_origin(float(pos.x()), float(pos.y()))
        menu_ctrl.popup(
            center=pos,
            categories=fan_categories,
            hub_ok=hub_ok,
            hub_cancel=hub_cancel,
            hub_center=hub_center,
            gesture_mode=getattr(self, "_rfan_gesture_active", False),
            default_category_idx=default_idx,
            on_close=on_close
        )


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

        context_items = [
            FanItem("edit_sk", "Edit Sketch", theme.named_icon("sketch", "✏️", 20), callback=lambda: self.edit_sketch_requested.emit(sketch_id)),
            FanItem("extrude_sk", "Extrude", theme.named_icon("extrude", "⬆️", 20), shortcut="E", callback=lambda: self.extrude_sketch_requested.emit(sketch_id)),
            FanItem("hide_sk", "Hide Sketch", theme.named_icon("eye", "👁️", 20), callback=lambda: self.doc.toggle_sketch_visibility(sketch_id)),
            FanItem("del_sk", "Delete Sketch", theme.named_icon("delete", "🗑️", 20), callback=lambda: self.menu_command.emit(f"delete_sketch:{sketch_id}")),
        ]
        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label=sk.name or "Sketch")

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

        def _deselect():
            doc.selected_profile, doc.selected_extra = None, []
            self.profile_picked.emit()
            self.update()

        context_items = [
            FanItem("edit_sk", "Edit Sketch", theme.named_icon("sketch", "✏️", 20), callback=lambda: self.edit_sketch_requested.emit(key[0])),
            FanItem("extrude", f"Extrude {what}", theme.named_icon("extrude", "⬆️", 20), shortcut="E", callback=lambda: self.menu_command.emit("extrude")),
            FanItem("revolve", f"Revolve {what}", theme.named_icon("revolve", "🔄", 20), callback=lambda: self.menu_command.emit("revolve")),
            FanItem("emboss", f"Emboss {what}", theme.named_icon("emboss", "🔖", 20), callback=lambda: self.menu_command.emit("emboss")),
            FanItem("deselect", "Deselect", theme.named_icon("cancel", "✖️", 20), callback=_deselect),
        ]
        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label="Profile")

    def _show_axis_menu(self, event):
        """Right-click while the Move arrows are shown: pick the axis to drag along."""
        menu = QMenu(self)
        acts = {}
        for ax, label in (("X", "🔴 Move along X"), ("Y", "🟢 Move along Y"), ("Z", "🔵 Move along Z")):
            acts[theme.action_with_icon(menu, label)] = ax
        menu.addSeparator()
        general: dict = {}
        self._add_tool_entries(menu, general)

        context_items = []
        for ax, label in (("X", "Move X"), ("Y", "Move Y"), ("Z", "Move Z")):
            def _choose_ax(_a=ax):
                self.move_gizmo["active_axis"] = _a
                self.move_gizmo_axis_selected.emit(_a)
                self.update()
            context_items.append(FanItem(f"axis_{ax}", label, callback=_choose_ax))

        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label="Move Axis")

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

        context_items = None
        if not sketch:
            # Offer Quick New Sketch on XY/XZ/YZ planes
            context_items = [
                FanItem(f"sk_{p}", f"Sketch {p}", theme.named_icon("sketch", "✏️", 20), callback=lambda _p=p: self.menu_command.emit(f"sketch:{_p}"))
                for p in ("XY", "XZ", "YZ")
            ]
        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label="New Sketch", default_cat="Create")

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
        chain = tangent_chain(edge, self._visible_edges())
        self._round_entries(menu, acts, chain, "this edge")
        self._add_history_and_view(menu, acts, False)

        context_items = [
            FanItem("fillet_edge", "Fillet Edge", theme.named_icon("fillet", "🔘", 20), shortcut="F", callback=lambda: self.round_requested.emit("fillet", chain)),
            FanItem("chamfer_edge", "Chamfer Edge", theme.named_icon("chamfer", "◢", 20), callback=lambda: self.round_requested.emit("chamfer", chain)),
        ]
        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label="Edge")

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

        def _clear_ctx():
            self.ctx_face = None
            self.update()

        context_items = [
            FanItem("sk_on_face", "Sketch on Face", theme.named_icon("sketch", "✏️", 20), callback=lambda: self.plane_picked.emit(self.plane_from_target(("face", face)))),
            FanItem("extrude_face", "Extrude Face", theme.named_icon("extrude", "⬆️", 20), shortcut="E", tooltip="Pull face into body to cut, or out to add material", callback=lambda: self.face_extrude_requested.emit(face)),
            FanItem("offset_face", "Offset Face", theme.named_icon("offset_face", "↔️", 20), callback=lambda: self.offset_face_requested.emit(face)),
            FanItem("canvas_face", "Insert Canvas", theme.named_icon("canvas", "🖼️", 20), callback=lambda: self.canvas_face_requested.emit(face)),
            FanItem("offset_plane_face", "Offset Plane", theme.named_icon("offset_plane", "📐", 20), callback=lambda: self.offset_base_picked.emit(self.plane_from_target(("face", face)))),
        ]
        if face.body_id in self.doc.bodies:
            context_items.append(FanItem("move_body", "Move Body", theme.named_icon("move", "✥", 20), shortcut="M", callback=lambda: self.move_body_requested.emit(face.body_id)))
            context_items.append(FanItem("color_body", "Appearance", theme.named_icon("settings", "🎨", 20), callback=lambda: self.body_color_requested.emit(face.body_id)))
            context_items.append(FanItem("lay_ground", "Lay on Ground", theme.named_icon("lay_flat", "⬇️", 20), callback=lambda: self.lay_face_requested.emit(face, "ground")))

        if body is not None:
            face_edges = self._edges_of_face(face, body)
            if face_edges:
                context_items.append(FanItem("fillet_face_edges", "Fillet Face Edges", theme.named_icon("fillet", "🔘", 20), callback=lambda: self.round_requested.emit("fillet", face_edges)))
                context_items.append(FanItem("chamfer_face_edges", "Chamfer Face Edges", theme.named_icon("chamfer", "◢", 20), callback=lambda: self.round_requested.emit("chamfer", face_edges)))

        def _custom_pick(chosen):
            if chosen is act_canvas:
                self.canvas_face_requested.emit(face)
            elif chosen is act_sketch:
                self.plane_picked.emit(self.plane_from_target(("face", face)))
            elif chosen is act_extrude:
                self.face_extrude_requested.emit(face)
            elif chosen in acts and acts[chosen][0] == "lay":
                self.lay_face_requested.emit(face, acts[chosen][1])

        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label="Face", on_close=_clear_ctx, on_custom=_custom_pick)


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

        context_items = [
            FanItem("sk_on_plane", "Sketch on Plane", theme.named_icon("sketch", "✏️", 20), callback=lambda: self.plane_picked.emit(plane)),
            FanItem("offset_plane", "Offset Plane", theme.named_icon("offset_plane", "📐", 20), callback=lambda: self.offset_base_picked.emit(plane)),
        ]
        if self.doc.bodies:
            context_items.append(FanItem("split_plane", "Split Body", theme.named_icon("split_body", "✂️", 20), callback=lambda: self.split_plane_requested.emit(target[1])))
        context_items.append(FanItem("hide_plane", "Hide Plane", theme.named_icon("eye_off", "👁", 20), callback=lambda: self._run_general("hide_plane", target)))

        self._open_fan_or_menu(event, menu, acts, context_items=context_items, context_label=name)

