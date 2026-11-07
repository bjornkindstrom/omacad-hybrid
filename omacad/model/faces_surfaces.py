"""Faces surfaces for CAD mesh geometry."""

import hashlib
from typing import List, Tuple
import numpy as np
import manifold3d as m3d
import trimesh
from omacad.model.faces_types import PlanarFace, PlanarEdge
from omacad.model.faces_topology import _classified_roots, _groups_of_roots, _coplanar, _curved_roots, _sliver_roots
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
    from omacad import viewport_accel
    native_roots = viewport_accel.coplanar_roots(v, f, normals, areas, adj, tol)
    if native_roots is not None:
        parent = native_roots
    else:
        for a_idx, b_idx in adj:
            if _coplanar(a_idx, b_idx, normals, v, f, areas, tol):
                ra, rb = find(int(a_idx)), find(int(b_idx))
                if ra != rb:
                    parent[rb] = ra

    if native_roots is not None:
        groups, roots = _groups_of_roots(native_roots), native_roots
    else:
        groups: dict = {}
        for i in range(len(f)):
            groups.setdefault(find(i), []).append(i)
        roots = np.array([find(i) for i in range(len(f))], dtype=np.int64)
    slivers, curved = _classified_roots(v, f, tm, find, groups, adj, tm.face_adjacency_angles, native_roots)
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
    roots, _, planar, slivers, curved = _face_groups(v, f, tm)
    a, b = roots[tm.face_adjacency[:, 0]], roots[tm.face_adjacency[:, 1]]
    is_planar = np.isin(roots, list(planar))
    is_sliver = np.isin(roots, list(slivers))
    pa, pb = is_planar[tm.face_adjacency[:, 0]], is_planar[tm.face_adjacency[:, 1]]
    sa, sb = is_sliver[tm.face_adjacency[:, 0]], is_sliver[tm.face_adjacency[:, 1]]
    angles = tm.face_adjacency_angles
    mask = ((a != b) & (pa | pb) & ~sa & ~sb
            & (angles >= np.radians(min_deg)) & (angles <= np.radians(sharp_deg)))
    return mask & ~_facet_seams(v, tm, roots, is_planar, is_sliver, mask, sharp_deg)


FACET_WIDTH_RATIO = 1.5     # a "flat face" at most this many neighbour strips wide is a facet of a curved surface


def _facet_seams(v, tm, roots, is_planar, is_sliver, mask, sharp_deg) -> np.ndarray:
    """Candidate tangent edges that are only the join between two facets of one tessellated curve (Björn #214): a
    boolean can leave a facet of a cone or cylinder (or a piece of one, split by a zero-area sliver) as a separate
    flat group, and a line was drawn down its sides. A facet bends smoothly into the curve on both sides and is no
    wider across the seam than the strip next to it. A real flat face is many strips wide (a box side next to its
    fillet), and a short real flat side between an arc and a corner bends smoothly on one side only."""
    out = np.zeros(len(mask), dtype=bool)
    idx = np.flatnonzero(mask)
    if not len(idx):
        return out
    fa_all = tm.face_adjacency
    ra_all, rb_all = roots[fa_all[:, 0]], roots[fa_all[:, 1]]
    # a zero-area sliver's angle means nothing: it counts as a smooth way on into the curve
    slivered = is_sliver[fa_all[:, 0]] | is_sliver[fa_all[:, 1]]
    smooth = (ra_all != rb_all) & ((tm.face_adjacency_angles <= np.radians(sharp_deg)) | slivered)
    onward: dict = {}                                 # group -> the groups it runs smoothly into
    sliver_roots = set(roots[is_sliver].tolist())
    for x, y in zip(ra_all[smooth].tolist(), rb_all[smooth].tolist()):
        onward.setdefault(x, set()).add(y)
        onward.setdefault(y, set()).add(x)
    members: dict = {}

    def width(root: int, along: np.ndarray) -> float:
        if root not in members:
            tris = np.flatnonzero(roots == root)
            normal = tm.face_normals[tris].sum(0)
            members[root] = (np.unique(tm.faces[tris]), normal / max(np.linalg.norm(normal), 1e-12))
        verts, normal = members[root]
        across = np.cross(normal, along)
        return float(np.ptp(v[verts] @ across)) if np.linalg.norm(across) > 1e-6 else 0.0

    for k in idx:
        edge = v[tm.face_adjacency_edges[k, 1]] - v[tm.face_adjacency_edges[k, 0]]
        along = edge / max(np.linalg.norm(edge), 1e-12)
        x, y = int(ra_all[k]), int(rb_all[k])
        facet = True
        for side, (r, other) in enumerate(((x, y), (y, x))):
            if not is_planar[fa_all[k, side]]:
                continue
            near = set()
            for n in onward.get(r, ()):                # through a sliver to the facet on its far side
                near |= ({m for m in onward.get(n, ()) if m != r} if n in sliver_roots else {n})
            strips = [n for n in near if n not in sliver_roots] or [other]
            widest = max(width(n, along) for n in strips)      # a strip split by a sliver is narrower than its facet
            if len(onward.get(r, ())) < 2 or width(r, along) > FACET_WIDTH_RATIO * widest:
                facet = False
        out[k] = facet
    return out


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
    ids = np.array([find(r) if r in parent and find(r) in with_curve else -1 for r in roots.tolist()],
                   dtype=np.int64)
    ids = _heal_surface_fragments(ids, roots, tm, sharp_deg)
    return _merge_crumbs(ids, v, tm, sharp_deg)


CRUMB_TRIANGLES = 6         # a "curved surface" of at most this many triangles ...
CRUMB_AREA_SHARE = 0.1      # ... and at most this share of a neighbour's area ...
CRUMB_SEAM_SHARE = 0.4      # ... which it runs smoothly into along this much of its outline, is part of it


def _merge_crumbs(ids, v, tm, sharp_deg):
    """A bent Japandi rib face came out as one big surface dotted with dozens of two-triangle "surfaces" (the strip
    widths of the arched profile differ more than `radius_ratio`), so its highlight was full of holes drawn as zigzag
    outlines (Björn #215). A crumb that mostly borders one much larger curved surface smoothly is part of it. Real
    small surfaces (a fillet between two walls, a short arc) touch their neighbour along less of their outline or
    are not that small."""
    if not np.any(ids >= 0):
        return ids
    labels, counts = np.unique(ids[ids >= 0], return_counts=True)
    crumbs = set(labels[counts <= CRUMB_TRIANGLES].tolist())
    if not crumbs:
        return ids
    area = dict(zip(labels.tolist(), np.bincount(np.searchsorted(labels, ids[ids >= 0]),
                                                  weights=tm.area_faces[ids >= 0]).tolist()))
    fa = tm.face_adjacency
    la, lb = ids[fa[:, 0]], ids[fa[:, 1]]
    edges = tm.face_adjacency_edges
    length = np.linalg.norm(v[edges[:, 0]] - v[edges[:, 1]], axis=1)
    smooth = tm.face_adjacency_angles <= np.radians(sharp_deg)
    outline: dict = {}
    seam: dict = {}
    for x, y, ln, sm in zip(la.tolist(), lb.tolist(), length.tolist(), smooth.tolist()):
        if x == y:
            continue
        for c, o in ((x, y), (y, x)):
            if c in crumbs:
                outline[c] = outline.get(c, 0.0) + ln
                if sm and o >= 0 and o not in crumbs:
                    seam[c, o] = seam.get((c, o), 0.0) + ln
    into: dict = {}
    for (c, o), ln in seam.items():
        if (ln >= CRUMB_SEAM_SHARE * outline[c] and area[c] <= CRUMB_AREA_SHARE * area[o]
                and ln > seam.get((c, into.get(c, -1)), 0.0)):
            into[c] = o
    if not into:
        return ids
    out = ids.copy()
    for c, o in into.items():
        out[ids == c] = o
    return out


def _heal_surface_fragments(ids, planar_roots, tm, sharp_deg):
    """Absorb tiny classification islands in an otherwise continuous curved wall.

    Shells of lofts can split one wall into hundreds of tiny radius/planarity groups.
    Repair only smooth components overwhelmingly covered by one surface, with no
    substantial second curved surface or flat face. Sharp creases remain barriers.
    """
    if not np.any(ids >= 0):
        return ids
    parent = np.arange(len(ids))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return int(i)

    adjacency = tm.face_adjacency[tm.face_adjacency_angles <= np.radians(sharp_deg)]
    for a, b in adjacency:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            parent[rb] = ra
    components = _groups_of_roots(np.array([find(i) for i in range(len(ids))]))
    for triangles in components.values():
        triangles = np.asarray(triangles)
        labels = ids[triangles]
        area = tm.area_faces[triangles]
        total = float(area.sum())
        if total <= 0:
            continue
        unique, inverse = np.unique(labels, return_inverse=True)
        sums = np.bincount(inverse, weights=area)
        curves = [(float(weight), int(label)) for label, weight in zip(unique, sums) if label >= 0]
        curves.sort(reverse=True)
        if not curves or curves[0][0] < .95 * total:
            continue
        if len(curves) > 1 and curves[1][0] > .005 * total:
            continue
        flat = labels < 0
        if float(area[flat].sum()) > .005 * total:
            continue
        # A real planar face must keep its identity even beside a very large curved wall.
        if np.any(flat):
            _, inverse = np.unique(planar_roots[triangles][flat], return_inverse=True)
            if np.bincount(inverse, weights=area[flat]).max() > .001 * total:
                continue
        ids[triangles] = curves[0][1]
    return _absorb_surface_islands(ids, planar_roots, tm, components.values(), sharp_deg)


ISLAND_SHARE = .005        # an island (cluster of specks) is at most this part of its smooth region's area
ISLAND_FLAT_SHARE = .001   # ... and holds no flat group larger than this: a real face keeps its identity
ISLAND_ENCLOSED = .6       # ... and this much of its outline runs along the main surface (sharp creases, the
                           # wall's own border, count for neither side)


def _absorb_surface_islands(ids, planar_roots, tm, components, sharp_deg: float = 20.0):
    """Islands left inside a big curved wall join it (#205). The shell of a loft left the inner wall at 94 % one
    surface plus ~800 specks (one to a few triangles each, read as other curves or flat bits, many in a row along
    the rim), so `_heal_surface_fragments` kept them all and the selected wall was drawn with an outline around
    every speck and a zigzag along the rim. Specks that touch each other are judged together: a cluster that is
    small and mostly bordered by the main surface (or by a sharp crease) joins it. A real fillet between the wall
    and a flat face clusters with that face, which is too large, so it stays apart."""
    adj = tm.face_adjacency
    smooth_pair = tm.face_adjacency_angles <= np.radians(sharp_deg)
    ends = tm.vertices[tm.face_adjacency_edges]
    lengths = np.linalg.norm(ends[:, 0] - ends[:, 1], axis=1)
    area_faces = tm.area_faces
    planar_roots = np.asarray(planar_roots, dtype=np.int64)
    for triangles in components:
        triangles = np.asarray(triangles)
        labels = ids[triangles]
        if len(triangles) < 3 or not np.any(labels >= 0) or len(np.unique(labels)) < 2:
            continue
        total = float(area_faces[triangles].sum())
        curved_labels, inverse = np.unique(labels[labels >= 0], return_inverse=True)
        sums = np.bincount(inverse, weights=area_faces[triangles][labels >= 0])
        if sums.max() < .5 * total:
            continue
        main = int(curved_labels[int(np.argmax(sums))])
        other = np.zeros(len(ids), dtype=bool)
        other[triangles[labels != main]] = True
        is_main = np.zeros(len(ids), dtype=bool)
        is_main[triangles[labels == main]] = True
        # clusters of non-main triangles joined across smooth edges
        parent = {int(t): int(t) for t in np.flatnonzero(other)}

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        join = smooth_pair & other[adj[:, 0]] & other[adj[:, 1]]
        for p, q in adj[join].tolist():
            rp, rq = find(p), find(q)
            if rp != rq:
                parent[rq] = rp
        members = np.fromiter(parent.keys(), dtype=np.int64)
        cluster = np.array([find(int(t)) for t in members], dtype=np.int64)
        lookup = np.full(len(ids), -1, dtype=np.int64)
        lookup[members] = cluster
        c_uniq, c_inv = np.unique(cluster, return_inverse=True)
        c_area = np.bincount(c_inv, weights=area_faces[members])
        # the largest flat group in each cluster
        flat = ids[members] < 0
        c_flat = np.zeros(len(c_uniq))
        if flat.any():
            pair_key = np.stack([c_inv[flat], planar_roots[members[flat]]], axis=1)
            pk, pinv = np.unique(pair_key, axis=0, return_inverse=True)
            np.maximum.at(c_flat, pk[:, 0], np.bincount(pinv.ravel(), weights=area_faces[members[flat]]))
        # outline along smooth edges: shared with main vs anything else
        rim = smooth_pair & (other[adj[:, 0]] != other[adj[:, 1]])
        p, q, length = adj[rim, 0], adj[rim, 1], lengths[rim]
        inner = np.where(other[p], p, q)
        outer = np.where(other[p], q, p)
        pos = np.searchsorted(c_uniq, lookup[inner])
        outline = np.bincount(pos, weights=length, minlength=len(c_uniq))
        shared = np.bincount(pos, weights=length * is_main[outer], minlength=len(c_uniq))
        take = ((c_area <= ISLAND_SHARE * total) & (c_flat <= ISLAND_FLAT_SHARE * total)
                & (shared >= ISLAND_ENCLOSED * outline) & (outline > 0))
        if take.any():
            ids[members[take[c_inv]]] = main
    return ids


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
