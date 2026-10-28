"""Faces refs for CAD mesh geometry."""

from typing import List
import numpy as np
from omacad.model.faces_types import PlanarEdge, CircularEdge


def match_edge(stored_p0, stored_p1, candidates: List[PlanarEdge], tol: float = 1e-3):
    """The candidate lying on the same line as a stored edge (it may have been shortened by
    earlier rounding at its ends). Returns the one overlapping most, or None."""
    a = np.asarray(stored_p0, dtype=float)
    b = np.asarray(stored_p1, dtype=float)
    L = np.linalg.norm(b - a)
    if L < 1e-9:
        return None
    t = (b - a) / L
    best, best_overlap = None, 1e-6
    for c in candidates:
        for q in (c.p0, c.p1):
            if np.linalg.norm((q - a) - ((q - a) @ t) * t) > tol * max(1.0, L):
                break
        else:
            lo, hi = sorted((float((c.p0 - a) @ t), float((c.p1 - a) @ t)))
            overlap = min(hi, L) - max(lo, 0.0)
            if overlap > best_overlap:
                best, best_overlap = c, overlap
    return best

def edge_from_ref(ref, candidates):
    """The current edge a stored Fillet/Chamfer reference points at (lines may have been shortened)."""
    if ref and ref[0] == "wrapped":
        return next((e for e in candidates if getattr(e, "kind", "") == "wrapped" and e.matches(ref)), None)
    if ref and ref[0] == "curve":
        return next((e for e in candidates if getattr(e, "kind", "") == "curve" and e.matches(ref)), None)
    if ref and ref[0] == "arc":
        probe = CircularEdge(np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3]), 1.0, 1.0, True,
                             a0=float(ref[4]), sweep=float(ref[5]))
        return next((c for c in candidates if getattr(c, "kind", "") == "circle" and probe.same_as(c)), None)
    if ref and ref[0] == "circle":
        probe = CircularEdge(np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3]), 1.0, 1.0, True)
        return next((c for c in candidates if getattr(c, "kind", "") == "circle" and probe.same_as(c)), None)
    if ref and ref[0] == "loop":
        c0, n0, per = np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3])
        tol = 1e-3 * max(1.0, per)
        return next((c for c in candidates if getattr(c, "kind", "") == "loop" and float(c.n @ n0) > 0.999
                     and np.linalg.norm(c.centroid - c0) < tol and abs(c.perimeter - per) < tol), None)
    lines = [c for c in candidates if getattr(c, "kind", "") == "line"]
    return match_edge(ref[0], ref[1], lines)

def fuzzy_edge_from_ref(ref, candidates, used=(), reach: float = 1e9):
    """When an upstream change moved or resized the geometry (a longer box, a wider cylinder) the stored
    end points no longer lie on any edge. Pick the same kind of edge that is nearest to where the old one was:
    a parallel line, a circle round the same axis, an outline facing the same way. Edges already claimed by
    another reference in the same step (`used`) are not taken twice."""
    def free(c):
        return not any(c is u or (getattr(c, "kind", "") == getattr(u, "kind", "") and c.same_as(u)) for u in used)

    if ref and ref[0] == "wrapped":
        matches = [e for e in candidates if getattr(e, "kind", "") == "wrapped" and free(e) and e.matches(ref, reach=reach)]
        return min(matches, key=lambda e: np.linalg.norm(e.centroid-np.asarray(ref[1])), default=None)
    if ref and ref[0] == "curve":
        matches = [e for e in candidates if getattr(e, "kind", "") == "curve" and free(e) and e.matches(ref, reach=reach)]
        return min(matches, key=lambda e: np.linalg.norm(e.centroid - np.asarray(ref[1])), default=None)
    if ref and ref[0] in ("circle", "arc"):
        c0, ax, R = np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3])
        cand = [c for c in candidates if getattr(c, "kind", "") == "circle" and free(c) and float(c.axis @ ax) > 0.999
                and c.is_arc == (ref[0] == "arc")]
        cand = [c for c in cand if np.linalg.norm(c.center - c0) <= reach]
        # same side of the part: the circle's centre moves least along its own axis
        return min(cand, key=lambda c: np.linalg.norm(c.center - c0) + 0.05 * abs(c.radius - R), default=None)
    if ref and ref[0] == "loop":
        c0, n0, per = np.array(ref[1], dtype=float), np.array(ref[2], dtype=float), float(ref[3])
        cand = [c for c in candidates if getattr(c, "kind", "") == "loop" and free(c) and float(c.n @ n0) > 0.999
                and 0.4 <= c.perimeter / max(per, 1e-9) <= 2.5 and np.linalg.norm(c.centroid - c0) <= reach]
        return min(cand, key=lambda c: np.linalg.norm(c.centroid - c0), default=None)
    a, b = np.array(ref[0], dtype=float), np.array(ref[1], dtype=float)
    L = float(np.linalg.norm(b - a))
    if L < 1e-9:
        return None
    t = (b - a) / L
    mid = (a + b) / 2.0
    cand = []
    for c in candidates:
        if getattr(c, "kind", "") != "line" or not free(c):
            continue
        d = c.p1 - c.p0
        lc = float(np.linalg.norm(d))
        if lc < 1e-9 or abs(float(d @ t)) / lc < 0.999:
            continue
        cmid = (c.p0 + c.p1) / 2.0
        off = cmid - mid
        dist = float(np.linalg.norm(off - (off @ t) * t))   # how far the line moved sideways
        if dist <= reach:
            cand.append((dist + 0.25 * abs(lc - L) + 0.01 * abs(float(off @ t)), c))
    return min(cand, key=lambda z: z[0], default=(0, None))[1]
