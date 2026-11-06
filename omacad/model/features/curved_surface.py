"""Curved surface: fits an extruded or ruled wall of arbitrary cross-section (splines, arcs, lines)
from a picked surface face reference (`kind == "surface"`). Slices the patch triangles across the extrusion
axis to chain an ordered 2D polyline parameterized by arc length s, with smooth outward normals."""

import math
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np
import shapely.geometry as sg
from shapely.ops import linemerge
import manifold3d as m3d

from omacad.model.features.offset_face import _surface_patch


def ensure_positive_volume(solid: m3d.Manifold) -> m3d.Manifold:
    """Ensure the manifold solid has positive volume by flipping triangle winding if inverted."""
    if solid.volume() >= 0.0:
        return solid
    mesh = solid.to_mesh()
    v = np.ascontiguousarray(mesh.vert_properties, dtype=np.float64)
    t = np.ascontiguousarray(mesh.tri_verts[:, [0, 2, 1]], dtype=np.uint64)
    return m3d.Manifold(m3d.Mesh64(v, t))


def _normal_axis(normals: np.ndarray) -> Optional[np.ndarray]:
    """Find the common axis perpendicular to all normals of an extruded/cylindrical surface (svd of normals)."""
    if len(normals) < 3:
        return None
    _, s, vh = np.linalg.svd(normals)
    # The axis of extrusion is the right singular vector corresponding to the smallest singular value
    axis = vh[2]
    # Check that normals are indeed mostly perpendicular to this axis
    dots = np.abs(normals @ axis)
    if float(np.percentile(dots, 90)) > 0.15:
        return None
    axis = axis / np.linalg.norm(axis)
    # Standardize orientation (prefer +Z, +Y, +X)
    for c in reversed(axis):
        if abs(c) > 1e-4:
            if c < 0:
                axis = -axis
            break
    return axis


def _frame(origin: np.ndarray, axis: np.ndarray) -> np.ndarray:
    """Orthonormal frame matrix with Z along `axis` and translation `origin`."""
    z = axis / np.linalg.norm(axis)
    ref = np.array([0.0, 0.0, 1.0]) if abs(z[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = np.cross(ref, z)
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = x, y, z, origin
    return M


class CurvedWall:
    """A ruled/extruded surface with arc length s in [0, L] and local height z in [z0, z1]."""

    def __init__(self, s: np.ndarray, coords: np.ndarray, normals: np.ndarray, z0: float, z1: float,
                 closed: bool, M: np.ndarray):
        self.s = np.asarray(s, dtype=float)
        self.coords = np.asarray(coords, dtype=float)
        self.normals = np.asarray(normals, dtype=float)
        self.z0 = float(z0)
        self.z1 = float(z1)
        self.height = self.z1 - self.z0
        self.closed = bool(closed)
        self.M = np.asarray(M, dtype=float)
        self.L = float(self.s[-1])

    def point_and_normal(self, s_val: float, z_val: float) -> Tuple[np.ndarray, np.ndarray]:
        """Returns 3D world point and 3D world outward normal at (s, z)."""
        if self.closed and self.L > 1e-6:
            s_val = s_val % self.L
        else:
            s_val = float(np.clip(s_val, self.s[0], self.s[-1]))
        px = float(np.interp(s_val, self.s, self.coords[:, 0]))
        py = float(np.interp(s_val, self.s, self.coords[:, 1]))
        nx = float(np.interp(s_val, self.s, self.normals[:, 0]))
        ny = float(np.interp(s_val, self.s, self.normals[:, 1]))
        n_len = math.hypot(nx, ny)
        if n_len > 1e-12:
            nx, ny = nx / n_len, ny / n_len
        local_p = np.array([px, py, z_val, 1.0])
        local_n = np.array([nx, ny, 0.0])
        world_p = (self.M @ local_p)[:3]
        world_n = self.M[:3, :3] @ local_n
        return world_p, world_n

    def warp(self, t_low: float, t_high: float) -> Callable[[np.ndarray], np.ndarray]:
        """Returns a warper function that maps local (s, z, u) [where u in 0..1]
        to 3D local coordinates (x(s) + t*nx(s), y(s) + t*ny(s), z)."""
        s_arr = self.s
        coords = self.coords
        normals = self.normals
        L = self.L
        closed = self.closed

        def warper(pts: np.ndarray) -> np.ndarray:
            s_in = pts[:, 0]
            z_in = pts[:, 1]
            u = pts[:, 2]
            if closed and L > 1e-6:
                s_in = np.mod(s_in, L)
            t = t_low + u * (t_high - t_low)
            px = np.interp(s_in, s_arr, coords[:, 0])
            py = np.interp(s_in, s_arr, coords[:, 1])
            nx = np.interp(s_in, s_arr, normals[:, 0])
            ny = np.interp(s_in, s_arr, normals[:, 1])
            n_len = np.maximum(np.hypot(nx, ny), 1e-12)
            nx, ny = nx / n_len, ny / n_len
            return np.column_stack([px + t * nx, py + t * ny, z_in])

        return warper


def curved_wall(manifold, ref: Dict[str, Any]) -> Optional[CurvedWall]:
    """Extracts a CurvedWall from a picked surface reference or cylinder."""
    mesh = manifold.to_mesh()
    verts = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    tris = np.asarray(mesh.tri_verts, dtype=np.int64)
    a, b, c = (verts[tris[:, i]] for i in range(3))
    cross = np.cross(b - a, c - a)
    area2 = np.linalg.norm(cross, axis=1)
    normals = cross / np.where(area2 > 1e-12, area2, 1.0)[:, None]
    centroids = (a + b + c) / 3.0

    p = np.asarray(ref.get("point", [0, 0, 0]), dtype=float)
    n = np.asarray(ref.get("normal", [0, 0, 1]), dtype=float)
    dist = np.linalg.norm(centroids - p, axis=1) + 10.0 * (normals @ n < 0.5)
    seed = int(dist.argmin())
    if dist[seed] > 10.0 + 0.2 * float(np.ptp(verts, axis=0).max()):
        return None

    idx = _surface_patch(verts, tris, normals, seed, max_angle_deg=35.0)
    if len(idx) < 2:
        return None

    patch_nrm = normals[idx]
    patch_areas = np.maximum(area2[idx], 1e-12)
    weighted_nrm = patch_nrm * np.sqrt(patch_areas)[:, None]
    axis = _normal_axis(weighted_nrm)
    if axis is None:
        axis = _normal_axis(patch_nrm)
    if axis is None:
        return None

    patch_verts_idx = np.unique(tris[idx].ravel())
    center = verts[patch_verts_idx].mean(axis=0)
    M = _frame(center, axis)
    M_inv = np.linalg.inv(M)

    # Transform patch triangles to local frame
    local_verts = verts @ M_inv[:3, :3].T + M_inv[:3, 3]
    local_p_tris = local_verts[tris[idx]]
    local_nrm = patch_nrm @ M[:3, :3]  # inverse transpose of orthogonal M is M

    z0 = float(local_p_tris[:, :, 2].min())
    z1 = float(local_p_tris[:, :, 2].max())
    if z1 - z0 < 1e-3:
        return None
    z_mid = (z0 + z1) / 2.0

    # Slice patch triangles at z_mid
    segments = []
    for t, tnrm in zip(local_p_tris, local_nrm):
        zs = t[:, 2] - z_mid
        pts = []
        for i in range(3):
            j = (i + 1) % 3
            z_a, z_b = zs[i], zs[j]
            if (z_a < 0 and z_b > 0) or (z_a > 0 and z_b < 0):
                frac = -z_a / (z_b - z_a)
                p_cut = t[i] + frac * (t[j] - t[i])
                pts.append(p_cut[:2])
            elif abs(z_a) < 1e-6:
                pts.append(t[i][:2])
        dedup = []
        for pt in pts:
            if not any(np.linalg.norm(pt - d) < 1e-5 for d in dedup):
                dedup.append(pt)
        if len(dedup) == 2:
            p0, p1 = dedup[0], dedup[1]
            dp = p1 - p0
            # Orient so 2D outward normal is on the right
            if dp[0] * tnrm[1] - dp[1] * tnrm[0] > 0:
                p0, p1 = p1, p0
            segments.append(sg.LineString([p0, p1]))

    if not segments:
        return None

    line = linemerge(segments)
    if isinstance(line, sg.MultiLineString):
        # Pick longest component
        line = max(line.geoms, key=lambda g: g.length)

    coords = np.asarray(line.coords)
    if len(coords) < 2:
        return None

    closed = bool(np.linalg.norm(coords[0] - coords[-1]) < 1e-3)
    ds = np.hypot(np.diff(coords[:, 0]), np.diff(coords[:, 1]))
    s = np.concatenate(([0.0], np.cumsum(ds)))
    if s[-1] < 1e-3:
        return None

    tangents = np.gradient(coords, s, axis=0)
    norm = np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), 1e-12)
    tangents = tangents / norm
    normals_2d = np.column_stack([tangents[:, 1], -tangents[:, 0]])

    return CurvedWall(s, coords, normals_2d, z0, z1, closed, M)
