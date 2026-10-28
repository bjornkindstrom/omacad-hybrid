"""
Omacad - Extrude Feature
Linear extrusion of a sketch profile (one_side, symmetric, two_sides; new_body, join, cut, intersect, auto),
optionally twisted about the profile's centre.
"""

from typing import Any, Optional, Dict, Tuple, List
import numpy as np
from shapely.geometry import Polygon
import manifold3d as m3d
from omacad.model.features.base import (
    Feature, ProfileRefs, profile_cross_section, region_cross_section,
    profile_signature, find_profile, _planes_coincide, profile_polygon_in,
    combine_with_bodies
)


class ExtrudeFeature(ProfileRefs, Feature):
    """Linear extrusion of a sketch profile.

    direction: "one_side" (distance may be negative to flip), "symmetric"
    (distance is the total length, centered on the sketch plane) or
    "two_sides" (distance along the normal, distance2 against it).
    """

    def __init__(
        self,
        feature_id: str,
        name: str,
        sketch_id: str,
        profile_idx: int,
        distance: float,
        operation: str = "new_body",  # new_body, join, cut, intersect
        direction: str = "one_side",
        distance2: float = 0.0,
        extra_profiles=None,
        extra_refs=None,
        holes=None,
        start_offset: float = 0.0,
        twist: float = 0.0,
    ):
        super().__init__(feature_id, "extrude", name)
        self.sketch_id = sketch_id
        self.profile_idx = profile_idx
        self.extra_profiles = [int(i) for i in (extra_profiles or [])]   # more profiles of the same sketch, extruded together
        # profiles of other sketches in the same plane that were Shift+clicked in: (sketch_id, index, signature)
        self.extra_refs = [(str(r[0]), int(r[1]), tuple(float(x) for x in r[2])) for r in (extra_refs or [])]
        # shapes of other sketches in the same plane lying inside the chosen profile: left open, as Fusion does
        # (sketch_id, index, signature)
        self.holes = [(str(r[0]), int(r[1]), tuple(float(x) for x in r[2])) for r in (holes or [])]
        self.distance = float(distance)
        self.operation = operation
        self.direction = direction
        self.distance2 = float(distance2)
        self.start_offset = float(start_offset)
        self.twist = float(twist)     # degrees the profile turns from bottom to top (Lennart #85)

    def region(self, doc: Any, sketch: Any, idxs) -> Any:
        """What is extruded, as a shapely geometry in the sketch's plane: the chosen profiles (also those of
        other sketches in the plane), minus the shapes that were left out."""
        from shapely.ops import unary_union
        parts = [Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes) for i in idxs]
        for sid, idx, sig in self.extra_refs:
            other = doc.sketches.get(sid)
            j = find_profile(other, idx, sig) if other is not None else None
            if j is not None and _planes_coincide(sketch.plane, other.plane):
                parts.append(profile_polygon_in(other.profiles[j], other.plane, sketch.plane))
        region = unary_union([p.buffer(0) for p in parts])
        cut = []
        for sid, idx, sig in self.holes:
            other = doc.sketches.get(sid)
            j = find_profile(other, idx, sig) if other is not None else None
            if j is not None and _planes_coincide(sketch.plane, other.plane):
                cut.append(profile_polygon_in(other.profiles[j], other.plane, sketch.plane).buffer(0))
        return region.difference(unary_union(cut)) if cut else region

    @staticmethod
    def selection_parts(doc: Any, sketch_id: str, profile_idx: int, selected_extra) -> tuple:
        """(extra_profiles, extra_refs, holes) for a click selection: the Shift+clicked profiles of the same sketch,
        those of other sketches in its plane, and the shapes inside that are left open."""
        extra = [i for (sid, i) in selected_extra if sid == sketch_id]
        refs = []
        for sid, i in selected_extra:
            other = doc.sketches.get(sid)
            if sid != sketch_id and other is not None and i < len(other.profiles):
                refs.append((sid, i, profile_signature(other.profiles[i])))
        return extra, refs, ExtrudeFeature.detect_holes(doc, sketch_id, profile_idx, extra, refs)

    @staticmethod
    def detect_holes(doc: Any, sketch_id: str, profile_idx: int, extra_profiles=(), extra_refs=()) -> list:
        """Profiles of other visible sketches in the same plane that lie inside the chosen ones and were not chosen
        themselves: they are left open when extruding (select them too, with Shift+click, to fill them)."""
        from shapely.ops import unary_union
        sketch = doc.sketches.get(sketch_id)
        if sketch is None or profile_idx >= len(sketch.profiles):
            return []
        idxs = [profile_idx] + [i for i in extra_profiles if i != profile_idx and i < len(sketch.profiles)]
        chosen = [Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes).buffer(0) for i in idxs]
        picked = set()
        for sid, idx in [(r[0], r[1]) for r in extra_refs]:
            other = doc.sketches.get(sid)
            if other is not None and idx < len(other.profiles) and _planes_coincide(sketch.plane, other.plane):
                chosen.append(profile_polygon_in(other.profiles[idx], other.plane, sketch.plane).buffer(0))
                picked.add((sid, idx))
        region = unary_union(chosen)
        out = []
        for sid, other in doc.sketches.items():
            if sid == sketch_id or not other.visible or not _planes_coincide(sketch.plane, other.plane):
                continue
            for j, pr in enumerate(other.profiles):
                if (sid, j) in picked or pr.area < 1e-6:
                    continue
                poly = profile_polygon_in(pr, other.plane, sketch.plane).buffer(0)
                if poly.area > 1e-6 and region.buffer(1e-6).contains(poly):
                    out.append((sid, j, profile_signature(pr)))
        return out

    def _z_range(self):
        """Returns (z_min, z_max) of the extrusion in sketch-local coordinates."""
        d = self.distance
        off = float(getattr(self, "start_offset", 0.0) or 0.0)
        if self.direction == "symmetric":
            h = abs(d) / 2.0
            return off - h, off + h
        if self.direction == "two_sides":
            return off - abs(self.distance2), off + abs(d)
        z0, z1 = (off, off + d) if d >= 0 else (off + d, off)
        # For cuts starting on a body face, extend slightly into empty air past the start
        # plane to prevent CSG from leaving a zero-thickness coplanar skin/cap over the opening.
        if getattr(self, "operation", "") == "cut":
            eps = 0.02
            if d >= 0:
                z0 -= eps
            else:
                z1 += eps
        return z0, z1

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        sketch = doc.sketches.get(self.sketch_id)
        if sketch:
            self.resolve_profile_refs(sketch)
        if not sketch or self.profile_idx >= len(sketch.profiles):
            return None
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        if self.extra_refs or self.holes:
            cs = region_cross_section(self.region(doc, sketch, idxs))
        else:
            cs = profile_cross_section(sketch.profiles[idxs[0]])
            for i in idxs[1:]:
                cs = cs + profile_cross_section(sketch.profiles[i])

        z0, z1 = self._z_range()
        height = z1 - z0
        if height < 1e-6:
            return None

        if abs(self.twist) > 1e-6:
            solid = self._twisted(cs, height)
        else:
            solid = m3d.Manifold.extrude(cs, height=float(height))
        if abs(z0) > 1e-9:
            solid = solid.translate((0.0, 0.0, float(z0)))
        solid = solid.transform(sketch.plane.get_transform_matrix_3x4())
        return solid if not solid.is_empty() else None

    def _twisted(self, cs: m3d.CrossSection, height: float) -> m3d.Manifold:
        """The profile turned `twist` degrees about its own centre (area centroid) over the height, sliced finely
        enough that each slice turns at most ~2 degrees (coarser in interactive previews)."""
        from omacad.model import quality
        # area centroid from the signed contours (holes run the other way and subtract)
        area = cx = cy = 0.0
        for ring in cs.to_polygons():
            x, y = np.asarray(ring, dtype=float).T
            xn, yn = np.roll(x, -1), np.roll(y, -1)
            cross = x * yn - xn * y
            area += cross.sum() / 2.0
            cx += ((x + xn) * cross).sum() / 6.0
            cy += ((y + yn) * cross).sum() / 6.0
        if abs(area) > 1e-12:
            cx, cy = cx / area, cy / area
        else:
            bb = cs.bounds()
            cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
        step = 6.0 if quality.is_interactive_mode() else 2.0
        n = max(1, int(np.ceil(abs(self.twist) / step)))
        # Each side quad of a slice is split into two triangles the same way round, which bulges the wall
        # outward by an amount that does not shrink with more slices; it shrinks with shorter profile edges,
        # so long edges are cut into short pieces first (a hexagon twisted 90 degrees: +0.6 % volume -> ~0.03 %).
        bb = cs.bounds()
        piece = max(bb[2] - bb[0], bb[3] - bb[1]) / (40.0 if not quality.is_interactive_mode() else 12.0)
        rings = []
        for ring in cs.to_polygons():
            pts = np.asarray(ring, dtype=float)
            out = []
            for i in range(len(pts)):
                a_, b_ = pts[i], pts[(i + 1) % len(pts)]
                k = max(1, int(np.ceil(float(np.linalg.norm(b_ - a_)) / max(piece, 1e-9))))
                out.extend(a_ + (b_ - a_) * (j / k) for j in range(k))
            rings.append([(float(x) - cx, float(y) - cy) for x, y in out])
        fine = m3d.CrossSection(rings, m3d.FillRule.Positive)
        solid = m3d.Manifold.extrude(fine, height=float(height), n_divisions=n, twist_degrees=float(self.twist))
        return solid.translate((cx, cy, 0.0))

    def resolve_operation(self, doc: Any) -> str:
        """The 'Auto' choice. Into material -> cut; sitting on a body's face and going outward ->
        join; otherwise a new body."""
        tool = self.build_solid(doc)
        if tool is None:
            return "new_body"
        for body in doc.bodies.values():
            if not body.visible or not self._bbox_overlap(body.manifold, tool):
                continue
            inter = body.manifold ^ tool
            if not inter.is_empty() and inter.volume() > 1e-6:
                return "cut"
        sketch = doc.sketches.get(self.sketch_id)
        if sketch is not None and self.profile_idx < len(sketch.profiles):
            from shapely.ops import unary_union
            plane = sketch.plane
            n0 = np.asarray(plane.normal, dtype=float)
            off = float(getattr(self, "start_offset", 0.0) or 0.0)
            o0 = np.asarray(plane.origin, dtype=float) + n0 * off
            ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
            region = unary_union([Polygon(sketch.profiles[i].exterior_pts, sketch.profiles[i].interior_holes)
                                  for i in [self.profile_idx] + [j for j in self.extra_profiles if j < len(sketch.profiles)]])
            for body in doc.bodies.values():
                if not body.visible:
                    continue
                for face in body.faces:
                    if abs(float(np.dot(face.normal, n0))) < 0.999 or abs(float(np.dot(face.origin - o0, n0))) > 1e-3:
                        continue  # not a face in the extrusion start plane
                    tris = [Polygon([(float(v @ ua), float(v @ va)) for v in tri]) for tri in face.tris]
                    if region.intersection(unary_union([t for t in tris if t.is_valid and t.area > 0])).area > 1e-6:
                        return "join"
        return "new_body"

    @staticmethod
    def _bbox_overlap(a: m3d.Manifold, b: m3d.Manifold, tol: float = 1e-6) -> bool:
        a0, a1 = np.array(a.bounding_box()[:3]), np.array(a.bounding_box()[3:])
        b0, b1 = np.array(b.bounding_box()[:3]), np.array(b.bounding_box()[3:])
        return bool(np.all(a0 <= b1 + tol) and np.all(b0 <= a1 + tol))

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is None:
            return
        if self.operation == "auto":
            self.operation = self.resolve_operation(doc)  # decided once, then stored like any other choice

        combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "sketch_id": self.sketch_id,
            "profile_idx": self.profile_idx,
            "extra_profiles": list(self.extra_profiles),
            "distance": self.distance,
            "operation": self.operation,
            "direction": self.direction,
            "distance2": self.distance2,
            "start_offset": self.start_offset,
            "twist": self.twist,
            "extra_refs": [[sid, i, list(sig)] for sid, i, sig in self.extra_refs],
            "holes": [[sid, i, list(sig)] for sid, i, sig in self.holes],
            **self.profile_refs_dict(),
        }
