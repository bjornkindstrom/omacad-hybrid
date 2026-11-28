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


# -- Fillet where two lines cross ---------------------------------------------------------------------------------
# Two overlapping rectangles meet in crossings, not at line ends, so their inner corners are no corners to the plain
# fillet. A crossing has four quadrants; the one that faces the mouse is rounded: both lines are broken at the
# crossing and the two arms bounding that quadrant get the arc. The arms on the far side stay, so the shapes keep
# their closed profiles (the overlap and the rest).

def _unit(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > EPS else None


def _along(line: SketchLine, pt) -> float:
    d = _unit(line.p1, line.p2)
    return (pt[0] - line.p1[0]) * d[0] + (pt[1] - line.p1[1]) * d[1]


def line_crossings(sketch, tol: float = 1e-4):
    """(point, line a, line b) where two drawn lines cross inside at least one of them (an X or a T); where both
    end at the point it is an ordinary corner and left out."""
    lines = [e for e in sketch.entities if isinstance(e, SketchLine) and not e.is_construction
             and math.dist(e.p1, e.p2) > EPS]
    out = []
    for i, la in enumerate(lines):
        da = _unit(la.p1, la.p2)
        La = math.dist(la.p1, la.p2)
        for lb in lines[i + 1:]:
            db = _unit(lb.p1, lb.p2)
            cross = da[0] * db[1] - da[1] * db[0]
            if abs(cross) < 1e-6:
                continue                                           # parallel: no corner
            wx, wy = lb.p1[0] - la.p1[0], lb.p1[1] - la.p1[1]
            ta = (wx * db[1] - wy * db[0]) / cross
            tb = (wx * da[1] - wy * da[0]) / cross
            Lb = math.dist(lb.p1, lb.p2)
            if not (-tol <= ta <= La + tol and -tol <= tb <= Lb + tol):
                continue
            inside_a, inside_b = tol < ta < La - tol, tol < tb < Lb - tol
            if inside_a or inside_b:
                out.append(((la.p1[0] + da[0] * ta, la.p1[1] + da[1] * ta), la, lb))
    return out


def crossing_signs(la: SketchLine, lb: SketchLine, pt, toward) -> Tuple[int, int]:
    """Which arm of each line bounds the quadrant facing `toward` (+1 = towards the line's p2, -1 = towards p1).
    A line that ends at the crossing has only one arm."""
    signs = []
    for line in (la, lb):
        t, L = _along(line, pt), math.dist(line.p1, line.p2)
        if t <= 1e-4:
            signs.append(1)
        elif t >= L - 1e-4:
            signs.append(-1)
        else:
            d = _unit(line.p1, line.p2)
            signs.append(1 if (toward[0] - pt[0]) * d[0] + (toward[1] - pt[1]) * d[1] >= 0 else -1)
    return signs[0], signs[1]


def _line_through(sketch, line_id: str, direction, pt) -> Optional[SketchLine]:
    """The line `line_id`, or (after an earlier break moved the crossing onto a new piece) the collinear piece of it
    that passes through pt."""
    def through(line):
        d = _unit(line.p1, line.p2)
        if d is None or abs(d[0] * direction[1] - d[1] * direction[0]) > 1e-6:
            return False
        t = _along(line, pt)
        foot = (line.p1[0] + d[0] * t, line.p1[1] + d[1] * t)
        return math.dist(foot, pt) < 1e-6 and -1e-6 <= t <= math.dist(line.p1, line.p2) + 1e-6
    first = sketch.get_entity(line_id)
    if isinstance(first, SketchLine) and through(first):
        return first
    return next((e for e in sketch.entities if isinstance(e, SketchLine) and not e.is_construction and through(e)), None)


def _arm(sketch, line: SketchLine, pt, sign: int) -> SketchLine:
    """The piece of the line that runs from pt in direction `sign`, breaking the line at pt when pt is inside it."""
    t, L = _along(line, pt), math.dist(line.p1, line.p2)
    if 1e-6 < t < L - 1e-6:
        piece = apply_break(sketch, (line, pt))           # line keeps p1..pt, piece takes pt..p2
        return piece if sign > 0 else line
    return line


def fillet_crossing(sketch, pt, id_a: str, dir_a, id_b: str, dir_b, signs, radius: float):
    """Rounds one quadrant of the crossing at pt (see crossing_signs) with an arc of `radius`: (arc, message)."""
    la, lb = _line_through(sketch, id_a, dir_a, pt), _line_through(sketch, id_b, dir_b, pt)
    if la is None or lb is None:
        return None, "The lines no longer cross there."
    arm_a = _arm(sketch, la, pt, signs[0])
    arm_b = _arm(sketch, lb, pt, signs[1])
    return sketch.fillet_corner(arm_a, arm_b, radius, pt)
