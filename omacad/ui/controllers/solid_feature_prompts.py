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
from omacad.model.features.hole import HoleFeature


class SolidFeaturePromptsMixin:
    """SolidFeature prompt workflows for MainWindow."""

    @leaves_sketch
    def prompt_hole(self):
        if not self.doc.bodies:
            QMessageBox.information(self, "Hole", "Create or import a solid body first.")
            return
        from omacad.ui.dialogs import HoleDialog
        from omacad.model.features.base import Body
        dlg = HoleDialog(self.viewport, embedded=True)
        self.dock(dlg)
        points = []

        def pick_plane():
            self.viewport.end_hole_place()
            self.viewport.clear_hole_place()
            self.viewport.begin_plane_pick("hole_plane")
            self.status_label.setText("Hole: select a planar face or origin plane for hole placement.")

        def plane_picked(plane):
            points.clear()
            dlg.set_plane(plane)
            dlg.set_points(points)
            refresh_preview()
            self.viewport.begin_hole_place(plane)
            self.status_label.setText("Hole: click to place points on the selected plane. Esc pauses placement; select Place hole points to continue.")

        def start_placing():
            if dlg.plane is not None:
                self.viewport.begin_hole_place(dlg.plane, [p["origin"] for p in points])
                self.status_label.setText("Hole: click to place hole centers on the selected plane. Esc pauses placement.")

        def point_picked(position):
            p = np.asarray(position, dtype=float)
            n = np.asarray(dlg.plane.normal, dtype=float)
            if not any(np.linalg.norm(p - np.asarray(old["origin"])) < 1e-3 for old in points):
                points.append({"origin": p.tolist(), "normal": n.tolist()})
                dlg.set_points(points)
                self.viewport.hole_place_points = [q["origin"] for q in points]
                refresh_preview()

        def refresh_preview():
            if not points:
                self.viewport.set_display_override(None)
                return
            params = dlg.values()
            params["points"] = points
            feat = HoleFeature("preview", "preview", **params)
            preview_bodies = {}
            for bid, body in self.doc.bodies.items():
                if not body.visible:
                    continue
                clone = Body(bid, body.name, body.manifold)
                clone.update_render_mesh = lambda: None
                preview_bodies[bid] = clone

            class PreviewDoc:
                bodies = preview_bodies

            feat.execute(PreviewDoc)
            result = {bid: b.manifold for bid, b in preview_bodies.items()}
            self.viewport.set_display_override(result)

        def finished(result):
            if self.viewport.plane_pick_mode and self.viewport.plane_pick_purpose == "hole_plane":
                self.viewport.end_plane_pick()
            self.viewport.end_hole_place()
            self.viewport.plane_picked.disconnect(plane_picked)
            self.viewport.hole_point_picked.disconnect(point_picked)
            self.viewport.set_display_override(None)
            self.viewport.clear_hole_place()
            if result:
                if not points:
                    QMessageBox.information(self, "Hole", "Pick at least one point on a body face.")
                    self.prompt_hole()
                    return
                params = dlg.values()
                params["points"] = points
                self.doc.add_hole(**params, exprs=dlg.get_expressions())
            self.status_label.setText("Ready.")

        dlg.pick_requested.connect(pick_plane)
        dlg.place_requested.connect(start_placing)
        self._connect_debounced_preview(dlg, refresh_preview, interval_ms=50)
        self.viewport.plane_picked.connect(plane_picked)
        self.viewport.hole_point_picked.connect(point_picked)
        dlg.finished.connect(finished)

    @leaves_sketch
    def prompt_extrude(self, default_distance=None):
        if not self.doc.sketches:
            QMessageBox.information(
                self, "Extrude",
                "No sketches found. Create a sketch with a rectangle or circle first, then extrude!"
            )
            return

        if getattr(self, "_extrude_dlg", None) is not None:
            self._extrude_dlg.raise_()
            return

        dlg = ExtrudeDialog(self.doc, self.viewport, embedded=True)   # a small panel in the view, draggable
        dlg.place(self.viewport.size())
        if default_distance is not None:
            dlg.set_distance(default_distance)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._extrude_dlg = dlg

        def show_handle(s_id, p_idx, dist, direction, start_offset=0.0):
            """The arrow in the view: start at the profile's centre (shifted by start_offset), tip at the current distance."""
            from shapely.geometry import Polygon
            sk = self.doc.sketches.get(s_id)
            if sk is None or p_idx >= len(sk.profiles):
                return
            prof = sk.profiles[p_idx]
            c = Polygon(prof.exterior_pts, prof.interior_holes).representative_point()
            origin = np.asarray(sk.plane.uv_to_world(c.x, c.y), dtype=float) + np.asarray(sk.plane.normal, dtype=float) * float(start_offset)
            tip = dist / 2.0 if direction == "symmetric" else dist
            self.viewport.set_extrude_handle(origin, sk.plane.normal, tip, show_value=True,
                                             value_scale=2.0 if direction == "symmetric" else 1.0)

        def on_handle_dragged(t):
            direction = dlg.get_direction()[0]
            value = abs(t) * 2.0 if direction == "symmetric" else (max(t, 0.1) if direction == "two_sides" else t)
            dlg.spn_dist.setValue(value)

        def parts(s_id, p_idx):
            return ExtrudeFeature.selection_parts(self.doc, s_id, p_idx, self.doc.selected_extra)

        def refresh_preview():
            s_id, p_idx, dist, op = dlg.get_values()
            direction, dist2 = dlg.get_direction()
            start_offset = dlg.get_start_offset()
            solid = None
            if s_id is not None:
                extra, refs, holes = parts(s_id, p_idx)
                feat = ExtrudeFeature("preview", "preview", s_id, p_idx, dist, op, direction, dist2, extra_profiles=extra,
                                      extra_refs=refs, holes=holes, start_offset=start_offset, twist=dlg.get_twist())
                try:
                    solid = feat.build_solid(self.doc)
                    if op == "auto":
                        op = feat.resolve_operation(self.doc)
                        dlg.set_auto_result(op)
                except Exception:
                    solid = None
            self.viewport.set_preview(solid, op)
            if s_id is not None:
                show_handle(s_id, p_idx, dist, direction, start_offset)
            # Keep the viewport highlight in sync with the combo
            if s_id is not None and self.doc.selected_profile != (s_id, p_idx):
                self.doc.selected_profile = (s_id, p_idx)
                self.doc.selected_extra = []
                self.viewport.update()
            n = 1 + len(self.doc.selected_extra) if s_id is not None else 0
            self.status_label.setText(f"Extrude: {n} profile(s) selected. Click to choose, Shift+click to add or remove." if n
                                      else "Extrude: click a profile in the view (Shift+click for several).")

        def on_pick():
            if self.doc.selected_profile:
                dlg.select_profile(self.doc.selected_profile)
            refresh_preview()
            dlg.focus_primary()

        def on_pick_face():
            self.viewport.begin_plane_pick("extrude_target")
            self.status_label.setText("Extrude: click the face (or origin plane) to extrude up to (Esc to cancel).")

        def on_target_plane(plane):
            s_id, _, _, _ = dlg.get_values()
            if s_id is None:
                return
            sp = self.doc.sketches[s_id].plane
            n0, n1 = np.asarray(sp.normal, dtype=float), np.asarray(plane.normal, dtype=float)
            if abs(float(n0 @ n1)) < 0.999:
                self.status_label.setText("That face is not parallel to the sketch plane, so there is no single distance to it.")
            else:
                dist = float((np.asarray(plane.origin, dtype=float) - np.asarray(sp.origin, dtype=float)) @ n0) - dlg.get_start_offset()
                if abs(dist) < 1e-6:
                    self.status_label.setText("That face is at the extrusion start plane (distance 0).")
                else:
                    dlg.set_distance(dist)
                    self.status_label.setText(f"Extrude distance to the face: {dist:.3f} mm.")
            dlg.activateWindow()
            dlg.focus_primary()

        def on_finished(result):
            self.viewport.profile_picked.disconnect(on_pick)
            self.viewport.target_plane_picked.disconnect(on_target_plane)
            self.viewport.extrude_handle_dragged.disconnect(on_handle_dragged)
            self.viewport.clear_extrude_handle()
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self._extrude_dlg = None
            if result:
                s_id, p_idx, dist, op = dlg.get_values()
                if s_id is not None:
                    direction, dist2 = dlg.get_direction()
                    start_offset = dlg.get_start_offset()
                    extra, refs, holes = parts(s_id, p_idx)
                    self.doc.extrude_profile(s_id, p_idx, dist, op, direction=direction, distance2=dist2,
                                             extra_profiles=extra, extra_refs=refs, holes=holes,
                                             start_offset=start_offset, twist=dlg.get_twist())
                    self.doc.timeline.last_added.exprs = dlg.get_expressions()
                    op = self.doc.timeline.last_added.operation  # what Auto resolved to
                    self.doc.selected_profile = None
                    self.doc.selected_extra = []
                    self.viewport.zoom_fit()
                    self.status_label.setText(f"Extruded profile by {dist} mm ({op}).")

        self._connect_debounced_preview(dlg, refresh_preview)
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.extrude_handle_dragged.connect(on_handle_dragged)
        self.viewport.target_plane_picked.connect(on_target_plane)
        self.viewport.profile_picked.connect(on_pick)
        dlg.finished.connect(on_finished)
        dlg.show()
        refresh_preview()
        dlg.focus_primary()
        QTimer.singleShot(0, dlg, dlg.focus_primary)

    @leaves_sketch
    def prompt_revolve(self):
        """Revolve: profile (click it in the view), axis, angle, direction and operation, with live preview."""
        if not self.doc.sketches or not any(sk.profiles for sk in self.doc.sketches.values()):
            QMessageBox.information(self, "Revolve", "Draw a closed sketch profile first (and a construction line for the axis), then revolve it.")
            return
        if getattr(self, "_revolve_dlg", None) is not None:
            self._revolve_dlg.raise_()
            return
        from omacad.model.timeline import RevolveFeature
        from omacad.ui.dialogs import RevolveDialog
        dlg = RevolveDialog(self.doc, self.viewport, embedded=True)
        dlg.place(self.viewport.size())
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._revolve_dlg = dlg

        def extras(s_id):
            return [i for (sid, i) in self.doc.selected_extra if sid == s_id]

        def make(operation=None):
            s_id, p_idx = dlg.get_values()
            if s_id is None:
                return None
            return RevolveFeature("preview", "preview", s_id, p_idx, operation=operation or dlg.get_operation(), axis=dlg.get_axis(),
                                  angle=dlg.spn_angle.value(), direction=dlg.get_direction(), angle2=dlg.spn_angle2.value(),
                                  extra_profiles=extras(s_id))

        def refresh_preview():
            feat = make()
            solid, op = None, dlg.get_operation()
            dlg.lbl_info.setText("")
            if feat is not None:
                try:
                    solid = feat.build_solid(self.doc)
                    if op == "auto":
                        op = feat.resolve_operation(self.doc)
                        dlg.set_auto_result(op)
                except Exception:
                    solid = None
                dlg.lbl_info.setText(feat.problem)
                if self.doc.selected_profile != dlg.get_values():
                    self.doc.selected_profile = dlg.get_values()
                    self.doc.selected_extra = []
                    self.viewport.update()
            self.viewport.set_preview(solid, op)
            self.status_label.setText("Revolve: click a profile, pick the axis, set the angle." if feat is None else
                                      f"Revolve: {1 + len(self.doc.selected_extra)} profile(s). Enter = OK, Esc = cancel.")

        def on_pick():
            if self.doc.selected_profile:
                dlg.select_profile(self.doc.selected_profile)
            refresh_preview()

        def on_finished(result):
            self.viewport.profile_picked.disconnect(on_pick)
            self.viewport.set_preview(None)
            self._revolve_dlg = None
            if result:
                feat = make()
                if feat is not None:
                    new = self.doc.add_revolve(feat.sketch_id, feat.profile_idx, axis=feat.axis, angle=feat.angle, operation=feat.operation,
                                               direction=feat.direction, angle2=feat.angle2, extra_profiles=feat.extra_profiles,
                                               exprs=dlg.get_expressions())
                    self.doc.selected_profile = None
                    self.doc.selected_extra = []
                    self.viewport.zoom_fit()
                    self.status_label.setText(new.problem or f"{new.name}: {new.angle:g}° ({new.operation}).")
            self.viewport.update()

        self._connect_debounced_preview(dlg, refresh_preview)
        self.viewport.profile_picked.connect(on_pick)
        dlg.finished.connect(on_finished)
        dlg.show()
        refresh_preview()
