"""Sketch plane and 2D geometry entity definitions."""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import math
import numpy as np
from omacad.model import quality
from omacad.model.sketch_types import REF_PREFIX
import shapely
from shapely.geometry import LineString, Polygon, Point, MultiPoint
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union, snap

def _dist_point_segment(pt, p1, p2) -> float:
    px, py = pt
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
@dataclass
class SketchPlane:
    """Represents a 2D plane in 3D space (XY, XZ, YZ or arbitrary)."""
    name: str = "XY"
    origin: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.0], dtype=np.float32))
    u_axis: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0], dtype=np.float32))
    v_axis: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0], dtype=np.float32))
    normal: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0], dtype=np.float32))

    @classmethod
    def create_named(cls, name: str) -> "SketchPlane":
        if name.upper() == "XY":
            return cls(
                name="XY",
                origin=np.array([0.0, 0.0, 0.0], dtype=np.float32),
                u_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
                v_axis=np.array([0.0, 1.0, 0.0], dtype=np.float32),
                normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            )
        elif name.upper() == "XZ":
            return cls(
                name="XZ",
                origin=np.array([0.0, 0.0, 0.0], dtype=np.float32),
                u_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
                v_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32),
                normal=np.array([0.0, -1.0, 0.0], dtype=np.float32),
            )
        elif name.upper() == "YZ":
            return cls(
                name="YZ",
                origin=np.array([0.0, 0.0, 0.0], dtype=np.float32),
                u_axis=np.array([0.0, 1.0, 0.0], dtype=np.float32),
                v_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32),
                normal=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            )
        else:
            return cls()

    @classmethod
    def from_face(cls, normal: np.ndarray, point: np.ndarray, name: str = "FACE") -> "SketchPlane":
        """Plane on an arbitrary face. Origin = world origin projected onto the plane,
        u = world X (or Y when the normal is parallel to X) projected into the plane."""
        n = np.asarray(normal, dtype=np.float64)
        n = n / np.linalg.norm(n)
        hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = hint - np.dot(hint, n) * n
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        origin = n * float(np.dot(np.asarray(point, dtype=np.float64), n))
        f32 = lambda a: np.asarray(a, dtype=np.float32)
        return cls(name=name, origin=f32(origin), u_axis=f32(u), v_axis=f32(v), normal=f32(n))

    def centered_on(self, tris: np.ndarray) -> "SketchPlane":
        """Same plane with the origin moved to the middle of the given world triangles (a face), so
        (0, 0) is the face centre and the grid and the origin snap work from there."""
        pts = np.asarray(tris, dtype=np.float64).reshape(-1, 3) - np.asarray(self.origin, dtype=np.float64)
        u, v = pts @ np.asarray(self.u_axis, dtype=np.float64), pts @ np.asarray(self.v_axis, dtype=np.float64)
        c = self.uv_to_world((u.min() + u.max()) / 2, (v.min() + v.max()) / 2)
        return SketchPlane(name=self.name, origin=np.asarray(c, dtype=np.float32), u_axis=self.u_axis,
                           v_axis=self.v_axis, normal=self.normal)

    def uv_to_world(self, u: float, v: float) -> np.ndarray:
        """Convert local 2D (u, v) coordinates on the plane to 3D world (x, y, z)."""
        return self.origin + float(u) * self.u_axis + float(v) * self.v_axis

    def world_to_uv(self, world_pt: np.ndarray) -> Tuple[float, float]:
        """Project a 3D world point onto local (u, v) plane coordinates."""
        rel = world_pt - self.origin
        u = float(np.dot(rel, self.u_axis))
        v = float(np.dot(rel, self.v_axis))
        return u, v

    def get_transform_matrix_3x4(self) -> np.ndarray:
        """Returns 3x4 transform matrix [u | v | normal | origin] for Manifold3D."""
        return np.column_stack([self.u_axis, self.v_axis, self.normal, self.origin]).astype(float)

    def axis_names(self) -> Tuple[str, str]:
        """World axis labels ('X', 'Y', 'Z') aligned with this plane's horizontal (u) and vertical (v) axes."""
        def _axis_label(vec, fallback: str) -> str:
            v = np.abs(np.asarray(vec, dtype=float))
            idx = int(np.argmax(v))
            if v[idx] > 0.99:
                return ("X", "Y", "Z")[idx]
            return fallback
        u_lbl = _axis_label(self.u_axis, "X")
        v_lbl = _axis_label(self.v_axis, "Y")
        return (u_lbl, v_lbl) if u_lbl != v_lbl else ("X", "Y")
class SketchEntity:
    """Base class for 2D sketch elements."""
    def __init__(self, entity_id: str, entity_type: str, is_construction: bool = False):
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.is_construction = is_construction
        self.group: Optional[str] = None   # elements built together (a polygon's sides and its centre circle)

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """Returns line segments as ((u1, v1), (u2, v2))."""
        raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchEntity":
        raise NotImplementedError
class SketchLine(SketchEntity):
    def __init__(self, entity_id: str, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="line", is_construction=is_construction)
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        return [(self.p1, self.p2)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "line",
            "p1": list(self.p1),
            "p2": list(self.p2),
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchLine":
        return cls(
            entity_id=data["entity_id"],
            p1=tuple(data["p1"]),
            p2=tuple(data["p2"]),
            is_construction=data.get("is_construction", False),
        )
class SketchRect(SketchEntity):
    """2-point rectangle from corner1 to corner2."""

    def __init__(self, entity_id: str, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="rect", is_construction=is_construction)
        self.p1 = (float(p1[0]), float(p1[1]))
        self.p2 = (float(p2[0]), float(p2[1]))

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        x1, y1 = self.p1
        x2, y2 = self.p2
        c1 = (min(x1, x2), min(y1, y2))
        c2 = (max(x1, x2), min(y1, y2))
        c3 = (max(x1, x2), max(y1, y2))
        c4 = (min(x1, x2), max(y1, y2))
        return [(c1, c2), (c2, c3), (c3, c4), (c4, c1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "rect",
            "p1": list(self.p1),
            "p2": list(self.p2),
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchRect":
        return cls(
            entity_id=data["entity_id"],
            p1=tuple(data["p1"]),
            p2=tuple(data["p2"]),
            is_construction=data.get("is_construction", False),
        )
class SketchCenterRect(SketchEntity):
    """Center rectangle defined by center point and one corner."""

    def __init__(self, entity_id: str, center: Tuple[float, float], corner: Tuple[float, float], is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="center_rect", is_construction=is_construction)
        self.center = (float(center[0]), float(center[1]))
        self.corner = (float(corner[0]), float(corner[1]))

    def get_corners(self) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
        cx, cy = self.center
        dx = abs(self.corner[0] - cx)
        dy = abs(self.corner[1] - cy)
        c1 = (cx - dx, cy - dy)
        c2 = (cx + dx, cy - dy)
        c3 = (cx + dx, cy + dy)
        c4 = (cx - dx, cy + dy)
        return c1, c2, c3, c4

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        c1, c2, c3, c4 = self.get_corners()
        return [(c1, c2), (c2, c3), (c3, c4), (c4, c1)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "center_rect",
            "center": list(self.center),
            "corner": list(self.corner),
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchCenterRect":
        return cls(
            entity_id=data["entity_id"],
            center=tuple(data["center"]),
            corner=tuple(data["corner"]),
            is_construction=data.get("is_construction", False),
        )
class SketchCircle(SketchEntity):
    def __init__(self, entity_id: str, center: Tuple[float, float], radius: float, is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="circle", is_construction=is_construction)
        self.center = (float(center[0]), float(center[1]))
        self.radius = float(radius)

    def to_lines(self, segments: Optional[int] = None) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pts = self.get_polygon_points(segments)
        lines = []
        for i in range(len(pts)):
            lines.append((pts[i], pts[(i + 1) % len(pts)]))
        return lines

    def get_polygon_points(self, segments: Optional[int] = None) -> List[Tuple[float, float]]:
        segments = segments or quality.circle_segments()
        cx, cy = self.center
        r = self.radius
        pts = []
        for i in range(segments):
            angle = 2.0 * math.pi * i / segments
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return pts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "circle",
            "center": list(self.center),
            "radius": self.radius,
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchCircle":
        return cls(
            entity_id=data["entity_id"],
            center=tuple(data["center"]),
            radius=data["radius"],
            is_construction=data.get("is_construction", False),
        )
class SketchArc(SketchEntity):
    """3-point circular arc: p_start, p_mid, p_end."""

    def __init__(
        self,
        entity_id: str,
        p_start: Tuple[float, float],
        p_mid: Tuple[float, float],
        p_end: Tuple[float, float],
        is_construction: bool = False
    ):
        super().__init__(entity_id=entity_id, entity_type="arc", is_construction=is_construction)
        self.p_start = (float(p_start[0]), float(p_start[1]))
        self.p_mid = (float(p_mid[0]), float(p_mid[1]))
        self.p_end = (float(p_end[0]), float(p_end[1]))

    def get_circle_params(self) -> Optional[Tuple[Tuple[float, float], float, float, float, bool]]:
        """Returns (center, radius, start_angle, end_angle, ccw) or None if collinear."""
        p1 = np.array(self.p_start)
        p2 = np.array(self.p_mid)
        p3 = np.array(self.p_end)

        d = 2 * (p1[0] * (p2[1] - p3[1]) + p2[0] * (p3[1] - p1[1]) + p3[0] * (p1[1] - p2[1]))
        if abs(d) < 1e-7:
            return None

        p1_sq = np.sum(p1**2)
        p2_sq = np.sum(p2**2)
        p3_sq = np.sum(p3**2)

        cx = (p1_sq * (p2[1] - p3[1]) + p2_sq * (p3[1] - p1[1]) + p3_sq * (p1[1] - p2[1])) / d
        cy = (p1_sq * (p3[0] - p2[0]) + p2_sq * (p1[0] - p3[0]) + p3_sq * (p2[0] - p1[0])) / d
        center = (float(cx), float(cy))
        r = float(math.hypot(p1[0] - cx, p1[1] - cy))

        a1 = math.atan2(p1[1] - cy, p1[0] - cx) % (2 * math.pi)
        a2 = math.atan2(p2[1] - cy, p2[0] - cx) % (2 * math.pi)
        a3 = math.atan2(p3[1] - cy, p3[0] - cx) % (2 * math.pi)

        sweep_12 = (a2 - a1) % (2 * math.pi)
        sweep_13 = (a3 - a1) % (2 * math.pi)

        ccw = (sweep_12 < sweep_13)
        return center, r, a1, a3, ccw

    def get_points(self, segments: Optional[int] = None) -> List[Tuple[float, float]]:
        params = self.get_circle_params()
        if not params:
            return [self.p_start, self.p_mid, self.p_end]

        center, r, a1, a3, ccw = params
        cx, cy = center
        if segments is None:
            segments = quality.arc_segments((a3 - a1) % (2 * math.pi) if ccw else (a1 - a3) % (2 * math.pi))

        if ccw:
            total_sweep = (a3 - a1) % (2 * math.pi)
            step = total_sweep / segments
        else:
            total_sweep = (a1 - a3) % (2 * math.pi)
            step = -total_sweep / segments

        pts = []
        for i in range(segments + 1):
            ang = a1 + i * step
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        if pts:
            pts[0] = self.p_start
            pts[-1] = self.p_end
        return pts

    def to_lines(self, segments: Optional[int] = None) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pts = self.get_points(segments)
        lines = []
        for i in range(len(pts) - 1):
            lines.append((pts[i], pts[i + 1]))
        return lines

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "entity_id": self.entity_id,
            "entity_type": "arc",
            "p_start": list(self.p_start),
            "p_mid": list(self.p_mid),
            "p_end": list(self.p_end),
            "is_construction": self.is_construction,
        }
        if hasattr(self, "fillet_info") and self.fillet_info:
            d["fillet_info"] = self.fillet_info
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchArc":
        arc = cls(
            entity_id=data["entity_id"],
            p_start=tuple(data["p_start"]),
            p_mid=tuple(data["p_mid"]),
            p_end=tuple(data["p_end"]),
            is_construction=data.get("is_construction", False),
        )
        if "fillet_info" in data:
            arc.fillet_info = data["fillet_info"]
        return arc


class SketchSpline(SketchEntity):
    """Smooth interpolating spline through sketch points, sampled for display and profile operations."""

    def __init__(self, entity_id: str, points, is_construction: bool = False, tangents=None):
        super().__init__(entity_id=entity_id, entity_type="spline", is_construction=is_construction)
        self.points = [(float(p[0]), float(p[1])) for p in points]
        # optional explicit tangent vectors (Hermite derivative per span parameter) by point index
        self.tangents = {int(k): (float(v[0]), float(v[1])) for k, v in (tangents or {}).items()}

    def tangent_at(self, i: int):
        """Tangent vector at point i: the explicit one, else the Catmull-Rom default."""
        if i in self.tangents:
            return self.tangents[i]
        pts = self.points
        a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
        return (0.5 * (b[0] - a[0]), 0.5 * (b[1] - a[1]))

    def get_points(self, samples_per_span: int = 16):
        if len(self.points) < 2:
            return list(self.points)
        points = self.points
        out = []
        for i in range(len(points) - 1):
            p1, p2 = points[i], points[i + 1]
            m1, m2 = self.tangent_at(i), self.tangent_at(i + 1)
            # the clamped end tangent of the old Catmull-Rom curve was (p2-p0)/2 with p0=p1, i.e. same formula
            for j in range(samples_per_span):
                t = j / samples_per_span
                out.append(_hermite(p1, p2, m1, m2, t))
        out.append(points[-1])
        return out

    def to_lines(self):
        pts = self.get_points()
        return list(zip(pts, pts[1:]))

    def to_dict(self):
        return {"entity_id": self.entity_id, "entity_type": "spline", "points": [list(p) for p in self.points],
                "is_construction": self.is_construction,
                **({"tangents": {str(k): list(v) for k, v in self.tangents.items()}} if self.tangents else {})}

    @classmethod
    def from_dict(cls, data):
        return cls(data["entity_id"], data.get("points", []), data.get("is_construction", False),
                   tangents=data.get("tangents"))


def _hermite(p1, p2, m1, m2, t):
    t2, t3 = t * t, t * t * t
    h00, h10, h01, h11 = 2*t3 - 3*t2 + 1, t3 - 2*t2 + t, -2*t3 + 3*t2, t3 - t2
    return (h00*p1[0] + h10*m1[0] + h01*p2[0] + h11*m2[0],
            h00*p1[1] + h10*m1[1] + h01*p2[1] + h11*m2[1])


class SketchSlot(SketchEntity):
    """Center-to-center elongated slot / pill."""

    def __init__(
        self,
        entity_id: str,
        center1: Tuple[float, float],
        center2: Tuple[float, float],
        radius: float,
        is_construction: bool = False
    ):
        super().__init__(entity_id=entity_id, entity_type="slot", is_construction=is_construction)
        self.center1 = (float(center1[0]), float(center1[1]))
        self.center2 = (float(center2[0]), float(center2[1]))
        self.radius = float(radius)

    def get_polygon_points(self, arc_segments: int = 16) -> List[Tuple[float, float]]:
        c1x, c1y = self.center1
        c2x, c2y = self.center2
        dx = c2x - c1x
        dy = c2y - c1y
        length = math.hypot(dx, dy)
        r = self.radius

        if length < 1e-4:
            pts = []
            for i in range(arc_segments * 2):
                a = 2.0 * math.pi * i / (arc_segments * 2)
                pts.append((c1x + r * math.cos(a), c1y + r * math.sin(a)))
            return pts

        ux = dx / length
        uy = dy / length
        nx = -uy
        ny = ux

        base_angle = math.atan2(uy, ux)

        pts = []
        pts.append((c1x + r * nx, c1y + r * ny))
        pts.append((c2x + r * nx, c2y + r * ny))

        for i in range(1, arc_segments):
            ang = base_angle + math.pi * 0.5 - math.pi * (i / arc_segments)
            pts.append((c2x + r * math.cos(ang), c2y + r * math.sin(ang)))

        pts.append((c2x - r * nx, c2y - r * ny))
        pts.append((c1x - r * nx, c1y - r * ny))

        for i in range(1, arc_segments):
            ang = base_angle - math.pi * 0.5 - math.pi * (i / arc_segments)
            pts.append((c1x + r * math.cos(ang), c1y + r * math.sin(ang)))

        return pts

    def to_lines(self, arc_segments: int = 16) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        pts = self.get_polygon_points(arc_segments)
        lines = []
        for i in range(len(pts)):
            lines.append((pts[i], pts[(i + 1) % len(pts)]))
        return lines

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": "slot",
            "center1": list(self.center1),
            "center2": list(self.center2),
            "radius": self.radius,
            "is_construction": self.is_construction,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchSlot":
        return cls(
            entity_id=data["entity_id"],
            center1=tuple(data["center1"]),
            center2=tuple(data["center2"]),
            radius=data["radius"],
            is_construction=data.get("is_construction", False),
        )
def ref_id(seg) -> str:
    """Dimension reference to a fixed face edge, stored by its coordinates so it survives edge reordering."""
    (x1, y1), (x2, y2) = seg
    return f"{REF_PREFIX}{x1:.6f},{y1:.6f},{x2:.6f},{y2:.6f}"
def ref_segment(ref: str):
    """Inverse of ref_id: ((x1, y1), (x2, y2)) or None if `ref` is not an edge reference."""
    if not ref.startswith(REF_PREFIX):
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in ref[len(REF_PREFIX):].split(","))
    except ValueError:
        return None
    return (x1, y1), (x2, y2)
def point_of(ent, name: str):
    """A named point of an entity: line ends (p1, p2) or a circle centre."""
    if isinstance(ent, SketchLine):
        return ent.p1 if name == "p1" else ent.p2
    if isinstance(ent, SketchCircle) and name == "center":
        return ent.center
    return None
def arm_vector(line: "SketchLine", vertex_end: str):
    """Direction of a line pointing away from the end that sits at the angle's vertex."""
    a, b = (line.p1, line.p2) if vertex_end == "p1" else (line.p2, line.p1)
    return (b[0] - a[0], b[1] - a[1])
def arm_angle_deg(line_a: "SketchLine", end_a: str, line_b: "SketchLine", end_b: str) -> float:
    ax, ay = arm_vector(line_a, end_a)
    bx, by = arm_vector(line_b, end_b)
    na, nb = math.hypot(ax, ay), math.hypot(bx, by)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    cosang = max(-1.0, min(1.0, (ax * bx + ay * by) / (na * nb)))
    return math.degrees(math.acos(cosang))
def nearest_ends_to_vertex(line_a: "SketchLine", line_b: "SketchLine"):
    """(end of A, end of B) that meet at, or are nearest to, the lines' common vertex."""
    best = None
    for ea in ("p1", "p2"):
        for eb in ("p1", "p2"):
            pa, pb = point_of(line_a, ea), point_of(line_b, eb)
            d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
            if best is None or d < best[0]:
                best = (d, ea, eb)
    return best[1], best[2]
class SketchText(SketchEntity):
    """Text in a sketch, like Fusion's Text: a frame placed at `anchor`, or text running along a circle, arc or line
    (`path_id`). Its letter outlines are lines like any other, so the letters become profiles that can be extruded or
    embossed; counters (the hole of an O) are holes in the letter's profile."""

    PARAMS = ("text", "font", "height", "bold", "italic", "spacing", "h_align", "v_align", "flip_h", "flip_v", "angle",
              "anchor", "path_id", "placement", "fit", "box", "margin")

    def __init__(self, entity_id: str, text: str, anchor: Tuple[float, float] = (0.0, 0.0), height: float = 10.0,
                 font: str = "Sans Serif", bold: bool = False, italic: bool = False, spacing: float = 0.0,
                 h_align: str = "left", v_align: str = "bottom", flip_h: bool = False, flip_v: bool = False,
                 angle: float = 0.0, path_id: Optional[str] = None, placement: str = "above", fit: bool = False,
                 box=None, margin: float = 0.0, is_construction: bool = False):
        super().__init__(entity_id=entity_id, entity_type="text", is_construction=is_construction)
        self.text = str(text)
        self.anchor = (float(anchor[0]), float(anchor[1]))
        self.height = float(height)
        self.font = font
        self.bold, self.italic = bool(bold), bool(italic)
        self.spacing = float(spacing)                      # extra space between letters in percent of the font's own
        self.h_align, self.v_align = h_align, v_align      # left/center/right, top/middle/bottom (frame text)
        self.flip_h, self.flip_v = bool(flip_h), bool(flip_v)
        self.angle = float(angle)
        self.path_id = path_id                             # a circle, arc or line of this sketch: Text On Path
        self.placement = placement                         # on a path: "above" (left of the travel direction) or "below"
        self.fit = bool(fit)                               # on a path: spread the text over its whole length
        # Text In Box: (width, height) of a box centred on the anchor that the text fills as far as it can
        self.box = (float(box[0]), float(box[1])) if box else None
        self.margin = float(margin)                        # Text In Box: room kept free inside each side of the box
        self.sketch: Optional["Sketch"] = None             # set by the sketch that owns this text (to find its path)
        self._geom = None
        self._key = None

    def path_spec(self) -> Optional[Dict[str, Any]]:
        """The curve this text follows, or None (no path chosen, or it is gone)."""
        if not self.path_id or self.sketch is None:
            return None
        ent = next((e for e in self.sketch.entities if e.entity_id == self.path_id), None)
        if isinstance(ent, SketchCircle):
            return {"kind": "circle", "center": ent.center, "radius": ent.radius}
        if isinstance(ent, SketchArc):
            params = ent.get_circle_params()
            if params:
                center, r, a0, a1, ccw = params
                return {"kind": "arc", "center": center, "radius": r, "a0": a0, "a1": a1, "ccw": ccw}
        if isinstance(ent, SketchLine):
            return {"kind": "line", "p1": ent.p1, "p2": ent.p2}
        return None

    def geometry(self):
        """The letters as shapely polygons in sketch units (cached until a parameter or the path changes)."""
        path = self.path_spec()
        key = (tuple(getattr(self, k) for k in self.PARAMS if k != "path_id"), repr(path))
        if key != self._key:
            from omacad.model import text_layout
            self._geom = text_layout.layout(
                text=self.text, font=self.font, height=self.height, bold=self.bold, italic=self.italic,
                spacing=self.spacing, h_align=self.h_align, v_align=self.v_align, flip_h=self.flip_h,
                flip_v=self.flip_v, angle=self.angle, anchor=self.anchor, path=path, placement=self.placement,
                fit=self.fit, box=self.box, margin=self.margin)
            self._key = key
        return self._geom

    def fitted_height(self) -> float:
        """Text In Box: the capital height the box gives the text (the height field shows it)."""
        if not self.box:
            return self.height
        from omacad.model import text_layout
        text_layout._ensure_app()
        geom = text_layout._frame(dict(text=self.text, font=self.font, height=1.0, bold=self.bold, italic=self.italic,
                                       spacing=self.spacing, h_align=self.h_align, v_align="middle"))
        return text_layout.fit_in_box(geom, self.box, self.margin)[1]

    def box_corners(self):
        """The box's four corners in sketch coordinates (turned with the text), or None."""
        if not self.box:
            return None
        import math
        w, h = self.box[0] / 2.0, self.box[1] / 2.0
        a = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        return [(self.anchor[0] + x * ca - y * sa, self.anchor[1] + x * sa + y * ca)
                for x, y in ((-w, -h), (w, -h), (w, h), (-w, h))]

    def polygons(self) -> list:
        g = self.geometry()
        return [] if g is None or g.is_empty else list(getattr(g, "geoms", [g]))

    def bbox(self) -> Optional[Tuple[float, float, float, float]]:
        g = self.geometry()
        return None if g is None or g.is_empty else tuple(g.bounds)

    def to_lines(self) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
        lines = []
        for poly in self.polygons():
            for ring in [poly.exterior, *poly.interiors]:
                pts = list(ring.coords)
                lines.extend((pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        return lines

    def to_dict(self) -> Dict[str, Any]:
        d = {"entity_id": self.entity_id, "entity_type": "text", "is_construction": self.is_construction}
        for k in self.PARAMS:
            v = getattr(self, k)
            d[k] = list(v) if k == "anchor" else v
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SketchText":
        kw = {k: data[k] for k in cls.PARAMS if k in data and k != "text"}
        return cls(data["entity_id"], data.get("text", ""), is_construction=data.get("is_construction", False), **kw)
def _shift(pt, du, dv):
    return (pt[0] + du, pt[1] + dv)
def rotate_point(pt: Tuple[float, float], angle_deg: float, origin: Tuple[float, float] = (0.0, 0.0)) -> Tuple[float, float]:
    """Rotates a 2D point around an origin by angle_deg degrees."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    ox, oy = origin
    x, y = pt[0] - ox, pt[1] - oy
    return (ox + x * cos_a - y * sin_a, oy + x * sin_a + y * cos_a)
def move_entity(ent: "SketchEntity", du: float, dv: float) -> None:
    """Translates an entity in place."""
    if isinstance(ent, (SketchLine, SketchRect)):
        ent.p1, ent.p2 = _shift(ent.p1, du, dv), _shift(ent.p2, du, dv)
    elif isinstance(ent, SketchCenterRect):
        ent.center, ent.corner = _shift(ent.center, du, dv), _shift(ent.corner, du, dv)
    elif isinstance(ent, SketchCircle):
        ent.center = _shift(ent.center, du, dv)
    elif isinstance(ent, SketchArc):
        ent.p_start, ent.p_mid, ent.p_end = (_shift(ent.p_start, du, dv), _shift(ent.p_mid, du, dv),
                                             _shift(ent.p_end, du, dv))
    elif isinstance(ent, SketchSlot):
        ent.center1, ent.center2 = _shift(ent.center1, du, dv), _shift(ent.center2, du, dv)
    elif isinstance(ent, SketchText):
        ent.anchor = _shift(ent.anchor, du, dv)
    elif isinstance(ent, SketchSpline):
        ent.points = [_shift(p, du, dv) for p in ent.points]
def rotate_entity(ent: "SketchEntity", angle_deg: float, origin: Tuple[float, float]) -> None:
    """Rotates an entity in place around origin by angle_deg degrees."""
    if isinstance(ent, SketchLine):
        ent.p1 = rotate_point(ent.p1, angle_deg, origin)
        ent.p2 = rotate_point(ent.p2, angle_deg, origin)
    elif isinstance(ent, SketchRect):
        # Rotating an axis-aligned rect turns its corner coords; rotate both corners
        ent.p1 = rotate_point(ent.p1, angle_deg, origin)
        ent.p2 = rotate_point(ent.p2, angle_deg, origin)
    elif isinstance(ent, SketchCenterRect):
        ent.center = rotate_point(ent.center, angle_deg, origin)
        ent.corner = rotate_point(ent.corner, angle_deg, origin)
    elif isinstance(ent, SketchCircle):
        ent.center = rotate_point(ent.center, angle_deg, origin)
    elif isinstance(ent, SketchArc):
        ent.p_start = rotate_point(ent.p_start, angle_deg, origin)
        ent.p_mid = rotate_point(ent.p_mid, angle_deg, origin)
        ent.p_end = rotate_point(ent.p_end, angle_deg, origin)
    elif isinstance(ent, SketchSlot):
        ent.center1 = rotate_point(ent.center1, angle_deg, origin)
        ent.center2 = rotate_point(ent.center2, angle_deg, origin)
    elif isinstance(ent, SketchText):
        ent.anchor = rotate_point(ent.anchor, angle_deg, origin)
        ent.angle += angle_deg
    elif isinstance(ent, SketchSpline):
        ent.points = [rotate_point(p, angle_deg, origin) for p in ent.points]
        ent.tangents = {k: rotate_point(v, angle_deg, (0.0, 0.0)) for k, v in ent.tangents.items()}
def entity_key_points(ent: "SketchEntity") -> List[Tuple[float, float]]:
    """Points on an entity that are worth snapping when it is dragged (ends, corners, centres)."""
    if isinstance(ent, SketchLine):
        return [ent.p1, ent.p2]
    if isinstance(ent, SketchRect):
        (x1, y1), (x2, y2) = ent.p1, ent.p2
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    if isinstance(ent, SketchCenterRect):
        return list(ent.get_corners()) + [ent.center]
    if isinstance(ent, SketchCircle):
        return [ent.center]
    if isinstance(ent, SketchArc):
        return [ent.p_start, ent.p_end]
    if isinstance(ent, SketchSlot):
        return [ent.center1, ent.center2]
    if isinstance(ent, SketchText):
        return [ent.anchor]
    if isinstance(ent, SketchSpline):
        return list(ent.points)
    return []
