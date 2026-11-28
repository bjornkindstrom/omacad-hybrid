"""Loose ends of almost-closed outlines in a sketch (sketch plan step 7).

A chain of two or more curves that does not close leaves an end that touches nothing: that is usually the gap that
keeps a profile from forming. A lone line is left alone, since drawing one is not a mistake.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple

UV = Tuple[float, float]


def _point_segment_distance(p: UV, a: UV, b: UV) -> float:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 <= 0.0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def open_ends(sketch, tol: float = 1e-4) -> List[UV]:
    """The free ends of open chains: an end of a curve that meets no other curve, on a curve whose other end does."""
    curves: List[Tuple[UV, UV, Sequence[Tuple[UV, UV]]]] = []
    for ent in sketch.entities:
        if getattr(ent, "is_construction", False) or getattr(ent, "entity_type", "") == "point":
            continue
        try:
            segs = ent.to_lines()
        except Exception:
            continue
        if not segs:
            continue
        start, end = tuple(segs[0][0]), tuple(segs[-1][1])
        if math.hypot(start[0] - end[0], start[1] - end[1]) <= tol:
            continue                                   # a circle or a closed spline has no ends
        curves.append((start, end, segs))
    if len(curves) < 2:
        return []

    def touches(p: UV, own: int) -> bool:
        for j, (_s, _e, segs) in enumerate(curves):
            if j != own and any(_point_segment_distance(p, a, b) <= tol for a, b in segs):
                return True
        return False

    out: List[UV] = []
    for i, (start, end, _segs) in enumerate(curves):
        free_start, free_end = not touches(start, i), not touches(end, i)
        if free_start != free_end:                     # joined at one end only: the other is a gap
            out.append(start if free_start else end)
    return out
