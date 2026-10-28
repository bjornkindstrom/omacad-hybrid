"""Hatching for the cut face of a section view: diagonal lines clipped to the cut, plus its outline (as in Fusion 360)."""
import math
from typing import List, Tuple

import numpy as np
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import unary_union


def cut_shape(polygons) -> "Polygon":
    """Counter-clockwise rings are material, clockwise rings are holes (the orientation Manifold's CrossSection uses)."""
    solids, holes = [], []
    for ring in polygons:
        pts = [(float(x), float(y)) for x, y in ring]
        if len(pts) < 3:
            continue
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue
        signed = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        (solids if signed >= 0 else holes).append(poly)
    shape = unary_union(solids) if solids else Polygon()
    return shape.difference(unary_union(holes)) if holes else shape


def _segments(geom) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    out = []
    parts = getattr(geom, "geoms", [geom])
    for g in parts:
        if g.is_empty:
            continue
        if hasattr(g, "geoms"):
            out += _segments(g)
        elif g.geom_type == "LineString":
            c = list(g.coords)
            out += [((c[i][0], c[i][1]), (c[i + 1][0], c[i + 1][1])) for i in range(len(c) - 1)]
    return out


def hatch_and_outline(polygons, spacing: float, angle_deg: float = 45.0):
    """(hatch segments, outline segments) of the cut in its own 2D coordinates, as float arrays of shape (n, 2, 2)."""
    shape = cut_shape(polygons)
    if shape.is_empty or spacing <= 0:
        return np.zeros((0, 2, 2)), np.zeros((0, 2, 2))
    outline = _segments(shape.boundary)
    minx, miny, maxx, maxy = shape.bounds
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    reach = math.hypot(maxx - minx, maxy - miny) / 2.0 + spacing
    a = math.radians(angle_deg)
    d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    count = int(reach / spacing)
    lines = [LineString([(cx + n[0] * k * spacing - d[0] * reach, cy + n[1] * k * spacing - d[1] * reach),
                         (cx + n[0] * k * spacing + d[0] * reach, cy + n[1] * k * spacing + d[1] * reach)])
             for k in range(-count, count + 1)]
    hatch = _segments(shape.intersection(MultiLineString(lines)))
    return np.asarray(hatch, dtype=float).reshape(-1, 2, 2), np.asarray(outline, dtype=float).reshape(-1, 2, 2)
