"""Trim: remove the piece of a sketch line / circle / arc between its neighbouring intersections
(or up to its free end, which removes a dangling stub)."""
import math
from typing import List, Optional, Tuple

TAU = 2 * math.pi
EPS = 1e-6


def _circle_of(ent):
    """(centre, radius, start_angle, sweep) for circles (sweep = TAU) and arcs, else None. Arcs run ccw."""
    from omacad.model.sketch import SketchCircle, SketchArc
    if isinstance(ent, SketchCircle):
        return ent.center, ent.radius, 0.0, TAU
    if isinstance(ent, SketchArc):
        par = ent.get_circle_params()
        if par is None:
            return None
        c, r, a1, a3, ccw = par
        if ccw:
            return c, r, a1, (a3 - a1) % TAU
        return c, r, a3, (a1 - a3) % TAU      # same arc seen counter-clockwise from its end
    return None


def _in_sweep(ang, start, sweep):
    d = (ang - start) % TAU
    return d <= sweep + 1e-5 or d >= TAU - 1e-5


def _line_hits(p, d, L, other) -> List[float]:
    """Parameters t (0..L along the unit direction d from p) where another entity crosses the line."""
    from omacad.model.sketch import SketchLine
    out = []
    if isinstance(other, SketchLine):
        q, e = other.p1, (other.p2[0] - other.p1[0], other.p2[1] - other.p1[1])
        le = math.hypot(*e)
        if le < EPS:
            return out
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-9 * le:
            return out
        wx, wy = q[0] - p[0], q[1] - p[1]
        t = (wx * e[1] - wy * e[0]) / den
        s = (wx * d[1] - wy * d[0]) / den
        if -EPS <= t <= L + EPS and -EPS <= s <= le + EPS:
            out.append(t)
        return out
    cc = _circle_of(other)
    if cc is None:
        return out
    (cx, cy), r, a0, sw = cc
    fx, fy = p[0] - cx, p[1] - cy
    b = fx * d[0] + fy * d[1]
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < 0:
        return out
    sq = math.sqrt(disc)
    for t in ({-b - sq, -b + sq}):
        if -EPS <= t <= L + EPS:
            ang = math.atan2(fy + t * d[1], fx + t * d[0])
            if _in_sweep(ang, a0, sw):
                out.append(t)
    return out


def _circle_hits(c, r, other) -> List[float]:
    """Angles on circle (c, r) where another entity crosses it."""
    from omacad.model.sketch import SketchLine
    out = []
    if isinstance(other, SketchLine):
        p = other.p1
        e = (other.p2[0] - p[0], other.p2[1] - p[1])
        L = math.hypot(*e)
        if L < EPS:
            return out
        d = (e[0] / L, e[1] / L)
        for t in _line_hits_circle(p, d, L, c, r):
            out.append(math.atan2(p[1] + t * d[1] - c[1], p[0] + t * d[0] - c[0]) % TAU)
        return out
    cc = _circle_of(other)
    if cc is None:
        return out
    (ox, oy), orad, a0, sw = cc
    dx, dy = ox - c[0], oy - c[1]
    D = math.hypot(dx, dy)
    if D < EPS or D > r + orad + EPS or D < abs(r - orad) - EPS:
        return out
    a = (r * r - orad * orad + D * D) / (2 * D)
    h2 = r * r - a * a
    h = math.sqrt(max(h2, 0.0))
    mx, my = c[0] + a * dx / D, c[1] + a * dy / D
    pts = [(mx, my)] if h < 1e-7 else [(mx + h * dy / D, my - h * dx / D), (mx - h * dy / D, my + h * dx / D)]
    for x, y in pts:
        if _in_sweep(math.atan2(y - oy, x - ox) % TAU, a0, sw):
            out.append(math.atan2(y - c[1], x - c[0]) % TAU)
    return out


def _line_hits_circle(p, d, L, c, r):
    fx, fy = p[0] - c[0], p[1] - c[1]
    b = fx * d[0] + fy * d[1]
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < 0:
        return []
    sq = math.sqrt(disc)
    return [t for t in {-b - sq, -b + sq} if -EPS <= t <= L + EPS]


def _arc_pts(c, r, a0, sweep, n=24):
    return [(c[0] + r * math.cos(a0 + sweep * i / n), c[1] + r * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]


def trim_plan(sketch, u: float, v: float, tol: float):
    """What a Trim click at (u, v) would do: (entity, removed polyline, new pieces) or None.
    Pieces are ("line", p1, p2) or ("arc", start, mid, end)."""
    from omacad.model.sketch import SketchLine, SketchCircle, SketchArc, _dist_point_segment
    cands = [e for e in sketch.entities if isinstance(e, (SketchLine, SketchCircle, SketchArc)) and not e.is_construction]
    best, best_d = None, tol
    for e in cands:
        for a, b in e.to_lines():
            d = _dist_point_segment((u, v), a, b)
            if d <= best_d:
                best, best_d = e, d
    if best is None:
        return None
    others = [e for e in sketch.entities if e is not best and isinstance(e, (SketchLine, SketchCircle, SketchArc))]

    if isinstance(best, SketchLine):
        p, q = best.p1, best.p2
        L = math.hypot(q[0] - p[0], q[1] - p[1])
        if L < EPS:
            return None
        d = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
        cuts = sorted({round(t, 7) for o in others for t in _line_hits(p, d, L, o) if EPS < t < L - EPS})
        tc = max(0.0, min(L, (u - p[0]) * d[0] + (v - p[1]) * d[1]))
        lo = max([0.0] + [t for t in cuts if t <= tc])
        hi = min([L] + [t for t in cuts if t >= tc])
        at = lambda t: (p[0] + d[0] * t, p[1] + d[1] * t)
        pieces = []
        if lo > EPS:
            pieces.append(("line", p, at(lo)))
        if hi < L - EPS:
            pieces.append(("line", at(hi), q))
        return best, [at(lo), at(hi)], pieces

    c, r, a0, sw = _circle_of(best) or (None, None, None, None)
    if c is None:
        return None
    full = isinstance(best, SketchCircle)
    cuts = sorted({round((a - a0) % TAU, 7) for o in others for a in _circle_hits(c, r, o)})
    cuts = [s for s in cuts if full or 1e-5 < s < sw - 1e-5]
    ac = (math.atan2(v - c[1], u - c[0]) - a0) % TAU
    if full:
        if len(cuts) == 0:
            return best, _arc_pts(c, r, a0, TAU), []
        if len(cuts) == 1:
            return None
        below = [s for s in cuts if s <= ac]
        lo = below[-1] if below else cuts[-1] - TAU
        hi = next((s for s in cuts if s > ac), cuts[0] + TAU)
        keep0, keep_sw = a0 + hi, TAU - (hi - lo)
        if keep_sw < EPS:
            return None
    else:
        lo = max([0.0] + [s for s in cuts if s <= ac])
        hi = min([sw] + [s for s in cuts if s >= ac])
    pieces = []
    spans = [(0.0, lo), (hi, sw)] if not full else [(hi, lo + TAU)]
    for s0, s1 in spans:
        if s1 - s0 > EPS:
            pt = lambda s: (c[0] + r * math.cos(a0 + s), c[1] + r * math.sin(a0 + s))
            pieces.append(("arc", pt(s0), pt((s0 + s1) / 2), pt(s1)))
    return best, _arc_pts(c, r, a0 + lo, hi - lo), pieces


def apply_trim(sketch, plan) -> int:
    """Carry out a plan: the element is replaced by its remaining pieces. Returns the number of new pieces."""
    from omacad.model.sketch import SketchLine, SketchArc
    ent, _removed, pieces = plan
    sketch.delete_entities([ent.entity_id])
    for pc in pieces:
        if pc[0] == "line":
            sketch.entities.append(SketchLine(sketch._new_entity_id("line"), pc[1], pc[2]))
        else:
            sketch.entities.append(SketchArc(sketch._new_entity_id("arc"), pc[1], pc[2], pc[3]))
    sketch.solve_profiles()
    return len(pieces)
