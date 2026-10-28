"""Fix Sketch: make what was drawn close into a face, in as few changes as possible.

A shape stays open when its ends do not meet exactly (profiles need them within 1e-4 mm). In order, smallest change
first, each step only where the earlier ones did not already close the shape:

1. Lines of zero length and exact duplicates go (they only confuse the loop search).
2. Two free ends close to each other are joined: a line end moves onto the other end (both meet halfway when both are
   line ends; an arc's end stays where it is), and a Coincident constraint keeps them together.
3. A free line end that stops just short of, or just past, another curve is extended or shortened along its own line
   until it touches it.
4. Ends that are still free are closed with new lines, nearest pairs first: an open chain gets the one line that
   closes it.

Construction lines are left alone (they never make faces). `fix_sketch` returns what it did, in words, for the
status line; the caller records it as one undo step.
"""
from typing import List, Optional, Tuple

import numpy as np

from omacad.model.sketch_entities import SketchArc, SketchLine
from omacad.model.sketch_types import SketchConstraint

JOINED = 1e-4          # ends closer than this already meet (the precision the profile search uses)


def _ends(sketch):
    """[(entity, point name, xy, movable)] for the open curves: line ends move, arc ends stay."""
    out = []
    for e in sketch.entities:
        if e.is_construction:
            continue
        if isinstance(e, SketchLine):
            out += [(e, "p1", np.asarray(e.p1, float), True), (e, "p2", np.asarray(e.p2, float), True)]
        elif isinstance(e, SketchArc):
            out += [(e, "p_start", np.asarray(e.p_start, float), False), (e, "p_end", np.asarray(e.p_end, float), False)]
    return out


def _segments(sketch, skip=None):
    """Every straight piece of the non-construction curves (arcs as their polyline), with the entity it belongs to."""
    segs = []
    for e in sketch.entities:
        if e.is_construction or e is skip:
            continue
        for a, b in e.to_lines():
            segs.append((e, np.asarray(a, float), np.asarray(b, float)))
    return segs


def _dist_to_segment(p, a, b) -> Tuple[float, np.ndarray]:
    ab = b - a
    t = float(np.clip((p - a) @ ab / max(float(ab @ ab), 1e-18), 0.0, 1.0))
    q = a + t * ab
    return float(np.linalg.norm(p - q)), q


def free_ends(sketch):
    """The ends that touch nothing: no other end at the same spot and not on another curve (a T joint is closed)."""
    ends = _ends(sketch)
    free = []
    for i, (e, name, p, mov) in enumerate(ends):
        if any(j != i and np.linalg.norm(p - q) < JOINED for j, (_, _, q, _) in enumerate(ends)):
            continue
        if any(_dist_to_segment(p, a, b)[0] < JOINED for o, a, b in _segments(sketch, skip=e)):
            continue
        free.append((e, name, p, mov))
    return free


def _set_end(e, name, xy):
    xy = (float(xy[0]), float(xy[1]))
    if name == "p1":
        e.p1 = xy
    elif name == "p2":
        e.p2 = xy


def _gap_tolerance(sketch) -> float:
    """How far apart two ends may be and still be 'meant to meet': 3 % of the drawing's size, at least 0.5 mm."""
    pts = np.array([p for _, _, p, _ in _ends(sketch)] or [[0.0, 0.0]])
    diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    return max(0.5, 0.03 * diag)


def _ray_hit(p, d, a, b) -> Optional[Tuple[float, np.ndarray]]:
    """Where the line through p along d (both ways) crosses segment ab: (signed distance along d, point)."""
    m = np.column_stack([d, a - b])
    if abs(np.linalg.det(m)) < 1e-12:
        return None
    t, s = np.linalg.solve(m, a - p)
    if -1e-9 <= s <= 1 + 1e-9:
        return float(t), p + t * d
    return None


def _direction(e, name) -> np.ndarray:
    """Unit direction of line `e` pointing out through its end `name`."""
    end, other = (np.asarray(e.p1, float), np.asarray(e.p2, float)) if name == "p1" else (np.asarray(e.p2, float), np.asarray(e.p1, float))
    d = end - other
    return d / max(float(np.linalg.norm(d)), 1e-18)


def _sideways(e, name, target) -> float:
    """How far moving line end `name` to `target` would turn the line (its move across the line's direction)."""
    d = _direction(e, name)
    end = np.asarray(e.p1 if name == "p1" else e.p2, float)
    move = np.asarray(target, float) - end
    return abs(float(move[0] * d[1] - move[1] * d[0]))


def _corner(ea, na, eb, nb, tol) -> Optional[np.ndarray]:
    """Where the two lines (extended) cross, if that is near both ends; None for (nearly) parallel lines."""
    pa = np.asarray(ea.p1 if na == "p1" else ea.p2, float)
    pb = np.asarray(eb.p1 if nb == "p1" else eb.p2, float)
    da, db = _direction(ea, na), _direction(eb, nb)
    m = np.column_stack([da, -db])
    if abs(np.linalg.det(m)) < 1e-3:
        return None
    t, u = np.linalg.solve(m, pb - pa)
    q = pa + t * da
    return q if np.linalg.norm(q - pa) < tol and np.linalg.norm(q - pb) < tol else None


def _bounding_entities(sketch) -> set:
    """Ids of the curves that run along the outline of one of the sketch's faces."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    if not sketch.profiles:
        return set()
    outline = unary_union([Polygon(p.exterior_pts, p.interior_holes).boundary for p in sketch.profiles])
    ids = set()
    for e, a, b in _segments(sketch):
        if e.entity_id not in ids and LineString([a, b]).intersection(outline.buffer(1e-4)).length > 1e-3:
            ids.add(e.entity_id)
    return ids


def fix_sketch(sketch) -> List[str]:
    done: List[str] = []

    # 1. zero-length and duplicate lines
    lines = [e for e in sketch.entities if isinstance(e, SketchLine) and not e.is_construction]
    doomed, seen = [], []
    for ln in lines:
        a, b = np.asarray(ln.p1, float), np.asarray(ln.p2, float)
        if np.linalg.norm(a - b) < JOINED:
            doomed.append(ln.entity_id)
            continue
        if any((np.linalg.norm(a - c) < JOINED and np.linalg.norm(b - d) < JOINED)
               or (np.linalg.norm(a - d) < JOINED and np.linalg.norm(b - c) < JOINED) for c, d in seen):
            doomed.append(ln.entity_id)
            continue
        seen.append((a, b))
    if doomed:
        sketch.delete_entities(doomed)
        done.append(f"removed {len(doomed)} empty or doubled line(s)")

    tol = _gap_tolerance(sketch)

    # 2. join free ends that nearly meet
    joined = 0
    while True:
        free = free_ends(sketch)
        best = None
        for i in range(len(free)):
            for j in range(i + 1, len(free)):
                (ea, na, pa, ma), (eb, nb, pb, mb) = free[i], free[j]
                if ea is eb or not (ma or mb):
                    continue
                dist = float(np.linalg.norm(pa - pb))
                if dist < tol and (best is None or dist < best[0]):
                    best = (dist, free[i], free[j])
        if best is None:
            break
        _, (ea, na, pa, ma), (eb, nb, pb, mb) = best
        if ma and mb:
            corner = _corner(ea, na, eb, nb, tol)
            if corner is not None:          # two lines meant to meet at a corner: both run on (or back) to it
                _set_end(ea, na, corner)
                _set_end(eb, nb, corner)
            else:                           # in line with each other: the end that moves along its own line moves
                if _sideways(ea, na, pb) <= _sideways(eb, nb, pa):
                    _set_end(ea, na, pb)
                else:
                    _set_end(eb, nb, pa)
        elif ma:
            _set_end(ea, na, pb)            # an arc's end stays: the line comes to it
        else:
            _set_end(eb, nb, pa)
        sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "COINCIDENT", [ea.entity_id, eb.entity_id], [na, nb]))
        joined += 1
    if joined:
        done.append(f"joined {joined} gap(s)")

    # 3. a line end just short of (or just past) another curve: extend or shorten it to touch
    reached = 0
    for e, name, p, movable in free_ends(sketch):
        if not movable:
            continue
        other = np.asarray(e.p2 if name == "p1" else e.p1, float)
        d = p - other
        length = float(np.linalg.norm(d))
        if length < JOINED:
            continue
        d /= length
        hits = []
        for o, a, b in _segments(sketch, skip=e):
            hit = _ray_hit(p, d, a, b)
            if hit is not None and abs(hit[0]) < tol and length + hit[0] > JOINED:   # never through its other end
                hits.append(hit)
        if hits:
            t, q = min(hits, key=lambda h: abs(h[0]))
            _set_end(e, name, q)
            reached += 1
    if reached:
        done.append(f"extended or trimmed {reached} line end(s) to touch")

    # 4. close what is still open with new lines, nearest free ends first. An end of a curve that already bounds a
    # face is only a tail sticking out past a corner (an overshoot): nothing to close there.
    added = 0
    sketch.solve_profiles()
    in_face = _bounding_entities(sketch)
    free = [f for f in free_ends(sketch) if f[0].entity_id not in in_face]
    while len(free) >= 2:
        pairs = [(float(np.linalg.norm(free[i][2] - free[j][2])), i, j)
                 for i in range(len(free)) for j in range(i + 1, len(free))
                 if not (free[i][0] is free[j][0] and (len(free) > 2 or isinstance(free[i][0], SketchLine)))]
        if not pairs:
            break
        _, i, j = min(pairs)
        a, b = free[i], free[j]
        ln = sketch.add_line(tuple(a[2]), tuple(b[2]))
        sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "COINCIDENT", [ln.entity_id, a[0].entity_id], ["p1", a[1]]))
        sketch.constraints.append(SketchConstraint(sketch.new_constraint_id(), "COINCIDENT", [ln.entity_id, b[0].entity_id], ["p2", b[1]]))
        added += 1
        free = [f for k, f in enumerate(free) if k not in (i, j)]
    if added:
        done.append(f"closed {added} opening(s) with a line")

    sketch.solve_profiles()
    return done
