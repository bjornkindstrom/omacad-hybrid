"""A surface of revolution (a pot, a vase) unrolled onto a flat pattern. The detection of round faces also accepts these,
but their radius changes along the axis, so anything that assumes one radius only meets the surface in a few bands.

The unrolling is conformal: x = angle * R, y = R * integral of ds / r(s), with R the largest radius. Small shapes keep
their proportions everywhere; they only scale by r / R (`scale`), so a pattern can be made even by working in true sizes."""

import math
from typing import Optional

import numpy as np
import manifold3d as m3d

MAX_LEVELS = 240            # outlines read along the axis
CREASE = math.radians(40)   # the profile turning this much ends the face: the rim of a pot, a step
ROUND_RING = 0.9            # a ring whose nearest and furthest points differ more than this is not round
END_OVERSHOOT = 0.01        # mm
STRAIGHT_SHARE = 0.5        # at least this share of the profile on one radius is a cylinder (perhaps with rounded ends)


def _profile_points(local: m3d.Manifold, internal: bool):
    """(radius, z) of the wall along the axis of `local`, None where its outline there is not a circle."""
    mesh = local.to_mesh64()
    heights = np.unique(np.round(np.asarray(mesh.vert_properties)[:, 2], 3))
    if len(heights) < 2:
        return []
    # just inside both ends of every stretch between mesh rings: a plain cylinder has only its two ends to read,
    # and a step shows as a jump, which ends the face
    inside = np.minimum(1e-3, np.diff(heights) / 4.0)
    levels = np.sort(np.concatenate((heights[:-1] + inside, heights[1:] - inside)))
    if len(levels) > MAX_LEVELS:
        levels = levels[np.linspace(0, len(levels) - 1, MAX_LEVELS).astype(int)]
    points = []
    for z in levels:
        rings = [np.asarray(r, dtype=float) for r in local.slice(float(z)).to_polygons()]
        chosen = None
        for ring in rings:
            x, y = ring[:, 0], ring[:, 1]
            hole = float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)) < 0
            radii = np.hypot(x, y)
            if hole == internal and (chosen is None or radii.max() > chosen.max()):
                chosen = radii
        if chosen is not None and chosen.min() > ROUND_RING * chosen.max():
            points.append((float(chosen.max()), float(z)))
        else:
            points.append(None)
    return points


def _run_at(points, z_middle: float) -> Optional[np.ndarray]:
    """The smooth stretch of the profile that holds z_middle, as an array of (radius, z)."""
    runs, run = [], []
    for point in points:
        if point is None:
            runs.append(run)
            run = []
            continue
        if len(run) >= 2:
            a, b = np.subtract(run[-1], run[-2]), np.subtract(point, run[-1])
            if abs(math.atan2(a[0] * b[1] - a[1] * b[0], float(a @ b))) > CREASE:
                runs.append(run)
                run = [run[-1]]
        run.append(point)
    runs.append(run)
    for run in runs:
        if len(run) >= 3 and run[0][1] <= z_middle <= run[-1][1]:
            return np.asarray(run, dtype=float)
    return None


class RevolvedSurface:
    """One smooth wall of revolution round local z. `s` is the length along its profile."""

    def __init__(self, profile: np.ndarray, internal: bool):
        self.internal = internal
        self.r, self.z = profile[:, 0], profile[:, 1]
        steps = np.diff(profile, axis=0)
        lengths = np.linalg.norm(steps, axis=1)
        self.s = np.concatenate(([0.0], np.cumsum(lengths)))
        self.R = float(self.r.max())
        self.period = 2.0 * math.pi * self.R
        tangents = steps / np.maximum(lengths[:, None], 1e-12)
        smooth = np.vstack((tangents[:1], tangents[:-1] + tangents[1:], tangents[-1:]))
        smooth /= np.maximum(np.linalg.norm(smooth, axis=1, keepdims=True), 1e-12)
        self.nr, self.nz = smooth[:, 1], -smooth[:, 0]      # away from the axis on an upright wall
        floor = np.maximum(self.r, 0.01 * self.R)
        self.y = np.concatenate(([0.0], np.cumsum(lengths * 2.0 / (floor[:-1] + floor[1:])))) * self.R

    def radius_at(self, s):
        return np.interp(s, self.s, self.r)

    def scale_at_y(self, y):
        """True size per unit of the flat pattern, where it lies at height y."""
        return self.radius_at(self.s_at(y)) / self.R

    def y_at(self, s: float) -> float:
        """Past the ends the pattern goes on evenly, so that cells there are bounded by neighbours of a fair size."""
        if s < self.s[0]:
            return float(self.y[0] + (s - self.s[0]) * self.R / max(self.r[0], 0.01 * self.R))
        if s > self.s[-1]:
            return float(self.y[-1] + (s - self.s[-1]) * self.R / max(self.r[-1], 0.01 * self.R))
        return float(np.interp(s, self.s, self.y))

    def s_at(self, y):
        return np.interp(y, self.y, self.s)

    def usable(self, min_radius: float):
        """(s_low, s_high) of the stretch round the middle where the radius is at least min_radius, or None."""
        ok = self.r >= min_radius
        if not ok.any():
            return None
        middle = int(np.argmax(ok & (self.r >= self.r[ok].max() * 0.999)))
        low = middle
        while low > 0 and ok[low - 1]:
            low -= 1
        high = middle
        while high < len(ok) - 1 and ok[high + 1]:
            high += 1
        return float(self.s[low]), float(self.s[high])

    def centre(self, x: float, y: float):
        """The local 3D point of the surface under (x, y) and the unit normal away from the axis there."""
        s = float(self.s_at(y))
        theta = x / self.R
        rr, zz = float(self.radius_at(s)), float(np.interp(s, self.s, self.z))
        nr, nz = float(np.interp(s, self.s, self.nr)), float(np.interp(s, self.s, self.nz))
        length = max(math.hypot(nr, nz), 1e-12)
        nr, nz = nr / length, nz / length
        return (np.array([rr * math.cos(theta), rr * math.sin(theta), zz]),
                np.array([nr * math.cos(theta), nr * math.sin(theta), nz]))

    def warp(self, low: float, high: float):
        """Warp of a unit-tall prism of the flat pattern onto the wall: from `low` to `high` mm along the normal."""
        def apply(points):
            theta = points[:, 0] / self.R
            s = np.interp(points[:, 1], self.y, self.s)
            nr, nz = np.interp(s, self.s, self.nr), np.interp(s, self.s, self.nz)
            length = np.maximum(np.hypot(nr, nz), 1e-12)
            t = low + points[:, 2] * (high - low)
            radius = np.interp(s, self.s, self.r) + t * nr / length
            return np.column_stack((radius * np.cos(theta), radius * np.sin(theta),
                                    np.interp(s, self.s, self.z) + t * nz / length))
        return apply


def revolved_surface(manifold: m3d.Manifold, M: np.ndarray, ref: dict) -> Optional[RevolvedSurface]:
    """The wall under a picked round face when its radius really changes along the axis; None for a cylinder, also one
    with rounded ends, and for anything that isn't round all the way along."""
    inverse = np.linalg.inv(M)
    internal = bool(ref.get("internal", False))
    points = _profile_points(manifold.transform(inverse[:3, :]), internal)
    if not points:
        return None
    run = _run_at(points, float(ref["length"]) / 2.0)
    if run is None:
        return None
    tolerance = 0.02 * float(ref["radius"]) + 1e-3
    steps = np.linalg.norm(np.diff(run, axis=0), axis=1)
    near = np.abs((run[:-1, 0] + run[1:, 0]) / 2.0 - float(ref["radius"])) < tolerance
    if steps[near].sum() >= STRAIGHT_SHARE * steps.sum():
        return None
    # a hair past both ends along the wall: cells reaching a rim must not leave a skin on its plane
    first, last = run[0] - run[1], run[-1] - run[-2]
    first, last = first / max(np.linalg.norm(first), 1e-12), last / max(np.linalg.norm(last), 1e-12)
    ends = (np.maximum(run[0] + END_OVERSHOOT * first, 0.0)[None], (run[-1] + END_OVERSHOOT * last)[None])
    return RevolvedSurface(np.vstack((ends[0], run, ends[1])), internal)
