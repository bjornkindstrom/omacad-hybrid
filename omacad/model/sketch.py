"""
Omacad - 2D Sketch System
Represents sketch planes, 2D geometry primitives, and closed profile detection.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import math
import numpy as np
from omacad import applog
from omacad.model import quality
import shapely
from shapely.geometry import LineString, MultiLineString, Polygon, Point, MultiPoint
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union, snap
from omacad.model.sketch_types import SketchProfile, SketchConstraint, SketchDimension, EDGE_PTS, SOLVER_DIM_TYPES, REF_PREFIX
from omacad.model.sketch_editing import SketchEditingMixin

from omacad.model.sketch_entities import (
    _dist_point_segment, SketchPlane, SketchEntity, SketchLine, SketchRect,
    SketchCenterRect, SketchCircle, SketchArc, SketchSlot, SketchSpline, SketchText,
    ref_id, ref_segment, point_of, arm_vector, arm_angle_deg, nearest_ends_to_vertex,
    rotate_point, move_entity, rotate_entity, entity_key_points
)

# PT_LINE_DIST point names meaning "the near/far edge of this circle" instead of a point
EDGE_PTS = ("edge_near", "edge_far")
SOLVER_DIM_TYPES = ("ANGLE", "DISTANCE", "HORIZ_DIST", "VERT_DIST", "PT_LINE_DIST")

REF_PREFIX = "ref:"




class Sketch(SketchEditingMixin):
    """A 2D parametric sketch container with entities, dimensions, and closed profile solver."""

    def __init__(self, sketch_id: str, name: str = "Sketch 1", plane: Optional[SketchPlane] = None):
        self.sketch_id = sketch_id
        self.name = name
        self.plane = plane or SketchPlane.create_named("XY")
        self.entities: List[SketchEntity] = []
        self.profiles: List[SketchProfile] = []
        self.dimensions: List[SketchDimension] = []
        self.constraints: List[SketchConstraint] = []
        self.dof: Optional[int] = None  # degrees of freedom from the last solve (None = unknown)
        # In-plane edges of existing bodies (face outlines). They close regions that the sketch
        # geometry alone leaves open, e.g. an arc whose ends sit on the edge of a face.
        self.reference_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        self.visible: bool = True
        self.face_center = None  # supporting face area centroid in sketch coordinates
        self.face_key = None  # set for sketches made from a body face, so the same face is not duplicated
        self.parent_body_id: Optional[str] = None  # body this sketch was drawn on, or None if independent

    def _new_entity_id(self, prefix: str) -> str:
        """Unique id even after entities were deleted."""
        used = {e.entity_id for e in self.entities}
        n = len(self.entities) + 1
        while f"{prefix}_{n}" in used:
            n += 1
        return f"{prefix}_{n}"

    def hit_test(self, u: float, v: float, tol: float, include_construction: bool = True) -> Optional[SketchEntity]:
        """Nearest entity whose outline passes within `tol` of (u, v)."""
        best, best_d = None, tol
        text_bbox_hit: Optional[SketchEntity] = None
        for ent in self.entities:
            if not include_construction and ent.is_construction:
                continue
            box = ent.bbox() if isinstance(ent, SketchText) else None
            if box is not None:
                if u < box[0] - tol or u > box[2] + tol or v < box[1] - tol or v > box[3] + tol:
                    continue                               # lots of segments: skip text the point is nowhere near
                if box[0] - tol <= u <= box[2] + tol and box[1] - tol <= v <= box[3] + tol:
                    pt = Point(u, v)
                    for poly in ent.polygons():
                        if poly.contains(pt):
                            best, best_d = ent, 0.0
                            break
                    if text_bbox_hit is None and box[0] <= u <= box[2] and box[1] <= v <= box[3]:
                        text_bbox_hit = ent
            for p1, p2 in ent.to_lines():
                d = _dist_point_segment((u, v), p1, p2)
                if d <= best_d:
                    best, best_d = ent, d
        return best if best is not None else text_bbox_hit

    def restore_from_dict(self, data: Dict[str, Any]) -> None:
        """Replaces entities/dimensions with a snapshot, keeping this object's identity
        (timeline features hold references to it)."""
        snap = Sketch.from_dict(data)
        self.entities = snap.entities
        self.dimensions = snap.dimensions
        self.constraints = snap.constraints
        self._bind_texts()
        self.solve_profiles()  # uses this sketch's own reference edges

    def connected_entities(self, entity_id: str, tol: float = 1e-6) -> set:
        """Entities joined to this one through coincident constraints or shared end points
        (e.g. all four lines of a rectangle)."""
        by_id = {e.entity_id: e for e in self.entities}
        links: Dict[str, set] = {eid: set() for eid in by_id}
        for c in self.constraints:
            if c.ctype == "COINCIDENT" and len(c.refs) == 2 and all(r in by_id for r in c.refs):
                links[c.refs[0]].add(c.refs[1])
                links[c.refs[1]].add(c.refs[0])
        ends = [(eid, pt) for eid, e in by_id.items() for pt in entity_key_points(e)]
        for i, (ea, pa) in enumerate(ends):
            for eb, pb in ends[i + 1:]:
                if ea != eb and abs(pa[0] - pb[0]) < tol and abs(pa[1] - pb[1]) < tol:
                    links[ea].add(eb)
                    links[eb].add(ea)
        seen, stack = {entity_id}, [entity_id]
        while stack:
            for nxt in links.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for eid in list(seen):   # a polygon's centre circle belongs with its sides
            seen |= {e.entity_id for e in self.group_entities(by_id[eid])}
        return seen

    def delete_entities(self, entity_ids) -> int:
        """Removes entities and the dimensions attached to them; re-solves profiles."""
        ids = set(entity_ids)
        before = len(self.entities)
        self.entities = [e for e in self.entities if e.entity_id not in ids]
        self.dimensions = [d for d in self.dimensions
                           if d.target_entity_id not in ids and not (set(d.refs) & ids)]
        self.constraints = [c for c in self.constraints if not (set(c.refs) & ids)]
        self.solve_profiles()
        return before - len(self.entities)

    def new_constraint_id(self) -> str:
        used = {c.cid for c in self.constraints}
        n = len(self.constraints) + 1
        while f"c{n}" in used:
            n += 1
        return f"c{n}"

    def get_entity(self, entity_id: str) -> Optional[SketchEntity]:
        for ent in self.entities:
            if ent.entity_id == entity_id:
                return ent
        return None

    def add_dimension(
        self,
        dim_type: str,
        target_entity_id: str,
        value: float,
        offset_distance: float = 12.0,
        name: str = "",
        refs: Optional[List[str]] = None,
        pts: Optional[List[str]] = None,
    ) -> SketchDimension:
        used = {d.dim_id for d in self.dimensions}
        d_idx = len(self.dimensions) + 1
        while f"d{d_idx}" in used:
            d_idx += 1
        dim_id = f"d{d_idx}"
        dim_name = name or f"Dim {d_idx}"
        dim = SketchDimension(
            dim_id=dim_id,
            name=dim_name,
            dim_type=dim_type,
            target_entity_id=target_entity_id,
            value=float(value),
            offset_distance=float(offset_distance),
            refs=list(refs or []),
            pts=list(pts or []),
        )
        self.dimensions.append(dim)
        return dim

    def set_dimension_value(self, dim_id: str, new_value: float) -> bool:
        """Parametrically updates a dimension and solves geometry and closed profiles."""
        target_dim = None
        for d in self.dimensions:
            if d.dim_id == dim_id:
                target_dim = d
                break

        if not target_dim or new_value <= 0.001:
            return False

        target_dim.value = float(new_value)
        ent = self.get_entity(target_dim.target_entity_id)
        if not ent:
            return False
        if target_dim.dim_type in SOLVER_DIM_TYPES:
            return True  # geometry follows from the constraint solver

        if target_dim.dim_type == "RECT_WIDTH":
            if isinstance(ent, SketchRect):
                sign = 1.0 if ent.p2[0] >= ent.p1[0] else -1.0
                ent.p2 = (ent.p1[0] + sign * target_dim.value, ent.p2[1])
            elif isinstance(ent, SketchCenterRect):
                sign = 1.0 if ent.corner[0] >= ent.center[0] else -1.0
                ent.corner = (ent.center[0] + sign * (target_dim.value * 0.5), ent.corner[1])
        elif target_dim.dim_type == "RECT_HEIGHT":
            if isinstance(ent, SketchRect):
                sign = 1.0 if ent.p2[1] >= ent.p1[1] else -1.0
                ent.p2 = (ent.p2[0], ent.p1[1] + sign * target_dim.value)
            elif isinstance(ent, SketchCenterRect):
                sign = 1.0 if ent.corner[1] >= ent.center[1] else -1.0
                ent.corner = (ent.corner[0], ent.center[1] + sign * (target_dim.value * 0.5))
        elif target_dim.dim_type == "LENGTH":
            if isinstance(ent, SketchLine):
                dx = ent.p2[0] - ent.p1[0]
                dy = ent.p2[1] - ent.p1[1]
                cur_len = math.hypot(dx, dy)
                if cur_len > 1e-6:
                    ux = dx / cur_len
                    uy = dy / cur_len
                    ent.p2 = (ent.p1[0] + ux * target_dim.value, ent.p1[1] + uy * target_dim.value)
            elif isinstance(ent, SketchSlot):
                dx = ent.center2[0] - ent.center1[0]
                dy = ent.center2[1] - ent.center1[1]
                cur_len = math.hypot(dx, dy)
                if cur_len > 1e-6:
                    ux = dx / cur_len
                    uy = dy / cur_len
                    ent.center2 = (ent.center1[0] + ux * target_dim.value, ent.center1[1] + uy * target_dim.value)
        elif target_dim.dim_type == "DIAMETER":
            if isinstance(ent, SketchCircle):
                ent.radius = target_dim.value / 2.0
            elif isinstance(ent, SketchSlot):
                ent.radius = target_dim.value / 2.0
        elif target_dim.dim_type == "RADIUS":
            if isinstance(ent, SketchCircle):
                ent.radius = target_dim.value
            elif isinstance(ent, SketchSlot):
                ent.radius = target_dim.value
            elif isinstance(ent, SketchArc):
                if getattr(ent, "fillet_info", None):
                    self._update_fillet_arc(ent, target_dim.value)
                else:
                    params = ent.get_circle_params()
                    if params and params[1] > 1e-5:
                        scale = target_dim.value / params[1]
                        cx, cy = params[0]
                        ent.p_start = (cx + (ent.p_start[0] - cx) * scale, cy + (ent.p_start[1] - cy) * scale)
                        ent.p_mid = (cx + (ent.p_mid[0] - cx) * scale, cy + (ent.p_mid[1] - cy) * scale)
                        ent.p_end = (cx + (ent.p_end[0] - cx) * scale, cy + (ent.p_end[1] - cy) * scale)

        self.solve_profiles()
        return True

    def add_line(self, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False) -> SketchLine:
        ent_id = self._new_entity_id("line")
        line = SketchLine(ent_id, p1, p2, is_construction=is_construction)
        self.entities.append(line)
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        self.add_dimension("LENGTH", ent_id, length, offset_distance=12.0, name="Length")
        self.solve_profiles()
        return line















    @staticmethod
    def corner_radius_limit(p1, p2, radius: float) -> float:
        """The radius a rounded rectangle can really have: just under half the shorter side."""
        return min(radius, 0.495 * min(abs(p2[0] - p1[0]), abs(p2[1] - p1[1])))

    @staticmethod
    def rounded_rect_outline(p1, p2, radius: float, steps: int = 8) -> List[Tuple[float, float]]:
        """Closed outline of a rounded rectangle as points (for the live preview)."""
        x0, x1 = sorted((p1[0], p2[0]))
        y0, y1 = sorted((p1[1], p2[1]))
        r = Sketch.corner_radius_limit(p1, p2, radius)
        if r <= 0.001:
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        pts = []
        for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for k in range(steps + 1):
                a = math.radians(a0 + 90.0 * k / steps)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        return pts















    def solve_profiles(self) -> List[SketchProfile]:
        """Finds all closed 2D loops and builds SketchProfile objects."""
        all_lines = []
        for ent in self.entities:
            if ent.is_construction:
                continue
            all_lines.extend(ent.to_lines())

        if not all_lines:
            self.profiles = []
            self._profiles_cache_key = None
            return self.profiles

        # Fingerprint check to skip shapely unary_union + polygonize if geometry hasn't changed
        try:
            line_fp = tuple((round(p1[0], 5), round(p1[1], 5), round(p2[0], 5), round(p2[1], 5)) for p1, p2 in all_lines)
            ref_fp = tuple((round(a[0], 5), round(a[1], 5), round(b[0], 5), round(b[1], 5)) for a, b in self.reference_segments) if self.reference_segments else ()
            cache_key = (line_fp, ref_fp)
            if getattr(self, "_profiles_cache_key", None) == cache_key and self.profiles:
                return self.profiles
        except Exception:
            cache_key = None

        # A line that ends on a circle or arc ends on the true curve, just outside its chords: that end
        # becomes a corner of the drawn curve, so the line meets it and the region between them closes (Björn #93)
        rounds = [ent for ent in self.entities if not ent.is_construction and getattr(ent, "radius", 0) > 1e-4
                  and getattr(ent, "center", None) is not None]
        if rounds:
            ends = [q for ent in self.entities if not ent.is_construction and ent not in rounds
                    for seg in ent.to_lines() for q in seg]
            all_lines = []
            for ent in self.entities:
                if ent.is_construction:
                    continue
                segs = ent.to_lines()
                if ent in rounds:
                    (cx, cy), r = ent.center, ent.radius
                    on = [q for q in ends if abs(math.hypot(q[0] - cx, q[1] - cy) - r) < 1e-3 * max(1.0, r)]
                    for q in on:
                        for i, (a, b) in enumerate(segs):
                            d = LineString([a, b]).distance(Point(q))
                            if d < 2e-2 * r and Point(a).distance(Point(q)) > 1e-6 and Point(b).distance(Point(q)) > 1e-6:
                                ab = (b[0] - a[0], b[1] - a[1])
                                t = ((q[0] - a[0]) * ab[0] + (q[1] - a[1]) * ab[1]) / max(ab[0] ** 2 + ab[1] ** 2, 1e-18)
                                if 0.0 <= t <= 1.0:
                                    segs[i:i + 1] = [(a, tuple(q)), (tuple(q), b)]
                                    break
                all_lines.extend(segs)

        shapely_lines = []
        for p1, p2 in all_lines:
            # Avoid zero length lines
            if abs(p1[0] - p2[0]) > 1e-6 or abs(p1[1] - p2[1]) > 1e-6:
                shapely_lines.append(LineString([p1, p2]))

        if not shapely_lines:
            self.profiles = []
            return self.profiles

        try:
            sketch_union = unary_union(shapely.set_precision(shapely_lines, 1e-4))
            refs = [(a, b) for a, b in self.reference_segments if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9]
            projected = [seg for ent in self.entities if getattr(ent, "projected", False) and not ent.is_construction
                         for seg in ent.to_lines()]
            if refs and projected:
                # a face edge that was projected is in the sketch already, as fitted lines and arcs; its chords
                # beside them only cut slivers between the two (Björn #103)
                mids = shapely.points([((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0) for a, b in refs])
                near = shapely.distance(mids, MultiLineString(projected)) < 2e-2
                refs = [ab for ab, drop in zip(refs, near) if not drop]
            if refs:
                ref_union = unary_union([LineString([a, b]) for a, b in refs])
                # Sketch end points that sit on a face edge are inserted into that edge (a tiny float
                # gap would otherwise leave the loop open), so the regions close.
                sketch_points = MultiPoint([c for g in getattr(sketch_union, "geoms", [sketch_union])
                                            for c in g.coords])
                merged = unary_union([sketch_union, snap(ref_union, sketch_points, 1e-3)])
                polys = []
                guard = sketch_union.buffer(2e-3)
                for poly in polygonize(merged):
                    # keep regions whose outline uses sketch geometry; the bare face itself is not a profile
                    if poly.exterior.intersection(guard).length > 5e-3:
                        polys.append(poly)
            else:
                polys = list(polygonize(sketch_union))

            # Also handle standalone circles and slots if not polygonized
            for ent in self.entities:
                if ent.is_construction:
                    continue
                if isinstance(ent, SketchCircle) and ent.radius > 1e-4:
                    circle_pts = ent.get_polygon_points()
                    circle_poly = Polygon(circle_pts)
                    if not any(p.contains(Point(ent.center)) for p in polys):
                        polys.append(circle_poly)
                elif isinstance(ent, SketchSlot) and ent.radius > 1e-4:
                    slot_pts = ent.get_polygon_points(16)
                    slot_poly = Polygon(slot_pts)
                    if not any(p.contains(Point(ent.center1)) for p in polys):
                        polys.append(slot_poly)

            profiles = []
            for idx, p in enumerate(polys):
                if p.is_valid and p.area > 1e-5:
                    p_ccw = orient(p, sign=1.0)
                    ext = list(p_ccw.exterior.coords)[:-1]
                    holes = [list(h.coords)[:-1] for h in p_ccw.interiors]
                    prof = SketchProfile(
                        profile_id=f"{self.sketch_id}_prof_{idx + 1}",
                        exterior_pts=ext,
                        interior_holes=holes,
                        area=p_ccw.area
                    )
                    profiles.append(prof)

            self.profiles = profiles
            self._profiles_cache_key = cache_key
        except Exception as e:      # no closed shapes rather than a crash, but the reason goes in the log
            applog.log("ERROR", f"{self.name}: profiles could not be found: {e!r}")
            self.profiles = []
            self._profiles_cache_key = None

        return self.profiles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sketch_id": self.sketch_id,
            "name": self.name,
            "plane": {
                "name": self.plane.name,
                "origin": self.plane.origin.tolist(),
                "u_axis": self.plane.u_axis.tolist(),
                "v_axis": self.plane.v_axis.tolist(),
                "normal": self.plane.normal.tolist(),
            },
            "entities": [dict(e.to_dict(), **({"group": e.group} if getattr(e, "group", None) else {}),
                          **({"projected": True} if getattr(e, "projected", False) else {})) for e in self.entities],
            "dimensions": [d.to_dict() for d in self.dimensions],
            "constraints": [c.to_dict() for c in self.constraints],
            "face_key": list(self.face_key) if self.face_key else None,
            "parent_body_id": self.parent_body_id,
            "face_center": list(self.face_center) if self.face_center is not None else None,
            "visible": self.visible,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sketch":
        plane_data = data.get("plane", {})
        plane = SketchPlane(
            name=plane_data.get("name", "XY"),
            origin=np.array(plane_data.get("origin", [0, 0, 0]), dtype=np.float32),
            u_axis=np.array(plane_data.get("u_axis", [1, 0, 0]), dtype=np.float32),
            v_axis=np.array(plane_data.get("v_axis", [0, 1, 0]), dtype=np.float32),
            normal=np.array(plane_data.get("normal", [0, 0, 1]), dtype=np.float32),
        )
        sketch = cls(data["sketch_id"], name=data.get("name", "Sketch"), plane=plane)
        sketch.visible = data.get("visible", True)
        sketch.face_key = tuple(data["face_key"]) if data.get("face_key") else None
        sketch.parent_body_id = data.get("parent_body_id", None)
        sketch.face_center = tuple(data["face_center"]) if data.get("face_center") is not None else None

        groups = {ed.get("entity_id"): ed["group"] for ed in data.get("entities", []) if ed.get("group")}
        for ent_data in data.get("entities", []):
            t = ent_data.get("entity_type")
            if t == "line":
                sketch.entities.append(SketchLine.from_dict(ent_data))
            elif t == "rect":
                sketch.entities.append(SketchRect.from_dict(ent_data))
            elif t == "center_rect":
                sketch.entities.append(SketchCenterRect.from_dict(ent_data))
            elif t == "circle":
                sketch.entities.append(SketchCircle.from_dict(ent_data))
            elif t == "arc":
                sketch.entities.append(SketchArc.from_dict(ent_data))
            elif t == "slot":
                sketch.entities.append(SketchSlot.from_dict(ent_data))
            elif t == "spline":
                sketch.entities.append(SketchSpline.from_dict(ent_data))
            elif t == "text":
                sketch.entities.append(SketchText.from_dict(ent_data))

        for dim_data in data.get("dimensions", []):
            sketch.dimensions.append(SketchDimension.from_dict(dim_data))
        for c_data in data.get("constraints", []):
            sketch.constraints.append(SketchConstraint.from_dict(c_data))

        projected = {ed.get("entity_id") for ed in data.get("entities", []) if ed.get("projected")}
        for e in sketch.entities:
            if e.entity_id in groups:
                e.group = groups[e.entity_id]
            if e.entity_id in projected:
                e.projected = True
        sketch._migrate_legacy_rects()
        sketch._bind_texts()
        sketch.solve_profiles()
        return sketch
