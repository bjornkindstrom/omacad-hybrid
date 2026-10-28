"""Free-form creases: sharp chains of mesh edges between two curved surfaces (the corner lines of a twisted
extrude or a loft). Straight edges, circles and outlines are found elsewhere; these are the rest."""
import math
from dataclasses import dataclass

import numpy as np

CREASE_DEG = 20.0
MIN_LENGTH = 0.15          # of the body's diagonal: shorter chains are tessellation detail (threads, letters)


@dataclass
class CurveEdge:
    pts: np.ndarray         # (N, 3) along the crease; the last point equals the first when it is closed
    convex: bool = True

    kind = "curve"

    @property
    def closed(self) -> bool:
        return bool(np.linalg.norm(self.pts[0] - self.pts[-1]) < 1e-9)

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.diff(self.pts, axis=0), axis=1).sum())

    @property
    def centroid(self) -> np.ndarray:
        return self.pts.mean(axis=0)

    def polyline(self, n: int = 0) -> np.ndarray:
        return self.pts

    def ref(self):
        return ("curve", tuple(map(float, self.centroid)), float(self.length))

    def matches(self, ref, reach=None) -> bool:
        tol = 1e-3 * max(1.0, self.length)
        return (np.linalg.norm(self.centroid - np.asarray(ref[1])) < (tol if reach is None else reach)
                and (abs(self.length - ref[2]) < tol if reach is None else 0.4 < self.length / max(ref[2], 1e-9) < 2.5))

    def same_as(self, other) -> bool:
        return getattr(other, "kind", "") == self.kind and self.matches(other.ref())


def curve_edges(v, f, tm, find, planar) -> list:
    """Chains of mesh edges sharper than CREASE_DEG where neither side is a flat face, joined through vertices
    that only two of them meet in."""
    adj, edge_ids = tm.face_adjacency, tm.face_adjacency_edges
    sharp = tm.face_adjacency_angles >= math.radians(CREASE_DEG)
    diag = float(np.linalg.norm(np.ptp(v, axis=0))) or 1.0
    area = tm.area_faces
    segs = []
    for (a, b), (e0, e1), keep in zip(adj, edge_ids, sharp):
        if keep and find(int(a)) not in planar and find(int(b)) not in planar \
                and area[a] > 1e-9 * diag * diag and area[b] > 1e-9 * diag * diag:
            segs.append((int(e0), int(e1)))
    at = {}
    for i, (p, q) in enumerate(segs):
        at.setdefault(p, []).append(i)
        at.setdefault(q, []).append(i)
    done, out = set(), []

    def walk(start, vertex):
        """Vertices from `vertex` on through the segment `start`, until a junction, an end or the beginning."""
        chain, seg = [vertex], start
        while seg not in done:
            done.add(seg)
            p, q = segs[seg]
            vertex = q if p == vertex else p
            chain.append(vertex)
            nxt = [s for s in at[vertex] if s != seg]
            if len(at[vertex]) != 2 or not nxt:
                break
            seg = nxt[0]
        return chain

    ends = [vtx for vtx, s in at.items() if len(s) != 2]
    for vtx in ends:                                   # open chains first, from their ends
        for s in at[vtx]:
            if s not in done:
                out.append(walk(s, vtx))
    for i, (p, _q) in enumerate(segs):             # what is left are closed rings
        if i not in done:
            out.append(walk(i, p))
    edges = [CurveEdge(v[np.asarray(c)].astype(float)) for c in out if len(c) >= 3]
    return [e for e in edges if e.length > MIN_LENGTH * diag]
