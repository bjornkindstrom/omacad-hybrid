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
import shapely
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
    construction: bool = False   # a helper body: dull, see-through, never picked, never in the way
    is_lid: bool = False         # a slide-over or screw lid (toggleable via viewport HUD)
    faces: List[PlanarFace] = field(default_factory=list)
    edges: List[PlanarEdge] = field(default_factory=list)
    relief: bool = False         # a dense picture relief: only its large flat faces are picked, no edges
    # Exact OpenCascade shape (experimental "brep_bodies" setting). When set, `manifold` is its tessellation.
    brep: Any = field(default=None, repr=False, compare=False)

    def __setattr__(self, name, value):
        # Writing a new mesh makes this a plain mesh body: the old shape would no longer match it.
        if name == "manifold" and self.__dict__.get("brep") is not None and not self.__dict__.get("_setting_brep"):
            object.__setattr__(self, "brep", None)
        object.__setattr__(self, name, value)

    def set_brep(self, shape, manifold: m3d.Manifold) -> None:
        """The exact shape together with its tessellation (omacad.model.brep.attach builds the pair)."""
        object.__setattr__(self, "_setting_brep", True)
        try:
            self.manifold = manifold
            self.brep = shape
        finally:
            object.__setattr__(self, "_setting_brep", False)

    @property
    def is_brep(self) -> bool:
        return self.brep is not None

    @property
    def pickable(self) -> bool:
        return self.visible and not self.construction

    def update_render_mesh(self):
        """Marks the render mesh, faces and edges as belonging to the current manifold. They are computed the first
        time something reads them (`_LazyAnalysis`): a step's intermediate bodies that nothing picks, draws or
        matches edges on are never analysed, and the results are exactly those an immediate analysis gives (same
        manifold, same body id). Shallow copies (checkpoints, cached step outputs) share one analysis."""
        for name in _LAZY_FIELDS:
            self.__dict__.pop(name, None)
        # Manifold evaluates booleans lazily: settle this result now, as the analysis used to by reading the mesh.
        # Otherwise the next boolean folds it into a deeper CSG tree and triangulates the same solid differently.
        self.manifold.num_tri()
        object.__setattr__(self, "_lazy", _LazyAnalysis(self.manifold, self.body_id, self.name, self.relief))

    def analyse_now(self) -> None:
        """Computes anything still pending (the end of a rebuild does this, so the cost stays off the GUI thread)."""
        for name in _LAZY_FIELDS:
            getattr(self, name)

    def __getattr__(self, name):
        # only reached when the attribute is not set: a pending render mesh, faces or edges
        if name in _LAZY_FIELDS:
            lazy = self.__dict__.get("_lazy")
            if lazy is not None:
                value = lazy.get(name)
                self.__dict__[name] = value
                return value
            return _LAZY_DEFAULTS[name]()
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")


_LAZY_FIELDS = ("render_mesh", "faces", "edges")
del Body.render_mesh   # the dataclass default stays in __init__; without the class attribute a pending value reaches __getattr__
_LAZY_DEFAULTS = {"render_mesh": lambda: None, "faces": list, "edges": list}


class _LazyAnalysis:
    """The render mesh and face/edge analysis of one manifold, computed once on first use (thread-safe: a rebuild on
    the busy thread and a paint on the GUI thread may ask at the same time)."""
    __slots__ = ("manifold", "body_id", "name", "relief", "values", "lock")

    def __init__(self, manifold, body_id: str, name: str, relief: bool):
        import threading
        self.manifold, self.body_id, self.name, self.relief = manifold, body_id, name, relief
        self.values: Dict[str, Any] = {}
        self.lock = threading.Lock()

    def get(self, name: str):
        values = self.values
        if name in values:
            return values[name]
        with self.lock:
            if name not in values:
                if name == "render_mesh":
                    values["render_mesh"] = CadKernel.extract_render_mesh(self.manifold)
                else:
                    values.update(zip(("faces", "edges"), self._faces_and_edges()))
            return values[name]

    def _faces_and_edges(self):
        m, bid = self.manifold, self.body_id
        if self.relief and m.num_tri() > 5000:
            # Full edge analysis of hundreds of thousands of relief facets takes many seconds and finds only noise
            limit = 0.005 * m.surface_area()
            return [f for f in compute_planar_faces(m, bid) if f.area >= limit], []
        try:
            return compute_planar_faces_and_edges(m, bid)
        except Exception as e:      # fall back piece by piece; a body without picks still shows, the log says why
            applog.log("ERROR", f"{self.name}: face/edge analysis failed, trying separately: {e!r}")
            try:
                faces = compute_planar_faces(m, bid)
            except Exception as e2:
                applog.log("ERROR", f"{self.name}: faces unavailable: {e2!r}")
                faces = []
            try:
                edges = compute_planar_edges(m)
            except Exception as e2:
                applog.log("ERROR", f"{self.name}: edges unavailable: {e2!r}")
                edges = []
            return faces, edges


def analyse_bodies(doc: Any) -> None:
    """Finishes the pending analysis of the document's bodies, where the rebuild runs (the busy thread), so the first
    paint or pick after it does not pay for it on the GUI thread. A failure is logged; the body then has no picks."""
    from omacad import busy
    tangent = _show_tangent_edges() if busy.in_worker() else None   # only in the app's busy thread, never in tests
    for body in list(getattr(doc, "bodies", {}).values()):
        if isinstance(body, Body):
            try:
                body.analyse_now()
                if body.visible and body.render_mesh is not None and tangent is not None:
                    body.render_mesh.prepare_display(tangent)   # the first paint's edge lines and smoothing
                    _warm_picking(body)                         # and the first hover's triangle indexes
            except Exception as e:
                applog.log("ERROR", f"{body.name}: render/analysis failed: {e!r}")


def _warm_picking(body) -> None:
    from omacad import viewport_accel
    from omacad.model.faces_hit_tests import face_stack
    if body.faces:
        face_stack(body.faces)
    viewport_accel.mesh_index(body.render_mesh)


def _show_tangent_edges() -> Optional[bool]:
    """The view's tangent-edge setting, or None outside the app (scripts, tests without settings): nothing to warm."""
    try:
        from omacad.ui.settings import get_settings
        return bool(get_settings().get("show_tangent_edges", True))
    except Exception:
        return None


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


def clean_cut(target: m3d.Manifold, tool: m3d.Manifold) -> m3d.Manifold:
    """`target` minus `tool`, without the leftovers a cutter that almost coincides with a wall leaves behind."""
    # A cutter built from the target's own edges (a projected profile) misses the wall by nanometres: welded
    # onto the target's vertices and edges it coincides exactly and the kernel treats the two as one surface.
    tool = CadKernel.weld_to(tool, target)
    # A cutter coinciding with a faceted wall to within the kernel tolerance leaves
    # narrow strips; a nanometre larger cutter resolves them (fewer triangles). On
    # other cuts the grown cutter only adds nanometre steps (extra edges that break
    # later edge picks), so the exact cut is kept.
    result = target - tool
    nudged = target - CadKernel.grown(tool, 1e-6)
    if _triangle_count(nudged) < _triangle_count(result) or CadKernel.has_sheets(result):
        result = nudged
    # A profile drawn on the wall is cut into its own flat pieces, so its sides wander up
    # to a facet's sagitta around the wall (0.5 um at 360 segments, 5-50 um on coarser
    # projected arcs). The leftovers are either zero-thickness sheets or a skin a few 1e-5 mm
    # thick that stands above the floor (a moved body rounds its corners differently from the
    # sketch). Escalate clearance only while zero-thickness sheets remain; only when a micron of
    # clearance removes the needles (fewer triangles) is it used; exact volumes otherwise.
    if CadKernel.has_sheets(result):
        for clr in (CUT_CLEARANCE, 5e-3, 1e-2, 2e-2, 5e-2):
            result = target - CadKernel.grown(tool, clr)
            if not CadKernel.has_sheets(result):
                break
    elif CadKernel.has_needles(result):
        clear = target - CadKernel.grown(tool, CUT_CLEARANCE)
        if _triangle_count(clear) < _triangle_count(result):
            result = clear
    return result


def combine_with_bodies(doc: Any, feature_id: str, name: str, operation: str, tool: m3d.Manifold,
                        tool_brep=None) -> None:
    """Shared by Extrude and Revolve: add `tool` as a new body, or join/cut/intersect it with every body it touches.
    `tool_brep` (experimental B-rep bodies) builds the exact tool shape on demand: then a new body is a B-rep body,
    and B-rep bodies are joined/cut exactly. Whatever OpenCascade can't do falls back to the mesh."""
    from omacad.model import brep
    shape_cache = []

    def exact_tool():
        if tool_brep is None or not brep.active():
            return None
        if not shape_cache:
            try:
                shape_cache.append(tool_brep())
            except Exception as exc:
                applog.log("INFO", f"{name}: no B-rep tool ({exc!r}); using the mesh")
                shape_cache.append(None)
        return shape_cache[0]

    def new_body():
        body = Body(body_id=f"body_{feature_id}", name=name, manifold=tool)
        shape = exact_tool()
        if shape is not None:
            brep.attach(body, shape)
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
        shape = exact_tool() if all(b.brep is not None for b in targets) else None
        if shape is not None:
            try:
                for other in targets:
                    shape = brep.boolean(other.brep, shape, "join")
            except Exception as exc:
                applog.log("INFO", f"{name}: B-rep join not possible ({exc}); using the mesh")
                shape = None
        if shape is not None and brep.attach(targets[0], shape):
            for other in targets[1:]:
                doc.bodies.pop(other.body_id, None)
            targets[0].update_render_mesh()
            return
        merged = targets[0].manifold
        for other in targets[1:]:
            merged = merged + other.manifold
            doc.bodies.pop(other.body_id, None)
        targets[0].manifold = merged + CadKernel.weld_to(tool, merged)
        targets[0].update_render_mesh()
        return

    for body in targets:
        if operation not in ("cut", "intersect"):
            continue
        shape = exact_tool() if body.brep is not None else None
        if shape is not None:
            try:
                exact = brep.boolean(body.brep, shape, operation)
            except ValueError:                  # nothing left
                doc.bodies.pop(body.body_id, None)
                continue
            except Exception as exc:
                applog.log("INFO", f"{name}: B-rep {operation} on {body.name} not possible ({exc}); using the mesh")
                exact = None
            if exact is not None and brep.attach(body, exact):
                body.update_render_mesh()
                continue
        if operation == "cut":
            result = clean_cut(body.manifold, tool)
        else:
            result = body.manifold ^ CadKernel.weld_to(tool, body.manifold)
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
                targets = selected or owned or refs
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
    parts, rings = [], []
    for poly in polys:
        if poly.is_empty or poly.area < 1e-9:
            continue
        if not poly.interiors:
            ring = shapely.get_coordinates(poly.exterior)[:-1]
            rings.append(ring if poly.exterior.is_ccw else ring[::-1])
            continue
        part = profile_cross_section(SimpleNamespace(exterior_pts=list(poly.exterior.coords)[:-1],
                                                     interior_holes=[list(r.coords)[:-1] for r in poly.interiors]))
        parts.append(part)
    if rings:
        parts.append(m3d.CrossSection(rings, m3d.FillRule.Positive))
    if len(parts) == 1:
        return parts[0]
    # all at once: adding them one by one is quadratic, seconds for a thousand texture cells
    return m3d.CrossSection.batch_boolean(parts, m3d.OpType.Add) if parts else m3d.CrossSection([])


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

