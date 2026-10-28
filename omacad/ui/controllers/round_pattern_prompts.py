"""Grouped MainWindow tool prompt workflows."""

import os
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox
from omacad.model.timeline import (
    ExtrudeFeature, SplitBodyFeature, ShellFeature, MoveFeature
)
from omacad.ui.dialogs import (
    RoundEdgesDialog, PatternDialog, OffsetPlaneDialog,
    SketchPlaneDialog, ExtrudeDialog, BoxDialog, CylinderDialog, PrismDialog,
    SphereDialog, CombineDialog, SplitBodyDialog, ShellDialog, MoveBodyDialog,
    ThreadDialog
)
from omacad.ui.canvas_dialog import CanvasEditorDialog
from omacad.ui.controllers.prompt_guards import leaves_sketch


class RoundPatternPromptsMixin:
    """RoundPattern prompt workflows for MainWindow."""

    def _connect_debounced_preview(self, dlg, preview_fn, interval_ms: int = 50, throttle: bool = False):
        """Connects `dlg.changed` to `preview_fn` via a single-shot QTimer (debounced) while running `preview_fn`
        in interactive quality mode. Throttling keeps previews updating during continuous dragging."""
        from omacad.model import quality
        timer = QTimer(dlg)
        timer.setSingleShot(True)
        timer.setInterval(interval_ms)

        def _fire():
            prev = quality.is_interactive_mode()
            quality.set_interactive_mode(True)
            try:
                preview_fn()
            finally:
                quality.set_interactive_mode(prev)

        timer.timeout.connect(_fire)
        if throttle:
            dlg.changed.connect(lambda: timer.start() if not timer.isActive() else None)
        else:
            dlg.changed.connect(timer.start)
        dlg.finished.connect(lambda *_: timer.stop())     # no preview after OK/Cancel
        return timer

    @leaves_sketch
    def prompt_round_edges(self, kind: str = "fillet", edges=None):
        """Fillet / Chamfer: click edges (outside or inside corners), type the size, OK."""
        if getattr(self, "_round_dlg", None) is not None:
            self._round_dlg.raise_()
            return
        if not any(b.edges for b in self.doc.bodies.values()):
            QMessageBox.information(self, "Fillet / Chamfer", "There are no straight edges between flat faces to round yet.")
            return
        self.doc.hide_used_sketches()  # finished sketches only get in the way of picking edges
        self.doc.notify_changed()
        dlg = RoundEdgesDialog(self.viewport, kind, embedded=True)
        self.dock(dlg)
        self._round_dlg = dlg
        self.viewport.begin_edge_pick()
        self.status_label.setText("Fillet/Chamfer: click an edge (joined edges follow, double-click = loop, Shift+double-click = loop on the other face, X or Alt = see-through, Ctrl+click = remove, Backspace = undo last, Ctrl+Backspace = clear). Esc cancels.")

        def update_arrow():
            edges = self.viewport.selected_edges
            if edges:
                e0 = edges[0]
                if hasattr(e0, "p0") and hasattr(e0, "p1"):
                    mid = (np.asarray(e0.p0) + np.asarray(e0.p1)) * 0.5
                    d1 = getattr(e0, "d1", None)
                    d2 = getattr(e0, "d2", None)
                    if d1 is not None and d2 is not None:
                        # For a convex edge, d1 + d2 points into the material (cutting direction)
                        axis = np.asarray(d1) + np.asarray(d2)
                        if not getattr(e0, "convex", True):
                            axis = -axis  # for inside corner, cut/fill bisector
                        n_axis = np.linalg.norm(axis)
                        axis = axis / n_axis if n_axis > 1e-6 else np.array([0.0, 0.0, 1.0])
                    else:
                        axis = np.array([0.0, 0.0, 1.0])
                elif hasattr(e0, "center") and hasattr(e0, "radius"):
                    # Circular edge: pick a point on the circle towards the camera or top
                    u, v_ = e0._basis() if hasattr(e0, "_basis") else (np.array([1., 0., 0.]), np.array([0., 1., 0.]))
                    mid = np.asarray(e0.center) + u * float(e0.radius)
                    # Bisector into the cut: radial inward plus wall inward
                    rad_inward = -u if e0.s1 < 0 else u
                    wall_inward = -np.asarray(e0.axis) * e0.s2
                    axis = rad_inward + wall_inward
                    n_axis = np.linalg.norm(axis)
                    axis = axis / n_axis if n_axis > 1e-6 else np.array([0.0, 0.0, 1.0])
                elif hasattr(e0, "c"):
                    mid = np.asarray(e0.c)
                    axis = np.asarray(getattr(e0, "n", [0.0, 0.0, 1.0]))
                elif hasattr(e0, "pts") and len(e0.pts):
                    mid = np.mean(e0.pts, axis=0)
                    axis = np.asarray(getattr(e0, "n", [0.0, 0.0, 1.0]))
                else:
                    mid = np.array([0.0, 0.0, 0.0])
                    axis = np.array([0.0, 0.0, 1.0])
                if dlg.spn_size.value() < 0:
                    axis = -axis
                self.viewport.set_extrude_handle(mid, axis, max(0.5, abs(dlg.spn_size.value())), color=(0.10, 0.75, 1.0))
            else:
                self.viewport.clear_extrude_handle()

        def preview():
            from omacad.model.timeline import FilletFeature
            from omacad.model.features.base import Body
            edges = self.viewport.selected_edges
            dlg.set_count(len(edges))
            if not edges:
                self.viewport.set_display_override(None)
                update_arrow()
                return
            # Like Fusion: run the real step on copies of the bodies and draw the finished result in their place
            # (the originals keep their edges, so picking goes on working).
            tmp_bodies = {}
            for bid, b in self.doc.bodies.items():
                t = Body(bid, b.name, b.manifold, edges=list(b.edges))
                t.update_render_mesh = lambda: None
                tmp_bodies[bid] = t

            class _TmpDoc:
                bodies = tmp_bodies

            v = dlg.values()
            tmp = FilletFeature("preview", "preview", [e.ref() for e in edges], v["size"], v["kind"],
                                v["chamfer_type"], v["size2"], v["angle"], v["flip"])
            try:
                tmp.execute(_TmpDoc)
            except Exception as ex:
                self.viewport.set_display_override(None)
                self.status_label.setText(f"Fillet/Chamfer: {ex or 'these edges cannot be rounded with that size.'}")
                update_arrow()
                return
            changed = {bid: t.manifold for bid, t in tmp_bodies.items()
                       if t.manifold is not self.doc.bodies[bid].manifold}
            self.viewport.set_display_override(changed)
            if tmp.skipped:
                self.status_label.setText(f"Fillet/Chamfer: {tmp.skipped} edge(s) cannot be rounded with that size.")
            update_arrow()

        def on_handle_drag(val: float):
            sign = -1.0 if dlg.kind() == "fillet" and dlg.spn_size.value() < 0 else 1.0
            v = sign * max(0.2, abs(val))
            dlg.spn_size.setValue(round(v, 2))

        def on_cancel_pick():
            dlg.reject()

        def on_finished(result):
            self.viewport.edges_selection_changed.disconnect(preview)
            self.viewport.edge_pick_cancelled.disconnect(on_cancel_pick)
            try:
                self.viewport.extrude_handle_dragged.disconnect(on_handle_drag)
            except (RuntimeError, TypeError):
                pass
            self.viewport.clear_extrude_handle()
            self.viewport.set_display_override(None)
            self.viewport.edge_tangent_chain = True
            edges = [e.ref() for e in self.viewport.selected_edges]
            self._round_dlg = None
            dlg.deleteLater()
            self.inspector.undock_tool()
            self.viewport.end_edge_pick()
            self.viewport.set_preview(None)
            if result and edges:
                v = dlg.values()
                spin = v.pop("size")
                feat = self.doc.add_fillet(edges, spin, v.pop("kind"), exprs=dlg.get_expressions(), **v)
                note = f" ({feat.skipped} edge(s) could not be rounded)" if feat.skipped else ""
                self.status_label.setText(f"{feat.name}: {len(edges)} edge(s), {spin:g} mm.{note}")
            elif result:
                self.status_label.setText("No edges were selected.")

        def on_chain(on: bool):
            self.viewport.edge_tangent_chain = on

        dlg.tangent_chain_toggled.connect(on_chain)
        self.viewport.edges_selection_changed.connect(preview)
        self.viewport.edge_pick_cancelled.connect(on_cancel_pick)
        self.viewport.extrude_handle_dragged.connect(on_handle_drag)
        self._connect_debounced_preview(dlg, preview)
        dlg.finished.connect(on_finished)
        dlg.show()
        if edges:   # started from a right-click on an edge or face
            self.viewport.selected_edges = list(edges)
            self.viewport.edges_selection_changed.emit()

    @leaves_sketch
    def prompt_offset_face(self, face=None):
        """Offset Face: move flat faces, or change the radius of holes and pins (tolerances for threads and fits)."""
        from omacad.model.features.offset_face import OffsetFaceFeature, plane_face_ref
        from omacad.ui.dialogs import OffsetFaceDialog
        if not self.doc.bodies:
            QMessageBox.information(self, "Offset Face", "Create a 3D body first.")
            return
        if self.inspector.current_tool_dlg is not None:
            return
        dlg = OffsetFaceDialog(self, embedded=True)
        self.dock(dlg)
        vp = self.viewport
        hidden = [None]    # the body whose preview replaces it

        def show_body():
            if hidden[0] in self.doc.bodies:
                self.doc.bodies[hidden[0]].visible = True
            hidden[0] = None

        def refresh_preview():
            vp.highlighted_faces = []
            dlg.set_note("")
            body = self.doc.bodies.get(dlg.body_id)
            if body is None or not dlg.faces:
                show_body()
                vp.shell_target_body_id = ""
                vp.set_preview(None)
                return
            thread = self.doc.thread_faces(dlg.faces)
            result, skipped = OffsetFaceFeature.compute(body.manifold, thread or dlg.faces, dlg.distance(), self.doc)
            body.visible = False
            hidden[0] = body.body_id
            vp.shell_target_body_id = body.body_id
            vp.set_preview(result, "new_body")
            if thread is not None:
                feat = next(f for f in self.doc.timeline.features if f.feature_id == thread[0]["thread_id"])
                d = dlg.distance()
                dlg.set_note(f"{feat.name}: only {body.name} changes, {abs(d):g} mm "
                             f"{'more material (tighter)' if d > 0 else 'more room (looser)'} on the thread.")
                self.status_label.setText(f"Offset Face: the thread of {feat.name} on {body.name}.")
            elif skipped:
                self.status_label.setText(f"Offset Face: {skipped} face(s) could not be moved by this distance.")

        def on_picked(ref, body_id):
            if not dlg.toggle(ref, body_id):
                self.status_label.setText("Offset Face: all faces must belong to the same body.")

        def on_finished(result):
            timer.stop()                    # a pending preview would hide the rebuilt body again
            vp.offset_face_picked.disconnect(on_picked)
            faces, body_id, dist = list(dlg.faces), dlg.body_id, dlg.distance()
            exprs = dlg.get_expressions()
            show_body()
            vp.shell_target_body_id = ""
            vp.end_plane_pick()
            vp.set_preview(None)
            self.inspector.undock_tool()
            dlg.deleteLater()
            if result and faces:
                feat = self.doc.add_offset_face(body_id, faces, dist, exprs=exprs)
                note = f" ({feat.skipped} could not be moved)" if getattr(feat, "skipped", 0) else ""
                self.status_label.setText(f"Offset Face: {len(faces)} face(s) moved {dist:g} mm{note}.")
            else:
                self.status_label.setText("Offset Face cancelled." if not result else "No faces were selected.")
            vp.update()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(60)
        timer.timeout.connect(refresh_preview)
        dlg.changed.connect(timer.start)
        dlg.finished.connect(on_finished)
        vp.offset_face_picked.connect(on_picked)
        vp.begin_plane_pick("offset_face")
        self.status_label.setText("Offset Face: click flat faces, holes or pins, type the distance, OK. Esc cancels.")
        if face is not None:
            dlg.toggle(plane_face_ref(face), face.body_id)
        dlg.show()

    @leaves_sketch
    def prompt_honeycomb(self):
        """Honeycomb: click flat and round faces of one body, choose the cells; live preview of the result."""
        from omacad.model.features.honeycomb import HoneycombFeature
        from omacad.ui.dialogs import HoneycombDialog
        if not self.doc.bodies:
            QMessageBox.information(self, "Honeycomb", "Create a 3D body first.")
            return
        if self.inspector.current_tool_dlg is not None:
            return
        dlg = HoneycombDialog(self, embedded=True)
        self.dock(dlg)
        vp = self.viewport
        hidden = [None]    # the body whose preview replaces it

        def show_body():
            if hidden[0] in self.doc.bodies:
                self.doc.bodies[hidden[0]].visible = True
            hidden[0] = None

        def refresh_preview():
            body = self.doc.bodies.get(dlg.body_id)
            if body is None or not dlg.faces:
                show_body()
                vp.shell_target_body_id = ""
                vp.set_preview(None)
                dlg.lbl_info.setText("")
                return
            result, cells, skipped = HoneycombFeature.compute(body.manifold, dlg.faces, dlg.params())
            body.visible = False
            hidden[0] = body.body_id
            vp.shell_target_body_id = body.body_id
            vp.set_preview(result, "new_body")
            note = f" {skipped} face(s) have no room for a cell." if skipped else ""
            dlg.lbl_info.setText(f"{cells} cells will be cut.{note}")

        def on_picked(ref, body_id):
            if ref.get("kind") not in ("plane", "cylinder"):
                self.status_label.setText("Honeycomb: only flat and cylindrical faces can take a honeycomb.")
            elif not dlg.toggle(ref, body_id):
                self.status_label.setText("Honeycomb: all faces must belong to the same body.")

        def on_finished(result):
            timer.stop()
            vp.offset_face_picked.disconnect(on_picked)
            faces, body_id, params, exprs = list(dlg.faces), dlg.body_id, dlg.params(), dlg.get_expressions()
            show_body()
            vp.shell_target_body_id = ""
            vp.end_plane_pick()
            vp.set_preview(None)
            self.inspector.undock_tool()
            dlg.deleteLater()
            if result and faces:
                feat = self.doc.add_honeycomb(body_id, faces, exprs=exprs, **params)
                self.status_label.setText(f"Honeycomb: {feat.cells} cells cut in {len(faces)} face(s).")
            else:
                self.status_label.setText("Honeycomb cancelled." if not result else "No faces were selected.")
            vp.update()

        timer = self._connect_debounced_preview(dlg, refresh_preview, interval_ms=80)
        dlg.finished.connect(on_finished)
        vp.offset_face_picked.connect(on_picked)
        vp.begin_plane_pick("offset_face")   # the same face picking as Offset Face: flat faces and cylinders light up
        self.status_label.setText("Honeycomb: click flat or round faces, choose shape and sizes, OK. Esc cancels.")
        dlg.show()

    @leaves_sketch
    def prompt_pattern(self, kind=None):
        """Copy what some steps did: evenly spaced, mirrored around the body, or around an axis."""
        from omacad.model.timeline import PatternFeature
        existing = getattr(self, "_pattern_dlg", None)
        if existing is not None:
            if kind in existing.KINDS:
                existing.cmb_kind.setCurrentIndex(existing.KINDS.index(kind))
            existing.raise_()
            return
        if not any(f.feature_type != "pattern" for f in self.doc.timeline.features):
            QMessageBox.information(self, "Pattern / Mirror", "Make something first (for example a hole), then copy it.")
            return
        self.doc.timeline.recompute(self.doc)  # fresh before/after states of every step
        dlg = PatternDialog(self.doc, self)
        self._pattern_dlg = dlg
        if kind in dlg.KINDS:
            dlg.cmb_kind.setCurrentIndex(dlg.KINDS.index(kind))
        if kind == "circular":
            dlg.setWindowTitle("Circular Feature Pattern")
            dlg.spn_count1.setValue(12)
        dlg.bind_axis_picker(self.viewport)
        dlg.bind_timeline(self.timeline_bar)

        def preview():
            ids = dlg.source_ids()
            if not ids:
                dlg.lbl_info.setText("Tick the steps to copy (for example the hole's sketch, cut and chamfer).")
                self.viewport.set_preview(None)
                return
            if dlg.kind() == "circular" and dlg.cmb_rotation.currentIndex() == 3 and dlg.picked_direction is None:
                dlg.lbl_info.setText("Pick a circular edge or cylinder for the rotation axis.")
                self.viewport.set_preview(None)
                return
            feat = PatternFeature("tmp", "tmp", ids, dlg.kind(), **dlg.get_params())
            solid, op, extra, copies = None, "cut", None, 0
            for bid in list(self.doc.bodies):
                res = feat.compute(self.doc, bid)
                if res is None:
                    continue
                rem, add = res
                copies = feat.copies
                solid, op = (rem, "cut") if rem is not None else (add, "join")
                extra = add if rem is not None else None
                break
            info = f"{copies} copies will be made." if solid is not None \
                else "Nothing to copy with these settings (the chosen steps changed nothing, or it is already symmetric)."
            used = getattr(feat, "margin_used", None)
            if dlg.kind() == "fill" and used is not None and used < dlg.spn_margin.value() - 1e-2:
                info += f" Margin held to {used:.1f} mm, the original's own distance to the edge."
            dlg.lbl_info.setText(info)
            self.viewport.set_preview(solid, op, extra=extra, extra_op="join")

        def on_step_clicked(point):
            """Click on the thing to copy: tick the step that made that surface (and its sketch)."""
            idx = self.doc.step_at_point(point)
            if idx is None:
                self.status_label.setText("Pattern: no step claims that spot. Tick the steps in the list instead.")
                return
            feat = self.doc.timeline.features[idx]
            wanted = {feat.feature_id}
            sk_id = getattr(feat, "sketch_id", None)
            wanted |= {f.feature_id for f in self.doc.timeline.features if f.feature_type == "sketch" and sk_id and f.feature_id == sk_id}
            items = [dlg.lst.item(i) for i in range(dlg.lst.count())]
            main_item = next((it for it in items if it.data(Qt.ItemDataRole.UserRole) == feat.feature_id), None)
            state = Qt.CheckState.Unchecked if main_item is not None and main_item.checkState() == Qt.CheckState.Checked \
                else Qt.CheckState.Checked
            for item in items:
                if item.data(Qt.ItemDataRole.UserRole) in wanted:
                    item.setCheckState(state)
            self.status_label.setText(f"Pattern: {feat.name} is {'no longer' if state == Qt.CheckState.Unchecked else 'now'} part of the copy "
                                      "(click it again to toggle).")

        timer = self._connect_debounced_preview(dlg, preview)
        self.dock(dlg)
        self.viewport.pick_step_mode = True
        self.viewport.step_point_clicked.connect(on_step_clicked)

        self.status_label.setText("Circular Pattern: choose the rib and its fillet in the timeline or list; set the axis and total quantity."
                                  if kind == "circular" else
                                  "Pattern / Mirror: click features in the timeline or 3D view, or tick steps in the list.")
        preview()

        def on_finished(ok):
            timer.stop()
            self._pattern_dlg = None
            self.viewport.pick_step_mode = False
            try:
                self.viewport.step_point_clicked.disconnect(on_step_clicked)
            except Exception:
                pass
            self.viewport.set_preview(None)
            self.inspector.undock_tool()
            if ok and dlg.source_ids():
                feat = self.doc.add_pattern(dlg.source_ids(), dlg.kind(), exprs=dlg.get_expressions(), **dlg.get_params())
                self.status_label.setText(f"{feat.name}: {feat.copies} copies.")

        dlg.finished.connect(on_finished)
        dlg.show()
