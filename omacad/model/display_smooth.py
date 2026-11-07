"""Smooth look for the view ("Fast view, exact export"): curved triangles of a render mesh are split and their new
corners pushed out onto the curve the corner normals describe (Phong tessellation), so a circle built with few
pieces is drawn round, silhouette and edge lines included. Only what is drawn changes: picking, measuring and exports
keep using the real model.

Every midpoint belongs to its edge, not to a triangle: the triangles on both sides of an edge get the same point, so
no crack opens where a curved wall meets a flat cap (the cap's rim moves out with the wall, in its own plane)."""
import numpy as np

# Weight of the tangent-plane projection. 0.5 puts the midpoint of a chord of a circle on the circle (to the
# fourth order in the chord angle); Phong tessellation's usual 0.75 bulges a circle out.
SHAPE = 0.5
MAX_TRIANGLES = 2_000_000       # drawn triangles a smoothed body may grow to
LEVELS = 2                      # each level halves the angle a piece spans


def _vertex_ids(points: np.ndarray):
    """Unique positions and, for every row of `points`, its index among them."""
    p = np.ascontiguousarray(points, dtype=np.float32)
    keys = p.view(np.dtype((np.void, p.dtype.itemsize * 3))).ravel()
    _, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
    return p[first].astype(np.float64), inverse.ravel()


def _curved(normals: np.ndarray) -> np.ndarray:
    """Triangles whose corners have different normals (smooth shaded); flat triangles share one normal."""
    n0, n1, n2 = normals[:, 0], normals[:, 1], normals[:, 2]
    least = np.minimum(np.minimum((n0 * n1).sum(1), (n1 * n2).sum(1)), (n0 * n2).sum(1))
    return least < 1.0 - 1e-7


def _level(P, T, N, curved, L):
    """One split of every triangle that is curved or borders a curved one. Returns the new P, T, N, curved, L."""
    nv = len(P)
    pairs = np.array([[0, 1], [1, 2], [2, 0]])
    a, b = T[:, pairs[:, 0]], T[:, pairs[:, 1]]                     # (F, 3) edge ends
    lo, hi = np.minimum(a, b).ravel(), np.maximum(a, b).ravel()
    code = lo * np.int64(1 << 31) + hi
    ukeys, inv = np.unique(code, return_inverse=True)
    inv = inv.ravel()

    pa, pb = P[a].reshape(-1, 3), P[b].reshape(-1, 3)
    na, nb = N[:, pairs[:, 0]].reshape(-1, 3), N[:, pairs[:, 1]].reshape(-1, 3)
    mid = 0.5 * (pa + pb)
    proj_a = mid - ((mid - pa) * na).sum(1, keepdims=True) * na
    proj_b = mid - ((mid - pb) * nb).sum(1, keepdims=True) * nb
    bulged = mid + SHAPE * (0.5 * (proj_a + proj_b) - mid)

    w = np.repeat(curved, 3).astype(np.float64)
    count = np.bincount(inv, weights=w, minlength=len(ukeys))
    total = np.zeros((len(ukeys), 3))
    linear = np.zeros((len(ukeys), 3))
    np.add.at(total, inv, bulged * w[:, None])
    linear[inv] = mid
    edge_mid = np.where(count[:, None] > 0, total / np.maximum(count, 1)[:, None], linear)

    split = curved | (count[inv].reshape(-1, 3) > 0).any(1)
    m_id = (nv + inv).reshape(-1, 3)                                 # midpoint ids per (tri, edge)
    m_n = na + nb
    m_n /= np.maximum(np.linalg.norm(m_n, axis=1, keepdims=True), 1e-12)
    m_n = m_n.reshape(-1, 3, 3)

    s = np.flatnonzero(split)
    t, mi, n, mn = T[s], m_id[s], N[s], m_n[s]
    # corners: a b c, midpoints ab=0 bc=1 ca=2
    kids_t = np.concatenate([
        np.stack([t[:, 0], mi[:, 0], mi[:, 2]], 1),
        np.stack([mi[:, 0], t[:, 1], mi[:, 1]], 1),
        np.stack([mi[:, 2], mi[:, 1], t[:, 2]], 1),
        np.stack([mi[:, 0], mi[:, 1], mi[:, 2]], 1)])
    kids_n = np.concatenate([
        np.stack([n[:, 0], mn[:, 0], mn[:, 2]], 1),
        np.stack([mn[:, 0], n[:, 1], mn[:, 1]], 1),
        np.stack([mn[:, 2], mn[:, 1], n[:, 2]], 1),
        np.stack([mn[:, 0], mn[:, 1], mn[:, 2]], 1)])
    keep = ~split
    T2 = np.concatenate([T[keep], kids_t])
    N2 = np.concatenate([N[keep], kids_n])
    curved2 = np.concatenate([curved[keep], np.tile(curved[s], 4)])
    P2 = np.concatenate([P, edge_mid])

    if len(L):
        llo, lhi = np.minimum(L[:, 0], L[:, 1]), np.maximum(L[:, 0], L[:, 1])
        lcode = llo * np.int64(1 << 31) + lhi
        at = np.clip(np.searchsorted(ukeys, lcode), 0, len(ukeys) - 1)
        found = (ukeys[at] == lcode) & (count[at] > 0)
        m = nv + at
        L = np.concatenate([L[~found], np.stack([L[found, 0], m[found]], 1), np.stack([m[found], L[found, 1]], 1)])
    return P2, T2, N2, curved2, L


def smooth_arrays(vertices: np.ndarray, normals: np.ndarray, lines: np.ndarray, levels: int = LEVELS):
    """Unrolled triangle corners, their normals and edge-line pairs, smoothed for drawing. Unchanged when nothing
    is curved or the mesh is too big to grow."""
    vertices = np.asarray(vertices, dtype=np.float32)
    corner_n = np.asarray(normals, dtype=np.float64).reshape(-1, 3, 3)
    if len(corner_n) == 0:
        return vertices, normals, lines
    curved = _curved(corner_n)
    n_curved = int(curved.sum())
    while levels > 0 and len(corner_n) + n_curved * (4 ** levels) * 2 > MAX_TRIANGLES:
        levels -= 1
    if levels == 0 or n_curved == 0:
        return vertices, normals, lines

    lines = np.asarray(lines, dtype=np.float32).reshape(-1, 3)
    P, ids = _vertex_ids(np.concatenate([vertices, lines]))
    T = ids[:len(vertices)].reshape(-1, 3).astype(np.int64)
    L = ids[len(vertices):].reshape(-1, 2).astype(np.int64)
    for _ in range(levels):
        P, T, corner_n, curved, L = _level(P, T, corner_n, curved, L)
    return (P[T].reshape(-1, 3).astype(np.float32), corner_n.reshape(-1, 3).astype(np.float32),
            P[L].reshape(-1, 3).astype(np.float32))
