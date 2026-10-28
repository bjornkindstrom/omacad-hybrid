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


class SketchScenePromptsMixin:
    """Sketchscene  prompt workflows for MainWindow."""

    def prompt_create_sketch(self):
        """Pick the sketch plane directly in the viewport (origin plane or planar face)."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.viewport.begin_plane_pick()
        self.status_label.setText("Create Sketch: click an origin plane or a flat face (Esc to cancel).")

    def on_plane_picked(self, plane):
        self.doc.auto_include_edges = self.viewport.sketch_palette.chk_project.isChecked()
        sketch = self.doc.start_sketch_on_plane(plane)
        self.viewport.align_to_plane(plane)
        face = getattr(plane, "face", None)
        if face is not None:
            self.viewport.frame_face(plane, face.tris)
        where = f"{plane.name} plane" if plane.name != "FACE" else "face"
        self.status_label.setText(f"Active Sketch: {sketch.name} on {where}. Select a tool (Line, Rect, Circle) to draw.")

    def prompt_offset_plane(self):
        """Offset Plane: pick an origin plane, construction plane, or flat face to offset from."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        self.viewport.begin_plane_pick("offset_base")
        self.status_label.setText("Offset Plane: click a plane (XY, XZ, YZ, construction plane) or a flat face to start from (Esc cancels).")

    def on_offset_base_picked(self, base):
        from omacad.model.sketch import SketchPlane
        n = np.asarray(base.normal, dtype=float)
        n = n / np.linalg.norm(n)
        o = np.asarray(base.origin, dtype=float)

        # Start an offset from the centre of the visible model, projected onto
        # the selected base plane. This keeps planes selected from the origin
        # planes near the part instead of anchored at world origin.
        meshes = [b.render_mesh for b in self.doc.bodies.values()
                  if b.visible and b.render_mesh is not None and len(b.render_mesh.vertices)]
        if meshes:
            lo = np.min([m.bounds_min for m in meshes], axis=0)
            hi = np.max([m.bounds_max for m in meshes], axis=0)
            centre = (lo + hi) * 0.5
            o = centre - n * float((centre - o) @ n)

        dlg = OffsetPlaneDialog(base.name, self)
        self.dock(dlg)
        self.status_label.setText("Offset Plane: type the distance in mm (or drag the 3D arrow). Click 'To surface…' to touch a surface.")

        frame = base if getattr(base, "u_axis", None) is not None else SketchPlane.from_face(n, o, name="PLANE")

        def placed():
            """(origin, normal) of the new plane: turned about the chosen axis, then offset (#51)."""
            point, direction = dlg.get_axis(frame)
            return self.doc.angled_plane(n, o, dlg.spn_dist.value(), dlg.get_angle(), point, direction)

        def update_preview():
            dist = dlg.spn_dist.value()
            po, pn = placed()
            plane = SketchPlane.from_face(pn, po, name="PLANE")
            # Keep sketch coordinates anchored as usual, but draw the marker
            # around the part instead of around world origin.
            plane.display_origin = np.asarray(po, dtype=np.float32)
            self.viewport.set_preview_plane(plane)
            self.viewport.set_extrude_handle(po - pn * dist, pn, dist if abs(dist) > 0.1 else 5.0, color=(0.75, 0.55, 0.95))

        def on_handle_drag(dist: float):
            dlg.spn_dist.setValue(round(dist, 3))

        dlg.changed.connect(update_preview)
        self.viewport.extrude_handle_dragged.connect(on_handle_drag)
        update_preview()

        # Surface pick mode if user clicks "To surface…"
        def plane_at(hit):
            rel = float((hit["point"] - o) @ n)
            proj = (hit["patch"] - o) @ n
            dist = float(proj.max() if rel >= 0 else proj.min())
            if abs(rel) < 1e-6:
                dist = float(proj[np.abs(proj).argmax()])
            return dist

        def on_surface_picked(hit):
            dist = plane_at(hit)
            dlg.spn_dist.setValue(round(dist, 3))
            self.viewport.end_plane_pick()
            self.status_label.setText(f"Offset set to {dist:.3f} mm from the surface. Adjust it or click OK.")

        def start_surface_pick():
            self.viewport.begin_plane_pick("offset_surface")
            try:
                self.viewport.surface_picked.disconnect(on_surface_picked)
            except Exception:
                pass
            self.viewport.surface_picked.connect(on_surface_picked)
            self.status_label.setText("Click a surface (flat or curved) to place the plane tangent to it.")

        dlg.surface_requested.connect(start_surface_pick)

        edge_wired = []

        def unwire_edge():
            if edge_wired:
                self.viewport.edges_selection_changed.disconnect(on_edge_picked)
                edge_wired.clear()

        def on_edge_picked():
            edges = [e for e in self.viewport.selected_edges if hasattr(e, "p0") and hasattr(e, "p1")]
            if not edges:
                return
            e = edges[-1]
            p0, p1 = np.asarray(e.p0, dtype=float), np.asarray(e.p1, dtype=float)
            unwire_edge()
            self.viewport.end_edge_pick()
            dlg.set_edge((p0 + p1) / 2.0, p1 - p0)
            self.status_label.setText("Offset Plane: the plane turns about that edge. Type the angle.")

        def start_edge_pick():
            unwire_edge()
            self.viewport.begin_edge_pick()
            self.viewport.edges_selection_changed.connect(on_edge_picked)
            edge_wired.append(True)
            self.status_label.setText("Offset Plane: click a straight edge to turn the plane about.")

        dlg.edge_requested.connect(start_edge_pick)

        def cleanup():
            try:
                self.viewport.surface_picked.disconnect(on_surface_picked)
            except Exception:
                pass
            unwire_edge()
            if self.viewport.edge_pick_mode:
                self.viewport.end_edge_pick()
            try:
                self.viewport.extrude_handle_dragged.disconnect(on_handle_drag)
            except Exception:
                pass
            self.viewport.set_preview_plane(None)
            self.viewport.clear_extrude_handle()
            self.viewport.end_plane_pick()
            self.inspector.undock_tool()

        if dlg.exec():
            dist = dlg.spn_dist.value()
            point, direction = dlg.get_axis(frame)
            pid = self.doc.add_construction_plane(base, dist, origin=o, angle=dlg.get_angle(),
                                                  axis_point=point, axis_dir=direction)
            self.status_label.setText(f"{self.doc.construction_planes[pid]['name']} created {dist:.3f} mm from {base.name}.")
        cleanup()

    def prompt_section(self):
        """Section view: pick a plane or face, then slide the cut through the model (view only)."""
        if self.doc.active_sketch:
            self.on_finish_sketch()
        if not self.doc.bodies:
            QMessageBox.information(self, "Section View", "There is nothing to cut through yet.")
            return
        if self.viewport.section is not None:
            self.viewport.clear_section()
        self.viewport.begin_plane_pick("section_base")
        self.status_label.setText("Section View: click an origin plane or a flat face to cut along (Esc cancels).")

    def on_section_base_picked(self, base, section_id=None):
        """Section dialog; Done saves it as a section view in the tree (new, or the one being changed)."""
        from omacad.ui.dialogs import SectionDialog
        n = np.asarray(base.normal, dtype=float)
        o = np.asarray(base.origin, dtype=float)
        meshes = [b.render_mesh for b in self.doc.bodies.values() if b.render_mesh is not None and len(b.render_mesh.vertices)]
        pts = np.array([m.bounds_min for m in meshes] + [m.bounds_max for m in meshes], dtype=float)
        centre = (pts.min(axis=0) + pts.max(axis=0)) / 2.0
        extent = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) / 2.0
        anchor = centre - n * float((centre - o) @ n)       # where the arrow stands on the base plane
        start = float((centre - o) @ n)                      # first cut: the middle of the model
        existing = self.doc.sections.get(section_id) if section_id else None
        dlg = SectionDialog("face" if base.name == "FACE" else f"{base.name} plane", extent + abs(start), self.viewport)
        if existing:
            dlg.setWindowTitle("Change Section View")
        dlg.place(self.viewport.size())
        self.viewport.section_editing = True

        def apply():
            off = dlg.offset()
            self.viewport.set_section(o, n, off, dlg.flip())
            self.viewport.set_extrude_handle(anchor, n, off, color=(0.10, 0.45, 1.0))   # blue: the cut face and plane are orange

        def dragged(val):
            dlg.set_offset(val)

        def finished(result):
            self.viewport.extrude_handle_dragged.disconnect(dragged)
            self.viewport.section_editing = False
            self.viewport.clear_section()
            self._section_dlg = None
            if result:
                if existing:
                    self.doc.update_section(section_id, origin=[float(x) for x in o], normal=[float(x) for x in n],
                                            offset=dlg.offset(), flip=dlg.flip())
                    self.doc.set_section_active(section_id, True)
                else:
                    self.doc.add_section(o, n, dlg.offset(), dlg.flip())
                self.status_label.setText("Section view saved in the tree: click its eye to turn it on and off.")
            else:
                self.viewport.sync_section()
                self.status_label.setText("Section view cancelled.")
            dlg.deleteLater()

        self._section_dlg = dlg
        self.viewport.extrude_handle_dragged.connect(dragged)
        dlg.changed.connect(apply)
        dlg.finished.connect(finished)
        dlg.show()
        dlg.set_offset(round(existing["offset"] if existing else start, 2))
        if existing:
            dlg.chk_flip.setChecked(bool(existing["flip"]))
        apply()
        self.status_label.setText("Section View: slide the offset until you are happy, then Done saves it in the tree.")

    def edit_section(self, sid: str):
        from omacad.model.sketch import SketchPlane
        sec = self.doc.sections.get(sid)
        if sec is None or getattr(self, "_section_dlg", None) is not None:
            return
        base = SketchPlane.from_face(np.array(sec["normal"]), np.array(sec["origin"]), name="PLANE")
        self.on_section_base_picked(base, sid)
