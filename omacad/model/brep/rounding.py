"""Fillet and chamfer of B-rep bodies (step 2): Omacad's picked edges (found on the tessellation) are matched to the
exact OpenCascade edges they run along, then BRepFilletAPI does the rounding. Every function raises on failure;
the caller (FilletFeature) then falls back to the mesh tools for that body."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

SAMPLES = (0.17, 0.33, 0.5, 0.67, 0.83)     # interior points of a B-rep edge tested against a picked edge


def _unique(shape, kind):
    from OCP.TopExp import TopExp_Explorer
    out, exp = [], TopExp_Explorer(shape, kind)
    while exp.More():
        cur = exp.Current()
        if not any(cur.IsSame(o) for o in out):
            out.append(cur)
        exp.Next()
    return out


def edges(shape):
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    return [TopoDS.Edge(e) for e in _unique(shape, TopAbs_EDGE)]


def faces(shape):
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    return [TopoDS.Face(f) for f in _unique(shape, TopAbs_FACE)]


def edge_points(edge, params: Sequence[float] = SAMPLES) -> np.ndarray:
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c = BRepAdaptor_Curve(edge)
    u0, u1 = c.FirstParameter(), c.LastParameter()
    return np.array([c.Value(u0 + t * (u1 - u0)).Coord() for t in params], dtype=float)


def _distance_to_polyline(points: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance of each point to the nearest segment of the polyline."""
    a, b = poly[:-1], poly[1:]
    ab = b - a
    ll = np.maximum((ab * ab).sum(axis=1), 1e-300)
    rel = points[:, None, :] - a[None]
    t = np.clip((rel * ab[None]).sum(axis=2) / ll[None], 0.0, 1.0)
    near = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(points[:, None, :] - near, axis=2).min(axis=1)


def polyline_tolerance(poly: np.ndarray) -> float:
    """How far an exact curve may lie from the picked polyline: the polyline's chords sag inside a round edge, so
    allow a fraction of a segment there; a straight edge (two points) must match to 0.1 um."""
    if len(poly) <= 2:
        return 1e-4
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    return 1e-4 + 0.15 * float(np.median(seg))


def match_edges(shape, polylines: Sequence[np.ndarray]) -> List[list]:
    """For each picked polyline, the B-rep edges it runs along. Raises ValueError when a picked edge has no B-rep
    counterpart (then the mesh tools must do it). Two ways to match, either is enough:
    - most of the B-rep edge's interior lies along the pick (a crease found on the mesh can stop short of a closed
      B-rep edge: a saddle loop came out 0.7 mm open), or
    - most of the pick lies along the B-rep edge (the mesh splits one B-rep edge into pieces: the same saddle at
      72 segments was two creases).
    A neighbour only touches the pick at an end, so it matches neither way."""
    all_edges = edges(shape)
    samples = [edge_points(e) for e in all_edges]
    dense = [edge_points(e, np.linspace(0.0, 1.0, 129)) for e in all_edges]
    out = []
    for poly in polylines:
        poly = np.asarray(poly, dtype=float)
        if len(poly) < 2:
            raise ValueError("picked edge has no length")
        tol = polyline_tolerance(poly)
        inner = poly[1:-1] if len(poly) > 4 else np.vstack([poly[0] * (1 - t) + poly[-1] * t for t in SAMPLES])
        hits = []
        for e, pts, line in zip(all_edges, samples, dense):
            along_pick = (_distance_to_polyline(pts, poly) <= tol).sum() >= 3
            along_edge = (_distance_to_polyline(inner, line) <= tol + 1e-3).mean() >= 0.8
            if along_pick or along_edge:
                hits.append(e)
        if not hits:
            raise ValueError("picked edge not found on the B-rep shape")
        out.append(hits)
    return out


def _dedupe(items):
    out = []
    for item in items:
        if not any(item[0].IsSame(o[0]) for o in out):
            out.append(item)
    return out


def fillet(shape, items: Sequence):
    """items = [(B-rep edge, radius)]; edges with different radii meet in one corner blend."""
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
    mk = BRepFilletAPI_MakeFillet(shape)
    for e, r in _dedupe(list(items)):
        mk.Add(float(r), e)
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("OpenCascade could not build the fillet")
    return _checked(mk.Shape())


def _face_normal_at(face, point) -> Tuple[np.ndarray, bool]:
    """(unit normal of `face` near `point`, face is planar)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GeomLProp import GeomLProp_SLProps
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.gp import gp_Pnt
    surf = BRep_Tool.Surface_s(face)
    proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*map(float, point)), surf)
    u, v = proj.LowerDistanceParameters()
    props = GeomLProp_SLProps(surf, u, v, 1, 1e-9)
    n = np.array(props.Normal().Coord()) if props.IsNormalDefined() else np.zeros(3)
    if face.Orientation() == TopAbs_REVERSED:
        n = -n
    return n, BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane


def adjacent_faces(shape, edge):
    out = []
    for f in faces(shape):
        if any(edge.IsSame(e) for e in edges(f)):
            out.append(f)
    return out


def first_face(shape, edge, flip: bool):
    """The face the first chamfer distance is measured on, the same rule as FilletFeature.tool_sizes: a flat face
    next to a curved one, else the more horizontal face (ties: the one facing X more); Flip takes the other."""
    fs = adjacent_faces(shape, edge)
    if len(fs) != 2:
        raise ValueError("edge is not between two faces")
    mid = edge_points(edge, (0.5,))[0]
    (n1, flat1), (n2, flat2) = (_face_normal_at(f, mid) for f in fs)
    if flat1 != flat2:
        first = 0 if flat1 else 1
    else:
        z1, z2 = abs(n1[2]), abs(n2[2])
        if abs(z1 - z2) < 1e-6:
            z1, z2 = abs(n1[0]), abs(n2[0])
        first = 0 if z1 >= z2 - 1e-9 else 1
    if flip:
        first = 1 - first
    return fs[first]


def chamfer(shape, items: Sequence, ratio: Optional[float] = None, flip: bool = False):
    """items = [(B-rep edge, first distance)]. Equal chamfer, or the first distance on the first face (see
    first_face) and first * ratio on the other."""
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
    mk = BRepFilletAPI_MakeChamfer(shape)
    for e, d1 in _dedupe(list(items)):
        if ratio is None:
            mk.Add(float(d1), e)
        else:
            mk.Add(float(d1), float(d1 * ratio), e, first_face(shape, e, flip))
    mk.Build()
    if not mk.IsDone():
        raise RuntimeError("OpenCascade could not build the chamfer")
    return _checked(mk.Shape())


def _checked(shape):
    from omacad.model import brep
    if not brep.is_valid(shape):
        raise RuntimeError("OpenCascade made an invalid shape")
    return shape
