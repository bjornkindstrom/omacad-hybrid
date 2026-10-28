"""Sweep, Loft and Pipe prompts for MainWindow (Björn #46)."""

from PySide6.QtWidgets import QMessageBox

from omacad.ui.controllers.prompt_guards import leaves_sketch


class SweepPromptsMixin:
    """One panel for the three path/profile tools: pick profiles in the view, choose the path sketch, live preview."""

    @leaves_sketch
    def prompt_sweep_tool(self, mode: str):
        from omacad.model.features.sweep import LoftFeature, PipeFeature, SweepFeature, path_points
        from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog, TITLES
        title = TITLES[mode]
        if mode != "pipe" and not self.doc.sketches:
            QMessageBox.information(self, title, "Draw the profile in a sketch first.")
            return
        if self.inspector.current_tool_dlg is not None:
            return
        from omacad.ui.dialogs.sweep_dlg import path_entities
        candidates = [sid for sid, sk in self.doc.sketches.items() if path_entities(sk)]
        if mode != "loft" and not candidates and not any(b.edges for b in self.doc.bodies.values()):
            QMessageBox.information(self, title, "There is nothing to use as the path: draw it in a sketch or make "
                                                 "a body whose edges it can follow.")
            return
        dlg = SweepLoftDialog(self.doc, mode, self, embedded=True)
        shown = {sid: sk.visible for sid, sk in self.doc.sketches.items()}
        for sk in self.doc.sketches.values():          # the profiles must be visible to be clicked
            sk.visible = True
        self.doc.selected_profile, self.doc.selected_extra = None, []
        self.viewport.profile_chain_mode = mode == "loft"   # Loft: each click adds a profile, from any plane
        self.dock(dlg)

        class _PathLine:            # the picked path, outlined in the view like a timeline step's edges
            def __init__(self, pts):
                self.pts = pts

            def polyline(self, n: int = 2):
                return self.pts

        def show_path():
            try:
                pts, closed = path_points(self.doc, dlg.path())
                self.viewport.step_edges = [_PathLine(list(pts) + ([pts[0]] if closed else []))]
            except Exception:
                self.viewport.step_edges = []
            self.viewport.update()

        def default_path():
            """One sketch besides the profile's has path elements: take it, so the common case needs no click."""
            used = {s for s, _ in dlg.profiles}
            others = [sid for sid in candidates if sid not in used]
            if dlg.path() is None and len(others) == 1:
                dlg.set_path(others[0], path_entities(self.doc.sketches[others[0]])[0])
                show_path()

        def on_edges():
            dlg.set_edge_path([e.ref() for e in self.viewport.selected_edges])
            show_path()

        def on_active(target):
            self.viewport.path_pick_mode = target == "path"
            self.viewport.profile_chain_mode = mode == "loft" or (mode == "sweep" and target == "profile")
            if target == "path" and not self.viewport.edge_pick_mode:
                keep = list(self.viewport.selected_edges)
                self.viewport.begin_edge_pick()            # body edges like Fillet: hover, joined edges, X see-through
                self.viewport.selected_edges = keep if dlg.path() and dlg.path()[0] == "@edges" else []
            elif target != "path" and self.viewport.edge_pick_mode:
                self.viewport.edge_pick_mode = False
                self.viewport.hover_edge = None
            self.status_label.setText(f"{title}: click " + ("a line, arc or circle of the path." if target == "path"
                                                             else "the profiles (each click adds one, a click again drops it), then Path." if mode == "sweep"
                                                             else "the profile."))

        def on_curve(sketch_id, entity_id):
            self.viewport.selected_edges = []              # a sketch path replaces picked edges
            if dlg.set_path(sketch_id, entity_id):
                show_path()
                self.status_label.setText(f"{title}: path picked. Adjust the values, OK.")
            else:
                self.status_label.setText(f"{title}: that element cannot be a path.")

        dlg.active_changed.connect(on_active)
        self.viewport.sketch_curve_picked.connect(on_curve)
        self.viewport.edges_selection_changed.connect(on_edges)
        self.viewport.edge_pick_cancelled.connect(dlg.reject)       # Esc while picking edges closes the tool
        on_active(dlg.active)
        if mode == "pipe":
            default_path()

        def feature():
            path = dlg.path()
            if mode != "loft" and path is None:
                return None
            if mode == "pipe":
                return PipeFeature("preview", title, path, dlg.spn_diam.value(), dlg.spn_thick.value(), dlg.operation())
            if not dlg.profiles:
                return None
            if mode == "sweep":
                sid, idx = dlg.profiles[0]
                return SweepFeature("preview", title, sid, idx, path, dlg.operation(), dlg.spn_twist.value(),
                                    [i for _s, i in dlg.profiles[1:]])
            if len(dlg.profiles) < 2:
                return None
            return LoftFeature("preview", title, [LoftFeature.section_ref(self.doc, s, i) for s, i in dlg.profiles],
                               dlg.operation(), dlg.spn_twist.value())

        def sync_profiles():
            self.doc.selected_profile = dlg.profiles[0] if dlg.profiles else None
            self.doc.selected_extra = list(dlg.profiles[1:])

        if mode == "loft":
            dlg.changed.connect(sync_profiles)

        def preview():
            solid = None
            try:
                feat = feature()
                solid = feat.build_solid(self.doc) if feat is not None else None
                dlg.lbl_problem.setText("" if solid is not None or feat is None
                                        else "No solid from these choices (does the path run from the profile?).")
            except Exception as exc:
                dlg.lbl_problem.setText(str(exc))
            self.viewport.set_preview(solid, dlg.operation())

        def on_pick():
            chosen = ([self.doc.selected_profile] if self.doc.selected_profile else []) + list(self.doc.selected_extra)
            dlg.set_profiles([c for c in chosen if c[0] == chosen[0][0]] if mode == "sweep" and chosen else chosen)   # Sweep: one sketch
            if mode == "sweep" and dlg.profiles:
                default_path()                      # more profiles may follow: Path is chosen with its own button

        def on_finished(result):
            self.viewport.profile_picked.disconnect(on_pick)
            self.viewport.sketch_curve_picked.disconnect(on_curve)
            self.viewport.edges_selection_changed.disconnect(on_edges)
            self.viewport.edge_pick_cancelled.disconnect(dlg.reject)
            if self.viewport.edge_pick_mode:
                self.viewport.end_edge_pick()
            self.viewport.profile_chain_mode = False
            self.viewport.path_pick_mode = False
            self.viewport.step_edges = []
            self.viewport.set_preview(None)
            for sid, vis in shown.items():
                if sid in self.doc.sketches:
                    self.doc.sketches[sid].visible = vis
            self.doc.selected_profile, self.doc.selected_extra = None, []
            if result:
                path, op = dlg.path(), dlg.operation()
                try:
                    if mode != "loft" and path is None:
                        feat = None
                    elif mode == "pipe":
                        feat = self.doc.add_pipe(path, dlg.spn_diam.value(), dlg.spn_thick.value(), op)
                    elif mode == "sweep" and dlg.profiles:
                        feat = self.doc.add_sweep(*dlg.profiles[0], path, op, dlg.spn_twist.value(), [i for _s, i in dlg.profiles[1:]])
                    elif mode == "loft" and len(dlg.profiles) >= 2:
                        feat = self.doc.add_loft(dlg.profiles, op, dlg.spn_twist.value())
                    else:
                        self.status_label.setText(f"{title}: pick the profile(s) first.")
                        return
                    if feat is None:
                        raise ValueError("pick the path first.")
                    feat.exprs = dlg.get_expressions()
                    self.status_label.setText(f"{feat.name} created.")
                except Exception as exc:
                    self.status_label.setText(f"{title}: {exc}")
            self.doc.notify_changed()

        self.viewport.profile_picked.connect(on_pick)
        self._connect_debounced_preview(dlg, preview)
        dlg.finished.connect(on_finished)
        self.status_label.setText(f"{title}: " + ("set the path and the diameter." if mode == "pipe" else
                                                  "click the profile." if mode == "sweep" else
                                                  "click the profiles in order (a click again drops one)."))
        self.doc.notify_changed()
        preview()
