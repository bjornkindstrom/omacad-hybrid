"""Grouped MainWindow tool prompt workflows."""

import os
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox, QColorDialog, QPushButton, QDialogButtonBox
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


class BodyPromptsMixin:
    """Body prompt workflows for MainWindow."""

    @leaves_sketch
    def prompt_combine(self):
        if len(self.doc.bodies) < 2:
            QMessageBox.information(
                self, "Combine", "You need at least 2 bodies in the document to perform a boolean combine!"
            )
            return

        selected_id = self.doc.selected_body_ids[0] if self.doc.selected_body_ids else ""
        dlg = CombineDialog(self.doc, self, preselected_target_id=selected_id or None)
        self.dock(dlg)

        vp = self.viewport
        hidden = {}     # body id -> visibility before the preview hid it

        def restore_visibility():
            for bid, vis in hidden.items():
                if bid in self.doc.bodies:
                    self.doc.bodies[bid].visible = vis
            hidden.clear()

        def refresh_preview():
            """Shows the result in place of the target once it is chosen; the tool stays visible so it can be clicked."""
            from omacad.model.kernel import CadKernel
            restore_visibility()
            target_id, tool_id, op, _ = dlg.get_values()
            if not target_id or not tool_id or dlg.picking_target():
                vp.set_preview(None)
                vp.update()
                return
            hidden[target_id] = self.doc.bodies[target_id].visible
            self.doc.bodies[target_id].visible = False
            vp.set_preview(CadKernel.boolean_op(self.doc.bodies[target_id].manifold,
                                                self.doc.bodies[tool_id].manifold, op), "new_body")
            vp.update()

        def on_body_clicked(bid: str):
            dlg.select_body(bid)

        vp.body_clicked.connect(on_body_clicked)
        dlg.changed.connect(refresh_preview)
        refresh_preview()

        def on_finished(result):
            try:
                vp.body_clicked.disconnect(on_body_clicked)
            except (RuntimeError, TypeError):
                pass
            restore_visibility()
            vp.set_preview(None)
            self.inspector.undock_tool()
            if result:
                target_id, tool_id, op, keep = dlg.get_values()
                if target_id and tool_id:
                    self.doc.combine_bodies(target_id, tool_id, op, keep)       # one undo step
                    self.status_label.setText(f"Combined bodies with operation: {op}.")

        dlg.finished.connect(on_finished)
        dlg.show()

    @leaves_sketch
    def prompt_split_body(self, target_body_id: str = "", plane_id: str = ""):
        if not self.doc.bodies:
            QMessageBox.information(
                self, "Split Body", "No bodies found to split. Create a 3D body first!"
            )
            return

        selected_id = target_body_id or (self.doc.selected_body_ids[0] if self.doc.selected_body_ids else "")
        dlg = SplitBodyDialog(
            self.doc, self,
            preselected_body_id=selected_id or None,
            preselected_plane_id=plane_id or None,
        )
        self.dock(dlg)

        def on_body_clicked(bid: str):
            dlg.select_body(bid)

        self.viewport.body_clicked.connect(on_body_clicked)
        self.viewport.plane_clicked.connect(dlg.select_plane)     # click a plane in the view to split with it

        def on_finished(result):
            self.viewport.body_clicked.disconnect(on_body_clicked)
            self.viewport.plane_clicked.disconnect(dlg.select_plane)
            self.inspector.undock_tool()
            if result:
                b_id, p_id = dlg.get_values()
                if b_id and p_id:
                    feat = self.doc.split_body(b_id, p_id)
                    if feat:
                        target = self.doc.bodies.get(b_id)
                        new_body = self.doc.bodies.get(f"body_{feat.feature_id}")
                        t_name = target.name if target else b_id
                        n_name = new_body.name if new_body else "Split"
                        self.status_label.setText(f"Split body {t_name} into {t_name} and {n_name}.")
                        self.viewport.update()

        dlg.finished.connect(on_finished)
        dlg.show()

    @leaves_sketch
    def prompt_shell(self, target_body_id: str = ""):
        """Shell: hollow out a 3D solid body with specified wall thickness and optional open faces."""
        if not self.doc.bodies:
            QMessageBox.information(self, "Shell", "Create a 3D body first before shelling!")
            return

        selected_id = target_body_id or (self.doc.selected_body_ids[0] if self.doc.selected_body_ids else "")
        dlg = ShellDialog(self.doc, self, preselected_body_id=selected_id or None)
        self.dock(dlg)
        self.doc.hide_used_sketches()

        current_hidden_id = [None]

        def refresh_preview():
            bid, thickness, open_faces = dlg.get_values()
            if not bid or bid not in self.doc.bodies or thickness <= 0:
                if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                    self.doc.bodies[current_hidden_id[0]].visible = True
                    current_hidden_id[0] = None
                self.viewport.set_preview(None)
                return

            if current_hidden_id[0] and current_hidden_id[0] != bid and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True

            body = self.doc.bodies[bid]
            body.visible = False
            current_hidden_id[0] = bid
            switched = self.viewport.shell_target_body_id != bid
            self.viewport.shell_target_body_id = bid
            if switched and dlg.open_faces:   # open faces belong to the previous body
                dlg.clear_faces()
                return

            shelled = ShellFeature.shell_body(self.doc, bid, self.doc.timeline.marker_index, body.manifold, thickness,
                                              dlg.direction(), dlg.spn_thickness2.value(), open_faces)
            if shelled is not None:
                self.viewport.set_preview(shelled, "new_body")
            else:
                self.viewport.set_preview(body.manifold, "new_body")

        def on_face_picked(plane):
            if getattr(plane, "face", None):
                dlg.toggle_face(plane.face)
                self.viewport.highlighted_faces = [f["_face"] for f in dlg.open_faces if "_face" in f]
                self.viewport.update()

        self.viewport.shell_face_picked.connect(on_face_picked)
        self.viewport.begin_plane_pick("shell_face")
        self.status_label.setText("Shell: choose the body and the wall thickness. Click faces in 3D to leave them open.")

        def cleanup():
            try:
                self.viewport.shell_face_picked.disconnect(on_face_picked)
            except (RuntimeError, TypeError):
                pass
            try:
                self.viewport.body_clicked.disconnect(dlg.select_body)
            except (RuntimeError, TypeError):
                pass
            self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True
                current_hidden_id[0] = None
            self.inspector.undock_tool()

        def on_finished(result):
            timer.stop()                    # a pending preview would hide the rebuilt body again
            b_id, thickness, open_faces = dlg.get_values()
            cleanup()
            if result and b_id and thickness > 0:
                feat = self.doc.add_shell(b_id, thickness, open_faces, exprs=dlg.get_expressions(),
                                          direction=dlg.direction(), thickness2=dlg.spn_thickness2.value())
                if feat:
                    body = self.doc.bodies.get(b_id)
                    b_name = body.name if body else b_id
                    n_open = len(open_faces)
                    self.status_label.setText(f"Shell created on {b_name}: thickness {thickness:g} mm ({n_open} open faces).")
                    self.viewport.update()
            else:
                self.status_label.setText("Shell cancelled.")
                self.viewport.update()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(75)
        timer.timeout.connect(refresh_preview)

        dlg.changed.connect(lambda: timer.start())
        dlg.finished.connect(on_finished)
        self.viewport.body_clicked.connect(dlg.select_body)
        refresh_preview()
        dlg.show()

    @leaves_sketch
    def prompt_move_body(self, target_body_id: str = ""):
        """Move / Rotate: Translates and rotates a 3D solid body parametrically with interactive 3D gizmo."""
        if not self.doc.bodies:
            QMessageBox.information(self, "Move Body", "There are no bodies to move. Create a 3D body first!")
            return

        selected_id = target_body_id or (next(iter(self.doc.selected_body_ids)) if self.doc.selected_body_ids else "")
        if not selected_id or selected_id not in self.doc.bodies:
            selected_id = next(iter(self.doc.bodies.keys()))

        dlg = MoveBodyDialog(self.doc, self, preselected_body_id=selected_id)
        self.dock(dlg)

        current_hidden_id = [None]
        drag_state = {
            "dragging": False,
            "start_val": 0.0,
            "start_axis_val": 0.0,
        }

        def get_body_center(body):
            if body.render_mesh is not None and len(body.render_mesh.vertices) > 0:
                return (np.asarray(body.render_mesh.bounds_min, dtype=float) + np.asarray(body.render_mesh.bounds_max, dtype=float)) * 0.5
            pts = body.manifold.to_mesh().vert_properties[:, :3]
            if len(pts):
                return (pts.min(axis=0) + pts.max(axis=0)) * 0.5
            return np.array([0.0, 0.0, 0.0])

        def move_args(body, vals):
            """(d, r, pivot, from, to) of the dialog's values for MoveFeature.transform / transform_point."""
            from omacad.model.features.transform import MoveFeature
            _, dx, dy, dz, rx, ry, rz, pivot, _ = vals
            frm, to = (MoveFeature.resolve_point(self.doc, p) for p in dlg.get_points())
            piv = np.zeros(3) if pivot == "origin" else (frm if pivot == "point" and frm is not None else get_body_center(body))
            return (dx, dy, dz), (rx, ry, rz), piv, frm, to

        def update_handle():
            from omacad.model.features.transform import MoveFeature
            if dlg.btn_points.isChecked() or dlg.btn_lay.isChecked() or dlg.btn_f2f.isChecked():
                self.viewport.clear_move_gizmo()
                return
            vals = dlg.get_values()
            bid = vals[0]
            if not bid or bid not in self.doc.bodies:
                self.viewport.clear_move_gizmo()
                return
            d, r, piv, frm, to = move_args(self.doc.bodies[bid], vals)
            self.viewport.set_move_gizmo(MoveFeature.transform_point(piv, d, r, piv, frm, to))
            if self.viewport.move_gizmo:
                self.viewport.move_gizmo["active_axis"] = dlg.active_axis

        def refresh_preview():
            bid, dx, dy, dz, rx, ry, rz, pivot, _ = dlg.get_values()
            if not bid or bid not in self.doc.bodies:
                if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                    self.doc.bodies[current_hidden_id[0]].visible = True
                    current_hidden_id[0] = None
                self.viewport.set_preview(None)
                self.viewport.clear_move_gizmo()
                return

            if current_hidden_id[0] and current_hidden_id[0] != bid and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True

            from omacad.model.features.transform import MoveFeature
            body = self.doc.bodies[bid]
            # Copy mode previews the moved duplicate alongside the unchanged source body.
            body.visible = dlg.chk_copy_body.isChecked() or dlg.btn_f2f.isChecked() or dlg.btn_lay.isChecked()
            current_hidden_id[0] = bid
            self.viewport.point_pick_hidden_ok = bid      # its points can still be picked while the preview shows
            m = MoveFeature.transform(body.manifold, *move_args(body, dlg.get_values()))
            self.viewport.set_preview(m, "new_body")
            if not drag_state["dragging"]:
                update_handle()

        def on_gizmo_drag(axis: str, delta: float):
            if not drag_state["dragging"]:
                drag_state["dragging"] = True
                spn_map = {
                    "X": dlg.spn_dx, "Y": dlg.spn_dy, "Z": dlg.spn_dz,
                    "RX": dlg.spn_rx, "RY": dlg.spn_ry, "RZ": dlg.spn_rz
                }
                spn = spn_map.get(axis, dlg.spn_dx)
                drag_state["start_axis_val"] = spn.value()

            is_rot = axis in ("RX", "RY", "RZ")
            new_val = drag_state["start_axis_val"] + delta
            if is_rot:
                new_val = round(new_val, 1)   # the viewport already snapped delta to the ring ticks when outside the ring
            else:
                new_val = round(new_val, 2)
            dlg.set_active_axis_value(new_val)

        committed = []      # Move steps applied while the panel is open (each its own undo step)

        def pending() -> bool:
            _, dx, dy, dz, rx, ry, rz, _, _ = dlg.get_values()
            frm, to = dlg.get_points()
            return any(abs(v) > 1e-9 for v in (dx, dy, dz, rx, ry, rz)) or (frm is not None and to is not None)

        def apply_pending():
            """Make the move so far a real step at once (everything after it rebuilds), and start the next one from
            where the body now is: moving in several goes needs no OK in between."""
            bid, dx, dy, dz, rx, ry, rz, pivot, exprs = dlg.get_values()
            if not pending() or not bid or bid not in self.doc.bodies:
                return
            frm, to = dlg.get_points()
            copy = dlg.chk_copy_body.isChecked()
            feat = self.doc.move_body(bid, dx, dy, dz, rx, ry, rz, pivot=pivot, exprs=exprs,
                                      from_point=frm, to_point=to, copy_body=copy)
            if feat is None:
                return
            committed.append(feat.feature_id)
            new_id = f"body_{feat.feature_id}" if feat.copy_body else feat.target_body_id   # a copy has its own steps
            if copy and new_id != bid and new_id in self.doc.bodies:   # keep moving the copy just made
                dlg.add_body(new_id, self.doc.bodies[new_id].name)
                dlg.chk_copy_body.setChecked(False)
                dlg.select_body(new_id)
            dlg.reset_motion(keep_from_point=frm if to is None else None)
            current_hidden_id[0] = None
            refresh_preview()
            self.status_label.setText(f"Moved {self.doc.bodies[dlg.get_values()[0]].name}. Keep moving, or OK to finish "
                                      "(each move is one undo step).")

        def on_drag_finished():
            drag_state["dragging"] = False
            apply_pending()
            update_handle()

        def on_axis_changed(axis: str):
            drag_state["dragging"] = False
            if self.viewport.move_gizmo:
                self.viewport.move_gizmo["active_axis"] = axis
                self.viewport.update()

        def on_gizmo_axis_selected(axis: str):
            dlg.set_active_axis(axis)

        f2f = {"src": None, "dst": None, "moving_id": None}  # picked in either order; body id stays locked

        def apply_face_to_face():
            from omacad.model.geometry import face_centroid, face_to_face_values
            src, dst = f2f["src"], f2f["dst"]
            if src is None or dst is None or src.body_id not in self.doc.bodies:
                return
            dst_face = getattr(dst, "face", None)
            dst_point = face_centroid(dst_face) if dst_face is not None else np.asarray(dst.origin, dtype=float)
            vals = face_to_face_values(
                src.normal, face_centroid(src), dst.normal, dst_point, get_body_center(self.doc.bodies[src.body_id]),
                about_centre=dlg.cmb_pivot.currentData() == "center", mode=dlg.cmb_f2f.currentData(),
                centre_on=dlg.chk_f2f_centre.isChecked())
            for spn, v in zip((dlg.spn_dx, dlg.spn_dy, dlg.spn_dz, dlg.spn_rx, dlg.spn_ry, dlg.spn_rz), vals):
                spn.setValue(round(v, 4))

        def on_face_to_face_toggled(on):
            if on:
                apply_pending()             # picks are made on the body where it is now
            bid = dlg.get_values()[0]
            if bid in self.doc.bodies:
                # The source face must remain visible and pickable while the moved preview is shown.
                self.doc.bodies[bid].visible = bool(on or dlg.chk_copy_body.isChecked())
                self.viewport.update()
            if on:
                f2f["src"] = f2f["dst"] = None
                f2f["moving_id"] = dlg.get_values()[0]
                self.viewport.clear_move_gizmo()
                self.status_label.setText("Face to face: click the moving face or the target face first.")
            else:
                refresh_preview()

        def on_lay_toggled(on):
            if on:
                apply_pending()
            bid = dlg.get_values()[0]
            if on:
                if dlg.btn_f2f.isChecked():
                    dlg.btn_f2f.setChecked(False)
                if dlg.btn_points.isChecked():
                    dlg.btn_points.setChecked(False)
                if bid in self.doc.bodies:
                    self.doc.bodies[bid].visible = True
                self.viewport.clear_move_gizmo()
                self.viewport.update()
                self.status_label.setText("Lay on ground: click a face on the body to place flat on XY.")
            else:
                refresh_preview()

        def on_face_picked(plane):
            face = getattr(plane, "face", None)
            if dlg.btn_f2f.isChecked():
                moving_id = f2f["moving_id"]
                picked_body = getattr(face, "body_id", None)
                if picked_body == moving_id:
                    f2f["src"] = face
                    dlg.select_body(picked_body)
                elif f2f["src"] is None:
                    f2f["dst"] = plane
                else:
                    f2f["dst"] = plane
                if f2f["src"] is not None and f2f["dst"] is not None:
                    dlg.btn_f2f.setChecked(False)
                    apply_face_to_face()
                    self.status_label.setText("Face to face: done. Change the direction or the numbers, then OK.")
                elif f2f["src"] is None:
                    self.status_label.setText("Face to face: target saved. Now click a face on the body that should move.")
                else:
                    self.status_label.setText("Face to face: moving face saved. Now click its target face or plane.")
                return
            if face is not None and hasattr(face, "body_id"):
                dlg.select_body(face.body_id)
                if dlg.btn_lay.isChecked() and face.body_id in self.doc.bodies:
                    from omacad.model.geometry import lay_on_ground_values
                    about_centre = dlg.cmb_pivot.currentData() == "center"
                    vals = lay_on_ground_values(face.normal, face.origin, get_body_center(self.doc.bodies[face.body_id]), about_centre)
                    for spn, v in zip((dlg.spn_dx, dlg.spn_dy, dlg.spn_dz, dlg.spn_rx, dlg.spn_ry, dlg.spn_rz), vals):
                        spn.setValue(round(v, 4))
                    dlg.btn_lay.setChecked(False)
                    self.status_label.setText(f"{self.doc.bodies[face.body_id].name}: face laid flat on XY. Adjust the numbers or press OK.")

        def on_points_toggled(on):
            if on:
                apply_pending()
                dlg.set_points(None, None)
                self.viewport.clear_move_gizmo()
                self.viewport.begin_point_pick()
                self.status_label.setText("Point to point: click a point on the body (an edge end, or move near a rounding "
                                          "for its hidden corner). It becomes the rotation pivot.")
            else:
                self.viewport.end_point_pick()
                update_handle()

        def on_point_picked(p):
            frm, _ = dlg.get_points()
            if p is None:                                   # Esc: keep what was picked so far
                dlg.btn_points.setChecked(False)
                self.status_label.setText("Point picking ended." if frm else "Point picking cancelled.")
                return
            if frm is None:
                if p["body"] is None:
                    self.status_label.setText("Point to point: first click a point on the body that should move.")
                    return
                dlg.select_body(p["body"])
                dlg.set_points(p, None)
                self.status_label.setText("Point to point: now click where that point should go (a point on another body "
                                          "or the origin), or press Esc to keep it just as the rotation pivot.")
                return
            if p["body"] == frm["body"]:
                self.status_label.setText("Point to point: the target must be on another body or the origin.")
                return
            dlg.set_points(frm, p)
            dlg.btn_points.setChecked(False)
            self.status_label.setText("Point to point: done. Rotate about the point or add an offset, then OK.")

        def cleanup():
            self.viewport.end_point_pick()
            self.viewport.point_pick_hidden_ok = None
            for sig, slot in (
                (self.viewport.point_picked, on_point_picked),
                (self.viewport.move_body_picked, on_face_picked),
                (self.viewport.body_clicked, dlg.select_body),
                (self.viewport.move_gizmo_dragged, on_gizmo_drag),
                (self.viewport.move_gizmo_finished, on_drag_finished),
                (self.viewport.move_gizmo_axis_selected, on_gizmo_axis_selected),
            ):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            self.viewport.end_plane_pick()
            self.viewport.clear_move_gizmo()
            self.viewport.set_preview(None)
            if current_hidden_id[0] and current_hidden_id[0] in self.doc.bodies:
                self.doc.bodies[current_hidden_id[0]].visible = True
                current_hidden_id[0] = None
            self.inspector.undock_tool()

        def on_finished(result):
            bid, dx, dy, dz, rx, ry, rz, pivot, exprs = dlg.get_values()
            frm, to = dlg.get_points()
            has_pending = pending()
            cleanup()
            if not result and committed:    # Cancel / Esc drops only what is not applied yet; each applied move
                self.status_label.setText(  # is its own undo step, so nothing done here is lost by a stray Esc
                    f"Move closed: {len(committed)} move(s) kept (Ctrl+Z takes them back one by one).")
                self.viewport.update()
                return
            if result and not has_pending:
                self.status_label.setText(f"Move: {len(committed)} move(s) applied." if committed else "Move: nothing to move.")
                self.viewport.update()
                return
            if result and bid and bid in self.doc.bodies:
                copy = dlg.chk_copy_body.isChecked()
                feat = self.doc.move_body(bid, dx, dy, dz, rx, ry, rz, pivot=pivot, exprs=exprs,
                                          from_point=frm, to_point=to, copy_body=copy)
                if feat:
                    b_name = self.doc.bodies[bid].name if bid in self.doc.bodies else bid
                    action = "Copied and moved" if copy else "Moved"
                    self.status_label.setText(f"{action} {b_name}: dx={dx:g}, dy={dy:g}, dz={dz:g} mm, rx={rx:g}°, ry={ry:g}°, rz={rz:g}°.")
                    self.viewport.update()
            else:
                self.status_label.setText("Move cancelled.")
                self.viewport.update()

        self._connect_debounced_preview(dlg, refresh_preview, interval_ms=30)
        dlg.btn_f2f.toggled.connect(on_face_to_face_toggled)
        dlg.btn_lay.toggled.connect(on_lay_toggled)
        dlg.btn_points.toggled.connect(on_points_toggled)
        self.viewport.point_picked.connect(on_point_picked)
        dlg.f2f_changed.connect(apply_face_to_face)
        dlg.axis_changed.connect(on_axis_changed)
        dlg.finished.connect(on_finished)
        self.viewport.move_gizmo_dragged.connect(on_gizmo_drag)
        self.viewport.move_gizmo_finished.connect(on_drag_finished)
        self.viewport.move_gizmo_axis_selected.connect(on_gizmo_axis_selected)
        self.viewport.move_body_picked.connect(on_face_picked)
        self.viewport.body_clicked.connect(dlg.select_body)
        self.viewport.begin_plane_pick("move_body")
        self.status_label.setText("Move / Rotate: drag the 3D arrows to move, or drag the circular rings to rotate (Fusion 360 style).")

        refresh_preview()
        dlg.show()

    def prompt_body_color(self, body_id: str = ""):
        """Prompt to change the color of a body or reset to default uncolored."""
        if not body_id:
            if self.doc.selected_body_ids:
                body_id = self.doc.selected_body_ids[0]
            elif self.doc.bodies:
                body_id = next(iter(self.doc.bodies))
        if not body_id or body_id not in self.doc.bodies:
            return

        body = self.doc.bodies[body_id]
        body_name = body.name or body_id

        # Determine current color
        cur_rgba = getattr(self.doc, "body_colors", {}).get(body_id)
        if cur_rgba is None:
            initial = QColor(int(body.color[0] * 255), int(body.color[1] * 255), int(body.color[2] * 255))
        else:
            initial = QColor(int(cur_rgba[0] * 255), int(cur_rgba[1] * 255), int(cur_rgba[2] * 255))

        dlg = QColorDialog(initial, self)
        dlg.setWindowTitle(f"Färg / Appearance – {body_name}")
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)

        btn_reset = QPushButton("Återställ till ofärgad (Reset)")
        box = dlg.findChild(QDialogButtonBox)
        if box is not None:
            box.addButton(btn_reset, QDialogButtonBox.ButtonRole.ActionRole)
        elif dlg.layout() is not None:
            dlg.layout().addWidget(btn_reset)

        reset_clicked = [False]

        def on_reset():
            reset_clicked[0] = True
            dlg.accept()

        btn_reset.clicked.connect(on_reset)

        if dlg.exec():
            if reset_clicked[0]:
                self.doc.set_body_color(body_id, None)
                self.status_label.setText(f"Återställde {body_name} till ofärgad.")
            else:
                col = dlg.selectedColor()
                if col.isValid():
                    rgba = [col.redF(), col.greenF(), col.blueF(), 1.0]
                    self.doc.set_body_color(body_id, rgba)
                    self.status_label.setText(f"Ändrade färg på {body_name}.")
            self.viewport.update()

