"""Extrude and Revolve as B-rep (step 3). Sketch profiles reach the features as polygons (arcs and circles already
cut into pieces), so the round parts are recognised again: a run of points on one circle with small steps becomes an
exact arc, a ring entirely on one circle a full circle. Polygons with big steps (a hexagon) stay straight lines."""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

MAX_ARC_STEP = math.radians(15.0)       # a sketch arc is cut in steps of 360/segments (3.75 deg at 96); a hexagon is 60
MIN_ARC_STEP = math.radians(0.2)        # below this the polygon just goes straight on
POINT_TOL = 2e-4                        # profile points are rounded to 4 decimals (sketch snapping)


def _fit_circle(points: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """Least-squares circle (Kasa) through 2D points: (centre, radius, largest radial miss)."""
    x, y = points[:, 0], points[:, 1]
    a = np.column_stack([x, y, np.ones_like(x)])
    b = x * x + y * y
    (c0, c1, c2), *_ = np.linalg.lstsq(a, b, rcond=None)
    centre = np.array([c0 / 2, c1 / 2])
    r = math.sqrt(max(c2 + centre @ centre, 0.0))
    miss = float(np.abs(np.linalg.norm(points - centre, axis=1) - r).max())
    return centre, r, miss


def ring_pieces(points: Sequence) -> List[tuple]:
    """A closed polygon (no repeated last point) as [("circle", centre, r)] or a list of ("line", p, q) and
    ("arc", p, mid, q) pieces, in order. A vertex is on an arc when the outline turns there by a small angle and
    the segments on both sides are equally long (sketch arcs are cut in equal steps); a run of such vertices that a
    circle fits to within the rounding of the points becomes an arc."""
    pts = np.asarray(points, dtype=float)
    if len(pts) > 1 and np.linalg.norm(pts[0] - pts[-1]) < 1e-12:
        pts = pts[:-1]
    n = len(pts)
    seg = np.roll(pts, -1, axis=0) - pts                      # seg[i] = pts[i] -> pts[i+1]
    length = np.linalg.norm(seg, axis=1)
    prev = np.roll(seg, 1, axis=0)
    turn = np.arctan2(prev[:, 0] * seg[:, 1] - prev[:, 1] * seg[:, 0], (prev * seg).sum(axis=1))  # at vertex i
    plen = np.roll(length, 1)
    arcish = ((np.abs(turn) >= MIN_ARC_STEP) & (np.abs(turn) <= MAX_ARC_STEP)
              & (np.abs(length - plen) <= 0.02 * np.maximum(length, plen)))

    def similar(i, j):               # same direction of turn and about the same step
        return bool(np.sign(turn[i]) == np.sign(turn[j])
                    and abs(turn[i] - turn[j]) <= 0.3 * max(abs(turn[i]), abs(turn[j])))

    if n >= 8 and arcish.all() and all(similar(0, k) for k in range(n)):
        c, r, miss = _fit_circle(pts)
        if miss <= POINT_TOL + 1e-5 * r:
            return [("circle", c, r)]
    if arcish.all():
        return [("line", pts[i], pts[(i + 1) % n]) for i in range(n)]
    start = next(i for i in range(n) if not arcish[i])
    pieces, i, steps = [], start, 0
    while steps < n:
        j = (i + 1) % n
        if arcish[j]:
            run = [j]
            k = (j + 1) % n
            while arcish[k] and similar(k, run[0]) and len(run) < n:
                run.append(k)
                k = (k + 1) % n
            if len(run) >= 2:
                c, r, miss = _fit_circle(pts[[i] + run + [k]])
                if miss <= POINT_TOL + 1e-5 * r:
                    if len(run) % 2:
                        v = pts[run[len(run) // 2]] - c
                    else:
                        v = (pts[run[len(run) // 2 - 1]] + pts[run[len(run) // 2]]) / 2 - c
                    mid = c + v / max(float(np.linalg.norm(v)), 1e-300) * r
                    pieces.append(("arc", pts[i], mid, pts[k]))
                    steps += len(run) + 1
                    i = k
                    continue
        pieces.append(("line", pts[i], pts[j]))
        steps += 1
        i = j
    return pieces


def _pnt(p, z=0.0):
    from OCP.gp import gp_Pnt
    return gp_Pnt(float(p[0]), float(p[1]), float(z))


def wire(points: Sequence):
    """Exact wire in the XY plane from a polygon ring."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir
    pieces = ring_pieces(points)
    pts = np.asarray(points, dtype=float)
    clockwise = float(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])) < 0
    mk = BRepBuilderAPI_MakeWire()
    for piece in pieces:
        if piece[0] == "circle":                 # a full circle runs counter-clockwise; a hole ring runs the other way
            circ = gp_Circ(gp_Ax2(_pnt(piece[1]), gp_Dir(0, 0, -1 if clockwise else 1)), float(piece[2]))
            mk.Add(BRepBuilderAPI_MakeEdge(circ).Edge())
        elif piece[0] == "arc":
            arc = GC_MakeArcOfCircle(_pnt(piece[1]), _pnt(piece[2]), _pnt(piece[3])).Value()
            mk.Add(BRepBuilderAPI_MakeEdge(arc).Edge())
        else:
            if np.linalg.norm(np.asarray(piece[1]) - np.asarray(piece[2])) < 1e-9:
                continue
            mk.Add(BRepBuilderAPI_MakeEdge(_pnt(piece[1]), _pnt(piece[2])).Edge())
    if not mk.IsDone():
        raise RuntimeError("profile outline is not a closed wire")
    return mk.Wire()


def face(polygon):
    """Planar face (XY plane) of a shapely Polygon with holes."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.ShapeFix import ShapeFix_Face
    from shapely.geometry.polygon import orient
    polygon = orient(polygon, sign=1.0)                 # outline counter-clockwise (+Z face), holes clockwise
    mk = BRepBuilderAPI_MakeFace(wire(list(polygon.exterior.coords)[:-1]), True)
    for hole in polygon.interiors:
        mk.Add(wire(list(hole.coords)[:-1]))
    if not mk.IsDone():
        raise RuntimeError("profile face could not be built")
    fix = ShapeFix_Face(mk.Face())          # orients the hole wires correctly whatever their direction
    fix.Perform()
    return fix.Face()


def _polygons(geometry):
    if geometry.is_empty:
        return []
    return list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]


def _compound(shapes):
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    if len(shapes) == 1:
        return shapes[0]
    comp, builder = TopoDS_Compound(), BRep_Builder()
    builder.MakeCompound(comp)
    for s in shapes:
        builder.Add(comp, s)
    return comp


def extrude(geometry, z0: float, height: float, matrix):
    """Prism of a shapely (Multi)Polygon in sketch coordinates from z0 to z0+height, placed by the sketch plane's
    3x4 matrix."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    from omacad.model import brep
    solids = []
    for poly in _polygons(geometry):
        solids.append(BRepPrimAPI_MakePrism(face(poly), gp_Vec(0, 0, float(height))).Shape())
    if not solids:
        raise ValueError("nothing to extrude")
    shape = _compound(solids)
    if abs(z0) > 1e-12:
        shape = brep.translate(shape, (0.0, 0.0, z0))
    return _checked(brep.transform(shape, matrix))


def revolve(geometry, sweep_deg: float, start_deg: float, matrix):
    """Revolve of a shapely (Multi)Polygon in axis coordinates (x = distance from the axis, y = along it) about the
    Z axis, like Manifold.revolve, then placed by `matrix`."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
    from omacad.model import brep
    to_xz = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, 0]])    # (x, y, 0) -> (x, 0, y)
    axis = gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
    solids = []
    for poly in _polygons(geometry):
        f = brep.transform(face(poly), to_xz)
        if sweep_deg >= 360.0 - 1e-6:
            solids.append(BRepPrimAPI_MakeRevol(f, axis).Shape())
        else:
            solids.append(BRepPrimAPI_MakeRevol(f, axis, math.radians(sweep_deg)).Shape())
    if not solids:
        raise ValueError("nothing to revolve")
    shape = _compound(solids)
    if abs(start_deg) > 1e-12:
        c, s = math.cos(math.radians(start_deg)), math.sin(math.radians(start_deg))
        shape = brep.transform(shape, np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1.0, 0]]))
    return _checked(brep.transform(shape, matrix))


def _checked(shape):
    from omacad.model import brep
    if not brep.is_valid(shape):
        raise RuntimeError("the B-rep solid is not valid")
    if brep.volume(shape) <= 1e-12:
        raise ValueError("the B-rep solid has no volume")
    return shape
