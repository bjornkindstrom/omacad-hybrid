"""
Omacad - Sweep, Loft and Pipe (Björn #46)
Sweep: a sketch profile carried along a path of sketch lines and arcs. Pipe: a round (optionally hollow) section
along such a path. Loft: a skin through two or more profiles in order. Each adds a new body or joins/cuts/intersects
like Extrude.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature, ProfileRefs, combine_with_bodies, find_profile, profile_signature
from omacad.model.sweep_geometry import loft_solid, path_frames, pipe_solid, sweep_solid

PathRef = Tuple[str, list]   # (sketch id, entity ids of lines / arcs / a circle) or (EDGES, [body edge refs])
EDGES = "@edges"


def norm_path(path) -> tuple:
    """A path reference as stored: sketch element ids as strings, body edge refs in Fillet's form."""
    if path[0] == EDGES:
        from omacad.model.features.fillet import FilletFeature
        return (EDGES, [FilletFeature._norm_ref(r) for r in path[1]])
    return (str(path[0]), [str(i) for i in path[1]])


def _edge_path_points(doc: Any, refs):
    """World points along body edges (as picked for a Fillet: lines, circles, outlines) joined end to end."""
    from omacad.model.faces import edge_from_ref, fuzzy_edge_from_ref
    pieces = []
    for ref in refs:
        hit = None
        for body in doc.bodies.values():
            hit = edge_from_ref(ref, body.edges) or fuzzy_edge_from_ref(ref, body.edges, used=[], reach=1.0)
            if hit is not None:
                break
        if hit is None:
            raise ValueError("An edge of the path is gone.")
        pieces.append(np.asarray(hit.polyline(96), dtype=float))
    if len(pieces) == 1 and np.linalg.norm(pieces[0][0] - pieces[0][-1]) < 1e-6:
        return pieces[0][:-1], True                     # a whole circle or outline
    chain = list(pieces.pop(0))
    tol = 1e-3
    while pieces:                                       # join the pieces end to end, turning them as needed
        for i, pc in enumerate(pieces):
            if np.linalg.norm(pc[0] - chain[-1]) < tol:
                chain += list(pc[1:])
            elif np.linalg.norm(pc[-1] - chain[-1]) < tol:
                chain += list(pc[::-1][1:])
            elif np.linalg.norm(pc[-1] - chain[0]) < tol:
                chain = list(pc[:-1]) + chain
            elif np.linalg.norm(pc[0] - chain[0]) < tol:
                chain = list(pc[::-1][:-1]) + chain
            else:
                continue
            pieces.pop(i)
            break
        else:
            raise ValueError("The picked edges must join end to end.")
    pts = np.asarray(chain, dtype=float)
    closed = len(pts) > 2 and np.linalg.norm(pts[0] - pts[-1]) < tol
    return (pts[:-1] if closed else pts), closed


def path_points(doc: Any, path_ref: PathRef, step_deg: float = 4.0):
    """World points along a path (sketch elements or body edges) in travel order, and whether it closes."""
    from omacad.model.sketch_entities import SketchCircle
    from omacad.model.sketch_offset import build_chains, to_seg
    if path_ref[0] == EDGES:
        pts, closed = _edge_path_points(doc, path_ref[1])
        keep = [0] + [i for i in range(1, len(pts)) if np.linalg.norm(pts[i] - pts[i - 1]) > 1e-9]
        return pts[keep], closed
    sketch_id, ids = path_ref
    sketch = doc.sketches.get(sketch_id)
    if sketch is None:
        raise ValueError("The path's sketch is gone.")
    ents = [e for e in sketch.entities if e.entity_id in set(ids)]
    circles = [e for e in ents if isinstance(e, SketchCircle)]
    if circles:
        c = circles[0]
        n = max(24, int(360 / step_deg))
        a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
        uv = np.column_stack([c.center[0] + c.radius * np.cos(a), c.center[1] + c.radius * np.sin(a)])
        closed = True
    else:
        segs = [s for s in (to_seg(e) for e in ents) if s is not None]
        if not segs:
            raise ValueError("Pick lines, arcs or a circle as the path.")
        chains = build_chains(segs)
        chain, closed = max(chains, key=lambda c: len(c[0]))
        if len(chains) > 1:
            raise ValueError("The path must be one connected chain of lines and arcs.")
        uv = [chain[0].p]
        for s in chain:
            pts = s.points(max(2, int(math.degrees(s.sweep()) / step_deg))) if s.kind == "arc" else [s.p, s.q]
            uv.extend(pts[1:])
        uv = np.asarray(uv, dtype=float)
        if closed:
            uv = uv[:-1]
    world = np.array([sketch.plane.uv_to_world(float(u), float(v)) for u, v in uv], dtype=float)
    keep = [0] + [i for i in range(1, len(world)) if np.linalg.norm(world[i] - world[i - 1]) > 1e-9]
    return world[keep], closed


def _profile_world(sketch, profile):
    to_w = lambda pts: np.array([sketch.plane.uv_to_world(float(u), float(v)) for u, v in pts], dtype=float)
    return to_w(profile.exterior_pts), [to_w(h) for h in profile.interior_holes]


class SweepFeature(ProfileRefs, Feature):
    """A profile swept along a path (Fusion's Sweep, single path). `twist` turns it over the length."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, path: PathRef,
                 operation: str = "new_body", twist: float = 0.0, extra_profiles=None):
        super().__init__(feature_id, "sweep", name)
        self.sketch_id = sketch_id
        self.profile_idx = int(profile_idx)
        self.extra_profiles: List[int] = [int(i) for i in (extra_profiles or [])]   # more profiles of the same sketch
        self.path = norm_path(path)
        self.operation = operation
        self.twist = float(twist)

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        sketch = doc.sketches.get(self.sketch_id)
        if sketch is None:
            return None
        self.resolve_profile_refs(sketch)
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx]
        if not all(0 <= i < len(sketch.profiles) for i in idxs):
            return None
        path, closed = path_points(doc, self.path)
        solids = [self._swept(sketch, sketch.profiles[i], path, closed) for i in idxs]
        solid = solids[0]
        for extra in solids[1:]:
            solid = solid + extra
        return solid if not solid.is_empty() else None

    def _swept(self, sketch, profile, path, closed) -> m3d.Manifold:
        outer, holes = _profile_world(sketch, profile)
        centre = outer.mean(axis=0)
        if not closed and np.linalg.norm(path[-1] - centre) < np.linalg.norm(path[0] - centre):
            path = path[::-1]                               # start at the end the profile sits on
        # the section is read off in the frame where the profile sits on the path (it need not be at an end)
        k = int(np.argmin(np.linalg.norm(path - centre, axis=1)))
        t, r, b, _s, _a = path_frames(path, closed, sketch.plane.u_axis)
        at = path[k]
        local = lambda pts: np.column_stack([(pts - at) @ r[k], (pts - at) @ b[k]])
        n = np.asarray(sketch.plane.normal, dtype=float)
        if abs(float(n @ t[k])) < 0.05:
            raise ValueError("The profile lies along the path: it has to cross it (draw it on a plane across the path).")
        solid = sweep_solid(local(outer), path, closed, r[0], self.twist)
        for h in holes:
            solid = solid - sweep_solid(local(h), path, closed, r[0], self.twist)
        return solid

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is not None:
            combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "sketch_id": self.sketch_id, "profile_idx": self.profile_idx,
                "extra_profiles": list(self.extra_profiles),
                "path": [self.path[0], [list(r) if isinstance(r, tuple) else r for r in self.path[1]]], "operation": self.operation, "twist": self.twist,
                **self.profile_refs_dict()}


class PipeFeature(Feature):
    """Fusion's Pipe: a round section of `diameter` along a path; `thickness` > 0 makes it a tube."""

    def __init__(self, feature_id: str, name: str, path: PathRef, diameter: float = 5.0, thickness: float = 0.0,
                 operation: str = "new_body"):
        super().__init__(feature_id, "pipe", name)
        self.path = norm_path(path)
        self.diameter = float(diameter)
        self.thickness = float(thickness)
        self.operation = operation

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        from omacad.model import quality
        if self.diameter <= 1e-6:
            raise ValueError("The pipe needs a diameter.")
        path, closed = path_points(doc, self.path)
        solid = pipe_solid(path, closed, self.diameter, self.thickness, max(16, quality.circle_segments()))
        return solid if not solid.is_empty() else None

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is not None:
            combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "path": [self.path[0], [list(r) if isinstance(r, tuple) else r for r in self.path[1]]],
                "diameter": self.diameter, "thickness": self.thickness, "operation": self.operation}


class LoftFeature(Feature):
    """Fusion's Loft: a skin through two or more profiles, in the order they were picked. Each profile is
    remembered as (sketch id, index, signature) and found again when the sketch changes. Inner contours are lofted and subtracted to preserve hollow profiles."""

    def __init__(self, feature_id: str, name: str, sections, operation: str = "new_body", twist: float = 0.0):
        super().__init__(feature_id, "loft", name)
        self.twist = float(twist)
        self.sections = [(str(s[0]), int(s[1]), tuple(float(x) for x in s[2])) for s in sections]
        self.operation = operation

    @staticmethod
    def section_ref(doc: Any, sketch_id: str, idx: int):
        return (sketch_id, idx, profile_signature(doc.sketches[sketch_id].profiles[idx]))

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        rings, caps, holes, hole_caps = [], [], [], []
        for sid, idx, sig in self.sections:
            sketch = doc.sketches.get(sid)
            j = find_profile(sketch, idx, sig) if sketch is not None else None
            if j is None:
                raise ValueError("A profile of the loft is gone.")
            prof = sketch.profiles[j]
            outer, inner = _profile_world(sketch, prof)
            holes.append(inner)
            hole_caps.append(prof.interior_holes)
            rings.append(outer)
            caps.append(np.asarray(prof.exterior_pts, dtype=float))
        if len({len(h) for h in holes}) != 1:
            raise ValueError("All loft profiles must have the same number of holes.")
        solid = loft_solid(rings, [caps[0], caps[-1]], twist_deg=self.twist)
        for i in range(len(holes[0])):
            cavity = loft_solid([h[i] for h in holes],
                                [np.asarray(hole_caps[0][i]), np.asarray(hole_caps[-1][i])],
                                twist_deg=self.twist)
            solid = solid - cavity
        return solid if not solid.is_empty() else None

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is not None:
            combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "sections": [[s, i, list(sig)] for s, i, sig in self.sections],
                "operation": self.operation, "twist": self.twist}
