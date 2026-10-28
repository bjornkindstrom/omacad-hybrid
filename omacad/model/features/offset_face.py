"""Offset Face: moves flat faces along their normal and changes the radius of full cylinders (holes and pins).
A positive distance adds material (the face moves out of the body, a hole gets smaller), a negative one removes it.
Typical use: a tolerance on a thread, a pin or a pocket."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import manifold3d as m3d
from shapely.geometry import Polygon
from shapely.ops import unary_union

from omacad.model.features.base import Feature, region_cross_section

TOL = 1e-3


def _frame(origin, axis) -> np.ndarray:
    """4x4 matrix from a local frame (z = axis) to world."""
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = u, v, axis, np.asarray(origin, dtype=float)
    return M


def _apply(m: m3d.Manifold, M: np.ndarray) -> m3d.Manifold:
    return m.transform(M[:3, :])


def plane_face_ref(face) -> Dict[str, Any]:
    return {"kind": "plane", "normal": [float(x) for x in face.normal], "origin": [float(x) for x in face.origin]}


def cylinder_face_ref(cyl: Dict[str, Any]) -> Dict[str, Any]:
    return {"kind": "cylinder", "origin": [float(x) for x in cyl["origin"]], "axis": [float(x) for x in cyl["axis"]],
            "radius": float(cyl["radius"]), "length": float(cyl.get("length_exact", cyl["length"])),
            "internal": bool(cyl["is_internal"])}


def _point_in_tri(p, tri, tol=1e-6) -> bool:
    a, b, c = tri
    n = np.cross(b - a, c - a)
    area2 = float(np.linalg.norm(n))
    if area2 < 1e-12:
        return False
    w = [float(np.cross(b - p, c - p) @ n), float(np.cross(c - p, a - p) @ n), float(np.cross(a - p, b - p) @ n)]
    return all(x >= -tol * area2 * area2 for x in w)


def find_plane_face(manifold, ref):
    """The flat face of `manifold` that lies in the stored plane and contains the stored point."""
    from omacad.model.faces import compute_planar_faces
    n, o = np.asarray(ref["normal"], dtype=float), np.asarray(ref["origin"], dtype=float)
    best, best_d = None, 1e18
    for f in compute_planar_faces(manifold):
        if float(f.normal @ n) < 0.9999 or abs(float(f.normal @ (o - f.origin))) > TOL * 10:
            continue
        if any(_point_in_tri(o, t) for t in f.tris):
            return f
        d = float(np.min(np.linalg.norm(f.tris.mean(axis=1) - o, axis=1)))
        if d < best_d:
            best, best_d = f, d
    return best


def _face_region(face, M_inv) -> Optional[m3d.CrossSection]:
    pts = np.asarray(face.tris, dtype=float).reshape(-1, 3)
    local = (M_inv[:3, :3] @ pts.T).T + M_inv[:3, 3]
    polys = [Polygon(local[i:i + 3, :2]) for i in range(0, len(local), 3)]
    polys = [p for p in polys if p.area > 1e-12]
    if not polys:
        return None
    return region_cross_section(unary_union(polys).buffer(1e-9).buffer(-1e-9))


def _neighbour_planes(manifold, face) -> List[Tuple[np.ndarray, float, bool]]:
    """(normal, offset, convex) of the flat faces that meet `face` along an edge. The material that moves with
    the face ends at those planes: on their material side where the edge is convex, on their air side where it is
    concave (the foot of a wall)."""
    from omacad.model.faces import compute_planar_faces
    key = lambda p: tuple(np.round(p / TOL).astype(np.int64))
    mine = {key(p) for p in np.asarray(face.tris).reshape(-1, 3)}
    centre = np.asarray(face.tris).reshape(-1, 3).mean(axis=0)
    out = []
    for g in compute_planar_faces(manifold):
        if g.index == face.index or abs(float(g.normal @ face.normal)) > 0.9999:
            continue
        if len(mine & {key(p) for p in np.asarray(g.tris).reshape(-1, 3)}) >= 2:
            ng = np.asarray(g.normal, dtype=float)
            out.append((ng, float(ng @ g.origin), float(ng @ (centre - g.origin)) <= 1e-6))
    return out


def offset_plane(manifold, ref, d: float) -> Optional[m3d.Manifold]:
    face = find_plane_face(manifold, ref)
    if face is None:
        return None
    n, o = np.asarray(face.normal, dtype=float), np.asarray(face.origin, dtype=float)
    M = _frame(o, n)
    inv = np.linalg.inv(M)
    if d > 0:
        cs = _face_region(face, inv)
        if cs is None:
            return None
        prism = _apply(m3d.Manifold.extrude(cs, float(d)), M)
        for ng, off, convex in _neighbour_planes(manifold, face):
            if convex:
                prism = prism.trim_by_plane(tuple(-ng), -off)
        return manifold + prism
    depth = -float(d)
    bb = np.array(manifold.bounding_box())
    s = float(np.linalg.norm(bb[3:] - bb[:3])) * 2 + 10
    slab = _apply(m3d.Manifold.cube((s, s, depth)).translate((-s / 2, -s / 2, -depth)), M)
    tri = max(np.asarray(face.tris), key=lambda t: np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0])))
    probe_at = tri.mean(axis=0) - n * min(depth, 1.0) * 1e-3
    probe = m3d.Manifold.cube((1e-4, 1e-4, 1e-4), True).translate(tuple(probe_at))
    region = manifold ^ slab
    for ng, off, convex in _neighbour_planes(manifold, face):
        region = region.trim_by_plane(tuple(-ng), -off) if convex else region.trim_by_plane(tuple(ng), off)
    result = manifold
    for comp in region.decompose():
        if not (comp ^ probe).is_empty():
            result = result - comp
    return result


def _cylinder_loop(local, r, length):
    """The cross-section polygon of the wall of radius r about the local z axis, cut half way along it."""
    for poly in local.slice(length / 2.0).to_polygons():
        rad = np.hypot(poly[:, 0], poly[:, 1])
        if len(poly) >= 8 and np.all(np.abs(rad - r) < 0.03 * r + TOL):
            area2 = float(np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1]))
            return poly if area2 > 0 else poly[::-1]   # a hole's loop runs clockwise; cross-sections want counter-clockwise
    return None


def offset_cylinder(manifold, ref, d: float) -> Optional[m3d.Manifold]:
    r, length, internal = float(ref["radius"]), float(ref["length"]), bool(ref["internal"])
    r2 = r + d * (-1.0 if internal else 1.0)
    if r2 < 0.01:
        return None
    M = _frame(ref["origin"], ref["axis"])
    loop = _cylinder_loop(_apply(manifold, np.linalg.inv(M)), r, length)
    if loop is None:
        return None
    # The ring reaches a little into the material (when adding) or the air (when removing) on the side of the old
    # wall: a boundary that only nearly coincides with the wall would leave hair-thin slivers behind.
    margin = 0.05 * r + 1e-2
    r_in, r_out = sorted((r, r2))
    if r > r2:          # the old wall is the outer edge of the ring
        r_out += margin
    else:               # the old wall is the inner edge
        r_in = max(r_in - margin, 0.0)
    ring_xs = m3d.CrossSection([loop * (r_out / r)])
    if r_in > 1e-6:
        ring_xs = ring_xs - m3d.CrossSection([loop * (r_in / r)])
    ring = _apply(m3d.Manifold.extrude(ring_xs, length), M)
    return manifold + ring if d > 0 else manifold - ring


def surface_face_ref(pick: Dict[str, Any]) -> Dict[str, Any]:
    return {"kind": "surface", "point": [float(x) for x in pick["point"]], "normal": [float(x) for x in pick["normal"]]}


def _surface_patch(verts, tris, tri_normals, seed: int, max_angle_deg: float = 35.0) -> np.ndarray:
    """Triangle indices of the smooth surface around `seed` (neighbours join while their normals differ by less
    than max_angle_deg): a thread flank, a whole round thread, a fillet..."""
    by_vertex: Dict[int, List[int]] = {}
    for t, row in enumerate(tris):
        for x in row:
            by_vertex.setdefault(int(x), []).append(t)
    cos_min = float(np.cos(np.radians(max_angle_deg)))
    seen, stack = {seed}, [seed]
    while stack:
        t = stack.pop()
        for x in tris[t]:
            for nb in by_vertex[int(x)]:
                if nb not in seen and float(tri_normals[t] @ tri_normals[nb]) >= cos_min:
                    seen.add(nb)
                    stack.append(nb)
    return np.array(sorted(seen))


def _move_without_folds(verts, tris, mv, step, tries: int = 12) -> None:
    """verts[mv] += step, except that a vertex whose move would turn a triangle inside out (a hair-thin triangle in a
    flat end cap, narrower than `d`) goes only part of the way: the result stays a valid solid."""
    base = verts[mv].copy()
    scale = np.ones(len(mv))
    pos = np.full(len(verts), -1)
    pos[mv] = np.arange(len(mv))
    touched = np.where((pos[tris] >= 0).any(axis=1))[0]
    tv = tris[touched]

    def normals(v):
        return np.cross(v[tv[:, 1]] - v[tv[:, 0]], v[tv[:, 2]] - v[tv[:, 0]])

    before = normals(verts)
    real = np.linalg.norm(before, axis=1) > 2e-4      # micro triangles flip by float rounding alone; ignore them
    for _ in range(tries):
        verts[mv] = base + step * scale[:, None]
        flipped = (np.einsum("ij,ij->i", before, normals(verts)) < 0) & real
        if not flipped.any():
            return
        bad = np.unique(tv[flipped].ravel())
        scale[pos[bad[pos[bad] >= 0]]] *= 0.5
    verts[mv] = base + step * scale[:, None]


def offset_surfaces(manifold, refs, d: float) -> Optional[m3d.Manifold]:
    """Curved surfaces (threads, coils, fillets): the vertices of each picked smooth patch move `d` along their
    own outward normal; the neighbouring triangles stretch with them. Done for all patches at once."""
    mesh = manifold.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3].copy()
    tris = np.asarray(mesh.tri_verts, dtype=np.int64)
    a, b, c = (verts[tris[:, i]] for i in range(3))
    cross = np.cross(b - a, c - a)
    area2 = np.linalg.norm(cross, axis=1)
    normals = cross / np.where(area2 > 1e-12, area2, 1.0)[:, None]
    centroids = (a + b + c) / 3.0
    patch = set()
    for ref in refs:
        p, n = np.asarray(ref["point"], dtype=float), np.asarray(ref["normal"], dtype=float)
        dist = np.linalg.norm(centroids - p, axis=1) + 10.0 * (normals @ n < 0.5)   # nearest triangle facing the same way
        seed = int(dist.argmin())
        if dist[seed] > 5.0 + 0.1 * float(np.ptp(verts, axis=0).max()):
            continue
        patch.update(_surface_patch(verts, tris, normals, seed).tolist())
    if not patch:
        return None
    idx = np.array(sorted(patch))
    vn = np.zeros_like(verts)
    for k in range(3):
        np.add.at(vn, tris[idx, k], cross[idx])          # area-weighted vertex normals of the patch
    moved = np.unique(tris[idx].ravel())
    length = np.linalg.norm(vn[moved], axis=1)
    ok = length > 1e-12
    mv = moved[ok]
    step = d * vn[mv] / length[ok][:, None]
    # A vertex on the rim of the patch also belongs to the neighbouring surface (an end cap, a root). It slides
    # within that surface's plane, so the patch still moves `d` along its normal; moving it along the patch normal
    # would lift it out of the neighbour and fold the neighbour's triangles over.
    rest = np.setdiff1d(np.arange(len(tris)), idx)
    nb = np.zeros_like(vn)
    for k in range(3):
        np.add.at(nb, tris[rest, k], cross[rest])
    nb_len = np.linalg.norm(nb[mv], axis=1)
    n = vn[mv] / length[ok][:, None]
    m = nb[mv] / np.where(nb_len > 1e-12, nb_len, 1.0)[:, None]
    c = np.einsum("ij,ij->i", n, m)
    slide = (nb_len > 1e-12) & (1.0 - c * c > 0.1)       # nearly parallel surfaces keep the plain normal move
    step[slide] = d * (n - c[:, None] * m)[slide] / (1.0 - c * c)[slide, None]
    _move_without_folds(verts, tris, mv, step)
    out = m3d.Manifold(m3d.Mesh(vert_properties=verts.astype(np.float32), tri_verts=np.ascontiguousarray(tris.astype(np.uint32))))
    return out if out.status() == m3d.Error.NoError and not out.is_empty() else None


OVERSHOOT = 0.02   # a shell that is added or cut reaches this far past the old surface: never two coinciding faces


def offset_thread(manifold, ref, d: float, doc) -> Optional[m3d.Manifold]:
    """Offset Face on a thread (ref kind "thread"): the threaded zone (coil + bore or pin, `ThreadFeature.zone`) is
    rebuilt `d` bigger or smaller and cut from / added to THIS body only, so it gets clearance against the part it
    mates with (whose shape stays). sign -1: the body was cut by the zone (a nut, a jar); +1: the zone is its material
    (a bolt, a lid)."""
    feat = next((f for f in getattr(getattr(doc, "timeline", None), "features", []) if f.feature_id == ref["thread_id"]), None)
    if feat is None:
        return None
    shift = ref.get("shift") or [0.0, 0.0, 0.0]
    zone = lambda extra, channel=False: feat.zone(extra, channel).translate(shift)
    e = ref["sign"] * d          # how much the zone grows
    if ref["sign"] < 0:          # looser: a full channel, so the coil can screw out through this body's mouth
        return manifold - zone(e, channel=True) if e > 0 else manifold + (zone(OVERSHOOT) - zone(e))
    return manifold + (zone(e) - zone(-OVERSHOOT)) if e > 0 else manifold - (zone(OVERSHOOT) - zone(e))


class OffsetFaceFeature(Feature):
    """Moves the chosen faces of one body by `distance` (+ adds material, - removes it)."""

    def __init__(self, feature_id: str, name: str, target_body_id: str, faces: Optional[List[Dict[str, Any]]] = None,
                 distance: float = 0.2):
        super().__init__(feature_id, "offset_face", name)
        self.target_body_id = target_body_id
        self.faces = list(faces or [])
        self.distance = float(distance)
        self.skipped = 0

    @staticmethod
    def compute(manifold, faces, distance: float, doc: Any = None):
        """(new manifold, number of faces that could not be moved)."""
        skipped = 0
        if abs(distance) < 1e-6:
            return manifold, 0
        for ref in [r for r in faces if r.get("kind") == "thread"]:
            new = offset_thread(manifold, ref, distance, doc)
            if new is None or new.is_empty() or new.volume() < 1e-9:
                skipped += 1
            else:
                manifold = new
        surfaces = [r for r in faces if r.get("kind") == "surface"]
        if surfaces:
            try:
                new = offset_surfaces(manifold, surfaces, distance)
            except Exception as e:
                print(f"OffsetFaceFeature: {e}")
                new = None
            if new is None or new.volume() < 1e-9:
                skipped += len(surfaces)
            else:
                manifold = new
        for ref in faces:
            if ref.get("kind") in ("surface", "thread"):
                continue
            try:
                new = (offset_plane if ref.get("kind") == "plane" else offset_cylinder)(manifold, ref, distance)
            except Exception as e:   # a degenerate boolean must not break the history
                print(f"OffsetFaceFeature: {e}")
                new = None
            if new is None or new.is_empty() or new.volume() < 1e-9:
                skipped += 1
            else:
                manifold = new
        return manifold, skipped

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        target.manifold, self.skipped = self.compute(target.manifold, self.faces, self.distance, doc)
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
            "suppressed": self.suppressed, "target_body_id": self.target_body_id,
            "faces": self.faces, "distance": self.distance,
        }
