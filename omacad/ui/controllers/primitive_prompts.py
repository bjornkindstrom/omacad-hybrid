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


class PrimitivePromptsMixin:
    """Primitive prompt workflows for MainWindow."""

    @leaves_sketch
    def prompt_jar(self):
        """Jar with Lid: sizes with sliders and a live preview; OK adds the steps (one undo step)."""
        from omacad.model.jar import JarSpec, build_jar_silhouette, thread_tooth
        from omacad.ui.dialogs import JarDialog
        from omacad.ui.settings import get_settings
        if self.inspector.current_tool_dlg is not None:
            return
        dlg = JarDialog(self, JarSpec.from_dict(get_settings().get("jar_spec", {})), embedded=True)
        self.dock(dlg)
        vp = self.viewport

        def refresh_preview():
            spec = dlg.spec()
            tooth = thread_tooth(spec)
            problems = spec.problems(tooth)
            dlg.set_problems(spec.lid_wall(tooth), problems)
            if problems:
                vp.set_preview(None)
                return
            # The dialog only needs the overall envelope; full editable thread geometry is built on OK.
            vp.set_preview(build_jar_silhouette(spec), "new_body")

        def on_finished(result):
            from PySide6.QtWidgets import QApplication
            timer.stop()
            spec = dlg.spec()
            self.inspector.undock_tool()
            dlg.deleteLater()
            if result:
                # Keep the fast silhouette visible while the editable, full-quality history is built.
                self.status_label.setText("Building Jar with Lid…")
                self.progress_bar.setVisible(True)
                QApplication.processEvents()
                try:
                    self.doc.add_jar(spec)
                    get_settings().set("jar_spec", spec.to_dict())
                    self.status_label.setText(f"Jar with Lid: Ø{spec.diameter:g} × {spec.height:g} mm, thread tolerance {spec.tolerance:g} mm.")
                except Exception as exc:
                    self.status_label.setText(f"Could not build Jar with Lid: {exc}")
                finally:
                    self.progress_bar.setVisible(False)
                    vp.set_preview(None)
                    vp.update()
            else:
                vp.set_preview(None)
                self.status_label.setText("Jar with Lid cancelled.")
            vp.update()

        timer = self._connect_debounced_preview(dlg, refresh_preview, interval_ms=120)
        dlg.finished.connect(on_finished)
        self.status_label.setText("Jar with Lid: set the sizes (fields or sliders), OK. Esc cancels.")
        dlg.show()
        timer.start()

    @leaves_sketch
    def prompt_box(self):
        from omacad.model.features.primitives import BoxFeature
        dlg = BoxDialog(self)

        def refresh_preview():
            l, w, h, center, po, pn, pu, pv = dlg.get_values()
            smart = dlg.get_smart_params()
            feat = BoxFeature("preview_box", "Preview", l, w, h, center,
                              plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                              translation=getattr(dlg, "placement_offset", (0, 0, 0)), **smart)
            try:
                solid = feat.build_solid()
                dlg.lbl_problem.clear()
            except Exception as exc:
                from omacad import applog
                applog.log("ERROR", f"Box preview: {exc}")
                solid = None
                dlg.lbl_problem.setText(str(exc))
            self.viewport.set_preview(solid, "new_body")
            self.viewport.update()

        def on_pick_face():
            self.viewport.begin_plane_pick("primitive_face")
            self.status_label.setText("Box: Click the face or plane where the bottom should start (Esc to cancel).")

        def on_face_picked(plane):
            dlg.set_target_plane(plane)
            dlg.activateWindow()

        def on_finished(result):
            for sig, slot in (
                (dlg.pick_face_requested, on_pick_face),
                (self.viewport.primitive_face_picked, on_face_picked),
            ):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self.viewport.update()
            if result:
                l, w, h, center, po, pn, pu, pv = dlg.get_values()
                smart = dlg.get_smart_params()
                body = self.doc.add_box(l, w, h, center=center,
                                        plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                                        translation=getattr(dlg, "placement_offset", (0, 0, 0)), **smart)
                self.doc.timeline.last_added.exprs = dlg.get_expressions()
                self.viewport.zoom_fit()
                self.status_label.setText(f"Created {body.name} ({l}x{w}x{h} mm).")

        timer = self._connect_debounced_preview(dlg, refresh_preview, throttle=True)
        dlg.finished.connect(lambda _: timer.stop())
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.primitive_face_picked.connect(on_face_picked)
        dlg.finished.connect(on_finished)
        from omacad.ui.primitive_handles import attach_primitive_handles
        attach_primitive_handles(self.viewport, dlg, "box", refresh_preview)
        self.dock(dlg)
        refresh_preview()

    def prompt_prism(self):
        """Hexagon (any regular prism): the Cylinder flow with flat sides, sized across flats."""
        self.prompt_cylinder(prism=True)

    def prompt_cone(self):
        """Cone / frustum (Björn #46): the Cylinder flow with a top radius."""
        self.prompt_cylinder(cone=True)

    @leaves_sketch
    def prompt_cylinder(self, prism=False, cone=False):
        from omacad.model.features.primitives import ConeFeature, CylinderFeature, PrismFeature
        from omacad.ui.dialogs.primitives_dlg import ConeDialog
        dlg = PrismDialog(self) if prism else ConeDialog(self) if cone else CylinderDialog(self)
        label = "Prism" if prism else "Cone" if cone else "Cylinder"

        def make_feature(fid, name, size, h, center, **params):
            if prism:
                return PrismFeature(fid, name, size, h, center, sides=dlg.sides(), **params)
            if cone:
                return ConeFeature(fid, name, size, h, center, top_radius=dlg.top_radius(), **params)
            return CylinderFeature(fid, name, size, h, center, **params)


        def refresh_preview():
            r, h, center, po, pn, pu, pv = dlg.get_values()
            smart = dlg.get_smart_params()
            feat = make_feature("preview_cyl", "Preview", r, h, center,
                                plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                                translation=getattr(dlg, "placement_offset", (0, 0, 0)), **smart)
            try:
                solid = feat.build_solid()
                dlg.lbl_problem.clear()
            except Exception as exc:
                from omacad import applog
                applog.log("ERROR", f"{label} preview: {exc}")
                solid = None
                dlg.lbl_problem.setText(str(exc))
            self.viewport.set_preview(solid, "new_body")
            self.viewport.update()

        def on_pick_face():
            self.viewport.begin_plane_pick("primitive_face")
            self.status_label.setText(f"{label}: Click the face or plane where the bottom should start (Esc to cancel).")

        def on_face_picked(plane):
            dlg.set_target_plane(plane)
            dlg.activateWindow()

        def on_finished(result):
            for sig, slot in (
                (dlg.pick_face_requested, on_pick_face),
                (self.viewport.primitive_face_picked, on_face_picked),
            ):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self.viewport.update()
            if result:
                r, h, center, po, pn, pu, pv = dlg.get_values()
                smart = dlg.get_smart_params()
                place = dict(center=center, plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                             translation=getattr(dlg, "placement_offset", (0, 0, 0)), **smart)
                if prism:
                    body = self.doc.add_prism(r, h, sides=dlg.sides(), **place)
                elif cone:
                    place.pop("taper_angle", None)
                    body = self.doc.add_cone(r, dlg.top_radius(), h, **place)
                else:
                    body = self.doc.add_cylinder(r, h, **place)
                self.doc.timeline.last_added.exprs = dlg.get_expressions()
                self.viewport.zoom_fit()
                size = f"{r:g} across flats" if prism else f"R={r}"
                self.status_label.setText(f"Created {body.name} ({size}, H={h} mm).")

        timer = self._connect_debounced_preview(dlg, refresh_preview, throttle=True)
        dlg.finished.connect(lambda _: timer.stop())
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.primitive_face_picked.connect(on_face_picked)
        dlg.finished.connect(on_finished)
        from omacad.ui.primitive_handles import attach_primitive_handles
        attach_primitive_handles(self.viewport, dlg, "prism" if prism else "cylinder", refresh_preview)
        self.dock(dlg)
        refresh_preview()

    @leaves_sketch
    def prompt_sphere(self):
        from omacad.model.kernel import CadKernel
        from omacad.ui.primitive_handles import attach_primitive_handles
        dlg = SphereDialog(self)

        def preview():
            solid = CadKernel.create_sphere(dlg.get_values()).translate(tuple(getattr(dlg, "placement_offset", (0, 0, 0))))
            self.viewport.set_preview(solid, "new_body")

        def finished(result):
            self.viewport.set_preview(None)
            if result:
                r = dlg.get_values()
                body = self.doc.add_sphere(r, translation=getattr(dlg, "placement_offset", (0, 0, 0)))
                self.doc.timeline.last_added.exprs = dlg.get_expressions()
                self.viewport.zoom_fit()
                self.status_label.setText(f"Created {body.name} (R={r} mm).")

        timer = self._connect_debounced_preview(dlg, preview, throttle=True)
        dlg.finished.connect(lambda _: timer.stop())
        attach_primitive_handles(self.viewport, dlg, "sphere", preview)
        dlg.finished.connect(finished)
        self.dock(dlg)
        preview()

    @leaves_sketch
    def prompt_thread(self):
        from omacad.model.features.thread import ThreadFeature
        selected_id = self.doc.selected_body_ids[0] if self.doc.selected_body_ids else None
        dlg = ThreadDialog(self.doc, self, preselected_body_id=selected_id)

        preview_timer = QTimer(self)
        preview_timer.setSingleShot(True)
        preview_timer.setInterval(60)

        def do_refresh_preview():
            from omacad.model import quality
            prev = quality.is_interactive_mode()
            quality.set_interactive_mode(True)
            try:
                vals = dlg.get_values()
                feat = ThreadFeature("preview_thread", "Preview", **vals)
                try:
                    solid = feat.build_solid()
                except Exception:
                    solid = None
            finally:
                quality.set_interactive_mode(prev)
            op = "cut" if vals.get("operation") == "cut" else "new_body"
            self.viewport.set_preview(solid, op)
            self.viewport.update()

        def refresh_preview():
            preview_timer.start()

        preview_timer.timeout.connect(do_refresh_preview)

        def on_pick_face():
            self.viewport.begin_plane_pick("thread_surface")
            self.status_label.setText("Thread / Coil: Click a flat face or directly on the outside/inside of a cylinder (Esc to cancel).")

        def on_face_picked(plane):
            dlg.set_plane(plane)
            dlg.activateWindow()

        def on_cylinder_picked(cyl_info):
            dlg.apply_cylinder_info(cyl_info, body_id=cyl_info.get("body_id"))
            dlg.activateWindow()

        def on_finished(result):
            preview_timer.stop()            # a pending preview must not come back after the panel closed
            for sig, slot in (
                (dlg.changed, refresh_preview),
                (dlg.pick_face_requested, on_pick_face),
                (self.viewport.primitive_face_picked, on_face_picked),
                (self.viewport.cylinder_picked, on_cylinder_picked),
                (self.viewport.body_clicked, dlg.select_body),
            ):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            if self.viewport.plane_pick_mode:
                self.viewport.end_plane_pick()
            self.viewport.set_preview(None)
            self.viewport.update()
            if result:
                vals = dlg.get_values()
                body = self.doc.add_thread(exprs=dlg.get_expressions(), **vals)
                self.viewport.zoom_fit()
                if body:
                    self.status_label.setText(f"Created {body.name} (D={vals['diameter']}, P={vals['pitch']} mm).")

        dlg.changed.connect(refresh_preview)
        dlg.pick_face_requested.connect(on_pick_face)
        self.viewport.primitive_face_picked.connect(on_face_picked)
        self.viewport.cylinder_picked.connect(on_cylinder_picked)
        self.viewport.body_clicked.connect(dlg.select_body)
        dlg.finished.connect(on_finished)
        self.dock(dlg)
        refresh_preview()
        on_pick_face()
