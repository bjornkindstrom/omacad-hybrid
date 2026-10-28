"""Sketch Pattern (Björn #75): copies of the picked sketch elements in rows and columns, or around a centre.

Copies are free elements with new ids (no constraints or dimensions follow along), like Fusion's sketch pattern
without the pattern constraint."""

import copy
from typing import Iterable, List, Tuple

from omacad.model.sketch import move_entity, rotate_entity


def _fresh(sk, ent):
    new = copy.deepcopy(ent)
    new.entity_id = sk._new_entity_id(ent.entity_id.rsplit("_", 1)[0])
    if hasattr(new, "group"):
        new.group = None
    if getattr(new, "fillet_info", None):
        new.fillet_info = {}
    return new


def rectangular_copies(sk, ents: Iterable, count_x: int, spacing_x: float, count_y: int = 1,
                       spacing_y: float = 0.0) -> List:
    """Adds the copies to `sk` (the originals are the first cell) and returns them."""
    ents = list(ents)
    out = []
    for i in range(max(1, int(count_x))):
        for j in range(max(1, int(count_y))):
            if i == 0 and j == 0:
                continue
            for e in ents:
                c = _fresh(sk, e)
                move_entity(c, i * spacing_x, j * spacing_y)
                sk.entities.append(c)
                out.append(c)
    return out


def circular_copies(sk, ents: Iterable, count: int, centre: Tuple[float, float], angle: float = 360.0) -> List:
    """`count` instances in all (the originals included), spread evenly over `angle` degrees about `centre`; a full
    turn does not repeat the first one."""
    ents = list(ents)
    n = max(1, int(count))
    step = angle / n if abs(abs(angle) - 360.0) < 1e-6 else (angle / (n - 1) if n > 1 else 0.0)
    out = []
    for k in range(1, n):
        for e in ents:
            c = _fresh(sk, e)
            rotate_entity(c, k * step, centre)
            sk.entities.append(c)
            out.append(c)
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
