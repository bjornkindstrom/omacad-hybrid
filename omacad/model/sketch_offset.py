"""Offset of connected chains of lines and arcs. Radii follow along (an arc keeps its centre, its radius grows or shrinks)
and every joint is recomputed, so the result is one unbroken chain of lines and arcs, closed if the original was."""
import math
from typing import List, Optional, Tuple

TAU = 2 * math.pi
EPS = 1e-6
Pt = Tuple[float, float]


def offset_spline(spline, distance: float):
    """Sample an independent spline offset; closed curves use positive = outward.

    Keep the fit points sparse while retaining detail relative to the requested
    distance. Split offsets become separate splines rather than joined bridges.
    """
    from shapely.geometry import LineString, Polygon

    points = spline.get_points(samples_per_span=64)
    if len(points) < 2 or not math.isfinite(distance):
        return []
    curve = LineString(points)
    if curve.length < EPS:
        return []
    closed = _close(points[0], points[-1], EPS)
    if closed:
        shape = Polygon(points)
        if not shape.is_valid:
            shape = shape.buffer(0)
        result = shape.buffer(distance)
        polygons = list(result.geoms) if hasattr(result, "geoms") else [result]
        parts = [ring for poly in polygons if not poly.is_empty
                 for ring in [poly.exterior, *poly.interiors]]
    else:
        result = curve.offset_curve(distance)
        parts = list(result.geoms) if hasattr(result, "geoms") else [result]
    return [points for part in parts if not part.is_empty and part.length > EPS
            for points in [_fit_offset_spline(part, distance)] if points]


def _fit_offset_spline(part, distance):
    """Avoid loops from interpolating unevenly spaced buffer/offset vertices and pick
    a compact set of control points (aiming for ~6-8 points on open splines) while
    preserving curve shape and quality."""
    from shapely.geometry import LineString, Polygon
    from omacad.model.sketch_entities import SketchSpline

    closed = getattr(part, "is_ring", False)
    # Balanced tolerance: up to 0.18 mm or 8% of distance for sparse, clean control points
    max_dev = max(0.18, abs(distance) * 0.08)

    def is_acceptable(pts):
        if len(pts) < 2:
            return False
        fit_pts = SketchSpline("", pts).get_points()
        if closed:
            poly = Polygon(fit_pts)
            if not poly.is_valid:
                return False
        fitted = LineString(fit_pts)
        return fitted.is_simple and fitted.hausdorff_distance(part) <= max_dev

    # 1. Try Douglas-Peucker simplification with aggressive tolerance ladder
    ladder = [0.5, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05, 0.02, 0.01]
    for tol in ladder:
        try:
            simp = part.simplify(tol)
            pts = list(simp.coords)
            if is_acceptable(pts):
                # On open curves, if slightly above 8 points (e.g. 9-11), prune least-critical points down to ~8
                if not closed and len(pts) > 8:
                    best_pts = pts
                    while len(best_pts) > 8:
                        candidate = None
                        min_h = 1e9
                        for i in range(1, len(best_pts) - 1):
                            cand = best_pts[:i] + best_pts[i + 1:]
                            h = LineString(SketchSpline("", cand).get_points()).hausdorff_distance(part)
                            if h < min_h:
                                min_h = h
                                candidate = cand
                        if candidate and min_h <= max_dev:
                            best_pts = candidate
                        else:
                            break
                    if len(best_pts) <= 8 and is_acceptable(best_pts):
                        return best_pts
                return pts
        except Exception:
            continue

    # 2. Resample fallback using compact point counts
    for count in (6, 8, 12, 16, 24, 32):
        points = [part.interpolate(i / count, normalized=True).coords[0] for i in range(count + 1)]
        if is_acceptable(points):
            return points

    return list(part.coords)


class Seg:
    """One element in travel direction: a line p -> q, or an arc round c from angle a0 to a1 (ccw or not)."""

    def __init__(self, kind, p=None, q=None, c=None, r=0.0, a0=0.0, a1=0.0, ccw=True, src=None):
        self.kind, self.p, self.q, self.c, self.r, self.a0, self.a1, self.ccw, self.src = kind, p, q, c, r, a0, a1, ccw, src

    @staticmethod
    def line(p, q, src=None):
        return Seg("line", p=p, q=q, src=src)

    @staticmethod
    def arc(c, r, a0, a1, ccw, src=None):
        s = Seg("arc", c=c, r=r, a0=a0, a1=a1, ccw=ccw, src=src)
        s.p = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
        s.q = (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
        return s

    def sweep(self) -> float:
        return ((self.a1 - self.a0) % TAU) if self.ccw else ((self.a0 - self.a1) % TAU)

    def tangent_at_start(self) -> Pt:
        if self.kind == "line":
            return _unit((self.q[0] - self.p[0], self.q[1] - self.p[1]))
        s = 1.0 if self.ccw else -1.0
        return (-s * math.sin(self.a0), s * math.cos(self.a0))

    def tangent_at_end(self) -> Pt:
        if self.kind == "line":
            return self.tangent_at_start()
        s = 1.0 if self.ccw else -1.0
        return (-s * math.sin(self.a1), s * math.cos(self.a1))

    def points(self, n: int = 24) -> List[Pt]:
        if self.kind == "line":
            return [self.p, self.q]
        sw = self.sweep() * (1 if self.ccw else -1)
        return [(self.c[0] + self.r * math.cos(self.a0 + sw * i / n), self.c[1] + self.r * math.sin(self.a0 + sw * i / n)) for i in range(n + 1)]

    def mid(self) -> Pt:
        if self.kind == "line":
            return ((self.p[0] + self.q[0]) / 2, (self.p[1] + self.q[1]) / 2)
        sw = self.sweep() * (1 if self.ccw else -1)
        a = self.a0 + sw / 2
        return (self.c[0] + self.r * math.cos(a), self.c[1] + self.r * math.sin(a))


def _unit(v: Pt) -> Pt:
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n > 1e-12 else (1.0, 0.0)


def _left(t: Pt) -> Pt:
    return (-t[1], t[0])


def _close(a: Pt, b: Pt, tol: float = 1e-3) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) < tol


# ---- building chains from sketch elements ---------------------------------------------------------
def to_seg(ent) -> Optional[Seg]:
    from omacad.model.sketch import SketchLine, SketchArc
    if isinstance(ent, SketchLine):
        return Seg.line(tuple(ent.p1), tuple(ent.p2), ent)
    if isinstance(ent, SketchArc):
        par = ent.get_circle_params()
        if par is None:
            return None
        c, r, a0, a1, ccw = par
        return Seg.arc(tuple(c), r, a0, a1, ccw, ent)
    return None


def reversed_seg(s: Seg) -> Seg:
    if s.kind == "line":
        return Seg.line(s.q, s.p, s.src)
    return Seg.arc(s.c, s.r, s.a1, s.a0, not s.ccw, s.src)


def build_chains(segs: List[Seg]) -> List[Tuple[List[Seg], bool]]:
    """Orders elements that touch end to end into chains. Returns [(segments in travel order, closed)]."""
    left = list(segs)
    chains = []
    while left:
        chain = [left.pop(0)]
        grown = True
        while grown:
            grown = False
            for s in list(left):
                if _close(chain[-1].q, s.p):
                    chain.append(s); left.remove(s); grown = True; break
                if _close(chain[-1].q, s.q):
                    chain.append(reversed_seg(s)); left.remove(s); grown = True; break
                if _close(chain[0].p, s.q):
                    chain.insert(0, s); left.remove(s); grown = True; break
                if _close(chain[0].p, s.p):
                    chain.insert(0, reversed_seg(s)); left.remove(s); grown = True; break
        closed = len(chain) > 2 and _close(chain[-1].q, chain[0].p)
        chains.append((chain, closed))
    return chains


def signed_area(chain: List[Seg]) -> float:
    pts = []
    for s in chain:
        pts += s.points(16)[:-1]
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


# ---- intersections of the extended offset curves -------------------------------------------------------
def _line_line(p1, d1, p2, d2) -> Optional[Pt]:
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-9:
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


def _line_circle(p, d, c, r) -> List[Pt]:
    fx, fy = p[0] - c[0], p[1] - c[1]
    b = fx * d[0] + fy * d[1]
    disc = b * b - (fx * fx + fy * fy - r * r)
    if disc < 0:
        return []
    sq = math.sqrt(disc)
    return [(p[0] + d[0] * (-b + k * sq), p[1] + d[1] * (-b + k * sq)) for k in (-1, 1)]


def _circle_circle(c1, r1, c2, r2) -> List[Pt]:
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    D = math.hypot(dx, dy)
    if D < 1e-9 or D > r1 + r2 + 1e-9 or D < abs(r1 - r2) - 1e-9:
        return []
    a = (r1 * r1 - r2 * r2 + D * D) / (2 * D)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mx, my = c1[0] + a * dx / D, c1[1] + a * dy / D
    return [(mx + h * dy / D, my - h * dx / D), (mx - h * dy / D, my + h * dx / D)]


def _extended(s: Seg):
    """The infinite curve behind a segment: ('line', point, direction) or ('circle', centre, radius)."""
    if s.kind == "line":
        return ("line", s.p, _unit((s.q[0] - s.p[0], s.q[1] - s.p[1])))
    return ("circle", s.c, s.r)


def _intersect(a: Seg, b: Seg, near: Pt) -> Optional[Pt]:
    ea, eb = _extended(a), _extended(b)
    pts: List[Pt] = []
    if ea[0] == "line" and eb[0] == "line":
        p = _line_line(ea[1], ea[2], eb[1], eb[2])
        pts = [p] if p else []
    elif ea[0] == "line":
        pts = _line_circle(ea[1], ea[2], eb[1], eb[2])
    elif eb[0] == "line":
        pts = _line_circle(eb[1], eb[2], ea[1], ea[2])
    else:
        pts = _circle_circle(ea[1], ea[2], eb[1], eb[2])
    return min(pts, key=lambda q: math.hypot(q[0] - near[0], q[1] - near[1])) if pts else None


# ---- the offset itself -----------------------------------------------------------------------------------
def _shift(s: Seg, d: float) -> Optional[Seg]:
    """The element moved `d` to the left of its travel direction (negative: to the right)."""
    if s.kind == "line":
        n = _left(_unit((s.q[0] - s.p[0], s.q[1] - s.p[1])))
        return Seg.line((s.p[0] + n[0] * d, s.p[1] + n[1] * d), (s.q[0] + n[0] * d, s.q[1] + n[1] * d), s.src)
    r = s.r - d if s.ccw else s.r + d       # to the left of a ccw arc is towards its centre
    if r <= EPS:
        return None
    return Seg.arc(s.c, r, s.a0, s.a1, s.ccw, s.src)


def _angle(c: Pt, p: Pt) -> float:
    return math.atan2(p[1] - c[1], p[0] - c[0]) % TAU


def offset_chain(chain: List[Seg], closed: bool, d_left: float) -> List[Seg]:
    """Offset a chain `d_left` to the left of its travel direction. Joints are re-made: tangent joints stay tangent,
    others are cut or extended to where the offset curves meet. Elements that collapse disappear."""
    shifted = []
    for s in chain:
        o = _shift(s, d_left)
        if o is not None:
            shifted.append((s, o))
    keep = []
    for _ in range(4):                        # dropping an element changes its neighbours' joints: repeat until stable
        n = len(shifted)
        if n == 0:
            return []
        ends: List[Pt] = []                   # ends[i] = joint after element i
        for i in range(n):
            s, o = shifted[i]
            if not closed and i == n - 1:
                ends.append(o.q)
                continue
            s2, o2 = shifted[(i + 1) % n]
            joined = _close(s.q, s2.p, 1e-3)
            ta, tb = s.tangent_at_end(), s2.tangent_at_start()
            if joined and abs(ta[0] * tb[1] - ta[1] * tb[0]) < 1e-3 and ta[0] * tb[0] + ta[1] * tb[1] > 0:
                ends.append(o.q)               # a tangent joint (a filleted corner) stays tangent
                continue
            if joined:
                near = (s.q[0] + _left(ta)[0] * d_left, s.q[1] + _left(ta)[1] * d_left)
            else:                              # something between them collapsed: meet where their offset curves cross
                near = ((o.q[0] + o2.p[0]) / 2, (o.q[1] + o2.p[1]) / 2)
            p = _intersect(o, o2, near=near)
            ends.append(p if p is not None else o.q)
        out: List[Seg] = []
        starts = [ends[-1] if closed else shifted[0][1].p] + ends[:-1]
        keep = []
        for i, (s, o) in enumerate(shifted):
            a, b = starts[i], ends[i]
            if o.kind == "line":
                v = _unit((o.q[0] - o.p[0], o.q[1] - o.p[1]))
                if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-9 or (b[0] - a[0]) * v[0] + (b[1] - a[1]) * v[1] < 0:
                    continue
                keep.append(((s, o), Seg.line(a, b, s.src)))
            else:
                n_seg = Seg.arc(o.c, o.r, _angle(o.c, a), _angle(o.c, b), o.ccw, s.src)
                if n_seg.sweep() > 1.5 * s.sweep() + 0.1 or n_seg.sweep() < 1e-9:
                    continue
                keep.append(((s, o), n_seg))
        if len(keep) == len(shifted):
            return [k[1] for k in keep]
        shifted = [k[0] for k in keep]
    return [k[1] for k in keep]


def offset_entities_chains(entities, distance: float):
    """Offsets lines and arcs as chains. Returns (new segments, entities that were handled)."""
    segs = []
    for ent in entities:
        s = to_seg(ent)
        if s is not None:
            segs.append(s)
    out: List[Seg] = []
    for chain, closed in build_chains(segs):
        if closed:
            d_left = -distance if signed_area(chain) > 0 else distance     # positive = outward for a closed shape
        else:
            d_left = distance                                               # positive = left of the travel direction
        out += offset_chain(chain, closed, d_left)
    return out, [s.src for s in segs]
