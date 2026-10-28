"""Faces surfaces for CAD mesh geometry."""

import hashlib
from typing import List, Tuple
import numpy as np
import manifold3d as m3d
import trimesh
from omacad.model.faces_types import PlanarFace, PlanarEdge
from omacad.model.faces_topology import _coplanar, _curved_roots, _sliver_roots
from omacad.model.faces_edges import _edge_from, _loop_edges, _circular_edges, _circles_for_round_loops, drop_round_loop_chords

_TOPOLOGY_CACHE: dict = {}
_TOPOLOGY_CACHE_MAX = 512


def _face_groups(v, f, tm):
    """Union-find over adjacent, coplanar triangles (trimesh.facets needs scipy/networkx). Returns the group root of
    every triangle, the groups (root -> triangle ids), the roots of real flat faces (not the thin strips of a
    tessellated curved surface and not boolean slivers), of the slivers, and of the curved strips."""
    parent = np.arange(len(f))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    normals = tm.face_normals
    adj = tm.face_adjacency
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
    curved = _curved_roots(v, f, tm, find, groups, adj, tm.face_adjacency_angles)
    slivers = _sliver_roots(v, f, tm, groups)
    roots = np.array([find(i) for i in range(len(f))], dtype=np.int64)
    return roots, groups, {r for r in groups if r not in curved and r not in slivers}, slivers, curved


def compute_planar_faces(manifold: m3d.Manifold, body_id: str = "") -> List[PlanarFace]:
    """Returns every planar facet (>= 2 coplanar adjacent triangles) of the solid."""
    # Edge coordinates feed boolean tools: float32 rounding leaves slivers against the original solid.
    mesh = manifold.to_mesh64()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    if len(f) < 2:
        return []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
    _, groups, planar, _, _ = _face_groups(v, f, tm)
    return [PlanarFace(body_id=body_id, index=i, normal=np.asarray(tm.face_normals[ids[0]], dtype=np.float64),
                       origin=v[f[ids[0], 0]], area=float(tm.area_faces[ids].sum()), tris=v[f[ids]])
            for i, ids in enumerate(np.array(ids) for r, ids in groups.items() if r in planar)]


def tangent_edge_mask(v, f, tm, sharp_deg: float, min_deg: float = 0.1) -> np.ndarray:
    """Mask over `tm.face_adjacency` of the tangent edges: where a flat face runs smoothly (under `sharp_deg`) into a
    curved surface or into another flat face, like the seam between a straight wall and a tangent arc (Fusion's
    "Show tangent edges"). Joins inside a curved surface and boolean slivers are left out."""
    roots, _, planar, slivers, _ = _face_groups(v, f, tm)
    a, b = roots[tm.face_adjacency[:, 0]], roots[tm.face_adjacency[:, 1]]
    is_planar = np.isin(roots, list(planar))
    is_sliver = np.isin(roots, list(slivers))
    pa, pb = is_planar[tm.face_adjacency[:, 0]], is_planar[tm.face_adjacency[:, 1]]
    sa, sb = is_sliver[tm.face_adjacency[:, 0]], is_sliver[tm.face_adjacency[:, 1]]
    angles = tm.face_adjacency_angles
    return ((a != b) & (pa | pb) & ~sa & ~sb
            & (angles >= np.radians(min_deg)) & (angles <= np.radians(sharp_deg)))


def curved_surface_ids(v, f, tm, sharp_deg: float, radius_ratio: float = 1.5) -> np.ndarray:
    """Per triangle: the id of the curved surface it belongs to (a fillet, a cylinder wall: the tessellated strips
    joined across smooth seams up to `sharp_deg`), or -1 on a flat face. Two strips of different radius (a sketch
    fillet running tangent into a larger arc) stay apart: a strip's width over the seam angle is its radius, so the
    widths must agree within `radius_ratio`. Slivers join a curved surface they touch."""
    roots, groups, planar, _, curved = _face_groups(v, f, tm)
    parent = {int(r): int(r) for r in groups if r not in planar}

    def find(r: int) -> int:
        while parent[r] != r:
            parent[r] = parent[parent[r]]
            r = parent[r]
        return r

    smooth = tm.face_adjacency_angles <= np.radians(sharp_deg)
    a, b = roots[tm.face_adjacency[smooth, 0]], roots[tm.face_adjacency[smooth, 1]]
    edges = tm.face_adjacency_edges[smooth]
    seam: dict = {}
    for ra, rb, length in zip(a.tolist(), b.tolist(), np.linalg.norm(v[edges[:, 0]] - v[edges[:, 1]], axis=1)):
        if ra != rb and ra in parent and rb in parent:
            seam[ra, rb] = seam.get((ra, rb), 0.0) + float(length)
    area = {r: float(tm.area_faces[ids].sum()) for r, ids in groups.items() if r in parent}
    for (ra, rb), length in seam.items():
        wa, wb = area[ra] / length, area[rb] / length
        if ra in curved and rb in curved and max(wa, wb) > radius_ratio * min(wa, wb):
            continue
        if find(ra) != find(rb):
            parent[find(rb)] = find(ra)
    with_curve = {find(r) for r in curved}
    return np.array([find(r) if r in parent and find(r) in with_curve else -1 for r in roots.tolist()],
                    dtype=np.int64)


def clear_topology_cache():
    """Clears the global topology analysis cache."""
    _TOPOLOGY_CACHE.clear()

def compute_planar_faces_and_edges(manifold: m3d.Manifold, body_id: str = "") -> Tuple[List[PlanarFace], list]:
    """Computes both planar faces and edges in a single shared topological pass (2x faster than separate calls).
    Cached by a hash of the mesh to avoid redundant trimesh topology analysis."""
    if manifold.is_empty():
        return [], []

    # Keyed by the mesh itself: counts, volume and outer box stay the same when a hole moves inside a plate, and a
    # Chamfer on the moved hole then got the old hole's edges and cut where it used to be (Björn #105).
    mesh = manifold.to_mesh64()
    v = np.asarray(mesh.vert_properties[:, :3], dtype=np.float64)
    f = np.asarray(mesh.tri_verts, dtype=np.int64)
    cache_key = (len(v), len(f), hashlib.blake2b(v.tobytes() + f.tobytes(), digest_size=16).digest())

    if cache_key in _TOPOLOGY_CACHE:
        cached_faces, cached_edges = _TOPOLOGY_CACHE[cache_key]
        # Fast rebinding of body_id on cached faces without deep copy
        faces = [
            PlanarFace(
                body_id=body_id,
                index=f.index,
                normal=f.normal,
                origin=f.origin,
                area=f.area,
                tris=f.tris,
            ) for f in cached_faces
        ]
        return faces, cached_edges

    # Edge coordinates feed boolean tools (to_mesh64): float32 rounding leaves slivers against the original solid.
    if len(f) < 2:
        return [], []
    tm = trimesh.Trimesh(vertices=v, faces=f, process=False)

    normals = tm.face_normals
    adj = tm.face_adjacency
    angles = tm.face_adjacency_angles
    roots, groups, planar, _, curved = _face_groups(v, f, tm)
    tol = 1e-6 * max(1.0, float(np.ptp(v, axis=0).max()))
    find = lambda i: int(roots[i])

    faces: List[PlanarFace] = []
    for root in planar:
        tri_ids = groups[root]
        ids = np.array(tri_ids)
        faces.append(PlanarFace(
            body_id=body_id,
            index=len(faces),
            normal=np.asarray(normals[ids[0]], dtype=np.float64),
            origin=v[f[ids[0], 0]],
            area=float(tm.area_faces[ids].sum()),
            tris=v[f[ids]],
        ))

    if len(f) < 4:
        return faces, []

    adj_edges = tm.face_adjacency_edges
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
    # straight pieces of a loop stay edges of their own (Björn #104, see faces_edges)
    lines = drop_round_loop_chords(lines, loops)
    all_edges = lines + _circles_for_round_loops(loops, _circular_edges(v, f, tm, find, groups, adj, adj_edges, angles, curved, planar, normals))
    from omacad.model.wrapped_edges import cylindrical_contours
    all_edges += cylindrical_contours(v, f, tm)
    from omacad.model.curve_edges import curve_edges
    all_edges += curve_edges(v, f, tm, find, planar)

    if len(_TOPOLOGY_CACHE) >= _TOPOLOGY_CACHE_MAX:
        _TOPOLOGY_CACHE.clear()
    _TOPOLOGY_CACHE[cache_key] = (faces, all_edges)

    return faces, all_edges
