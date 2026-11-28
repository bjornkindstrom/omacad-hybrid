"""Profile hover, selection fill, and feature preview support."""

import threading
from typing import Optional, Tuple
import numpy as np
import manifold3d as m3d
from PySide6.QtCore import QObject, Qt, Signal
from omacad import applog
from omacad.model.kernel import CadKernel
from omacad.model.timeline import profile_cross_section
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect

PREVIEW_SMOOTH_TRIANGLES = 60000    # above this, smooth normals take over a second per preview: shade it flat until OK
ASYNC_PREVIEW_TRIANGLES = 30000     # a preview this big has its mesh read on a worker thread (see set_preview)


class _PreviewRelay(QObject):
    """Brings a preview mesh read on the worker thread back to the GUI thread (queued signal)."""
    done = Signal(object)


class _PreviewWorker:
    """One thread at a time reads preview meshes; a request made while it is busy replaces any request still waiting,
    so a slider that moves faster than the meshes are read only ever shows its latest value."""

    def __init__(self, relay: _PreviewRelay):
        self.relay = relay
        self.lock = threading.Lock()
        self.waiting = None
        self.thread: Optional[threading.Thread] = None

    def submit(self, job) -> None:
        with self.lock:
            self.waiting = job
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="omacad: preview", daemon=True)
                self.thread.start()

    def _run(self) -> None:
        while True:
            with self.lock:
                job, self.waiting = self.waiting, None
                if job is None:
                    self.thread = None
                    return
            generation, work = job
            try:
                result = work()
            except Exception as e:          # a broken preview must not take the thread down; the next one may work
                applog.log("ERROR", f"preview mesh failed: {e!r}")
                continue
            try:
                self.relay.done.emit((generation, result))
            except RuntimeError:            # the view is gone
                return


class ProfileMixin:
    """Profile selection and preview helpers used by :class:`Viewport3D`."""

    def set_flash_sketch(self, sketch_id) -> None:
        if sketch_id != self.flash_sketch_id:
            self.flash_sketch_id = sketch_id
            self.update()
    def set_preview(self, manifold: Optional[m3d.Manifold], operation: str = "new_body", extra=None, extra_op: str = "join",
                    min_thickness: float = 0.0):
        """Shows a translucent preview solid (None clears it). `extra` is a second solid in another colour
        (a pattern both adds and removes material). Under a section view only the kept side is shown, like the bodies.
        Material thinner than `min_thickness` is not drawn (the skins in the difference between two states)."""
        manifold, extra = self.section_trim(manifold), self.section_trim(extra)
        # previews are lit with their flat per-triangle normals (free); smooth normals took 3-4 s at 100k triangles
        mesh = lambda solid: CadKernel.extract_render_mesh(solid, min_thickness=min_thickness, smooth=False)
        manifold = None if manifold is None or manifold.is_empty() else manifold
        extra = None if extra is None or extra.is_empty() else extra
        self._preview_generation = getattr(self, "_preview_generation", 0) + 1     # anything still on its way is stale

        def build():
            return (mesh(manifold) if manifold is not None else None,
                    (mesh(extra), extra_op) if extra is not None else None, operation)

        # The boolean behind a preview holds the GIL, so it is evaluated here (num_tri); reading its mesh is numpy work
        # that lets the GUI thread run, so a big one goes to the worker and the old preview stays until it is ready.
        size = sum(s.num_tri() for s in (manifold, extra) if s is not None)
        if getattr(self, "ASYNC_PREVIEW", False) and size > ASYNC_PREVIEW_TRIANGLES:
            self._preview_worker().submit((self._preview_generation, build))
            return
        self.preview_mesh, self.preview_extra, self.preview_op = build()
        self.update()

    ASYNC_PREVIEW = False       # the app turns this on (app.py); tests read previews at once, as before

    def _preview_worker(self) -> _PreviewWorker:
        worker = getattr(self, "_preview_thread", None)
        if worker is None:
            relay = _PreviewRelay(self)
            relay.done.connect(self._preview_ready, Qt.ConnectionType.QueuedConnection)
            worker = self._preview_thread = _PreviewWorker(relay)
        return worker

    def _preview_ready(self, payload) -> None:
        generation, result = payload
        if generation == self._preview_generation:          # a newer preview (or a clear) since: drop this one
            self._install_preview(result)

    def _install_preview(self, result) -> None:
        self.preview_mesh, self.preview_extra, self.preview_op = result
        self.update()
    def set_display_override(self, manifolds: Optional[dict]):
        """Draws these solids (body id -> manifold) in place of the bodies, which keep their edges and faces for
        picking; None restores them. Fillet/Chamfer uses it to show the finished result while edges are picked.
        Under a section view the solids are cut like the bodies, with their own cut faces."""
        before, self.display_solids = getattr(self, "display_solids", None) or {}, manifolds or None
        self.display_override = ({bid: CadKernel.extract_render_mesh(m, smooth=m.num_tri() <= PREVIEW_SMOOTH_TRIANGLES)
                                  for bid, m in manifolds.items()} if manifolds else None)
        if self.section is not None:
            for bid in set(before) | set(manifolds or {}):
                solid = (manifolds or {}).get(bid) or getattr(self.doc.bodies.get(bid), "manifold", None)
                if solid is not None:
                    self._cut_into_section(bid, solid)
        self.update()

    def pick_sketch_curve(self, x: float, y: float):
        """(sketch id, entity id) of the drawn line, arc or circle of a finished, visible sketch under the cursor
        (nearest plane first), else None. Used to pick a Sweep / Pipe path in the 3D view."""
        from omacad.model.sketch_entities import SketchArc, SketchCircle, SketchLine
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        tol = self._entity_tolerance()
        best, best_t = None, float("inf")
        for s_id, sketch in self.doc.sketches.items():
            if not sketch.visible or sketch is self.doc.active_sketch:
                continue
            hit = ray_plane_intersect(origin, ray_dir, sketch.plane.origin, sketch.plane.normal)
            if hit is None:
                continue
            t = float(np.linalg.norm(hit - origin))
            if t >= best_t:
                continue
            u, v = sketch.plane.world_to_uv(hit)
            ent = sketch.hit_test(u, v, tol)
            if (isinstance(ent, (SketchLine, SketchArc, SketchCircle)) and not getattr(ent, "is_construction", False)
                    and not getattr(ent, "projected", False)):
                best, best_t = (s_id, ent.entity_id), t
        return best

    def pick_profile(self, x: float, y: float) -> Optional[Tuple[str, int]]:
        """Returns (sketch_id, profile_idx) of the smallest closed profile under the cursor."""
        proj, view, _ = self.get_matrices()
        origin, ray_dir = ray_from_screen(x, y, self.width(), self.height(), view, proj)
        best, best_area, best_t = None, 0.0, 0.0
        for s_id, sketch in self.doc.sketches.items():
            if not sketch.visible or sketch is self.doc.active_sketch or not sketch.profiles:
                continue
            plane = sketch.plane
            hit = ray_plane_intersect(origin, ray_dir, plane.origin, plane.normal)
            if hit is None:
                continue
            t = float(np.linalg.norm(hit - origin))
            u, v = plane.world_to_uv(hit)
            for idx, prof in enumerate(sketch.profiles):
                if not prof.contains_point(u, v):
                    continue
                # Nearest plane wins; on the same plane the smallest profile wins
                if best is None or t < best_t - 1e-3 or (abs(t - best_t) <= 1e-3 and prof.area < best_area):
                    best, best_area, best_t = (s_id, idx), prof.area, t
        return best
    def bare_face_profile(self, picked) -> bool:
        """True when the profile only copies a body face: its whole outline (holes too) lies on projected entities.
        Such a profile floats where the face was (the open top of a cut-off cup) and must not catch the click
        meant for the floor seen through it (Björn #239)."""
        sid, idx = picked
        sketch = self.doc.sketches.get(sid)
        if sketch is None or idx >= len(sketch.profiles):
            return False
        projected = [ent for ent in sketch.entities if getattr(ent, "projected", False) and not ent.is_construction]
        if not projected:
            return False
        from shapely.geometry import MultiLineString, Point
        try:
            lines = MultiLineString([tuple(map(tuple, seg)) for ent in projected for seg in ent.to_lines()])
        except Exception:
            return False
        prof = sketch.profiles[idx]
        pts = list(prof.exterior_pts) + [q for hole in prof.interior_holes for q in hole]
        return bool(pts) and all(lines.distance(Point(q[0], q[1])) < 1e-3 for q in pts)

    def click_profile(self, x: float, y: float):
        """The profile a plain click (no tool open) selects: none when it only copies a face outline and a body
        face or surface is seen through it, so that face is what gets selected (Björn #239)."""
        picked = self.pick_profile(x, y)
        if picked is not None and not self.active_tool_title() and self.bare_face_profile(picked) and (
                self._pick_face(x, y) is not None or self._pick_curved_surface(x, y) is not None):
            return None
        return picked

    def _sketches_share_plane(self, a: str, b: str) -> bool:
        from omacad.model.timeline import _planes_coincide
        sa, sb = self.doc.sketches.get(a), self.doc.sketches.get(b)
        return sa is not None and sb is not None and _planes_coincide(sa.plane, sb.plane)
    def _selection_fill(self) -> Optional[np.ndarray]:
        """Triangles of what an extrude of the current selection would take: the chosen profiles minus the shapes
        of other sketches inside them (those stay unshaded; Shift+click them to include them)."""
        doc = self.doc
        sid, idx = doc.selected_profile
        key = ("selection", sid, idx, tuple(doc.selected_extra))
        cached = self._profile_fill_cache.get(key)
        if cached is not None:
            return cached
        sketch = doc.sketches.get(sid)
        if not sketch or idx >= len(sketch.profiles):
            return None
        from omacad.model.timeline import ExtrudeFeature, region_cross_section
        extra, refs, holes = ExtrudeFeature.selection_parts(doc, sid, idx, doc.selected_extra)
        feat = ExtrudeFeature("sel", "sel", sid, idx, 1.0, extra_profiles=extra, extra_refs=refs, holes=holes)
        idxs = [idx] + [i for i in extra if i != idx and i < len(sketch.profiles)]
        solid = m3d.Manifold.extrude(region_cross_section(feat.region(doc, sketch, idxs)), height=0.02)
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        mesh = solid.to_mesh()
        tris = mesh.vert_properties[:, :3][mesh.tri_verts].reshape(-1, 3).astype(np.float32)
        self._profile_fill_cache[key] = tris
        return tris
    def _profile_fill(self, key: Tuple[str, int]) -> Optional[np.ndarray]:
        """World-space triangles for a profile's filled face (cached)."""
        cached = self._profile_fill_cache.get(key)
        if cached is not None:
            return cached
        sketch = self.doc.sketches.get(key[0])
        if not sketch or key[1] >= len(sketch.profiles):
            return None
        solid = m3d.Manifold.extrude(profile_cross_section(sketch.profiles[key[1]]), height=0.02)
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        mesh = solid.to_mesh()
        tris = mesh.vert_properties[:, :3][mesh.tri_verts].reshape(-1, 3).astype(np.float32)
        self._profile_fill_cache[key] = tris
        return tris
    def _update_profile_hover(self, x: float, y: float):
        hover = None
        if not self.doc.active_sketch and not self.is_orbiting and not self.is_panning:
            hover = self.pick_profile(x, y)
        if hover != self.hover_profile:
            self.hover_profile = hover
            self.update()
