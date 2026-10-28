"""
Omacad - 3D Camera & Graphics Math
Matrices, vectors, and ray casting helpers using NumPy.
"""

import math
from typing import Tuple, Optional
import numpy as np


def perspective(fovy_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    """Create a 4x4 perspective projection matrix (OpenGL convention)."""
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2.0 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def ortho(left: float, right: float, bottom: float, top: float, near: float, far: float) -> np.ndarray:
    """Create a 4x4 orthographic projection matrix."""
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = 2.0 / (right - left)
    m[1, 1] = 2.0 / (top - bottom)
    m[2, 2] = -2.0 / (far - near)
    m[0, 3] = -(right + left) / (right - left)
    m[1, 3] = -(top + bottom) / (top - bottom)
    m[2, 3] = -(far + near) / (far - near)
    m[3, 3] = 1.0
    return m


REF_FOVY = 45.0   # field of view that `distance` is calibrated against (visible height at the target)


def camera_matrices(target, distance: float, azimuth: float, elevation: float, aspect: float,
                    fov_deg: float = REF_FOVY, ortho_view: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    """(projection, view) of the orbit camera. `distance` keeps its meaning at every field of view: the
    height visible at the target is 2*distance*tan(REF_FOVY/2), so changing the field of view or switching
    to orthographic changes only the perspective distortion, never the zoom."""
    half_h = distance * math.tan(math.radians(REF_FOVY) / 2.0)
    if ortho_view:
        far = distance + 5000.0
        proj = ortho(-half_h * aspect, half_h * aspect, -half_h, half_h, -far, far)
        return proj, orbit_view(target, distance, azimuth, elevation)
    eye_d = half_h / math.tan(math.radians(fov_deg) / 2.0)
    proj = perspective(fov_deg, aspect, max(0.5, eye_d * 0.01), eye_d + 5000.0)
    return proj, orbit_view(target, eye_d, azimuth, elevation)


def orbit_view(target, distance: float, azimuth: float, elevation: float) -> np.ndarray:
    """View matrix of the orbit camera. Z stays up at every elevation (the orbit is clamped just short of
    straight up/down), so the view turns smoothly when you pass over the top - no jump in roll."""
    az, el = math.radians(azimuth), math.radians(elevation)
    eye = np.array([target[0] + distance * math.cos(el) * math.sin(az),
                    target[1] - distance * math.cos(el) * math.cos(az),
                    target[2] + distance * math.sin(el)], dtype=np.float64)
    return look_at(eye, np.asarray(target, dtype=np.float64), np.array([0.0, 0.0, 1.0]))


def look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Create a 4x4 View matrix."""
    eye = np.asarray(eye, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)

    forward = target - eye
    norm_f = np.linalg.norm(forward)
    if norm_f < 1e-6:
        forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    else:
        forward /= norm_f

    norm_u = np.linalg.norm(up)
    if norm_u < 1e-6:
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    else:
        up /= norm_u

    right = np.cross(forward, up)
    norm_r = np.linalg.norm(right)
    if norm_r < 1e-6:
        # collinear, pick alternate up
        alt_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        right = np.cross(forward, alt_up)
        norm_r = np.linalg.norm(right)
        if norm_r < 1e-6:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            right /= norm_r
    else:
        right /= norm_r

    actual_up = np.cross(right, forward)

    m = np.eye(4, dtype=np.float32)
    m[0, :3] = right
    m[1, :3] = actual_up
    m[2, :3] = -forward
    m[0, 3] = -np.dot(right, eye)
    m[1, 3] = -np.dot(actual_up, eye)
    m[2, 3] = np.dot(forward, eye)
    return m


def ray_from_screen(
    screen_x: float,
    screen_y: float,
    viewport_w: int,
    viewport_h: int,
    view_mat: np.ndarray,
    proj_mat: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes (ray_origin, ray_direction) in 3D world space from 2D pixel coordinates.
    """
    ndc_x = (2.0 * screen_x) / float(viewport_w) - 1.0
    ndc_y = 1.0 - (2.0 * screen_y) / float(viewport_h)  # invert Y for OpenGL NDC

    inv_pv = np.linalg.inv(proj_mat @ view_mat)

    # Near plane point (Z = -1)
    near_clip = np.array([ndc_x, ndc_y, -1.0, 1.0], dtype=np.float32)
    near_world = inv_pv @ near_clip
    near_world /= near_world[3]

    # Far plane point (Z = 1)
    far_clip = np.array([ndc_x, ndc_y, 1.0, 1.0], dtype=np.float32)
    far_world = inv_pv @ far_clip
    far_world /= far_world[3]

    ray_origin = near_world[:3]
    ray_dir = far_world[:3] - near_world[:3]
    norm = np.linalg.norm(ray_dir)
    if norm > 1e-7:
        ray_dir /= norm

    return ray_origin, ray_dir


def ray_plane_intersect(
    ray_origin: np.ndarray,
    ray_dir: np.ndarray,
    plane_pt: np.ndarray,
    plane_normal: np.ndarray
) -> Optional[np.ndarray]:
    """Computes the 3D intersection point of a ray and a plane, or None if parallel."""
    denom = np.dot(ray_dir, plane_normal)
    if abs(denom) < 1e-7:
        return None  # Parallel
    t = np.dot(plane_pt - ray_origin, plane_normal) / denom
    if t < 0:
        return None  # Behind ray
    return ray_origin + t * ray_dir
