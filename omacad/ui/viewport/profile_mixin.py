"""Profile hover, selection fill, and feature preview support."""

from typing import Optional, Tuple
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.timeline import profile_cross_section
from omacad.ui.math3d import ray_from_screen, ray_plane_intersect


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
        mesh = lambda solid: CadKernel.extract_render_mesh(solid, min_thickness=min_thickness)
        if manifold is None or manifold.is_empty():
            self.preview_mesh = None
        else:
            self.preview_mesh = mesh(manifold)
        self.preview_extra = (mesh(extra), extra_op) if extra is not None and not extra.is_empty() else None
        self.preview_op = operation
        self.update()
    def set_display_override(self, manifolds: Optional[dict]):
        """Draws these solids (body id -> manifold) in place of the bodies, which keep their edges and faces for
        picking; None restores them. Fillet/Chamfer uses it to show the finished result while edges are picked.
        Under a section view the solids are cut like the bodies, with their own cut faces."""
        before, self.display_solids = getattr(self, "display_solids", None) or {}, manifolds or None
        self.display_override = ({bid: CadKernel.extract_render_mesh(m) for bid, m in manifolds.items()}
                                 if manifolds else None)
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
