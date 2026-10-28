"""Faces hit tests for CAD mesh geometry."""

from typing import Optional
import math
import numpy as np
from omacad.model.faces_types import PlanarFace

RADIAL_TOLERANCE_DEG = 10.0      # how far a cylinder's face normal may tilt from the radius through its centre

_FACE_STACKS: dict = {}


def _ray_triangles(tris: np.ndarray, ray_origin, ray_dir, bary_tol: float = 1e-9) -> np.ndarray:
    """Moller-Trumbore against many triangles (N, 3, 3) at once: hit distance per triangle, inf where missed."""
    o = np.asarray(ray_origin, dtype=np.float64)
    d = np.asarray(ray_dir, dtype=np.float64)
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    e1, e2 = v1 - v0, v2 - v0
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - v0
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, e1)
    w = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -bary_tol) & (w >= -bary_tol) & (u + w <= 1.0 + bary_tol) & (t > 1e-6)
    return np.where(hit, t, np.inf)

def ray_hit_face(face: PlanarFace, ray_origin: np.ndarray, ray_dir: np.ndarray,
                 bary_tol: float = 1e-9) -> Optional[float]:
    """Nearest hit distance of a ray on one face, or None."""
    t = _ray_triangles(face.tris, ray_origin, ray_dir, bary_tol)
    return float(t.min()) if len(t) and np.isfinite(t.min()) else None

def ray_hit_faces(faces, ray_origin: np.ndarray, ray_dir: np.ndarray, bary_tol: float = 1e-9) -> np.ndarray:
    """Nearest hit distance per face (inf = missed), all triangles of all faces in one go. The triangles
    are stacked once per face list (a body's list is replaced when it is rebuilt): hovering a body with
    thousands of faces stays fast."""
    hit = _FACE_STACKS.get(id(faces))
    if hit is None or hit[0] is not faces:
        if len(_FACE_STACKS) > 64:
            _FACE_STACKS.clear()
        tris = [np.asarray(f.tris, dtype=np.float64).reshape(-1, 3, 3) for f in faces]
        owner = np.repeat(np.arange(len(tris)), [len(t) for t in tris]).astype(int)
        hit = _FACE_STACKS[id(faces)] = (faces, np.concatenate(tris) if tris else np.zeros((0, 3, 3)), owner)
    _, tris, owner = hit
    out = np.full(len(faces), np.inf)
    if len(tris):
        np.minimum.at(out, owner, _ray_triangles(tris, ray_origin, ray_dir, bary_tol))
    return out

def in_plane_edges(bodies, plane, tol_rel: float = 1e-3):
    """Body edges lying in a sketch plane, as 2D (u, v) segments."""
    o = np.asarray(plane.origin, dtype=np.float64)
    n = np.asarray(plane.normal, dtype=np.float64)
    ua = np.asarray(plane.u_axis, dtype=np.float64)
    va = np.asarray(plane.v_axis, dtype=np.float64)
    out = []
    for body in bodies:
        mesh = body.render_mesh
        if not body.visible or mesh is None or len(mesh.sharp_lines) == 0:
            continue
        pts = np.asarray(mesh.sharp_lines, dtype=np.float64).reshape(-1, 2, 3) - o
        tol = tol_rel * max(1.0, float(np.ptp(mesh.bounds_max - mesh.bounds_min)))
        on_plane = (np.abs(pts @ n) < tol).all(axis=1)
        uv = np.stack([pts[on_plane] @ ua, pts[on_plane] @ va], axis=-1)     # (k, 2 ends, 2)
        # a sketch on a body face: that face's outline from its triangles (origin planes keep the sharp lines only,
        # whose exact chords other steps' profiles were built on)
        faces = _coplanar_face_outlines(body, o, n, ua, va, tol) if getattr(plane, "name", "") == "FACE" else []
        if faces and len(uv):   # a line on a face outline is that outline again (another tessellation): drop it
            import shapely
            from shapely.geometry import MultiLineString
            mids = shapely.points(uv.mean(axis=1))
            uv = uv[shapely.distance(mids, MultiLineString(faces)) > 10 * tol]
        out += [((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))) for a, b in uv] + faces
    return out


def _coplanar_face_outlines(body, o, n, ua, va, tol) -> list:
    """The outlines of the body's flat faces in the plane, read from their triangles. The sharp lines of the render
    mesh can miss short pieces where two tessellations meet (0.1-0.3 mm gaps), so a face's inner outline and holes
    never closed and Project dropped them (Björn #103); the union of the face's triangles is always closed."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    out = []
    for face in getattr(body, "faces", ()):
        if getattr(face, "index", -1) < 0 or abs(float(np.asarray(face.normal) @ n)) < 1.0 - 1e-6 \
                or abs(float((np.asarray(face.origin, dtype=np.float64) - o) @ n)) > tol:
            continue
        tris = np.asarray(face.tris, dtype=np.float64) - o
        uv = np.stack([tris @ ua, tris @ va], axis=-1)
        polys = [Polygon(t) for t in uv]
        region = unary_union([p for p in polys if p.area > 1e-12])
        for poly in getattr(region, "geoms", [region]):
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            for ring in (poly.exterior, *poly.interiors):
                c = list(ring.coords)
                out += [((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))) for a, b in zip(c[:-1], c[1:])]
    return out

def ray_mesh_hit(mesh, ray_origin, ray_dir):
    """Nearest hit of a ray with a RenderMesh (unrolled triangles). Returns (t, triangle index) or None."""
    tri = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3)
    o, d = np.asarray(ray_origin, dtype=np.float64), np.asarray(ray_dir, dtype=np.float64)
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    p = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    sv = o - v0
    u = np.einsum("ij,ij->i", sv, p) * inv
    q = np.cross(sv, e1)
    w = (q @ d) * inv
    t = np.einsum("ij,ij->i", e2, q) * inv
    hit = ok & (u >= -1e-9) & (w >= -1e-9) & (u + w <= 1 + 1e-9) & (t > 1e-6)
    if not hit.any():
        return None
    ts = np.where(hit, t, np.inf)
    i = int(ts.argmin())
    return float(ts[i]), i

def smooth_patch_vertices(mesh, tri_idx: int, max_angle_deg: float = 35.0):
    """Vertices of the smoothly connected surface around a triangle (a cylinder wall, a flat face, a sphere...).
    Neighbouring triangles join while their normals differ by less than max_angle_deg."""
    tri = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    nrm = nrm / np.where(ln > 0, ln, 1.0)[:, None]
    scale = max(float(np.ptp(tri.reshape(-1, 3), axis=0).max()), 1.0)
    keys = np.round(tri.reshape(-1, 3) / (scale * 1e-6)).astype(np.int64)
    ids = {}
    vid = np.array([ids.setdefault(tuple(k), len(ids)) for k in keys]).reshape(-1, 3)
    by_vertex = {}
    for t, row in enumerate(vid):
        for x in row:
            by_vertex.setdefault(int(x), []).append(t)
    cos_min = math.cos(math.radians(max_angle_deg))
    seen, stack = {tri_idx}, [tri_idx]
    while stack:
        t = stack.pop()
        for x in vid[t]:
            for nb in by_vertex[int(x)]:
                if nb not in seen and float(nrm[t] @ nrm[nb]) >= cos_min:
                    seen.add(nb)
                    stack.append(nb)
    return tri[sorted(seen)].reshape(-1, 3)

def _normal_axis(nrm) -> Optional[np.ndarray]:
    """The axis a set of face normals is perpendicular to (smallest singular vector), or None when the normals
    spread in all three directions (a sphere or torus, not a cylinder)."""
    try:
        _, s, vh = np.linalg.svd(nrm)
    except Exception:
        return None
    if s[2] / max(s[0], 1e-9) > 0.35:
        return None
    return vh[2].copy()


def _wall_mask(nrm, ref, tol: float = 0.02, steps: int = 720, area=None) -> Optional[np.ndarray]:
    """Triangles of a cylinder wall inside a mixed patch (a fillet joins the wall and is smooth enough to be in it).
    The wall's axis is perpendicular to `ref`, the normal of the triangle the ray hit, so the candidate axes are
    the directions in that plane. The axis with the most inlier area wins (the many small triangles of a fillet
    must not outvote the few tall ones of the wall), provided its inlier normals spread around
    a circle: a flat cap has all normals equal and is perpendicular to many axes, so it is refused."""
    if len(nrm) < 3:
        return None
    e1 = np.cross(ref, [1.0, 0.0, 0.0])
    if np.linalg.norm(e1) < 0.3:
        e1 = np.cross(ref, [0.0, 1.0, 0.0])
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(ref, e1)
    th = np.linspace(0.0, np.pi, steps, endpoint=False)
    axes = np.outer(np.cos(th), e1) + np.outer(np.sin(th), e2)
    inl = np.abs(nrm @ axes.T) < tol
    counts = inl.sum(axis=0)
    weight = counts if area is None else (inl * np.asarray(area)[:, None]).sum(axis=0)
    for k in np.argsort(-weight):
        if counts[k] < 3:
            break
        s = np.linalg.svd(nrm[inl[:, k]], compute_uv=False)
        if s[1] > 0.5 * s[0]:
            return _tightened(nrm, inl[:, k], tol)
    return None


def _tightened(nrm, mask, tol: float) -> np.ndarray:
    """The wall mask narrowed around its own axis. The axis with the most inliers leans a little towards the
    side where it also catches the first ring of a fillet (a lean of 0.6 degrees still keeps every wall normal
    within `tol`), and the fit through those normals leans with it; halving the tolerance round the fitted axis
    drops the fillet ring and leaves the wall."""
    while tol > 0.002:
        axis = _normal_axis(nrm[mask])
        tol /= 2.0
        narrow = np.abs(nrm @ axis) < tol if axis is not None else mask
        if int(narrow.sum()) < max(3, mask.sum() // 2):
            break
        mask = narrow
    return mask


def detect_cylinder_surface(mesh, tri_idx: int) -> Optional[dict]:
    """Detect if the smooth patch around tri_idx is a cylindrical surface (pin/bolt or internal hole).

    Returns a dict with:
      radius: cylinder radius (mm)
      diameter: cylinder diameter (mm)
      length: cylinder length along axis (mm)
      axis: normalized 3D axis vector
      origin: 3D point at the bottom/start of cylinder on the axis
      is_internal: True for internal hole / female, False for external pin / male
      u_axis, v_axis: orthogonal vectors perpendicular to axis
    or None if the patch is planar, spherical, or irregular.
    """
    patch = smooth_patch_vertices(mesh, tri_idx, max_angle_deg=35.0)
    if len(patch) < 24:
        return None

    tri = patch.reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(nrm, axis=1)
    solid = ln > 1e-9 * float(ln.max())   # sliver triangles of the float64 mesh carry no usable normal
    if int(solid.sum()) < 24:
        return None
    patch, tri, nrm, ln = tri[solid].reshape(-1, 3), tri[solid], nrm[solid] / ln[solid][:, None], ln[solid]

    # If all normals are almost identical, it's a planar face, not a cylinder
    if float(np.ptp(nrm, axis=0).max()) < 0.15:
        return None

    # For a cylindrical surface, face normals are perpendicular to the cylinder axis: nrm @ axis ~ 0
    axis = _normal_axis(nrm)
    if axis is None:
        # A fillet or round that runs into the wall is smooth enough to join the patch, and its normals spread out
        # of the wall's plane. Keep only the wall: the triangles whose normals are perpendicular to one axis.
        t = np.asarray(mesh.vertices, dtype=np.float64).reshape(-1, 3, 3)[tri_idx]
        ref = np.cross(t[1] - t[0], t[2] - t[0])
        if np.linalg.norm(ref) < 1e-12:
            return None
        keep = _wall_mask(nrm, ref / np.linalg.norm(ref), area=ln)
        if keep is None or int(keep.sum()) < 24:
            return None
        patch = patch.reshape(-1, 3, 3)[keep].reshape(-1, 3)
        nrm = nrm[keep]
        axis = _normal_axis(nrm)
        if axis is None:
            return None

    axis_len = float(np.linalg.norm(axis))
    if axis_len < 1e-6:
        return None
    axis /= axis_len

    # Standardize axis direction: prefer positive Z, then positive Y, then positive X
    if axis[2] < -1e-4 or (abs(axis[2]) <= 1e-4 and (axis[1] < -1e-4 or (abs(axis[1]) <= 1e-4 and axis[0] < 0))):
        axis = -axis

    # Create perpendicular basis u_vec, v_vec
    if abs(axis[0]) < 0.9:
        u_vec = np.cross(axis, [1.0, 0.0, 0.0])
    else:
        u_vec = np.cross(axis, [0.0, 1.0, 0.0])
    u_vec /= float(np.linalg.norm(u_vec))
    v_vec = np.cross(axis, u_vec)

    p_mean = patch.mean(axis=0)
    diff = patch - p_mean
    u_coords = diff @ u_vec
    v_coords = diff @ v_vec

    # 2D circle fit via linear least squares
    A = np.column_stack([2.0 * u_coords, 2.0 * v_coords, np.ones(len(patch))])
    b = u_coords**2 + v_coords**2
    try:
        sol, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        du, dv, c_const = sol
        rad_sq = c_const + du**2 + dv**2
        if rad_sq <= 0:
            return None
        radius = float(np.sqrt(rad_sq))
    except Exception:
        return None

    if radius < 0.1 or radius > 5000.0:
        return None

    center_on_axis = p_mean + du * u_vec + dv * v_vec

    # Verify fit quality: points should be at distance ~ radius from axis
    dists_to_axis = np.linalg.norm(diff - np.outer(diff @ axis, axis) - (du * u_vec + dv * v_vec), axis=1)
    if float(np.std(dists_to_axis)) > 0.15 * radius:
        return None

    # A cylinder's face normals point straight out from its axis. A flat wall of a big-radius fit (a 20 mm hex
    # wall "fits" a 28 mm circle within 0.15 * R) keeps one normal across its width, so it is refused here.
    tri_mid = patch.reshape(-1, 3, 3).mean(axis=1)
    radial = tri_mid - center_on_axis
    radial -= np.outer(radial @ axis, axis)
    radial /= np.maximum(np.linalg.norm(radial, axis=1), 1e-12)[:, None]
    # A few stray triangles (a fillet's edge, a coarse facet) may tilt more, so judge the 90th percentile.
    if float(np.percentile(np.abs(np.sum(nrm * radial, axis=1)), 10)) < math.cos(math.radians(RADIAL_TOLERANCE_DEG)):
        return None

    z_coords = (patch - center_on_axis) @ axis
    z_min, z_max = float(z_coords.min()), float(z_coords.max())
    length = max(0.5, z_max - z_min)
    origin_pt = center_on_axis + z_min * axis

    # Determine internal (hole) vs external (pin):
    sample_pt = patch[0]
    sample_norm = nrm[0]
    radial_vec = sample_pt - (center_on_axis + ((sample_pt - center_on_axis) @ axis) * axis)
    is_internal = bool(float(sample_norm @ radial_vec) < 0.0)

    return {
        "radius": radius,
        "diameter": round(2.0 * radius, 3),
        "length": round(length, 3),
        "length_exact": z_max - z_min,
        "axis": axis,
        "origin": origin_pt,
        "is_internal": is_internal,
        "u_axis": u_vec,
        "v_axis": v_vec,
        "patch": patch,
    }
