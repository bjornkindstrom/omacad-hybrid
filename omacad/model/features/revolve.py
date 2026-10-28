"""
Omacad - Revolve Feature
Revolves sketch profiles around an axis (one_side, symmetric, two_sides; new_body, join, cut, intersect, auto).
"""

from typing import Any, Optional, Dict
import math
import numpy as np
from shapely.geometry import Polygon
import manifold3d as m3d
from omacad.model.features.base import (
    Feature, ProfileRefs, profile_cross_section, _bbox_overlap, combine_with_bodies
)


class RevolveFeature(ProfileRefs, Feature):
    """Revolves sketch profiles around an axis, like Fusion 360's Revolve.

    axis: ("line", entity_id) a line of the same sketch (construction lines too), ("u",) / ("v",) the sketch's
    horizontal / vertical axis through its origin.
    direction: "one_side" (angle from the profile, negative flips), "symmetric" (angle is the total, half each way)
    or "two_sides" (angle one way, angle2 the other). angle >= 360 is a full turn."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, segments: int = 96,
                 operation: str = "new_body", axis=("v",), angle: float = 360.0, direction: str = "one_side",
                 angle2: float = 0.0, extra_profiles=None):
        super().__init__(feature_id, "revolve", name)
        self.sketch_id = sketch_id
        self.profile_idx = profile_idx
        self.extra_profiles = [int(i) for i in (extra_profiles or [])]
        self.segments = int(segments)
        self.operation = operation
        self.axis = tuple(axis)
        self.angle = float(angle)
        self.direction = direction
        self.angle2 = float(angle2)
        self.problem = ""

    def axis_uv(self, sketch):
        """((u, v) start, (u, v) end) of the axis in sketch coordinates, or None if it no longer exists."""
        if self.axis and self.axis[0] == "line":
            ent = sketch.get_entity(self.axis[1])
            if ent is None or getattr(ent, "entity_type", "") != "line":
                return None
            return tuple(ent.p1), tuple(ent.p2)
        if self.axis and self.axis[0] == "u":
            return (0.0, 0.0), (1.0, 0.0)
        return (0.0, 0.0), (0.0, 1.0)

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        from shapely import affinity
        self.problem = ""
        sketch = doc.sketches.get(self.sketch_id)
        if sketch:
            self.resolve_profile_refs(sketch)
        if not sketch or self.profile_idx >= len(sketch.profiles):
            return None
        ax = self.axis_uv(sketch)
        if ax is None:
            self.problem = "The axis line is gone."
            return None
        (au, av), (bu, bv) = ax
        L = math.hypot(bu - au, bv - av)
        if L < 1e-9:
            self.problem = "The axis has no length."
            return None
        d = ((bu - au) / L, (bv - av) / L)
        nrm = (-d[1], d[0])
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        polys = [Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes) for i in idxs]
        # which side of the axis the profile is on (the revolve only uses the positive side)
        side = 1.0
        mean_r = sum(((p.centroid.x - au) * nrm[0] + (p.centroid.y - av) * nrm[1]) * p.area for p in polys) / max(sum(p.area for p in polys), 1e-12)
        if mean_r < 0:
            side = -1.0
        # local coordinates: x = distance from the axis (profile side), y = position along the axis
        mat = [side * nrm[0], side * nrm[1], d[0], d[1], -(side * (au * nrm[0] + av * nrm[1])), -(au * d[0] + av * d[1])]
        local = [affinity.affine_transform(p, mat) for p in polys]
        if any(p.bounds[0] < -1e-6 for p in local):
            self.problem = "The profile crosses the axis."
            return None
        cs = None
        for p in local:
            q = profile_cross_section(type("P", (), {"exterior_pts": list(p.exterior.coords)[:-1],
                                                      "interior_holes": [list(h.coords)[:-1] for h in p.interiors]})())
            cs = q if cs is None else cs + q

        full = abs(self.angle) >= 360.0 - 1e-6 and self.direction == "one_side"
        if self.direction == "symmetric":
            sweep, start = abs(self.angle), -abs(self.angle) / 2.0
        elif self.direction == "two_sides":
            sweep, start = abs(self.angle) + abs(self.angle2), -abs(self.angle2)
        else:
            sweep, start = abs(self.angle), (0.0 if self.angle >= 0 else -abs(self.angle))
        sweep = min(sweep, 360.0)
        if sweep < 1e-6:
            return None
        if full or sweep >= 360.0 - 1e-6:
            solid = m3d.Manifold.revolve(cs, self.segments)
        else:
            solid = m3d.Manifold.revolve(cs, self.segments, float(sweep))
            if abs(start) > 1e-9:
                solid = solid.rotate((0.0, 0.0, float(start)))
        # axis frame in the world: z = along the axis, x = from the axis towards the profile
        plane = sketch.plane
        ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
        z = d[0] * ua + d[1] * va
        x = side * (nrm[0] * ua + nrm[1] * va)
        y = np.cross(z, x)
        o = np.asarray(plane.uv_to_world(au, av), dtype=float)
        solid = solid.transform(np.column_stack([x, y, z, o]).astype(float))
        return solid if not solid.is_empty() else None

    def resolve_operation(self, doc: Any) -> str:
        """The 'Auto' choice: into material -> cut, touching a body -> join, otherwise a new body."""
        tool = self.build_solid(doc)
        if tool is None:
            return "new_body"
        for body in doc.bodies.values():
            if not _bbox_overlap(body.manifold, tool):
                continue
            inter = body.manifold ^ tool
            if not inter.is_empty() and inter.volume() > 1e-6:
                return "cut"
        for body in doc.bodies.values():
            if _bbox_overlap(body.manifold, tool, 1e-4) and len((body.manifold + tool).decompose()) < 2:
                return "join"
        return "new_body"

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is None:
            return
        if self.operation == "auto":
            self.operation = self.resolve_operation(doc)
        combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name, "suppressed": self.suppressed,
            "sketch_id": self.sketch_id, "profile_idx": self.profile_idx, "extra_profiles": list(self.extra_profiles),
            "segments": self.segments, "operation": self.operation, "axis": list(self.axis),
            "angle": self.angle, "direction": self.direction, "angle2": self.angle2,
            **self.profile_refs_dict(),
        }
