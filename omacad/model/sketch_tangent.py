"""Tangent magnet for the 3-point Arc tool: when the arc being drawn leaves (or meets) a line or arc that ends at one
of its end points almost smoothly, the third point is moved so it is exactly tangent there (Björn #53)."""

import math
from typing import Iterable, Optional, Tuple

from omacad.model.sketch_entities import SketchArc, SketchLine

UV = Tuple[float, float]
TOL_DEG = 8.0      # how close to smooth the arc must be before it sticks
NEAR = 1e-4        # an end point is shared when closer than this


def _unit(x: float, y: float) -> Optional[UV]:
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 1e-12 else None


def _same(a: UV, b: UV) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) < NEAR


def arc_out_direction(start: UV, mid: UV, end: UV, at_end: bool = False) -> Optional[UV]:
    """Unit direction the arc start -> mid -> end leaves `start` in (at_end: arrives at `end` in)."""
    params = SketchArc("tmp", start, mid, end).get_circle_params()
    if params is None:
        return None
    (cx, cy), _, a1, a3, ccw = params
    a = a3 if at_end else a1
    t = (-math.sin(a), math.cos(a)) if ccw else (math.sin(a), -math.cos(a))
    return t


def _neighbour_directions(entities: Iterable, refs: Iterable, point: UV):
    """Directions to continue smoothly out of `point` from every line / arc / face edge that ends there."""
    for e in entities:
        if isinstance(e, SketchLine):
            for here, other in ((e.p1, e.p2), (e.p2, e.p1)):
                if _same(here, point):
                    d = _unit(here[0] - other[0], here[1] - other[1])
                    if d:
                        yield d
        elif isinstance(e, SketchArc):
            if _same(e.p_end, point):
                d = arc_out_direction(e.p_start, e.p_mid, e.p_end, at_end=True)
                if d:
                    yield d
            if _same(e.p_start, point):
                d = arc_out_direction(e.p_start, e.p_mid, e.p_end)
                if d:
                    yield (-d[0], -d[1])
    for a, b in refs:
        for here, other in ((a, b), (b, a)):
            if _same(here, point):
                d = _unit(here[0] - other[0], here[1] - other[1])
                if d:
                    yield d


def tangent_arc_mid(start: UV, end: UV, direction: UV) -> Optional[UV]:
    """The point halfway along the arc that leaves `start` along `direction` and ends at `end`."""
    n = (-direction[1], direction[0])
    cx, cy = end[0] - start[0], end[1] - start[1]
    k = n[0] * cx + n[1] * cy
    if abs(k) < 1e-9:                       # end straight ahead: that is a line, not an arc
        return None
    s = (cx * cx + cy * cy) / (2.0 * k)
    centre = (start[0] + s * n[0], start[1] + s * n[1])
    r = abs(s)
    # travel direction around the centre, then the angle halfway between start and end along it
    ccw = s > 0
    a1 = math.atan2(start[1] - centre[1], start[0] - centre[0])
    a3 = math.atan2(end[1] - centre[1], end[0] - centre[0])
    sweep = (a3 - a1) % (2 * math.pi) if ccw else -((a1 - a3) % (2 * math.pi))
    am = a1 + sweep / 2.0
    return (centre[0] + r * math.cos(am), centre[1] + r * math.sin(am))


def snap_tangent_arc(start: UV, end: UV, cursor: UV, entities: Iterable, refs: Iterable = (),
                     tol_deg: float = TOL_DEG) -> Optional[UV]:
    """The third point that makes the arc start -> cursor -> end exactly tangent at `start` or `end` to a line, arc or
    face edge ending there, when it already is within `tol_deg`; None when it is not close to smooth anywhere."""
    entities, refs = list(entities), list(refs)
    best = None
    for here, other, at_end in ((start, end, False), (end, start, True)):
        now = arc_out_direction(start, cursor, end, at_end=at_end)
        if now is None:
            continue
        if at_end:                          # leaving `end` backwards along the arc
            now = (-now[0], -now[1])
        for d in _neighbour_directions(entities, refs, here):
            off = math.degrees(math.acos(max(-1.0, min(1.0, now[0] * d[0] + now[1] * d[1]))))
            if off <= tol_deg and (best is None or off < best[0]):
                mid = tangent_arc_mid(here, other, d)
                if mid is not None:
                    best = (off, mid)
    return None if best is None else best[1]
