"""Solids that manifold3d has no call for: a profile swept along a path (Sweep, Pipe) and a skin through several
profiles (Loft). Each is a stack of rings with the same number of points, joined side by side and capped at the
ends (Björn #46)."""

import math
from typing import List, Optional, Sequence

import numpy as np
import manifold3d as m3d


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


CORNER_DEG = 20.0      # a ring point that turns more than this is a corner a resampled ring keeps
LOFT_TWIST_DEG = 4.0   # most a side segment may turn from one loft ring to the next before rings go in between


def ring_corners(ring) -> List[int]:
    """Indices of the points where a closed ring turns sharply (a rectangle's corners, not a circle's facets)."""
    pts = np.asarray(ring, dtype=float)
    d_in = pts - np.roll(pts, 1, axis=0)
    d_out = np.roll(pts, -1, axis=0) - pts
    ln = np.linalg.norm(d_in, axis=1) * np.linalg.norm(d_out, axis=1)
    cos = np.einsum("ij,ij->i", d_in, d_out) / np.maximum(ln, 1e-18)
    return [i for i in range(len(pts)) if ln[i] > 1e-18 and cos[i] < math.cos(math.radians(CORNER_DEG))]


def _even(pts: np.ndarray, at: np.ndarray) -> np.ndarray:
    """Points at arc lengths `at` along the open polyline `pts`."""
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    return np.column_stack([np.interp(at, cum, pts[:, d]) for d in range(pts.shape[1])])


def resample_ring(ring, n: int, corners: Optional[Sequence[int]] = None) -> np.ndarray:
    """`n` points spread by length round a closed ring. Every corner (`corners`, by default `ring_corners`) is one
    of the points, so a rectangle stays a rectangle; without corners the start is kept."""
    pts = np.asarray(ring, dtype=float)
    corners = sorted(ring_corners(pts) if corners is None else corners)
    if not corners or len(corners) > n:
        corners = [0]
    spans = [np.vstack([pts[a:b + 1] if a < b else np.vstack([pts[a:], pts[:b + 1]])])
             for a, b in zip(corners, corners[1:] + corners[:1])]
    lengths = np.array([float(np.sum(np.linalg.norm(np.diff(sp, axis=0), axis=1))) for sp in spans])
    if lengths.sum() <= 1e-12:
        return np.repeat(pts[:1], n, axis=0)
    share = (n - len(spans)) * lengths / lengths.sum()       # points besides the corners, largest remainder
    extra = np.floor(share).astype(int)
    extra[np.argsort(extra - share)[:n - len(spans) - int(extra.sum())]] += 1
    out = [_even(sp, np.linspace(0.0, ln, k + 1, endpoint=False)) for sp, ln, k in zip(spans, lengths, extra)]
    return np.vstack(out)


def signed_area(ring2d) -> float:
    p = np.asarray(ring2d, dtype=float)
    q = np.roll(p, -1, axis=0)
    return 0.5 * float(np.sum(p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]))


def ring_solid(rings: Sequence[np.ndarray], start_cap2d: Optional[np.ndarray] = None,
               end_cap2d: Optional[np.ndarray] = None, closed: bool = False) -> m3d.Manifold:
    """A solid skinned through `rings` (each (N, 3), same N, same turning sense). Open ends are capped with the
    triangulation of the matching 2D ring (the ring in its own plane coordinates, counter-clockwise); `closed`
    joins the last ring back to the first (a path that comes round)."""
    rings = [np.asarray(r, dtype=float) for r in rings]
    m, n = len(rings), len(rings[0])
    verts = np.vstack(rings)
    tris = []
    steps = m if closed else m - 1
    for k in range(steps):
        k2 = (k + 1) % m
        for i in range(n):
            j = (i + 1) % n
            a, b, c, d = k * n + i, k * n + j, k2 * n + j, k2 * n + i
            tris.append((a, b, c))
            tris.append((a, c, d))
    if not closed:
        start = m3d.triangulate([np.asarray(start_cap2d, dtype=float)])
        end = m3d.triangulate([np.asarray(end_cap2d, dtype=float)])
        tris += [(int(t[0]), int(t[2]), int(t[1])) for t in start]                     # faces back
        tris += [(int(t[0]) + (m - 1) * n, int(t[1]) + (m - 1) * n, int(t[2]) + (m - 1) * n) for t in end]
    tri = np.asarray(tris, dtype=np.uint64)
    for attempt in (tri, tri[:, ::-1]):                     # whichever turning sense gives an outward skin
        solid = m3d.Manifold(m3d.Mesh64(vert_properties=verts, tri_verts=np.ascontiguousarray(attempt)))
        if solid.status() == m3d.Error.NoError and not solid.is_empty() and solid.volume() > 0:
            return solid
    return m3d.Manifold()


# ---- along a path ----------------------------------------------------------------------------------------
def path_frames(path: np.ndarray, closed: bool = False, start_normal=None):
    """Tangent, normal, binormal at each path point (rotation-minimising frames, so the section does not twist), plus
    a stretch factor and direction for sharp corners: the section there lies in the bisecting plane, stretched
    1/cos(half the turn) across the bend so the walls meet in a clean mitre."""
    p = np.asarray(path, dtype=float)
    n = len(p)
    tang = np.zeros_like(p)
    stretch = np.ones(n)
    across = np.zeros_like(p)
    for i in range(n):
        if closed or 0 < i < n - 1:
            t_in = _unit(p[i] - p[i - 1])
            t_out = _unit(p[(i + 1) % n] - p[i])
            t = t_in + t_out
            if np.linalg.norm(t) < 1e-9:
                t = t_out
            tang[i] = _unit(t)
            cos_half = float(np.clip(tang[i] @ t_out, 1e-3, 1.0))
            if cos_half < 0.9999:
                stretch[i] = 1.0 / cos_half
                across[i] = _unit(t_out - t_in)
        elif i == 0:
            tang[i] = _unit(p[1] - p[0])
        else:
            tang[i] = _unit(p[-1] - p[-2])
    r0 = None if start_normal is None else np.asarray(start_normal, dtype=float)
    if r0 is None or np.linalg.norm(r0 - (r0 @ tang[0]) * tang[0]) < 1e-9:
        hint = np.array([0.0, 0.0, 1.0]) if abs(tang[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        r0 = hint
    r = [_unit(r0 - (r0 @ tang[0]) * tang[0])]
    for i in range(n - 1):                                  # double reflection (Wang et al. 2008)
        v1 = p[i + 1] - p[i]
        c1 = float(v1 @ v1)
        if c1 < 1e-18:
            r.append(r[-1])
            continue
        rl = r[-1] - (2.0 / c1) * float(v1 @ r[-1]) * v1
        tl = tang[i] - (2.0 / c1) * float(v1 @ tang[i]) * v1
        v2 = tang[i + 1] - tl
        c2 = float(v2 @ v2)
        r.append(_unit(rl - (2.0 / c2) * float(v2 @ rl) * v2) if c2 > 1e-18 else rl)
    r = np.asarray(r)
    b = np.cross(tang, r)
    return tang, r, b, stretch, across


def sweep_ring(section2d: np.ndarray, path: np.ndarray, closed: bool = False, start_normal=None,
               twist_deg: float = 0.0) -> List[np.ndarray]:
    """The 2D section (x along the start normal, y along the binormal, origin on the path) placed at every path
    point. `twist_deg` turns it gradually over the length."""
    tang, r, b, stretch, across = path_frames(path, closed, start_normal)
    sec = np.asarray(section2d, dtype=float)
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = max(cum[-1], 1e-12)
    rings = []
    for i, p in enumerate(path):
        a = math.radians(twist_deg) * cum[i] / total
        x = sec[:, 0] * math.cos(a) - sec[:, 1] * math.sin(a)
        y = sec[:, 0] * math.sin(a) + sec[:, 1] * math.cos(a)
        q = x[:, None] * r[i] + y[:, None] * b[i]
        if stretch[i] != 1.0:
            q = q + (q @ across[i])[:, None] * across[i] * (stretch[i] - 1.0)
        rings.append(p + q)
    return rings


def sweep_solid(section2d, path, closed: bool = False, start_normal=None, twist_deg: float = 0.0) -> m3d.Manifold:
    sec = np.asarray(section2d, dtype=float)
    if signed_area(sec) < 0:
        sec = sec[::-1]
    path = np.asarray(path, dtype=float)
    if closed and np.linalg.norm(path[0] - path[-1]) < 1e-9:
        path = path[:-1]
    rings = sweep_ring(sec, path, closed, start_normal, twist_deg)
    return ring_solid(rings, sec, sec, closed=closed)


def pipe_solid(path, closed: bool, diameter: float, thickness: float = 0.0, segments: int = 48) -> m3d.Manifold:
    """Fusion's Pipe: a round section of `diameter` along the path; `thickness` > 0 makes it a tube."""
    a = np.linspace(0.0, 2 * math.pi, segments, endpoint=False)
    circle = lambda rad: np.column_stack([rad * np.cos(a), rad * np.sin(a)])
    path = np.asarray(path, dtype=float)
    solid = sweep_solid(circle(diameter / 2.0), path, closed)
    if thickness > 1e-6:
        inner_r = diameter / 2.0 - thickness
        if inner_r <= 1e-3:
            raise ValueError("The wall is as thick as the pipe: make it thinner.")
        inner_path = path.copy()
        if not closed:                                      # the bore runs a hair past both ends: clean openings
            inner_path[0] = path[0] - _unit(path[1] - path[0]) * 0.01
            inner_path[-1] = path[-1] + _unit(path[-1] - path[-2]) * 0.01
        solid = solid - sweep_solid(circle(inner_r), inner_path, closed)
    return solid


# ---- through several profiles ------------------------------------------------------------------------------
def _turned(ring: np.ndarray, axis: np.ndarray, deg: float) -> np.ndarray:
    """`ring` turned `deg` degrees (right-hand) about `axis` through its own centre (Rodrigues)."""
    c = ring.mean(axis=0)
    a = math.radians(deg)
    q = ring - c
    return c + q * math.cos(a) + np.cross(axis, q) * math.sin(a) + np.outer(q @ axis, axis) * (1 - math.cos(a))


def _between_rings(rings: List[np.ndarray], twists: Sequence[float] = ()) -> List[np.ndarray]:
    """Rings put in between where a side segment turns much from one ring to the next (a square's side against a
    circle's arc): the straight skin between them is curved, and one quad per step folds visibly along its
    diagonal. Linear steps keep the same ruled skin, only finer. `twists` (degrees turned at each ring, about the
    loft direction) adds rings so that no step turns more than LOFT_TWIST_DEG, each turned by its own share."""
    twists = list(twists) or [0.0] * len(rings)
    out = [rings[0]]
    for k, (a, b) in enumerate(zip(rings, rings[1:])):
        axis = _unit(b.mean(axis=0) - a.mean(axis=0))
        if twists[k]:
            out[-1] = _turned(a, axis, twists[k])
        da, db = np.roll(a, -1, axis=0) - a, np.roll(b, -1, axis=0) - b
        ln = np.linalg.norm(da, axis=1) * np.linalg.norm(db, axis=1)
        ok = ln > 1e-18
        cos = np.einsum("ij,ij->i", da[ok], db[ok]) / ln[ok]
        turn = math.degrees(math.acos(float(np.clip(cos.min(), -1.0, 1.0)))) if ok.any() else 0.0
        dt = twists[k + 1] - twists[k]
        steps = int(min(256, max(1, math.ceil(turn / LOFT_TWIST_DEG), math.ceil(abs(dt) / LOFT_TWIST_DEG))))
        for t in range(1, steps + 1):
            ring = a + (b - a) * (t / steps)
            out.append(_turned(ring, axis, twists[k] + dt * t / steps) if (twists[k] or dt) else ring)
    return out


def loft_solid(rings3d: Sequence[np.ndarray], caps2d: Sequence[np.ndarray], n: int = 128, twist_deg: float = 0.0) -> m3d.Manifold:
    """A skin through closed 3D rings in order (`caps2d[0]` / `caps2d[-1]` are the first and last ring in their own
    plane coordinates, used for the end caps). The rings are resampled to `n` points, turned the same way round
    the loft direction, and each one's start is turned to line up with the one before. `twist_deg` turns the last
    profile that much against the first, in proportion to the distance along the loft."""
    if len(rings3d) < 2:
        raise ValueError("A loft needs at least two profiles.")
    corners = [ring_corners(r) for r in rings3d]
    rings = [resample_ring(r, n, c) for r, c in zip(rings3d, corners)]
    caps = [resample_ring(caps2d[0], n, corners[0]), resample_ring(caps2d[-1], n, corners[-1])]
    cents = [r.mean(axis=0) for r in rings]
    out = []
    for k, ring in enumerate(rings):
        d = _unit((cents[k + 1] - cents[k]) if k + 1 < len(rings) else (cents[k] - cents[k - 1]))
        area = 0.5 * np.sum(np.cross(ring, np.roll(ring, -1, axis=0)), axis=0)
        flipped = float(area @ d) < 0
        if flipped:
            ring = ring[::-1]
            if k == 0:
                caps[0] = caps[0][::-1]
            if k == len(rings) - 1:
                caps[1] = caps[1][::-1]
        if out:
            prev = out[-1] - cents[k - 1]
            cur = ring - cents[k]
            costs = [float(np.sum(np.linalg.norm(prev - np.roll(cur, -s, axis=0), axis=1))) for s in range(n)]
            s = int(np.argmin(costs))
            ring = np.roll(ring, -s, axis=0)
            if k == len(rings) - 1:
                caps[1] = np.roll(caps[1], -s, axis=0)
        out.append(ring)
    gaps = np.linalg.norm(np.diff(np.array(cents), axis=0), axis=1)
    share = np.concatenate([[0.0], np.cumsum(gaps)]) / (gaps.sum() or 1.0)
    out = _between_rings(out, [twist_deg * x for x in share] if twist_deg else ())
    # the caps' 2D rings must run counter-clockwise for the triangulation; their index order matches the 3D rings
    for i in (0, 1):
        if signed_area(caps[i]) < 0:
            caps[i] = caps[i] * np.array([1.0, -1.0])        # mirrored copy: same point order, ccw
    return ring_solid(out, caps[0], caps[1])
