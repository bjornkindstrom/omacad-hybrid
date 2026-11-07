"""Linked hole clearances (#216 follow-up): a pattern copy linked to its master circle also follows the master's
distance to the walls.

A rim/centre-to-line dimension on the master gets a "follower" dimension on every linked copy that sits the same
distance from a parallel wall (the mirrored wall for corner patterns). Changing the master's value moves the copies
with it; editing a follower directly unlinks it."""

import math
from typing import List, Optional, Set

from omacad.model.sketch_entities import SketchCircle, SketchLine


def linked_circles(sketch, eid: str) -> Set[str]:
    """Circles joined to `eid` by EQUAL constraints (the linked pattern holes), `eid` excluded."""
    found, pending = {eid}, [eid]
    while pending:
        current = pending.pop()
        for c in sketch.constraints:
            if c.ctype == "EQUAL" and current in c.refs:
                for other in c.refs:
                    if other not in found:
                        found.add(other)
                        pending.append(other)
    found.discard(eid)
    return {i for i in found if isinstance(sketch.get_entity(i), SketchCircle)}


def _unit(line):
    (x1, y1), (x2, y2) = line.p1, line.p2
    length = math.hypot(x2 - x1, y2 - y1)
    return ((x2 - x1) / length, (y2 - y1) / length) if length > 1e-9 else None


def _distance(point, line) -> float:
    u = _unit(line)
    return abs((point[0] - line.p1[0]) * u[1] - (point[1] - line.p1[1]) * u[0])


def _parallel(a, b) -> bool:
    ua, ub = _unit(a), _unit(b)
    return ua is not None and ub is not None and abs(ua[0] * ub[1] - ua[1] * ub[0]) < 1e-4


def _master_dim(dim, sketch) -> Optional[SketchLine]:
    """The wall of a dimension that can lead linked holes, or None."""
    if dim.dim_type != "PT_LINE_DIST" or dim.follows or not dim.refs or not dim.pts:
        return None
    if dim.pts[0] not in ("center", "edge_near", "edge_far"):
        return None
    if not isinstance(sketch.get_entity(dim.target_entity_id), SketchCircle):
        return None
    wall = sketch.get_entity(dim.refs[0])
    return wall if isinstance(wall, SketchLine) and _unit(wall) is not None else None


def followers(sketch, dim_id: str) -> List:
    return [d for d in sketch.dimensions if d.follows == dim_id]


def link_clearances(sketch, dims=None) -> List:
    """Adds follower dimensions for `dims` (default: every master clearance) on linked copies that currently mirror
    the master's distance to a parallel wall. Call before solving a new value. Returns the new followers."""
    added = []
    for dim in list(sketch.dimensions if dims is None else dims):
        wall = _master_dim(dim, sketch)
        if wall is None:
            continue
        master = sketch.get_entity(dim.target_entity_id)
        want = _distance(master.center, wall)
        tol = 1e-3 * max(1.0, want)
        walls = [e for e in sketch.entities if isinstance(e, SketchLine) and not e.is_construction
                 and _unit(e) is not None and _parallel(e, wall)]
        led = {d.target_entity_id for d in followers(sketch, dim.dim_id)}
        for cid in sorted(linked_circles(sketch, master.entity_id) - led):
            copy = sketch.get_entity(cid)
            if abs(copy.radius - master.radius) > tol:
                continue
            if any(d.dim_type == "PT_LINE_DIST" and d.target_entity_id == cid and d.refs
                   and isinstance(sketch.get_entity(d.refs[0]), SketchLine)
                   and _parallel(sketch.get_entity(d.refs[0]), wall) for d in sketch.dimensions):
                continue  # the copy has its own clearance in this direction
            fits = [w for w in walls if abs(_distance(copy.center, w) - want) <= tol]
            if not fits:
                continue
            target = wall if wall in fits else fits[0]
            sketch.add_dimension("PT_LINE_DIST", cid, dim.value, offset_distance=dim.offset_distance,
                                 refs=[target.entity_id], pts=list(dim.pts))
            new = sketch.dimensions[-1]
            new.follows = dim.dim_id
            new.moving_entity_id = cid
            added.append(new)
    return added


def push_value(sketch, dim) -> None:
    """Copy a master clearance's value (and formula) to its followers."""
    for f in followers(sketch, dim.dim_id):
        f.value = dim.value
        f.expr = None


def follower_walls(sketch, dim) -> List[str]:
    return [f.refs[0] for f in followers(sketch, dim.dim_id) if f.refs]
