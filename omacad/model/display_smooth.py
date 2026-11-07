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
FLAT_DEG = 1.0                  # corner normals this close to the triangle's own normal: drawn flat, not bulged
                                # (a 72-piece circle spans 5° per piece, its corners lean 2.5°)
MAX_LEAN = 0.35                 # sin of the most an edge may lean on a corner normal and still be bulged (~40° span)
NEEDLE = 1e-3                   # 2·area / longest² below this: a needle, never moves an edge (height < 0.1 % of length)
MIN_AGREE = 0.5                 # a corner normal further than 60° from its triangle's own normal is borrowed
MAX_SAG = 0.1                  # largest bulge per edge length (a 40° chord sags 0.044 of its length)


def _vertex_ids(points: np.ndarray):
    """Unique positions and, for every row of `points`, its index among them."""
    p = np.ascontiguousarray(points, dtype=np.float32)
    keys = p.view(np.dtype((np.void, p.dtype.itemsize * 3))).ravel()
    _, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
    return p[first].astype(np.float64), inverse.ravel()


def _curved(normals: np.ndarray, points: np.ndarray = None) -> np.ndarray:
    """Triangles whose corners have different normals (smooth shaded); flat triangles share one normal.
    With `points`, a triangle whose corner normals all stay within FLAT_DEG of its own normal is flat too: a big
    box side next to a rounded corner borrows a slightly tilted normal at the seam (0.7°), and bulging it lifted
    the middle of the side 0.1 mm off the real face, so the hover highlight sank behind it in stripes (#203)."""
    n0, n1, n2 = normals[:, 0], normals[:, 1], normals[:, 2]
    least = np.minimum(np.minimum((n0 * n1).sum(1), (n1 * n2).sum(1)), (n0 * n2).sum(1))
    curved = least < 1.0 - 1e-7
    if points is not None and curved.any():
        t = points.reshape(-1, 3, 3)
        own = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        own /= np.maximum(np.linalg.norm(own, axis=1, keepdims=True), 1e-12)
        closest = np.min((normals * own[:, None, :]).sum(2), axis=1)
        curved &= ~(closest > np.cos(np.radians(FLAT_DEG)))
    return curved


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
    # Only an edge that lies in both corners' tangent planes is a chord of the curve. A needle or a degenerate
    # triangle of a boolean seam can join an inner and an outer wall, or run across a cap while its corners carry
    # the wall's normals; bulging such an edge pushed points up to 0.9 mm out of the wall and drew streaks and
    # bumps on a plain jar (Björn #214). A real chord leans sin(span/2) on its normals and bulges by its sagitta.
    edge = pb - pa
    length = np.linalg.norm(edge, axis=1)
    unit = edge / np.maximum(length, 1e-12)[:, None]
    lean = np.maximum(np.abs((unit * na).sum(1)), np.abs((unit * nb).sum(1)))
    shift = np.linalg.norm(bulged - mid, axis=1)
    chord = (lean < MAX_LEAN) & (shift <= MAX_SAG * length) & ((na * nb).sum(1) > 0.0)
    bulged = np.where(chord[:, None], bulged, mid)

    # Only a sound triangle may move an edge: a needle or a zero-area sliver has no direction of its own, and its
    # corners often carry a neighbour's normals from the far side of a thin wall (#214)
    tri = P[T]
    own = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    twice_area = np.linalg.norm(own, axis=1)
    own /= np.maximum(twice_area, 1e-30)[:, None]
    longest = np.max(np.linalg.norm(tri - np.roll(tri, 1, axis=1), axis=2), axis=1)
    sound = (twice_area > NEEDLE * longest * longest) & np.all((N * own[:, None, :]).sum(2) > MIN_AGREE, axis=1)
    w = np.repeat(curved & sound, 3).astype(np.float64)
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
    curved = _curved(corner_n, vertices.astype(np.float64))
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
