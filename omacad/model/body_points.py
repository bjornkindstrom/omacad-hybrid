"""Points on a body that Move/Rotate can start from or go to.

- "end": the end of a straight edge (a box corner, where a straight piece meets a rounding ...).
- "corner": the sharp corner a rounding hides, where the straight edges on both sides would meet. For a
  rounding that runs on tangentially, that is where the tangents at the two ends of the arc cross, so
  it is found from the arc alone (like the guide lines of a rounded rectangle in a sketch).
- "top_center" / "bottom_center": area centres of the highest / lowest horizontal faces.
- "face_center": the area centre of every other flat face.
- "center": the centre of a full circular edge (a hole, the end of a cylinder ...).
- "quadrant": the four points of a full circle in line with the axes (a cross with its centre), so a cylinder
  can be put point to point by its side, not only by its centre.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

SHARP_TURN_DEG = 30.0   # a loop vertex turning more than this is a real corner, not a step of a tessellated arc


@dataclass
class BodyPoint:
    xyz: np.ndarray
    kind: str                                   # edge end, hidden corner, face/circle centre, top or bottom centre
    guides: Tuple[np.ndarray, ...] = field(default_factory=tuple)   # corner: the arc ends the guide lines start at


def _arc_ends(e):
    u, v = e._basis()
    ends, tangents = [], []
    for a in (e.a0, e.a0 + e.sweep):
        ends.append(e.center + e.radius * (np.cos(a) * u + np.sin(a) * v))
        tangents.append(-np.sin(a) * u + np.cos(a) * v)
    return ends, tangents


def tangent_corner(p0, t0, p1, t1) -> Optional[np.ndarray]:
    """Where the line through p0 along t0 meets the line through p1 along t1 (None if they miss or are parallel)."""
    a = np.column_stack([t0, -t1])
    st, *_ = np.linalg.lstsq(a, p1 - p0, rcond=None)
    q0, q1 = p0 + st[0] * t0, p1 + st[1] * t1
    if np.linalg.norm(q0 - q1) > 1e-6 * max(1.0, float(np.linalg.norm(p1 - p0))):
        return None
    return (q0 + q1) / 2.0


def circle_quadrants(e) -> List[np.ndarray]:
    """The four points of a full circle where it crosses the two world axes lying closest to its plane (X then Y
    for a horizontal circle), so they form a cross with the centre; a tilted circle uses the projected axes."""
    n = np.asarray(e.axis, float)
    n = n / np.linalg.norm(n)
    u = None
    for w in np.eye(3):
        p = w - float(w @ n) * n
        if np.linalg.norm(p) > 0.5:
            u = p / np.linalg.norm(p)
            break
    v = np.cross(n, u)
    c, r = np.asarray(e.center, float), float(e.radius)
    return [c + r * u, c + r * v, c - r * u, c - r * v]


def body_points(body) -> List[BodyPoint]:
    """Snap points on a body, including edge ends, hidden corners and horizontal face centres."""
    out: List[BodyPoint] = []
    for e in body.edges:
        kind = getattr(e, "kind", "")
        if kind == "line":
            out += [BodyPoint(np.asarray(e.p0, float), "end"), BodyPoint(np.asarray(e.p1, float), "end")]
        elif kind == "circle" and not e.is_arc:
            out.append(BodyPoint(np.asarray(e.center, float), "center"))
            out += [BodyPoint(p, "quadrant") for p in circle_quadrants(e)]
        elif kind == "circle" and e.is_arc:
            (p0, p1), (t0, t1) = _arc_ends(e)
            out += [BodyPoint(p0, "end"), BodyPoint(p1, "end")]
            if 1e-3 < e.sweep < np.pi - 1e-3:   # a rounding of a corner (a half circle has no corner)
                corner = tangent_corner(p0, t0, p1, t1)
                if corner is not None:
                    out.append(BodyPoint(corner, "corner", (p0, p1)))
        elif kind == "loop":
            pts = np.asarray(e.pts, float)
            d_in = pts - np.roll(pts, 1, axis=0)
            d_out = np.roll(pts, -1, axis=0) - pts
            cos = np.einsum("ij,ij->i", d_in, d_out) / np.maximum(
                np.linalg.norm(d_in, axis=1) * np.linalg.norm(d_out, axis=1), 1e-18)
            for i in np.flatnonzero(cos < np.cos(np.radians(SHARP_TURN_DEG))):
                out.append(BodyPoint(pts[i], "end"))
    # Use actual extreme horizontal faces rather than the bounding-box centre, so cuts and
    # asymmetric shapes keep their centre points on the top and bottom surfaces.
    horizontal = [(face, float(face.origin[2])) for face in getattr(body, "faces", ())
                  if abs(abs(float(face.normal[2])) - 1.0) < 1e-5]
    from omacad.model.geometry import face_centroid
    out += [BodyPoint(face_centroid(face), "face_center") for face in getattr(body, "faces", ())]
    vertices = np.asarray(body.manifold.to_mesh().vert_properties[:, :3], dtype=float)
    for kind, sign in (("top_center", 1.0), ("bottom_center", -1.0)):
        candidates = [(face, z) for face, z in horizontal if float(face.normal[2]) * sign > 0.999]
        if candidates:
            extreme = (max if sign > 0 else min)(z for _, z in candidates)
            faces = [face for face, z in candidates if abs(z - extreme) < 1e-5]
            centres = np.asarray([face_centroid(face) for face in faces])
            areas = np.asarray([face.area for face in faces], dtype=float)
            out.append(BodyPoint(np.average(centres, axis=0, weights=areas), kind))
        elif len(vertices):
            # Curved caps have no planar face; the extreme mesh vertices still give a stable
            # centre point (a sphere, for example, has one vertex at each pole).
            z = float(vertices[:, 2].max() if sign > 0 else vertices[:, 2].min())
            extreme_vertices = vertices[np.abs(vertices[:, 2] - z) < 1e-5]
            centre = extreme_vertices.mean(axis=0)
            out.append(BodyPoint(centre, kind))
    return _unique(out)


# where two points coincide, the one with the higher rank is kept (a cylinder's top: top centre, not circle centre)
_RANK = {"end": 0, "quadrant": 1, "corner": 2, "center": 3, "face_center": 4, "top_center": 5, "bottom_center": 5}
KINDS = tuple(_RANK)


def _unique(points: List[BodyPoint], tol: float = 1e-5) -> List[BodyPoint]:
    kept: List[BodyPoint] = []
    for p in points:
        same = next((i for i, k in enumerate(kept) if np.linalg.norm(k.xyz - p.xyz) < tol), None)
        if same is None:
            kept.append(p)
        elif _RANK[p.kind] > _RANK[kept[same].kind]:
            kept[same] = p
    return kept


def nearest_point(body, xyz, kind: Optional[str] = None) -> Optional[BodyPoint]:
    """The body's snap point closest to `xyz` (of the given kind): finds a picked point again after a rebuild."""
    xyz = np.asarray(xyz, float)
    pts = [p for p in body_points(body) if kind is None or p.kind == kind]
    return min(pts, key=lambda p: float(np.linalg.norm(p.xyz - xyz)), default=None)
