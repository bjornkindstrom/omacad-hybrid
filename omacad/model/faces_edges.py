"""Faces edges for CAD mesh geometry."""

from typing import List
import math
import numpy as np
import manifold3d as m3d
import trimesh
from omacad.model.faces_types import PlanarEdge, CircularEdge, LoopEdge
from omacad.model.faces_topology import _coplanar, _curved_roots, _sliver_roots


def tangent_chain(edge, edges) -> list:
    """`edge` plus every straight piece or arc joined to it end to end with a smooth (tangent) turn,
    e.g. the straight side and the rounded corner next to it. Corners with a visible knick stop the chain, and so
    does a switch between an inside and an outside corner (the foot of a wall running on into the end of a fillet
    band): one rounding would fill there and cut here."""
    def ends(e):
        pts = e.polyline()
        t0 = pts[1] - pts[0]
        t1 = pts[-1] - pts[-2]
        return [(pts[0], -t0 / np.linalg.norm(t0)), (pts[-1], t1 / np.linalg.norm(t1))]
    pool = [c for c in edges if c.kind == "line" or (c.kind == "circle" and c.is_arc)]
    if edge.kind not in ("line", "circle") or (edge.kind == "circle" and not edge.is_arc):
        return [edge]
    chain, frontier = [edge], [edge]
    while frontier:
        cur = frontier.pop()
        for p, t in ends(cur):
            for c in pool:
                if getattr(c, "convex", None) != getattr(cur, "convex", None) or any(c.same_as(k) for k in chain):
                    continue
                for q, u in ends(c):
                    # both directions point away from the joint, so a smooth continuation has them opposite
                    if np.linalg.norm(p - q) < 1e-4 and float(t @ u) < -0.995:
                        chain.append(c)
                        frontier.append(c)
                        break
    return chain

LOOP_WALL_LEAN = 0.7   # |cos| between a wall and the face it rounds with: walls up to ~45° off square

def _loop_edges(v, f, normals, find, adj, adj_edges, angles, planar) -> list:
    """Outlines of flat faces made of straight pieces and arcs with square or leaning walls (see LoopEdge)."""
    by_face: dict = {}
    for (a_idx, b_idx), (e0, e1), ang in zip(adj, adj_edges, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb or ang < np.radians(1.0):
            continue
        for pl_tri, nb_tri, pr, nr in ((a_idx, b_idx, ra, rb), (b_idx, a_idx, rb, ra)):
            if pr not in planar:
                continue
            n_pl = normals[pl_tri]
            third_nb = v[[i for i in f[nb_tri] if i not in (e0, e1)][0]]
            third_pl = v[[i for i in f[pl_tri] if i not in (e0, e1)][0]]
            lean = abs(float(normals[nb_tri] @ n_pl))
            side = float(n_pl @ (third_nb - v[e0]))
            # +1: the wall falls away below the face (an outer rim), -1: the wall rises from the face (the foot of a block)
            ok = (1 if side < -1e-9 else -1 if side > 1e-9 else 0) if lean < LOOP_WALL_LEAN else 0
            by_face.setdefault(pr, []).append((int(e0), int(e1), ok, nr in planar, third_pl, n_pl, normals[nb_tri], lean))
    out = []
    for pr, segs in by_face.items():
        comp: dict = {}

        def vfind(x):
            while comp.setdefault(x, x) != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x

        for e0, e1, *_ in segs:
            ra, rb = vfind(e0), vfind(e1)
            if ra != rb:
                comp[rb] = ra
        parts: dict = {}
        for seg in segs:
            parts.setdefault(vfind(seg[0]), []).append(seg)
        for part in parts.values():
            kinds = {sg[2] for sg in part}
            if len(kinds) != 1 or 0 in kinds or all(sg[3] for sg in part):
                continue   # all walls steep enough and on one side; only flat walls = straight edges of their own
            leaning = any(sg[7] >= 0.1 for sg in part)
            if not any(sg[3] for sg in part) and not leaning:
                continue   # only square curved walls: a circle (_circular_edges)
            nbrs: dict = {}
            for e0, e1, *_ in part:
                nbrs.setdefault(e0, []).append(e1)
                nbrs.setdefault(e1, []).append(e0)
            if any(len(x) != 2 for x in nbrs.values()):
                continue
            start = part[0][0]
            order, prev, cur = [start], None, start
            while len(order) <= len(part):
                nxt = [x for x in nbrs[cur] if x != prev][0]
                if nxt == start:
                    break
                order.append(nxt)
                prev, cur = cur, nxt
            if len(order) != len(part):
                continue
            pts = v[order]
            n_pl = part[0][5]
            t = pts[1] - pts[0]
            left = np.cross(n_pl, t)
            seg_pts = {order[0], order[1]}
            ref_seg = next((sg for sg in part if {sg[0], sg[1]} == seg_pts), part[0])
            if float((ref_seg[4] - pts[0]) @ left) < 0:
                order = order[::-1]
                pts = pts[::-1].copy()
            walls = None
            if leaning:   # the normal of the wall along each piece, piece k from point k to point k + 1
                wall_of = {frozenset(sg[:2]): sg[6] for sg in part}
                walls = np.array([wall_of[frozenset((order[k], order[(k + 1) % len(order)]))] for k in range(len(order))])
            if walls is not None and not any(sg[3] for sg in part) and _concyclic(pts):
                continue   # a cone: _circular_edges has it
            out.append(LoopEdge(pts.copy(), n_pl.copy(), kinds == {1}, walls))
    return out

def loop_contains(lp, e) -> bool:
    """Whether the straight edge or arc `e` is a piece of the outline `lp` (all of it lies on the outline)."""
    if getattr(lp, "kind", "") != "loop" or e.kind not in ("line", "circle"):
        return False
    if e.kind == "circle":
        # the outline's chords sag inside the true arc: allow for that
        return lp.contains_arc(e) or _on_polyline(lp, e.polyline(8), 0.02 * float(e.radius) + 1e-4)
    return _on_polyline(lp, [e.p0, (e.p0 + e.p1) / 2.0, e.p1], 1e-4)


def _on_polyline(lp, points, tol: float) -> bool:
    poly = lp.polyline()
    if any(abs(float(lp.n @ (q - poly[0]))) > 1e-4 for q in points):
        return False
    seg = poly[1:] - poly[:-1]
    for q in points:
        w = q - poly[:-1]
        tt = np.clip(np.einsum("ij,ij->i", w, seg) / np.maximum(np.einsum("ij,ij->i", seg, seg), 1e-18), 0, 1)
        if np.linalg.norm(w - tt[:, None] * seg, axis=1).min() > tol:
            return False
    return True


def drop_round_loop_chords(lines, loops) -> list:
    """The flat strips of a round wall (a loop whose points all lie on one circle) are no pieces to pick: that loop
    is one circle (_circles_for_round_loops)."""
    round_loops = [lp for lp in loops if lp.walls is None and _concyclic(lp.pts)]
    if not round_loops:
        return lines
    return [e for e in lines if not any(loop_contains(lp, e) for lp in round_loops)]


def _circles_for_round_loops(loops, circles) -> list:
    """A square-walled outline whose points all lie on one circle is that circle: a wall split into narrow flat strips
    by a boolean makes it come out both as a loop and as an arc with a gap. Give back the whole circle instead."""
    from dataclasses import replace
    out_loops, circles = [], list(circles)
    for lp in loops:
        if lp.walls is None and _concyclic(lp.pts):
            c = lp.pts.mean(axis=0)
            r = float(np.linalg.norm(lp.pts - c, axis=1).mean())
            k = next((i for i, ce in enumerate(circles) if abs(ce.radius - r) < 1e-3 * max(1.0, r)
                      and np.linalg.norm(ce.center - c) < 1e-3 * max(1.0, r) and abs(float(ce.axis @ lp.n)) > 0.999), None)
            if k is not None:
                circles[k] = replace(circles[k], a0=0.0, sweep=2 * np.pi)
                continue
        out_loops.append(lp)
    return out_loops + circles

def _concyclic(pts) -> bool:
    c = pts.mean(axis=0)
    r = np.linalg.norm(pts - c, axis=1)
    return float(r.std()) < 1e-3 * float(r.mean())

def compute_planar_edges(manifold: m3d.Manifold) -> list:
    """Straight edges between two flat faces and full circles between a flat face and a cylinder."""
    mesh = manifold.to_mesh()
    return _planar_edges_from(mesh, manifold)

def _planar_edges_from(mesh, manifold) -> list:
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    if len(f) < 4:
        return []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    normals = tm.face_normals
    adj, adj_edges, angles = tm.face_adjacency, tm.face_adjacency_edges, tm.face_adjacency_angles

    parent = np.arange(len(f))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tol = 1e-6 * max(1.0, float(np.ptp(v, axis=0).max()))
    areas = tm.area_faces
    for a_idx, b_idx in adj:
        if _coplanar(a_idx, b_idx, normals, v, f, areas, tol):
            ra, rb = find(int(a_idx)), find(int(b_idx))
            if ra != rb:
                parent[rb] = ra
    groups: dict = {}
    for i in range(len(f)):
        groups.setdefault(find(i), []).append(i)
    curved = _curved_roots(v, f, tm, find, groups, adj, angles)
    slivers = _sliver_roots(v, f, tm, groups)
    planar = {r for r in groups if r not in curved and r not in slivers}

    # collect boundary segments between two different planar faces
    buckets: dict = {}
    for (a_idx, b_idx), (e0, e1), ang in zip(adj, adj_edges, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb or ra not in planar or rb not in planar or ang < np.radians(1.0):
            continue
        key = (min(ra, rb), max(ra, rb))
        third_a = v[[i for i in f[a_idx] if i not in (e0, e1)][0]]
        third_b = v[[i for i in f[b_idx] if i not in (e0, e1)][0]]
        if ra > rb:
            a_idx, b_idx, third_a, third_b = b_idx, a_idx, third_b, third_a
        buckets.setdefault(key, []).append((v[e0], v[e1], normals[a_idx], normals[b_idx], third_a, third_b))

    edges: List[PlanarEdge] = []
    for segs in buckets.values():
        p0, p1 = segs[0][0], segs[0][1]
        t = (p1 - p0) / np.linalg.norm(p1 - p0)
        # order the pieces along the edge and merge those that touch
        pieces = sorted(((float((a - p0) @ t), float((b - p0) @ t), a, b, n1, n2, ta, tb)
                         for a, b, n1, n2, ta, tb in segs), key=lambda z: min(z[0], z[1]))
        cur = None
        for s0, s1, a, b, n1, n2, ta, tb in pieces:
            lo, hi = (a, b) if s0 <= s1 else (b, a)
            lo_s, hi_s = min(s0, s1), max(s0, s1)
            if cur is not None and lo_s <= cur["hi_s"] + tol * 10:
                if hi_s > cur["hi_s"]:
                    cur["hi"], cur["hi_s"] = hi, hi_s
                continue
            if cur is not None:
                edges.append(_edge_from(cur, t))
            cur = {"lo": lo, "hi": hi, "hi_s": hi_s, "n1": n1, "n2": n2, "ta": ta, "tb": tb}
        if cur is not None:
            edges.append(_edge_from(cur, t))
    lines = [e for e in edges if e is not None and e.length > 1e-6]
    loops = _loop_edges(v, f, normals, find, adj, adj_edges, angles, planar)
    # the straight pieces of such an outline stay edges of their own: a click takes one piece, a double-click the
    # whole outline (Björn #104)
    lines = drop_round_loop_chords(lines, loops)
    return lines + _circles_for_round_loops(loops, _circular_edges(v, f, tm, find, groups, adj, adj_edges, angles, curved, planar, normals))

def _edge_from(c, t):
    p0, p1 = c["lo"], c["hi"]
    m = (p0 + p1) / 2.0

    def inward(third):  # direction in that face's plane, perpendicular to the edge, away from it
        w = third - m
        w = w - (w @ t) * t
        n = np.linalg.norm(w)
        return w / n if n > 1e-12 else None

    d1, d2 = inward(c["ta"]), inward(c["tb"])
    if d1 is None or d2 is None:
        return None
    convex = float(c["n1"] @ (c["tb"] - m)) < 0
    return PlanarEdge(p0, p1, c["n1"], c["n2"], d1, d2, convex)

def _circular_edges(v, f, tm, find, groups, adj, adj_edges, angles, curved, planar, normals) -> list:
    """Closed loops where a flat face meets the strips of a cylinder whose axis is the face normal."""
    # cluster the strips of one curved surface (shallow-angle neighbours belong together)
    cl = {r: r for r in curved}

    def cfind(x):
        while cl[x] != x:
            cl[x] = cl[cl[x]]
            x = cl[x]
        return x

    for (a_idx, b_idx), ang in zip(adj, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra != rb and ra in curved and rb in curved and ang < np.radians(25.0):
            ca, cb = cfind(ra), cfind(rb)
            if ca != cb:
                cl[cb] = ca

    buckets: dict = {}
    for (a_idx, b_idx), (e0, e1), ang in zip(adj, adj_edges, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb or ang < np.radians(25.0):
            continue
        if ra in planar and rb in curved:
            pl_tri, cu_tri, pr, cr = a_idx, b_idx, ra, rb
        elif rb in planar and ra in curved:
            pl_tri, cu_tri, pr, cr = b_idx, a_idx, rb, ra
        else:
            continue
        third_pl = v[[i for i in f[pl_tri] if i not in (e0, e1)][0]]
        third_cu = v[[i for i in f[cu_tri] if i not in (e0, e1)][0]]
        buckets.setdefault((pr, cfind(cr)), []).append((int(e0), int(e1), pl_tri, cu_tri, third_pl, third_cu))

    # group by flat face only, then split into connected loops (strips can hang together through slivers)
    by_face: dict = {}
    for (pr, _), segs in buckets.items():
        by_face.setdefault(pr, []).extend(segs)
    loops = []
    for pr, segs in by_face.items():
        # Boolean operations can leave duplicate vertices and tiny seam edges around a true
        # circular boundary. Snap this boundary graph before checking its degree; otherwise a
        # microscopic spur turns a closed circle into a branched, unpickable contour.
        snap_tol = 1e-5 * max(1.0, float(np.ptp(v, axis=0).max()))
        representatives = []
        cleaned, seen = [], set()

        def snap_vertex(index):
            point = v[index]
            for candidate in representatives:
                if np.linalg.norm(v[candidate] - point) <= snap_tol:
                    return candidate
            representatives.append(index)
            return index

        for seg in segs:
            a, b = snap_vertex(seg[0]), snap_vertex(seg[1])
            if a == b:
                continue
            key = (min(a, b), max(a, b))
            if key in seen:
                continue
            seen.add(key)
            cleaned.append((a, b, *seg[2:]))
        segs = cleaned
        comp = {}

        def vfind(x):
            while comp.setdefault(x, x) != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x

        for e0, e1, *_ in segs:
            ra, rb = vfind(e0), vfind(e1)
            if ra != rb:
                comp[rb] = ra
        parts: dict = {}
        for seg in segs:
            parts.setdefault(vfind(seg[0]), []).append(seg)
        loops.extend((pr, part) for part in parts.values())

    out = []
    for pr, segs in loops:
        n_plane = normals[segs[0][2]]
        # every vertex of a closed loop has exactly two segments
        deg: dict = {}
        for e0, e1, *_ in segs:
            deg[e0] = deg.get(e0, 0) + 1
            deg[e1] = deg.get(e1, 0) + 1
        ends = [k for k, d in deg.items() if d == 1]
        closed = not ends and len(segs) >= 8
        if not closed and not (len(ends) == 2 and all(d <= 2 for d in deg.values()) and len(segs) >= 4):
            continue
        pts = v[list(deg.keys())]
        # circle fit in the plane of the face
        u = np.cross(n_plane, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(n_plane, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        w = np.cross(n_plane, u)
        xy = np.stack([(pts - pts[0]) @ u, (pts - pts[0]) @ w], axis=1)
        A = np.c_[2 * xy, np.ones(len(xy))]
        sol, *_ = np.linalg.lstsq(A, (xy ** 2).sum(axis=1), rcond=None)
        cx, cy = sol[0], sol[1]
        R = float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0)))
        resid = np.abs(np.hypot(xy[:, 0] - cx, xy[:, 1] - cy) - R)
        if R < 1e-6 or resid.max() > 2e-3 * max(1.0, R):
            continue
        center = pts[0] + cx * u + cy * w
        # the wall must be a cylinder around the face normal (wall strips perpendicular to it)
        if any(abs(float(normals[cu] @ n_plane)) > 0.1 for _, _, _, cu, _, _ in segs):
            continue
        e0, e1, pl_tri, cu_tri, third_pl, third_cu = segs[0]
        m = v[e0]
        # which side of the circle the flat face lies on: use the centre of its triangle (a corner can sit
        # exactly on the circle)
        # (only the direction matters: step from the middle of the segment into the flat triangle and see
        # whether that moves away from the axis; the triangle's centroid can lie on the wrong side of a big face)
        # every segment votes: a hair-thin flat triangle along the seam can point either way
        mids = (v[[sg[0] for sg in segs]] + v[[sg[1] for sg in segs]]) / 2.0
        radial = (mids - center) - np.outer((mids - center) @ n_plane, n_plane)
        s1 = 1.0 if float(np.einsum("ij,ij->i", np.array([sg[4] for sg in segs]) - mids, radial).sum()) > 0 else -1.0
        s2 = 1.0 if float((third_cu - center) @ n_plane) > 0 else -1.0
        convex = float(n_plane @ (third_cu - m)) < 0
        if closed:
            out.append(CircularEdge(center, n_plane.copy(), R, s1, s2, convex, len(segs)))
            continue
        # an open arc: walk the chain from one end and measure the angle it covers
        nxt: dict = {}
        for e0, e1, *_ in segs:
            nxt.setdefault(e0, []).append(e1)
            nxt.setdefault(e1, []).append(e0)
        order, prev = [ends[0]], None
        while True:
            cand = [x for x in nxt[order[-1]] if x != prev]
            if not cand:
                break
            prev = order[-1]
            order.append(cand[0])
        if len(order) != len(deg):
            continue
        q = v[order] - center
        ang = np.unwrap(np.arctan2(q @ w, q @ u))
        sweep = float(ang[-1] - ang[0])
        a0 = float(ang[0])
        if sweep < 0:
            a0, sweep = float(ang[-1]), -sweep
        if sweep < np.radians(8.0) or sweep > 2 * np.pi - 0.2:
            continue
        out.append(CircularEdge(center, n_plane.copy(), R, s1, s2, convex, int(round(len(segs) * 2 * np.pi / sweep)), a0, sweep))
    return _join_arcs(out, v)

def _join_arcs(edges: list, v: np.ndarray) -> list:
    """Booleans (emboss, patterns, shells) leave zero-area triangles along a seam; they chop the circle where a flat
    face meets a wall into short arcs with gaps that cannot be picked. Arcs of one circle are joined across a gap when
    the mesh has points on the circle all through it (no wider apart than a facet), so a real notch stays a gap."""
    def near(a, b):   # short arcs fit their circle loosely: same plane and side, centre and radius roughly alike
        r = max(a.radius, b.radius)
        return (float(a.axis @ b.axis) > 0.999 and abs(float(a.axis @ (a.center - b.center))) < 1e-4 * max(1.0, r)
                and np.linalg.norm(a.center - b.center) < 0.1 * r and abs(a.radius - b.radius) < 0.1 * r
                and (a.s1, a.s2, a.convex) == (b.s1, b.s2, b.convex))

    groups: list = []
    for e in edges:
        if e.is_arc:
            g = next((g for g in groups if near(g[0], e)), None)
            g.append(e) if g is not None else groups.append([e])
    out = [e for e in edges if not e.is_arc]
    for g in groups:
        joined = _join_arc_group(g, v) if len(g) > 1 else None
        out.extend(g if joined is None else joined)
    whole = [e for e in out if not e.is_arc and all(e is not o for o in edges)]   # circles made here

    def covered(e):   # a short arc with a poor fit of its own, lying on a circle joined here
        for c in whole:
            p = e.polyline() - c.center
            if float(c.axis @ e.axis) > 0.999 and np.abs(p @ c.axis).max() < 1e-4 * max(1.0, c.radius) and np.abs(
                    np.linalg.norm(p - np.outer(p @ c.axis, c.axis), axis=1) - c.radius).max() < 2e-3 * max(1.0, c.radius):
                return True
        return False
    return [e for e in out if not (e.is_arc and covered(e))]

def _join_arc_group(g: list, v: np.ndarray):
    """The arcs of one circle joined where the mesh bridges the gaps, or None when it fits no circle."""
    o = g[0]
    u, w = o._basis()
    R = float(np.mean([e.radius for e in g]))
    c = np.mean([e.center for e in g], axis=0)
    d = v - c
    d = d[np.abs(d @ o.axis) < 1e-4 * max(1.0, R)]
    xy = np.stack([d @ u, d @ w], axis=1)
    fine = 2e-3 * max(1.0, R)
    band = max(1.5 * max(abs(e.radius - R) + np.linalg.norm(e.center - c) for e in g), 4 * fine)
    while True:   # fit the circle to the mesh points on it, narrowing the band down to `fine`
        pts = xy[np.abs(np.hypot(xy[:, 0], xy[:, 1]) - R) < band]
        if len(pts) < 3:
            return None
        sol, *_ = np.linalg.lstsq(np.c_[2 * pts, np.ones(len(pts))], (pts ** 2).sum(axis=1), rcond=None)
        xy = xy - sol[:2]
        c = c + sol[0] * u + sol[1] * w
        R = float(np.sqrt(max(sol[2] + sol[0] ** 2 + sol[1] ** 2, 0.0)))
        if band <= fine:
            break
        band = max(band / 4, fine)
    band = fine
    on = np.abs(np.hypot(xy[:, 0], xy[:, 1]) - R) < band
    if on.sum() < 3:
        return None
    ang = np.unique(np.mod(np.arctan2(xy[on, 1], xy[on, 0]), 2 * np.pi))
    gaps = np.diff(np.r_[ang, ang[0] + 2 * np.pi])
    step = float(np.percentile(gaps, 90))   # one facet of the wall (the arcs' own facet counts are rough)
    wide = np.flatnonzero(gaps > 1.5 * step)
    nseg = int(round(2 * np.pi / step))
    if len(wide) == 0:
        return [CircularEdge(c, o.axis.copy(), R, o.s1, o.s2, o.convex, nseg)]
    out = []
    for i, k in enumerate(wide):   # each run of close points between two wide gaps that holds arcs becomes one arc
        start = float(ang[(k + 1) % len(ang)])
        sweep = float(np.mod(ang[wide[(i + 1) % len(wide)]] - start, 2 * np.pi))
        inside = [e for e in g if np.mod(e.a0 + e.sweep / 2 - start, 2 * np.pi) <= sweep + 1e-9]
        if len(inside) == 1:
            out.append(inside[0])
        elif inside:
            out.append(CircularEdge(c, o.axis.copy(), R, o.s1, o.s2, o.convex, nseg, start, sweep))
    return out
