"""
Omacad - Sketch constraint solver (SolveSpace)

Translates a Sketch (lines + circles, constraints, and the dimensions that apply to them)
into a SolveSpace system, solves it and writes the new coordinates back.
Rectangles, arcs and slots are not part of the solver yet and keep their coordinates; a fillet arc's
two lines are solved as the sharp corner it rounds (Sketch.refit_fillets puts the arc back after).
"""

import math
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from python_solvespace import SolverSystem

from omacad.model.sketch import Sketch, SketchLine, SketchCircle, SOLVER_DIM_TYPES, EDGE_PTS, point_of, ref_segment

SUPPORTED = (SketchLine, SketchCircle)
FIXED_GROUP, FREE_GROUP = 1, 2


@dataclass
class SolveResult:
    ok: bool
    dof: Optional[int] = None
    message: str = ""


def solve_sketch(sketch: Sketch, fixed_ids: Iterable[str] = (), pinned: Iterable[Tuple[str, str]] = ()) -> SolveResult:
    """Enforces the sketch's constraints in place. Geometry is only modified on success.

    fixed_ids: entities held exactly where they are (e.g. just moved by the user); the
    connected geometry adjusts around them.
    pinned: (entity_id, point_name) pairs held in place, e.g. the start of a line whose length
    dimension is being edited, so the line grows from that end.
    """
    _measure_from_walls(sketch)
    ents = {e.entity_id: e for e in sketch.entities if isinstance(e, SUPPORTED)}
    if not sketch.constraints and not any(d.dim_type in SOLVER_DIM_TYPES for d in sketch.dimensions):
        sketch.dof = None
        return SolveResult(True, None, "")
    fixed = {c.refs[0] for c in sketch.constraints if c.ctype == "FIX" and c.refs} | set(fixed_ids)

    corners = _sharp_corners(sketch, ents)
    sol, msg = _attempt(sketch, ents, fixed, True, tuple(pinned), corners)
    if sol is None and not msg.startswith("Constraints would collapse"):
        # SolveSpace reports redundant-but-consistent systems (e.g. a closed triangle with all
        # three lengths dimensioned) as failures: retry without dimensions and accept the
        # result if the dimensions happen to hold.
        alt, _ = _attempt(sketch, ents, fixed, False, tuple(pinned), corners)
        if alt is not None and _dims_hold(sketch, ents, alt[0], corners):
            sol, msg = alt, ""
    if sol is None:
        sketch.dof = None
        return SolveResult(False, None, msg)

    values, dof = sol
    for eid, ent in ents.items():
        if isinstance(ent, SketchLine):
            ent.p1, ent.p2 = values[eid]
        else:
            ent.center = values[eid]
            if f"{eid}#r" in values:
                ent.radius = values[f"{eid}#r"]
    sketch.dof = dof
    sketch.refit_fillets()
    sketch.solve_profiles()
    return SolveResult(True, dof, "")


def _measure_from_walls(sketch) -> None:
    """A distance measured from a rounded corner's guide line is moved over to the wall the guide carries on (#100):
    the guide is free in the solver and re-seated afterwards, so the solver moved the guide instead of the point."""
    walls = sketch.corner_guide_walls()
    if not walls:
        return
    for d in sketch.dimensions:
        if d.dim_type == "PT_LINE_DIST" and d.refs and d.refs[0] in walls:
            d.refs = [walls[d.refs[0]], *d.refs[1:]]


def _sharp_corners(sketch, ents) -> list:
    """(line_a, end_a, line_b, end_b, corner, trim_a, trim_b) for every fillet between two solver lines. The arc is
    not in the solver, so lengthening one side left its neighbour where it was and the refit pulled the side back;
    solved as the sharp corner, the neighbour follows, and a length dimension (which measures the flat) becomes
    flat + the trims at its ends."""
    corners = []
    for arc in sketch.entities:
        corner = sketch.sharp_corner(arc)
        info = getattr(arc, "fillet_info", None)
        if corner is None or info["line_a"] not in ents or info["line_b"] not in ents:
            continue
        trims = [math.hypot(p[0] - corner[0], p[1] - corner[1]) for p in (arc.p_start, arc.p_end)]
        corners.append((info["line_a"], info["end_a"], info["line_b"], info["end_b"], corner, *trims))
    return corners


def _length_add(corners) -> Dict[str, float]:
    add: Dict[str, float] = {}
    for la, _, lb, _, _, ta, tb in corners:
        add[la] = add.get(la, 0.0) + ta
        add[lb] = add.get(lb, 0.0) + tb
    return add


def _dims_hold(sketch, ents, values, corners=(), tol=1e-4) -> bool:
    """Do the dimensions hold for these solved coordinates? (used to accept redundant systems)"""
    def pos(eid, name):
        v = values[eid]
        if isinstance(ents[eid], SketchLine):
            return v[0] if name == "p1" else v[1]
        return v

    def line_vec(eid):
        (x1, y1), (x2, y2) = values[eid]
        return x2 - x1, y2 - y1

    add = _length_add(corners)
    for d in sketch.dimensions:
        a = d.target_entity_id
        if a not in ents:
            continue
        if d.dim_type == "LENGTH" and isinstance(ents[a], SketchLine):
            x, y = line_vec(a)
            if abs(math.hypot(x, y) - d.value - add.get(a, 0.0)) > tol * max(1.0, d.value):
                return False
        elif d.dim_type == "ANGLE" and d.refs and d.refs[0] in ents and len(d.pts) == 2:
            u = line_vec(a) if d.pts[0] == "p1" else tuple(-c for c in line_vec(a))
            w = line_vec(d.refs[0]) if d.pts[1] == "p1" else tuple(-c for c in line_vec(d.refs[0]))
            nu, nw = math.hypot(*u), math.hypot(*w)
            if nu < 1e-9 or nw < 1e-9:
                return False
            ang = math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * w[0] + u[1] * w[1]) / (nu * nw)))))
            if abs(ang - d.value) > 1e-3 * max(1.0, d.value):
                return False
        elif d.dim_type == "PT_LINE_DIST" and d.refs and d.pts:
            seg = ref_segment(d.refs[0])
            if seg is None and d.refs[0] in ents and isinstance(ents[d.refs[0]], SketchLine):
                seg = values[d.refs[0]]
            if seg is not None:
                P = pos(a, _pt_name(d.pts[0]))
                (x1, y1), (x2, y2) = seg
                L = math.hypot(x2 - x1, y2 - y1)
                if L > 1e-9:
                    dist = abs((P[0] - x1) * (y2 - y1) - (P[1] - y1) * (x2 - x1)) / L
                    want = _centre_distance(ents[a], d.pts[0], d.value) if isinstance(ents[a], SketchCircle) else d.value
                    if abs(dist - want) > tol * max(1.0, want) * 10:
                        return False
        elif d.dim_type in ("DISTANCE", "HORIZ_DIST", "VERT_DIST") and d.refs and d.refs[0] in ents and len(d.pts) == 2:
            pa, pb = pos(a, d.pts[0]), pos(d.refs[0], d.pts[1])
            dist = (math.hypot(pa[0] - pb[0], pa[1] - pb[1]) if d.dim_type == "DISTANCE"
                    else abs(pa[0] - pb[0]) if d.dim_type == "HORIZ_DIST" else abs(pa[1] - pb[1]))
            if abs(dist - d.value) > tol * max(1.0, d.value):
                return False
    return True


def _attempt(sketch, ents, fixed, use_dims, pinned=(), corners=()):
    ents = {e.entity_id: e for e in sketch.entities if isinstance(e, SUPPORTED)}

    sys_ = SolverSystem()
    wp = sys_.create_2d_base()
    pts: Dict[Tuple[str, str], object] = {}
    geo: Dict[str, object] = {}
    radii: Dict[str, object] = {}
    normal = None
    sharp = {}
    for la, ea, lb, eb, corner, _, _ in corners:
        sharp[(la, ea)] = sharp[(lb, eb)] = corner

    def build(ent):
        nonlocal normal
        if isinstance(ent, SketchLine):
            p1 = sharp.get((ent.entity_id, "p1"), ent.p1)
            p2 = sharp.get((ent.entity_id, "p2"), ent.p2)
            a = sys_.add_point_2d(p1[0], p1[1], wp)
            b = sys_.add_point_2d(p2[0], p2[1], wp)
            geo[ent.entity_id] = sys_.add_line_2d(a, b, wp)
            pts[(ent.entity_id, "p1")], pts[(ent.entity_id, "p2")] = a, b
        else:
            c = sys_.add_point_2d(ent.center[0], ent.center[1], wp)
            if normal is None:
                # the workplane normal is a constant: in the free group its quaternion counted as 3 extra
                # degrees of freedom, so a fully dimensioned sketch with a circle still said "under defined"
                sys_.set_group(FIXED_GROUP)
                normal = sys_.add_normal_3d(1.0, 0.0, 0.0, 0.0)
                sys_.set_group(FREE_GROUP if ent.entity_id not in fixed else FIXED_GROUP)
            r = sys_.add_distance(float(ent.radius), wp)
            geo[ent.entity_id] = sys_.add_circle(normal, c, r, wp)
            pts[(ent.entity_id, "center")] = c
            radii[ent.entity_id] = r

    # Fixed entities live in an earlier group so the solver treats them as constants
    sys_.set_group(FIXED_GROUP)
    for eid, ent in ents.items():
        if eid in fixed:
            build(ent)
    sys_.set_group(FREE_GROUP)
    for eid, ent in ents.items():
        if eid not in fixed:
            build(ent)

    for eid, pname in pinned:
        handle = pts.get((eid, pname))
        if handle is not None and eid not in fixed:
            sys_.dragged(handle, wp)

    def line(eid):
        return geo[eid] if isinstance(ents.get(eid), SketchLine) else None

    def circle(eid):
        return geo[eid] if isinstance(ents.get(eid), SketchCircle) else None

    def center_handle(line_ids):
        """Create an auxiliary solver point at the midpoint of a four-line loop's diagonal."""
        corners = []
        for eid in line_ids:
            ent = ents.get(eid)
            if not isinstance(ent, SketchLine):
                return None
            for name in ("p1", "p2"):
                uv = getattr(ent, name)
                handle = pts[(eid, name)]
                if not any(math.hypot(uv[0] - old[0][0], uv[1] - old[0][1]) < 1e-5 for old in corners):
                    corners.append((uv, handle))
        if len(corners) != 4:
            return None
        a, b = max(((a, b) for i, a in enumerate(corners) for b in corners[i + 1:]),
                   key=lambda pair: math.hypot(pair[0][0][0] - pair[1][0][0], pair[0][0][1] - pair[1][0][1]))
        center = (sum(pt[0][0] for pt in corners) / 4.0, sum(pt[0][1] for pt in corners) / 4.0)
        center_point = sys_.add_point_2d(center[0], center[1], wp)
        diagonal = sys_.add_line_2d(a[1], b[1], wp)
        sys_.midpoint(center_point, diagonal, wp)
        return center_point, center

    for c in sketch.constraints:
        if any(r not in ents for r in c.refs):
            continue  # references an entity the solver does not handle (e.g. rectangle)
        if c.ctype == "FIX" or all(r in fixed for r in c.refs):
            continue  # nothing free to solve for
        a = c.refs[0]
        b = c.refs[1] if len(c.refs) > 1 else None
        t = c.ctype
        if t == "HORIZONTAL" and line(a):
            sys_.horizontal(geo[a], wp)
        elif t == "VERTICAL" and line(a):
            sys_.vertical(geo[a], wp)
        elif t == "PARALLEL" and line(a) and line(b):
            sys_.parallel(geo[a], geo[b], wp)
        elif t == "PERPENDICULAR" and line(a) and line(b):
            sys_.perpendicular(geo[a], geo[b], wp)
        elif t == "EQUAL" and b and ((line(a) and line(b)) or (circle(a) and circle(b))):
            sys_.equal(geo[a], geo[b], wp)
        elif t == "CONCENTRIC" and circle(a) and circle(b):
            sys_.coincident(pts[(a, "center")], pts[(b, "center")], wp)
        elif t == "COINCIDENT" and b and len(c.pts) == 2:
            sys_.coincident(pts[(a, c.pts[0])], pts[(b, c.pts[1])], wp)
        elif t == "POINT_ON_CIRCLE" and circle(a) and b and line(b) and c.pts:
            sys_.coincident(pts[(b, c.pts[0])], geo[a], wp)
        elif t == "TANGENT" and b:
            _tangent(sys_, wp, ents, pts, geo, a, b)
        elif t == "MIDPOINT" and b and line(b) and c.pts and (a, c.pts[0]) in pts:
            sys_.midpoint(pts[(a, c.pts[0])], geo[b], wp)
        elif t == "SYMMETRIC" and len(c.refs) == 3 and len(c.pts) == 2 and line(c.refs[2]) and b \
                and (a, c.pts[0]) in pts and (b, c.pts[1]) in pts:
            sys_.symmetric(pts[(a, c.pts[0])], pts[(b, c.pts[1])], geo[c.refs[2]], wp)
        elif t == "CENTER" and len(c.refs) == 8:
            center_a = center_handle(c.refs[:4])
            center_b = center_handle(c.refs[4:])
            if center_a is not None and center_b is not None:
                reference_point, reference_uv = center_a
                target_point, _target_uv = center_b
                sys_.set_group(FIXED_GROUP)
                anchor = sys_.add_point_2d(reference_uv[0], reference_uv[1], wp)
                axis_start = sys_.add_point_2d(reference_uv[0], reference_uv[1] - 1.0, wp)
                axis_end = sys_.add_point_2d(reference_uv[0], reference_uv[1] + 1.0, wp)
                vertical_axis = sys_.add_line_2d(axis_start, axis_end, wp)
                sys_.set_group(FREE_GROUP)
                sys_.coincident(reference_point, anchor, wp)
                # Keep only the horizontal centre alignment. The target may move vertically
                # and can be positioned with the normal distance dimension between its edges.
                sys_.coincident(target_point, vertical_axis, wp)

    for la, ea, lb, eb, _, _, _ in corners:
        # a fixed side already holds the corner: joining to it would make e.g. the opposite size dimension redundant
        if la not in fixed and lb not in fixed:
            sys_.coincident(pts[(la, ea)], pts[(lb, eb)], wp)

    ref_lines: Dict[str, object] = {}  # fixed face edges used by dimensions, created on demand
    add = _length_add(corners)

    # Dimensions that belong to solver entities
    for d in (sketch.dimensions if use_dims else []):
        ent = ents.get(d.target_entity_id)
        if d.dim_type in SOLVER_DIM_TYPES:
            _add_multi_dimension(sys_, wp, ents, pts, geo, fixed, d, ref_lines)
            continue
        if ent is None or ent.entity_id in fixed:
            continue
        if d.dim_type == "LENGTH" and isinstance(ent, SketchLine):
            sys_.distance(pts[(ent.entity_id, "p1")], pts[(ent.entity_id, "p2")],
                          float(d.value) + add.get(ent.entity_id, 0.0), wp)
        elif d.dim_type == "DIAMETER" and isinstance(ent, SketchCircle):
            sys_.diameter(geo[ent.entity_id], float(d.value))
        elif d.dim_type == "RADIUS" and isinstance(ent, SketchCircle):
            sys_.diameter(geo[ent.entity_id], float(d.value) * 2.0)

    flag = sys_.solve()
    if flag != 0:
        failed = sys_.failures()
        return None, "Conflicting or unsolvable constraints" + (f" ({len(failed)} involved)" if failed else "")

    # Reject solutions that collapse geometry (e.g. a line forced both horizontal and vertical)
    for eid, ent in ents.items():
        if eid in fixed:
            continue
        if isinstance(ent, SketchLine):
            p1, p2 = _xy(sys_, pts[(eid, "p1")]), _xy(sys_, pts[(eid, "p2")])
            if math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < 1e-3:
                return None, "Constraints would collapse a line to a point"

    values = {}
    for eid, ent in ents.items():
        if isinstance(ent, SketchLine):
            values[eid] = (_xy(sys_, pts[(eid, "p1")]), _xy(sys_, pts[(eid, "p2")]))
        else:
            values[eid] = _xy(sys_, pts[(eid, "center")])
            solved_r = float(sys_.params(radii[eid].params)[0])
            if getattr(ent, "group", None) or abs(solved_r - float(ent.radius)) > 1e-6:
                values[f"{eid}#r"] = solved_r
    return (values, int(sys_.dof())), ""



def _side_sign(p, a, b) -> float:
    """SolveSpace's point-to-line distance is signed: positive when the point is to the right of
    a -> b. Using the point's current side keeps it from jumping across the line."""
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    return 1.0 if cross <= 0 else -1.0


def _centre_distance(ent, pt_name: str, value: float) -> float:
    """Distance to hold between a circle's centre and a line when the dimension is measured to the
    circle's near/far edge (the radius is read at solve time, so diameter changes carry through)."""
    if pt_name == "edge_near":
        return max(0.0, value + ent.radius)
    if pt_name == "edge_far":
        return max(0.0, value - ent.radius)
    return value


def _pt_name(pt_name: str) -> str:
    return "center" if pt_name in EDGE_PTS else pt_name


def _add_multi_dimension(sys_, wp, ents, pts, geo, fixed, d, ref_lines) -> None:
    """Angle and distance dimensions between two entities (or an entity and a line)."""
    a = d.target_entity_id
    others = list(d.refs)
    edge_refs = [o for o in others if ref_segment(o) is not None]
    others_ents = [o for o in others if o not in edge_refs]
    if a not in ents or any(o not in ents for o in others_ents):
        return
    if all(e in fixed for e in [a] + others_ents):
        return  # nothing free to move
    value = float(d.value)

    if edge_refs:  # distance from a point to a fixed face edge
        if d.dim_type != "PT_LINE_DIST" or not d.pts or (a, _pt_name(d.pts[0])) not in pts:
            return
        key = edge_refs[0]
        if key not in ref_lines:
            (x1, y1), (x2, y2) = ref_segment(key)
            sys_.set_group(FIXED_GROUP)  # constants for the solver
            p1, p2 = sys_.add_point_2d(x1, y1, wp), sys_.add_point_2d(x2, y2, wp)
            ref_lines[key] = sys_.add_line_2d(p1, p2, wp)
            sys_.set_group(FREE_GROUP)
        (x1, y1), (x2, y2) = ref_segment(key)
        sign = _side_sign(point_of(ents[a], _pt_name(d.pts[0])), (x1, y1), (x2, y2))
        sys_.distance(pts[(a, _pt_name(d.pts[0]))], ref_lines[key], sign * _centre_distance(ents[a], d.pts[0], value), wp)
        return

    if d.dim_type == "ANGLE":
        b = others[0]
        if not (isinstance(ents[a], SketchLine) and isinstance(ents[b], SketchLine)) or len(d.pts) < 2:
            return
        # value is the angle between the arms at the vertex; SolveSpace measures between the
        # line vectors p1->p2, so a line whose vertex end is p2 is reversed (180 - angle).
        flip = (d.pts[0] == "p2") != (d.pts[1] == "p2")
        sys_.angle(geo[a], geo[b], 180.0 - value if flip else value, wp)
        return

    if d.dim_type == "PT_LINE_DIST":
        line_id = others[0]
        if isinstance(ents[line_id], SketchLine) and d.pts and (a, _pt_name(d.pts[0])) in pts:
            ln = ents[line_id]
            sign = _side_sign(point_of(ents[a], _pt_name(d.pts[0])), ln.p1, ln.p2)
            sys_.distance(pts[(a, _pt_name(d.pts[0]))], geo[line_id], sign * _centre_distance(ents[a], d.pts[0], value), wp)
        return

    b = others[0]
    if len(d.pts) < 2 or (a, d.pts[0]) not in pts or (b, d.pts[1]) not in pts:
        return
    pa, pb = pts[(a, d.pts[0])], pts[(b, d.pts[1])]
    if d.dim_type == "DISTANCE":
        sys_.distance(pa, pb, value, wp)
        return
    # Horizontal / vertical distance: measure to a helper point sharing one coordinate with B
    ax, ay = point_of(ents[a], d.pts[0])
    bx, by = point_of(ents[b], d.pts[1])
    horizontal = d.dim_type == "HORIZ_DIST"
    helper = sys_.add_point_2d(bx if horizontal else ax, ay if horizontal else by, wp)
    l_a = sys_.add_line_2d(pa, helper, wp)
    l_b = sys_.add_line_2d(pb, helper, wp)
    if horizontal:
        sys_.horizontal(l_a, wp)
        sys_.vertical(l_b, wp)
    else:
        sys_.vertical(l_a, wp)
        sys_.horizontal(l_b, wp)
    sys_.distance(pa, helper, value, wp)


def _xy(sys_, handle) -> Tuple[float, float]:
    p = sys_.params(handle.params)
    return float(p[0]), float(p[1])


def _tangent(sys_, wp, ents, pts, geo, a, b):
    """Line-circle: centre-to-line distance = radius. Circle-circle: centre distance = r1 +/- r2
    (the radius is held by the circle's diameter dimension, so the current value is used)."""
    ea, eb = ents[a], ents[b]
    if isinstance(ea, SketchCircle) and isinstance(eb, SketchLine):
        ea, eb, a, b = eb, ea, b, a
    if isinstance(ea, SketchLine) and isinstance(eb, SketchCircle):
        sign = _side_sign(eb.center, ea.p1, ea.p2)
        sys_.distance(pts[(b, "center")], geo[a], sign * float(eb.radius), wp)
    elif isinstance(ea, SketchCircle) and isinstance(eb, SketchCircle):
        d = math.hypot(ea.center[0] - eb.center[0], ea.center[1] - eb.center[1])
        inner = d < max(ea.radius, eb.radius) - 1e-6
        value = abs(ea.radius - eb.radius) if inner else ea.radius + eb.radius
        sys_.distance(pts[(a, "center")], pts[(b, "center")], float(value), wp)


def midpoint_spec(lines, circles):
    """(ctype, refs, pts) for a Midpoint constraint from two selected elements: a circle's centre, or the end of one
    line nearest the other line's middle, goes to the middle of the other line (Fusion: point + line)."""
    if circles:
        return ("MIDPOINT", [circles[0].entity_id, lines[0].entity_id], ["center"])
    best = None
    for a, b in ((lines[0], lines[1]), (lines[1], lines[0])):
        mid = ((b.p1[0] + b.p2[0]) / 2.0, (b.p1[1] + b.p2[1]) / 2.0)
        for name in ("p1", "p2"):
            p = getattr(a, name)
            d = math.hypot(p[0] - mid[0], p[1] - mid[1])
            if best is None or d < best[0]:
                best = (d, a, b, name)
    _, a, b, name = best
    return ("MIDPOINT", [a.entity_id, b.entity_id], [name])


def _across(axis, b, c) -> Optional[float]:
    """How far the mirror of b's middle is from c's middle, or None when b and c do not lie on opposite sides of axis."""
    ax, ay = axis.p2[0] - axis.p1[0], axis.p2[1] - axis.p1[1]
    length = math.hypot(ax, ay)
    if length == 0.0:
        return None

    def side(p):
        return (ax * (p[1] - axis.p1[1]) - ay * (p[0] - axis.p1[0])) / length

    mb = ((b.p1[0] + b.p2[0]) / 2.0, (b.p1[1] + b.p2[1]) / 2.0)
    mc = ((c.p1[0] + c.p2[0]) / 2.0, (c.p1[1] + c.p2[1]) / 2.0)
    if side(mb) * side(mc) >= 0.0:
        return None
    dx, dy = mc[0] - mb[0], mc[1] - mb[1]
    gap = math.hypot(dx, dy)
    return abs(ax * dx + ay * dy) / (length * gap) if gap else 0.0


def symmetric_spec(lines, circles, axis_id=None):
    """(ctype, refs, pts) for a Symmetric constraint: two circles (their centres) or two lines (their nearest end
    points) mirrored across the third selected line. The mirror line is the one that puts the other two on opposite
    sides and most square to them. Returns None when no line fits that description."""
    if circles:
        if len(circles) != 2 or len(lines) != 1:
            return None
        return ("SYMMETRIC", [circles[0].entity_id, circles[1].entity_id, lines[0].entity_id], ["center", "center"])
    if len(lines) != 3:
        return None
    best = None
    axes = [line for line in lines if line.entity_id == axis_id] if axis_id else lines
    for axis in axes:
        b, c = [l for l in lines if l is not axis]
        dev = _across(axis, b, c)
        if dev is not None and (best is None or dev < best[0]):
            best = (dev, axis, b, c)
    if best is None:
        return None
    _, axis, b, c = best
    pa, pb = min(((x, y) for x in ("p1", "p2") for y in ("p1", "p2")),
                 key=lambda t: math.hypot(getattr(b, t[0])[0] - getattr(c, t[1])[0],
                                          getattr(b, t[0])[1] - getattr(c, t[1])[1]))
    return ("SYMMETRIC", [b.entity_id, c.entity_id, axis.entity_id], [pa, pb])
