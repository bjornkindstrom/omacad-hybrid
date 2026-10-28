"""Faces topology for CAD mesh geometry."""

import numpy as np

SLIVER_AREA = 0.03  # mm^2: boolean operations leave hair-thin triangles; they are not faces
SLIVER_MIN_WIDTH = 0.04  # mm: strips narrower than this are boolean cut leftovers or facet artifacts


def _group_min_width(v, f, tm, tri_ids) -> float:
    """Narrow dimension of a coplanar triangle group (principal-axis extent): thin strips are the
    facets of a tessellated curved surface, a real flat face is wide."""
    if len(tri_ids) == 1:
        tri = f[tri_ids[0]]
        p0, p1, p2 = v[tri[0]], v[tri[1]], v[tri[2]]
        e0 = float(np.linalg.norm(p1 - p0))
        e1 = float(np.linalg.norm(p2 - p1))
        e2 = float(np.linalg.norm(p0 - p2))
        area = float(tm.area_faces[tri_ids[0]])
        return float(2.0 * area / max(e0, e1, e2, 1e-12))
    pts = v[np.unique(f[np.array(tri_ids)].ravel())]
    c = pts - pts.mean(axis=0)
    if len(c) < 3:
        return 0.0
    w, vecs = np.linalg.eigh(c.T @ c)
    # in-plane principal axes = the two eigenvectors with the largest eigenvalues
    axes = vecs[:, np.argsort(w)[::-1][:2]]
    proj = c @ axes
    ext = proj.max(axis=0) - proj.min(axis=0)
    return float(ext.min())

def _coplanar(a_idx, b_idx, normals, v, f, areas, tol) -> bool:
    """Are two adjacent triangles part of one flat face? Tiny triangles left by boolean operations may
    be a hair off the plane, so they get a looser test."""
    d = float(np.dot(normals[a_idx], normals[b_idx]))
    off = abs(float(np.dot(normals[a_idx], v[f[a_idx, 0]])) - float(np.dot(normals[a_idx], v[f[b_idx, 0]])))
    if d > 1.0 - 1e-9 and off < tol:
        return True
    # float noise in a small triangle's normal (1e-9 off) must not split a face: judge by how far
    # every corner of the neighbour sits from this triangle's plane
    if d > 1.0 - 1e-7:
        n = normals[a_idx]
        if float(np.abs((v[f[b_idx]] - v[f[a_idx, 0]]) @ n).max()) < tol:
            return True
    small = min(areas[a_idx], areas[b_idx]) < 0.01
    return small and d > 1.0 - 1e-4 and off < 1e-3

def _sliver_roots(v, f, tm, groups) -> set:
    """Groups that are leftovers of boolean operations: almost no area, or hair-thin (< SLIVER_MIN_WIDTH wide)."""
    out = set()
    for r, ids in groups.items():
        if float(tm.area_faces[ids].sum()) < SLIVER_AREA or _group_min_width(v, f, tm, ids) < SLIVER_MIN_WIDTH:
            out.add(r)
    return out

def _curved_roots(v, f, tm, find, groups, adj, angles) -> set:
    """Groups that are strips of a curved surface. A group is curved when it meets a neighbour at a
    shallow angle and is not clearly wider than that neighbour; so a wide flat face next to a fillet
    (also a shallow join) stays planar, while the thin strips of the fillet and of cylinders do not.
    Sliver triangles between two strips are looked through (the strips are neighbours of each other)."""
    sliver = _sliver_roots(v, f, tm, groups)
    shallow = {}
    touching = {}  # every neighbour regardless of angle (needed to look through slivers)
    for (a_idx, b_idx), ang in zip(adj, angles):
        ra, rb = find(int(a_idx)), find(int(b_idx))
        if ra == rb:
            continue
        touching.setdefault(ra, set()).add(rb)
        touching.setdefault(rb, set()).add(ra)
        if ang < np.radians(25.0):
            shallow.setdefault(ra, set()).add(rb)
            shallow.setdefault(rb, set()).add(ra)
    normal_of = {r: tm.face_normals[ids[0]] for r, ids in groups.items()}
    # slivers often come in chains: look through whole clusters of them
    cluster = {r: r for r in sliver}

    def cfind(x):
        while cluster[x] != x:
            cluster[x] = cluster[cluster[x]]
            x = cluster[x]
        return x

    for sl in sliver:
        for n in touching.get(sl, ()):
            if n in sliver and cfind(n) != cfind(sl):
                cluster[cfind(n)] = cfind(sl)
    members: dict = {}
    for sl in sliver:
        members.setdefault(cfind(sl), []).append(sl)
    for cl in members.values():
        real = {x for sl in cl for x in touching.get(sl, ()) if x not in sliver}
        for x in real:
            for y in real:
                if x != y and float(normal_of[x] @ normal_of[y]) > np.cos(np.radians(25.0)):
                    shallow.setdefault(x, set()).add(y)
    points = {}

    def width_across(r, other):
        # Measure perpendicular to the seam, not along the group's shortest principal axis.
        # A long flat chamfer is narrow across its band, but wide towards the curved corner at its end.
        n, nb = normal_of[r], normal_of[other]
        across = nb - float(nb @ n) * n
        length = np.linalg.norm(across)
        if length < 1e-6:
            return 0.0  # coplanar patches separated by a sliver do not establish curvature
        if r not in points:
            points[r] = v[np.unique(f[np.array(groups[r])].ravel())]
        return float(np.ptp(points[r] @ (across / length)))

    curved = set()
    for r, neighbours in shallow.items():
        if r in sliver:
            continue
        similar = 0
        for n in neighbours:
            if n in sliver:
                continue
            wr, wn = width_across(r, n), width_across(n, r)
            if wr > 0 and wn >= wr * 0.25:
                similar += 1
                if similar >= 2:
                    curved.add(r)
                    break
    return curved
