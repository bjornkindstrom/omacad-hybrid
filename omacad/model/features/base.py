"""
Omacad - Feature Base Classes and Helpers
Common data structures, mixins and boolean combination helpers used by all parametric features.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import math
import functools
import numpy as np
import manifold3d as m3d
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from omacad import applog
from omacad.model.kernel import CadKernel, RenderMesh
from omacad.model.faces import (
    PlanarFace, compute_planar_faces, PlanarEdge, compute_planar_edges, compute_planar_faces_and_edges
)


@dataclass
class Body:
    """Represents a 3D solid body in the document."""
    body_id: str
    name: str
    manifold: m3d.Manifold
    render_mesh: Optional[RenderMesh] = None
    color: List[float] = field(default_factory=lambda: [0.72, 0.77, 0.82, 1.0])  # Fusion 360 steel/aluminum
    visible: bool = True
    selected: bool = False
    faces: List[PlanarFace] = field(default_factory=list)
    edges: List[PlanarEdge] = field(default_factory=list)

    def update_render_mesh(self):
        self.render_mesh = CadKernel.extract_render_mesh(self.manifold)
        try:
            self.faces, self.edges = compute_planar_faces_and_edges(self.manifold, self.body_id)
        except Exception as e:      # fall back piece by piece; a body without picks still shows, the log says why
            applog.log("ERROR", f"{self.name}: face/edge analysis failed, trying separately: {e!r}")
            try:
                self.faces = compute_planar_faces(self.manifold, self.body_id)
            except Exception as e2:
                applog.log("ERROR", f"{self.name}: faces unavailable: {e2!r}")
                self.faces = []
            try:
                self.edges = compute_planar_edges(self.manifold)
            except Exception as e2:
                applog.log("ERROR", f"{self.name}: edges unavailable: {e2!r}")
                self.edges = []


def profile_cross_section(profile: Any) -> m3d.CrossSection:
    """Builds a Manifold CrossSection (with holes) from a SketchProfile."""
    poly = orient(Polygon(profile.exterior_pts, profile.interior_holes), sign=1.0)
    cs = m3d.CrossSection([list(poly.exterior.coords)[:-1]])
    for h in poly.interiors:
        ring = list(h.coords)[:-1]
        if Polygon(ring).exterior.is_ccw is False:   # a hole is stored clockwise; as a solid it must run counter-clockwise
            ring.reverse()
        cs = cs - m3d.CrossSection([ring])
    return cs


def _bbox_overlap(a: m3d.Manifold, b: m3d.Manifold, tol: float = 1e-6) -> bool:
    a0, a1 = np.array(a.bounding_box()[:3]), np.array(a.bounding_box()[3:])
    b0, b1 = np.array(b.bounding_box()[:3]), np.array(b.bounding_box()[3:])
    return bool(np.all(a0 <= b1 + tol) and np.all(b0 <= a1 + tol))


CUT_CLEARANCE = 1e-3   # mm a cutter is grown when a cut leaves strips: invisible, wider than facet mismatch


def _triangle_count(solid: m3d.Manifold) -> int:
    return len(solid.to_mesh().tri_verts)


def feature_bodies(doc, feature):
    """Stored targets constrain new operations; absent metadata keeps legacy replay."""
    ids = getattr(feature, 'target_body_ids', None)
    if ids is None:
        return list(doc.bodies.values())
    missing = [bid for bid in ids if bid not in doc.bodies]
    if missing:
        raise ValueError('Missing target body: ' + ', '.join(missing))
    return [doc.bodies[bid] for bid in ids]


def referenced_bodies(doc, feature):
    """Bodies a feature names itself: picked edges/faces/points and the bodies its sketches sit on."""
    from omacad.model.object_history import ObjectHistory
    refs = ObjectHistory.body_inputs(feature)
    for sketch_id in ObjectHistory.sketch_inputs(feature):
        sketch = getattr(doc, 'sketches', {}).get(sketch_id)
        refs.append(getattr(sketch, 'parent_body_id', None))
    return [bid for bid in dict.fromkeys(refs) if bid in doc.bodies]


def combine_with_bodies(doc: Any, feature_id: str, name: str, operation: str, tool: m3d.Manifold) -> None:
    """Shared by Extrude and Revolve: add `tool` as a new body, or join/cut/intersect it with every body it touches."""
    def new_body():
        body = Body(body_id=f"body_{feature_id}", name=name, manifold=tool)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    if operation == "new_body":
        new_body()
        return

    # Combine operations act on every body the tool actually touches
    feature = next((f for f in getattr(getattr(doc, "timeline", None), "features", []) if f.feature_id == feature_id), None)
    targets = [
        b for b in feature_bodies(doc, feature)
        if _bbox_overlap(b.manifold, tool)
        and (operation == "join" or not (b.manifold ^ tool).is_empty())
    ]

    if operation == "join":
        if not targets:
            new_body()
            return
        merged = targets[0].manifold
        for other in targets[1:]:
            merged = merged + other.manifold
            doc.bodies.pop(other.body_id, None)
        targets[0].manifold = merged + tool
        targets[0].update_render_mesh()
        return

    for body in targets:
        if operation == "cut":
            # A cutter coinciding with a faceted wall to within the kernel tolerance leaves
            # narrow strips; a nanometre larger cutter resolves them (fewer triangles). On
            # other cuts the grown cutter only adds nanometre steps (extra edges that break
            # later edge picks), so the exact cut is kept.
            result = body.manifold - tool
            nudged = body.manifold - CadKernel.grown(tool, 1e-6)
            if _triangle_count(nudged) < _triangle_count(result) or CadKernel.has_sheets(result):
                result = nudged
            # A profile drawn on the wall is cut into its own flat pieces, so its sides wander up
            # to a facet's sagitta (0.5 um at 360 segments) around the wall. The leftovers are either
            # zero-thickness sheets or a skin a few 1e-5 mm thick that stands above the floor (a
            # moved body rounds its corners differently from the sketch). Only when a micron of
            # clearance removes the needles (fewer triangles) is it used; exact volumes otherwise.
            if CadKernel.has_sheets(result):
                result = body.manifold - CadKernel.grown(tool, CUT_CLEARANCE)
            elif CadKernel.has_needles(result):
                clear = body.manifold - CadKernel.grown(tool, CUT_CLEARANCE)
                if _triangle_count(clear) < _triangle_count(result):
                    result = clear
        elif operation == "intersect":
            result = body.manifold ^ tool
        else:
            continue
        if result.is_empty():
            doc.bodies.pop(body.body_id, None)
        else:
            body.manifold = result
            body.update_render_mesh()


class Feature:
    """Base class for parametric history features."""
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        execute = cls.__dict__.get('execute')
        if execute is None:
            return

        @functools.wraps(execute)
        def tracked(self, doc):
            if (self.feature_type in ('extrude', 'revolve', 'sweep', 'loft', 'pipe', 'hole', 'fillet')
                    and getattr(self, 'operation', None) != 'new_body'
                    and not hasattr(self, 'target_body_ids')
                    and not getattr(getattr(doc, 'timeline', None), '_replaying', False)
                    and not getattr(doc, '_restoring', False)):
                selected = [bid for bid in getattr(doc, 'selected_body_ids', []) if bid in doc.bodies]
                history = getattr(doc, 'object_history', None)
                obj = history.objects.get(history.target_object_id) if history is not None else None
                owned = [bid for bid in obj.body_ids if bid in doc.bodies] if obj else []
                # The browser's active object only narrows an operation that refers to it: a cut sketched on
                # another body's face must not be aimed at the active object, miss it and be stored cutting nothing.
                refs = referenced_bodies(doc, self)
                if refs and not set(refs) & set(owned):
                    owned = []
                targets = selected or owned
                if targets:
                    self.target_body_ids = targets
                elif any(not b.visible for b in doc.bodies.values()):
                    # a hidden body is out of play: nothing is cut from or joined to it (Björn #99)
                    self.target_body_ids = [bid for bid, b in doc.bodies.items() if b.visible]
            before = {bid: b.manifold for bid, b in doc.bodies.items()}
            result = execute(self, doc)
            self._last_body_outputs = [bid for bid in dict.fromkeys([*before, *doc.bodies])
                                       if before.get(bid) is not getattr(doc.bodies.get(bid), 'manifold', None)]
            self._last_body_inputs = list(before)
            return result
        cls.execute = tracked

    def __init__(self, feature_id: str, feature_type: str, name: str):
        self.feature_id = feature_id
        self.feature_type = feature_type
        self.name = name
        self.suppressed: bool = False
        # field name -> formula, e.g. {"distance": "depth-2"}; evaluated when parameters change
        self.exprs: Dict[str, str] = {}
        self.error: str = ""        # why the step failed the last time it ran (shown on its timeline chip); not saved

    def execute(self, doc: Any) -> None:
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError


def profile_signature(profile: Any) -> Tuple[float, float, float]:
    """(centroid u, centroid v, area) of a sketch profile: what identifies it when the numbering of a sketch's
    profiles changes (a different curve smoothness, a re-drawn neighbour...)."""
    poly = Polygon(profile.exterior_pts, profile.interior_holes)
    c = poly.centroid
    return (float(c.x), float(c.y), float(poly.area))


def _profile_matches(profile: Any, sig, area_tol: float = 0.03) -> bool:
    u, v, a = profile_signature(profile)
    if abs(a - sig[2]) > max(area_tol * abs(sig[2]), 1e-3):
        return False
    return math.hypot(u - sig[0], v - sig[1]) <= max(0.25, 0.02 * math.sqrt(abs(sig[2])))


def _planes_coincide(a, b) -> bool:
    n1, n2 = np.asarray(a.normal, dtype=float), np.asarray(b.normal, dtype=float)
    return abs(abs(float(n1 @ n2)) - 1.0) < 1e-6 and abs(float((np.asarray(b.origin, dtype=float) - np.asarray(a.origin, dtype=float)) @ n1)) < 1e-4


def profile_polygon_in(profile: Any, src_plane: Any, dst_plane: Any) -> Polygon:
    """The profile as a shapely polygon in the (u, v) frame of `dst_plane` (both sketches lie in one plane)."""
    def conv(pts):
        if src_plane is dst_plane:
            return [tuple(p) for p in pts]
        return [tuple(dst_plane.world_to_uv(src_plane.uv_to_world(float(u), float(v)))) for u, v in pts]
    return Polygon(conv(profile.exterior_pts), [conv(h) for h in profile.interior_holes])


def find_profile(sketch: Any, idx: int, sig) -> Optional[int]:
    """Index of the profile of `sketch` that looks like `sig` (centre and area), preferring `idx`."""
    if 0 <= idx < len(sketch.profiles) and _profile_matches(sketch.profiles[idx], sig):
        return idx
    best, best_d = None, float("inf")
    for j, pr in enumerate(sketch.profiles):
        if _profile_matches(pr, sig):
            u, v, _a = profile_signature(pr)
            d = math.hypot(u - sig[0], v - sig[1])
            if d < best_d:
                best, best_d = j, d
    return best


def region_cross_section(geom) -> m3d.CrossSection:
    """CrossSection of a shapely polygon or multipolygon (holes included)."""
    from types import SimpleNamespace
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    cs = None
    for poly in polys:
        if poly.is_empty or poly.area < 1e-9:
            continue
        part = profile_cross_section(SimpleNamespace(exterior_pts=list(poly.exterior.coords)[:-1],
                                                     interior_holes=[list(r.coords)[:-1] for r in poly.interiors]))
        cs = part if cs is None else cs + part
    return cs if cs is not None else m3d.CrossSection([])


class ProfileRefs:
    """Mixin for steps that point at sketch profiles by number (Extrude, Revolve). Besides the numbers they
    remember each profile's signature, and when the numbers no longer fit (the sketch was solved again with a
    different curve smoothness, say) the profile is found again by its centre and area."""

    profile_sigs = None
    _sigs_for = None
    _follows_text: Optional[bool] = None

    def resolve_profile_refs(self, sketch) -> None:
        profiles = sketch.profiles
        idxs = [self.profile_idx] + list(self.extra_profiles)
        current = (self.profile_idx, tuple(self.extra_profiles))
        text_idxs = sketch.text_profile_indices() if hasattr(sketch, "text_profile_indices") else []

        if self.profile_sigs is None or self._sigs_for != current or len(self.profile_sigs) != len(idxs):
            if text_idxs and set(idxs) == set(text_idxs):
                self._follows_text = True
            elif self._follows_text is None:
                self._follows_text = False
            if all(0 <= i < len(profiles) for i in idxs):   # first sight (or edited): remember what they look like
                self.profile_sigs = [profile_signature(profiles[i]) for i in idxs]
                self._sigs_for = current
            return

        new, taken = [], set()
        unmatched = 0
        for i, sig in zip(idxs, self.profile_sigs):
            if 0 <= i < len(profiles) and i not in taken and _profile_matches(profiles[i], sig):
                new.append(i)
                taken.add(i)
            else:
                best, best_d = None, float("inf")
                for j, pr in enumerate(profiles):
                    if j in taken or not _profile_matches(pr, sig):
                        continue
                    u, v, _a = profile_signature(pr)
                    d = math.hypot(u - sig[0], v - sig[1])
                    if d < best_d:
                        best, best_d = j, d
                if best is not None:
                    new.append(best)
                    taken.add(best)
                else:
                    new.append(i)
                    unmatched += 1

        # If this feature follows SketchText (or all/most stored signatures failed to match after editing a sketch
        # whose profiles come from SketchText, e.g. changing text height/font/string), refresh to text_profile_indices().
        if text_idxs and (
            self._follows_text
            or (unmatched > 0 and len(idxs) >= 2 and set(idxs).issubset(set(range(len(profiles) + 10))) and len(text_idxs) >= 2)
        ):
            non_text_kept = [i for i in new if i not in text_idxs and 0 <= i < len(profiles)
                             and any(_profile_matches(profiles[i], s) for s in self.profile_sigs)]
            merged = list(text_idxs) + [i for i in non_text_kept if i not in text_idxs]
            if merged:
                self._follows_text = True
                self.profile_idx, self.extra_profiles = merged[0], merged[1:]
                self.profile_sigs = [profile_signature(profiles[i]) for i in merged]
                self._sigs_for = (self.profile_idx, tuple(self.extra_profiles))
                return

        if new != idxs:
            self.profile_idx, self.extra_profiles = new[0], new[1:]
            self._sigs_for = (self.profile_idx, tuple(self.extra_profiles))

    def profile_refs_dict(self) -> dict:
        if self.profile_sigs is None:
            return {}
        out = {"profile_sigs": [list(s) for s in self.profile_sigs],
               "profile_sigs_for": [self.profile_idx, list(self.extra_profiles)]}
        if self._follows_text is not None:
            out["follows_text"] = bool(self._follows_text)
        return out

    def load_profile_refs(self, data: dict) -> None:
        sigs, for_ = data.get("profile_sigs"), data.get("profile_sigs_for")
        if sigs and for_:
            self.profile_sigs = [tuple(float(x) for x in s) for s in sigs]
            self._sigs_for = (int(for_[0]), tuple(int(i) for i in for_[1]))
        if "follows_text" in data:
            self._follows_text = bool(data["follows_text"])

