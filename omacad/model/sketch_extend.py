"""Extend and Break for sketch lines (Fusion's Extend / Break).

Extend: the end of a line nearest the click grows straight on to the first curve it meets (a line, circle, arc or
spline); the end stays on that curve (a relation) and the line's length dimension follows.
Break: a line is cut in two where it is clicked (at a crossing with another curve when the click is near one); the
two pieces stay joined and in line, and relations and dimensions on the old ends move with them."""
from __future__ import annotations

import math
from typing import Optional, Tuple

from omacad.model.sketch_entities import SketchArc, SketchCircle, SketchLine
from omacad.model.sketch_trim import _line_hits

REACH = 1e6         # mm: how far an extension looks for something to meet
EPS = 1e-6


def _nearest_line(sketch, u: float, v: float, tol: float) -> Optional[Tuple[SketchLine, float]]:
    """(line, position 0..1 of the click's foot) for the line nearest the click within tol."""
    best = None
    for e in sketch.entities:
        if not isinstance(e, SketchLine) or getattr(e, "projected", False):
            continue
        dx, dy = e.p2[0] - e.p1[0], e.p2[1] - e.p1[1]
        L2 = dx * dx + dy * dy
        if L2 < EPS * EPS:
            continue
        t = max(0.0, min(1.0, ((u - e.p1[0]) * dx + (v - e.p1[1]) * dy) / L2))
        d = math.hypot(u - (e.p1[0] + t * dx), v - (e.p1[1] + t * dy))
        if d <= tol and (best is None or d < best[0]):
            best = (d, e, t)
    return (best[1], best[2]) if best else None


def extend_plan(sketch, u: float, v: float, tol: float):
    """(line, end name, new end point, the entity it meets) or None when the click is on no line or the end meets
    nothing going on."""
    hit = _nearest_line(sketch, u, v, tol)
    if hit is None:
        return None
    line, t = hit
    end = "p2" if t >= 0.5 else "p1"
    tip, other_end = (line.p2, line.p1) if end == "p2" else (line.p1, line.p2)
    L = math.dist(tip, other_end)
    d = ((tip[0] - other_end[0]) / L, (tip[1] - other_end[1]) / L)
    best = None
    for other in sketch.entities:
        if other is line or getattr(other, "entity_type", "") in ("text",):
            continue
        for s in _line_hits(tip, d, REACH, other):
            if s > 1e-4 and (best is None or s < best[0]):
                best = (s, other)
    if best is None:
        return None
    s, other = best
    return line, end, (tip[0] + d[0] * s, tip[1] + d[1] * s), other


def apply_extend(sketch, plan) -> None:
    """Moves the end, keeps it on what it met and gives the line's length dimension its new length."""
    from omacad.model.sketch_types import SketchConstraint
    line, end, point, other = plan
    setattr(line, end, (float(point[0]), float(point[1])))
    length = math.dist(line.p1, line.p2)
    for d in sketch.dimensions:
        if d.target_entity_id == line.entity_id and d.dim_type == "LENGTH":
            d.value = length
            d.expr = None
    if isinstance(other, SketchLine):
        rel = ("POINT_ON_LINE", [line.entity_id, other.entity_id], [end])
    elif isinstance(other, (SketchCircle, SketchArc)):
        rel = ("POINT_ON_CIRCLE", [other.entity_id, line.entity_id], [end])
    else:
        rel = None
    if rel is not None:
        sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), rel[0], rel[1], rel[2]))


def break_plan(sketch, u: float, v: float, tol: float):
    """(line, split point) or None. The split goes to a crossing with another curve when one is within tol of the
    click, otherwise to the click's foot on the line; never at the line's own ends."""
    hit = _nearest_line(sketch, u, v, tol)
    if hit is None:
        return None
    line, t = hit
    L = math.dist(line.p1, line.p2)
    d = ((line.p2[0] - line.p1[0]) / L, (line.p2[1] - line.p1[1]) / L)
    at = t * L
    crossings = [s for other in sketch.entities if other is not line for s in _line_hits(line.p1, d, L, other)]
    near = [s for s in crossings if abs(s - at) <= tol]
    if near:
        at = min(near, key=lambda s: abs(s - at))
    if at < tol * 0.5 or at > L - tol * 0.5:
        return None
    return line, (line.p1[0] + d[0] * at, line.p1[1] + d[1] * at)


def apply_break(sketch, plan) -> SketchLine:
    """Cuts the line at the point: the old line keeps its start, a new line takes the rest. Joined and parallel, so
    they stay one straight line; whatever was on the old end point is moved to the new piece."""
    from omacad.model.sketch_types import SketchConstraint
    line, point = plan
    old_end = line.p2
    line.p2 = (float(point[0]), float(point[1]))
    piece = SketchLine(sketch._new_entity_id("line"), line.p2, old_end, is_construction=line.is_construction)
    sketch.entities.insert(sketch.entities.index(line) + 1, piece)
    lid, pid = line.entity_id, piece.entity_id
    for c in sketch.constraints:            # relations on the old end point now belong to the new piece
        if c.ctype == "POINT_ON_CIRCLE":    # refs (curve, line), pts [the line's point]
            if len(c.refs) > 1 and c.refs[1] == lid and c.pts and c.pts[0] == "p2":
                c.refs[1] = pid
            continue
        for i, (ref, name) in enumerate(zip(c.refs, c.pts)):
            if ref == lid and name == "p2":
                c.refs[i] = pid
    for dim in sketch.dimensions:
        if dim.target_entity_id == lid and dim.pts and dim.pts[0] == "p2":
            dim.target_entity_id = pid
        if dim.refs and len(dim.pts) > 1 and dim.refs[0] == lid and dim.pts[1] == "p2":
            dim.refs[0] = pid
        if dim.target_entity_id == lid and dim.dim_type == "LENGTH":
            dim.value, dim.expr = math.dist(line.p1, line.p2), None
    sketch.add_dimension("LENGTH", pid, math.dist(piece.p1, piece.p2), offset_distance=12.0, name="Length")
    sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "COINCIDENT", [lid, pid], ["p2", "p1"]))
    sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "PARALLEL", [lid, pid], []))
    return piece


def chamfer_plan(sketch, corner, line_a_id: str, line_b_id: str, distance: float):
    """(line a, its corner end, line b, its corner end, new end a, new end b) for an equal-distance chamfer of the
    corner where two lines meet, or None (not two lines meeting there, or the chamfer longer than a line)."""
    la, lb = sketch.get_entity(line_a_id), sketch.get_entity(line_b_id)
    if not (isinstance(la, SketchLine) and isinstance(lb, SketchLine)) or distance <= 1e-6:
        return None
    ends = []
    for ln in (la, lb):
        end = min(("p1", "p2"), key=lambda n: math.dist(getattr(ln, n), corner))
        if math.dist(getattr(ln, end), corner) > 1e-3:
            return None
        tip, far = getattr(ln, end), getattr(ln, "p2" if end == "p1" else "p1")
        L = math.dist(tip, far)
        if distance >= L - 1e-3:
            return None
        ends.append((end, (tip[0] + (far[0] - tip[0]) / L * distance, tip[1] + (far[1] - tip[1]) / L * distance)))
    return la, ends[0][0], lb, ends[1][0], ends[0][1], ends[1][1]


def apply_chamfer(sketch, plan) -> SketchLine:
    """Cuts the corner off with a straight line: both lines end where it starts, joined to it, and their length
    dimensions follow; the corner's own join is dropped (the lines no longer meet)."""
    from omacad.model.sketch_types import SketchConstraint
    la, ea, lb, eb, pa, pb = plan
    a_id, b_id = la.entity_id, lb.entity_id
    sketch.constraints = [c for c in sketch.constraints
                          if not (c.ctype == "COINCIDENT" and set(c.refs) == {a_id, b_id})]
    setattr(la, ea, (float(pa[0]), float(pa[1])))
    setattr(lb, eb, (float(pb[0]), float(pb[1])))
    for ln in (la, lb):
        for d in sketch.dimensions:
            if d.target_entity_id == ln.entity_id and d.dim_type == "LENGTH":
                d.value, d.expr = math.dist(ln.p1, ln.p2), None
    cut = sketch.add_line(getattr(la, ea), getattr(lb, eb), is_construction=la.is_construction and lb.is_construction)
    sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "COINCIDENT", [a_id, cut.entity_id], [ea, "p1"]))
    sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "COINCIDENT", [b_id, cut.entity_id], [eb, "p2"]))
    return cut
