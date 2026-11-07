"""Sketch Pattern (Björn #75): copies of the picked sketch elements in rows and columns, or around a centre.

Copies have new ids and independent positions. Circles share the original diameter by default;
turn linking off for independent hole sizes."""

import copy
from typing import Iterable, List, Tuple

from omacad.model.sketch import SketchCircle, SketchConstraint, move_entity, rotate_entity


def _fresh(sk, ent, linked=True):
    new = copy.deepcopy(ent)
    new.entity_id = sk._new_entity_id(ent.entity_id.rsplit("_", 1)[0])
    if hasattr(new, "group"):
        new.group = None
    if getattr(new, "fillet_info", None):
        new.fillet_info = {}
    if linked and isinstance(ent, SketchCircle):
        sk.constraints.append(SketchConstraint(sk.new_constraint_id(), "EQUAL",
                                               [ent.entity_id, new.entity_id]))
    return new


def rectangular_copies(sk, ents: Iterable, count_x: int, spacing_x: float, count_y: int = 1,
                       spacing_y: float = 0.0, *, linked: bool = True) -> List:
    """Adds the copies to `sk` (the originals are the first cell) and returns them."""
    ents = list(ents)
    out = []
    for i in range(max(1, int(count_x))):
        for j in range(max(1, int(count_y))):
            if i == 0 and j == 0:
                continue
            for e in ents:
                c = _fresh(sk, e, linked)
                move_entity(c, i * spacing_x, j * spacing_y)
                sk.entities.append(c)
                out.append(c)
    return out


def circular_copies(sk, ents: Iterable, count: int, centre: Tuple[float, float], angle: float = 360.0, *, linked: bool = True) -> List:
    """`count` instances in all (the originals included), spread evenly over `angle` degrees about `centre`; a full
    turn does not repeat the first one."""
    ents = list(ents)
    n = max(1, int(count))
    step = angle / n if abs(abs(angle) - 360.0) < 1e-6 else (angle / (n - 1) if n > 1 else 0.0)
    out = []
    for k in range(1, n):
        for e in ents:
            c = _fresh(sk, e, linked)
            rotate_entity(c, k * step, centre)
            sk.entities.append(c)
            out.append(c)
    return out


def corner_bounds(sk, ents):
    """Bounds of the smallest surrounding closed outline, excluding the copied geometry."""
    from shapely import build_area
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    ids = {e.entity_id for e in ents}
    segments = [seg for e in sk.entities if e.entity_id not in ids and not e.is_construction
                for seg in e.to_lines()]
    if not segments:
        return None
    area = build_area(unary_union([LineString(seg) for seg in segments]))
    polygons = list(area.geoms) if hasattr(area, "geoms") else [area]
    points = _outline_points(ents)
    candidates = []
    for polygon in polygons:
        if polygon.is_empty or polygon.area <= 1e-9:
            continue
        region = polygon.buffer(1e-6)
        if all(region.covers(Point(pt)) for pt in points):
            candidates.append(polygon)
    return min(candidates, key=lambda p: p.area).bounds if candidates else None


def corner_copies(sk, ents, bounds, *, linked: bool = True):
    """Repeat the selection at the four corners with the same inset and orientation."""
    ents = list(ents)
    if bounds is None or not ents:
        return []
    left, bottom, right, top = bounds
    x, y = selection_centre(ents)
    dx, dy = left + right - 2 * x, bottom + top - 2 * y
    offsets = {(round(a, 9), round(b, 9)) for a, b in ((dx, 0), (0, dy), (dx, dy))}
    offsets.discard((0., 0.))
    out = []
    for a, b in sorted(offsets):
        for ent in ents:
            new = _fresh(sk, ent, linked)
            move_entity(new, a, b)
            sk.entities.append(new)
            out.append(new)
    return out


def _outline_points(ents):
    """Points along the drawn outline (a circle's rim too, not only its centre)."""
    return [p for e in ents for seg in e.to_lines() for p in seg]


def selection_centre(ents: Iterable) -> Tuple[float, float]:
    pts = _outline_points(list(ents))
    if not pts:
        return 0.0, 0.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def default_spacing(ents: Iterable, gap_ratio: float = 0.5) -> Tuple[float, float]:
    """Spacing that puts copies side by side with a gap of half their size: a sensible start for the sliders."""
    pts = _outline_points(list(ents))
    if not pts:
        return 10.0, 10.0
    w = max(p[0] for p in pts) - min(p[0] for p in pts)
    h = max(p[1] for p in pts) - min(p[1] for p in pts)
    return (max(w, 1.0) * (1 + gap_ratio), max(h, 1.0) * (1 + gap_ratio))
