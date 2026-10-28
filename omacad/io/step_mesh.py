"""Clean a triangle mesh so it can be written as a faceted STEP solid.

STEP readers (OpenCASCADE in Bambu Studio, FreeCAD, ...) build a vertex per
CARTESIAN_POINT and reject the whole solid when a facet is degenerate. Manifold
meshes can hold separate vertices at the same spot (where a body touches itself)
and slivers flatter than the written precision, so before writing we
1. weld vertices closer than WELD_TOL and drop triangles that collapse, and
2. remove each remaining sliver by splitting its neighbour across the long edge
   at the sliver's middle vertex (same surface, still closed and manifold).
"""
from typing import Tuple

import numpy as np

DECIMALS = 6
SLIVER_HEIGHT = 10.0 ** -DECIMALS
WELD_TOL = 10 * SLIVER_HEIGHT


def weld(verts: np.ndarray, tris: np.ndarray, tol: float = WELD_TOL) -> Tuple[np.ndarray, np.ndarray]:
    """Merge vertices closer than `tol` (union-find over a grid); drop triangles that lose a corner."""
    v = np.asarray(verts, dtype=float)
    parent = list(range(len(v)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cells = {}
    for i, key in enumerate(map(tuple, np.floor(v / tol).astype(np.int64))):
        cells.setdefault(key, []).append(i)
    offsets = [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)]
    for (cx, cy, cz), members in cells.items():
        for dx, dy, dz in offsets:
            for j in cells.get((cx + dx, cy + dy, cz + dz), ()):
                for i in members:
                    if i < j and np.linalg.norm(v[i] - v[j]) <= tol:
                        parent[root(j)] = root(i)
    roots = np.array([root(i) for i in range(len(v))], dtype=int)
    used, inv = np.unique(roots, return_inverse=True)
    t = inv[np.asarray(tris, dtype=int)]
    keep = (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])
    return v[used], t[keep]


def _sliver(pts: np.ndarray, tri) -> Tuple[int, int, int] | None:
    """(p, q, r) with p->q the triangle's longest directed edge and r its apex, if flatter than SLIVER_HEIGHT."""
    for k in range(3):
        p, q, r = tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]
        base = np.linalg.norm(pts[q] - pts[p])
        if base >= np.linalg.norm(pts[r] - pts[q]) and base >= np.linalg.norm(pts[p] - pts[r]):
            height = np.linalg.norm(np.cross(pts[q] - pts[p], pts[r] - pts[p])) / base
            return (p, q, r) if height < SLIVER_HEIGHT else None
    return None


def _flat(pts: np.ndarray, tris) -> np.ndarray:
    """Indices of live triangles thinner than SLIVER_HEIGHT (vectorised pre-filter for _sliver)."""
    idx = np.array([i for i, t in enumerate(tris) if t is not None], dtype=int)
    if len(idx) == 0:
        return idx
    t = np.array([tris[i] for i in idx], dtype=int)
    a, b, c = pts[t[:, 0]], pts[t[:, 1]], pts[t[:, 2]]
    longest = np.max([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], axis=0)
    height = np.linalg.norm(np.cross(b - a, c - a), axis=1) / np.maximum(longest, 1e-300)
    return idx[height < SLIVER_HEIGHT]


def remove_slivers(pts: np.ndarray, tris: np.ndarray, max_passes: int = 10) -> np.ndarray:
    """Split each sliver's neighbour at the sliver's apex; area and closedness stay exact."""
    tris = [tuple(t) for t in tris]
    owner = {}
    for i, (a, b, c) in enumerate(tris):
        owner[(a, b)] = owner[(b, c)] = owner[(c, a)] = i

    def put(tri):
        tris.append(tri)
        a, b, c = tri
        owner[(a, b)] = owner[(b, c)] = owner[(c, a)] = len(tris) - 1

    def drop(i):
        a, b, c = tris[i]
        for e in ((a, b), (b, c), (c, a)):
            if owner.get(e) == i:
                del owner[e]
        tris[i] = None

    for _ in range(max_passes):
        changed = False
        for i in _flat(pts, tris):
            if tris[i] is None or (s := _sliver(pts, tris[i])) is None:
                continue
            p, q, r = s
            j = owner.get((q, p))
            if j is None or j == i:
                continue
            nb = tris[j]
            o = nb[(nb.index(q) + 2) % 3]
            if o == r or (r, o) in owner or (o, r) in owner:
                continue
            # neighbour q->p->o becomes q->r->o and r->p->o; the sliver p->q->r goes away.
            drop(i)
            drop(j)
            put((q, r, o))
            put((r, p, o))
            changed = True
        if not changed:
            break
    return np.array([t for t in tris if t is not None], dtype=int).reshape(-1, 3)


def clean_for_step(verts: np.ndarray, tris: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Welded, sliver-free mesh with points already rounded to the written precision,
    so facet planes computed from it hold every corner exactly."""
    pts, t = weld(verts, tris)
    pts = np.round(pts, DECIMALS)
    return pts, remove_slivers(pts, t)


def step_str(text: str) -> str:
    """A STEP string literal body: quotes doubled, backslash and non-ASCII as \\X2\\hhhh\\X0\\."""
    out = []
    for ch in str(text):
        if ch == "'":
            out.append("''")
        elif ch == "\\" or not (32 <= ord(ch) < 127):
            out.append("\\X2\\" + "".join(f"{u:04X}" for u in _utf16(ch)) + "\\X0\\")
        else:
            out.append(ch)
    return "".join(out)


def _utf16(ch: str):
    data = ch.encode("utf-16-be")
    return [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]
