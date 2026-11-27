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
    n1: np.ndarray | None = None
    n2: np.ndarray | None = None

    kind = "curve"

    @property
    def closed(self) -> bool:
        return bool(np.linalg.norm(self.pts[0] - self.pts[-1]) < 1e-9)

    def circle_fit(self):
        """If this is a closed circular crease, return `(center, axis, u, w, radius, max_err)`, else `None`."""
        if not self.closed or len(self.pts) < 9:
            return None
        P = self.pts[:-1]
        c = P.mean(axis=0)
        _, _, vh = np.linalg.svd(P - c)
        axis, u, w = vh[-1], vh[0], vh[1]
        plane_err = float(np.abs((P - c) @ axis).max())
        xy = np.c_[(P - c) @ u, (P - c) @ w]
        sol, *_ = np.linalg.lstsq(np.c_[2.0 * xy, np.ones(len(xy))], (xy ** 2).sum(axis=1), rcond=None)
        cx, cy = float(sol[0]), float(sol[1])
        R = float(math.sqrt(max(float(sol[2]) + cx * cx + cy * cy, 0.0)))
        if R < 1e-6:
            return None
        circle_err = float(np.abs(np.hypot(xy[:, 0] - cx, xy[:, 1] - cy) - R).max())
        tol = 0.01 * max(1.0, R)
        if plane_err > tol or circle_err > tol:
            return None
        center = c + cx * u + cy * w
        return center, axis, u, w, R, max(plane_err, circle_err)

    def is_roundable(self) -> bool:
        return bool(self.closed and len(self.pts) >= 4 and self.n1 is not None and self.n2 is not None)

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


def curve_edges(v, f, tm, find, planar, claimed_planar=None) -> list:
    """Chains of mesh edges sharper than CREASE_DEG where neither side is a flat face, joined through vertices
    that only two of them meet in."""
    adj, edge_ids = tm.face_adjacency, tm.face_adjacency_edges
    sharp = tm.face_adjacency_angles >= math.radians(CREASE_DEG)
    diag = float(np.linalg.norm(np.ptp(v, axis=0))) or 1.0
    area = tm.area_faces
    face_normals = tm.face_normals
    skip = planar if claimed_planar is None else claimed_planar
    segs = []
    # the cheap tests for every adjacent pair at once; only the few sharp candidates go through the loop below
    if len(adj):
        roots = np.fromiter((find(int(i)) for i in range(len(area))), dtype=np.int64, count=len(area))
        ra_all, rb_all = roots[adj[:, 0]], roots[adj[:, 1]]
        planar_ids, skip_ids = np.fromiter(planar, dtype=np.int64), np.fromiter(skip, dtype=np.int64)
        in_planar_a, in_planar_b = np.isin(ra_all, planar_ids), np.isin(rb_all, planar_ids)
        min_area = 1e-12 * diag * diag
        cand = np.flatnonzero(sharp & ~(in_planar_a & in_planar_b) & ~np.isin(ra_all, skip_ids)
                              & ~np.isin(rb_all, skip_ids) & (area[adj[:, 0]] > min_area) & (area[adj[:, 1]] > min_area))
    else:
        cand = np.zeros(0, dtype=np.int64)
    for i in cand:
        (a, b), (e0, e1) = adj[i], edge_ids[i]
        if True:
            na, nb = face_normals[a], face_normals[b]
            if float(np.cross(na, nb) @ (v[e1] - v[e0])) < 0:
                na, nb = nb, na
                third_b = v[[k for k in f[a] if k not in (e0, e1)][0]]
            else:
                third_b = v[[k for k in f[b] if k not in (e0, e1)][0]]
            conv = float(na @ (third_b - v[e0])) < 0
            segs.append((int(e0), int(e1), na, nb, conv))
    at = {}
    for i, (p, q, *_rest) in enumerate(segs):
        at.setdefault(p, []).append(i)
        at.setdefault(q, []).append(i)
    done, out = set(), []

    def walk(start, vertex):
        """Vertices from `vertex` on through the segment `start`, until a junction, an end or the beginning."""
        chain, seg = [vertex], start
        n1_list, n2_list, conv_votes = [], [], 0
        while seg not in done:
            done.add(seg)
            p, q, na, nb, conv = segs[seg]
            if p == vertex:
                vertex = q
                n1_list.append(na)
                n2_list.append(nb)
            else:
                vertex = p
                n1_list.append(nb)
                n2_list.append(na)
            conv_votes += 1 if conv else -1
            chain.append(vertex)
            nxt = [s for s in at[vertex] if s != seg]
            if len(at[vertex]) != 2 or not nxt:
                break
            seg = nxt[0]
        return chain, n1_list, n2_list, conv_votes >= 0

    ends = [vtx for vtx, s in at.items() if len(s) != 2]
    for vtx in ends:                                   # open chains first, from their ends
        for s in at[vtx]:
            if s not in done:
                out.append(walk(s, vtx))
    for i, (p, _q, *_rest) in enumerate(segs):       # what is left are closed rings
        if i not in done:
            out.append(walk(i, p))

    def vertex_normals(n_list, closed):
        arr = np.asarray(n_list, dtype=float)
        if closed:
            vn = arr + np.roll(arr, 1, axis=0)
            vn = np.vstack([vn, vn[0:1]])
        else:
            vn = np.empty((len(arr) + 1, 3), dtype=float)
            vn[0] = arr[0]
            vn[1:-1] = arr[:-1] + arr[1:]
            vn[-1] = arr[-1]
        norms = np.linalg.norm(vn, axis=1, keepdims=True)
        return vn / np.maximum(norms, 1e-12)

    edges = []
    for chain, n1_list, n2_list, convex in out:
        if len(chain) < 3:
            continue
        closed = chain[0] == chain[-1]
        pts = v[np.asarray(chain)].astype(float)
        edges.append(CurveEdge(pts, convex=convex, n1=vertex_normals(n1_list, closed), n2=vertex_normals(n2_list, closed)))
    return [e for e in edges if e.length > MIN_LENGTH * diag]
