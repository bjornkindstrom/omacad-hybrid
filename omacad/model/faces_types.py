"""Face types for CAD mesh geometry."""

from dataclasses import dataclass
from typing import List, Optional
import math
import numpy as np


@dataclass
class PlanarFace:
    body_id: str
    index: int
    normal: np.ndarray      # unit outward normal (3,)
    origin: np.ndarray      # a point on the face (3,)
    area: float
    tris: np.ndarray        # (N, 3, 3) world-space triangles for picking/highlighting

@dataclass
class PlanarEdge:
    """A straight edge between two planar faces, with what is needed to round or chamfer it."""
    p0: np.ndarray
    p1: np.ndarray
    n1: np.ndarray       # outward normals of the two faces
    n2: np.ndarray
    d1: np.ndarray       # unit vectors lying in each face, pointing away from the edge
    d2: np.ndarray
    convex: bool         # True: a solid corner (material is removed); False: an inside corner (material is added)

    kind = "line"

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.p1 - self.p0))

    def polyline(self, n: int = 2) -> np.ndarray:
        return np.array([self.p0, self.p1])

    def same_as(self, other) -> bool:
        if getattr(other, "kind", "") != "line":
            return False
        return (np.allclose(self.p0, other.p0, atol=1e-6) and np.allclose(self.p1, other.p1, atol=1e-6)) or \
               (np.allclose(self.p0, other.p1, atol=1e-6) and np.allclose(self.p1, other.p0, atol=1e-6))

    def ref(self):
        """What a Fillet/Chamfer step stores to find this edge again."""
        return (tuple(map(float, self.p0)), tuple(map(float, self.p1)))

@dataclass
class CircularEdge:
    """A full circle where a flat face meets a cylinder (top of a pin, rim of a hole, screw head ...)."""
    center: np.ndarray
    axis: np.ndarray     # unit normal of the flat face (outward)
    radius: float
    s1: float            # +1: the flat face lies outside the circle, -1: inside it
    s2: float            # +1: the cylinder wall continues along +axis, -1: along -axis
    convex: bool         # rim of solid material (cut) vs inside corner (fill)
    nseg: int = 48       # segments of the tessellated circle (decides how far the chords sag inside the radius)
    a0: float = 0.0      # an arc only: where it starts (radians, in `_basis`) and how far it runs
    sweep: float = 2 * np.pi

    kind = "circle"

    @property
    def is_arc(self) -> bool:
        return self.sweep < 2 * np.pi - 1e-6

    def _basis(self):
        a = self.axis
        u = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(a, [0.0, 1.0, 0.0])
        u = u / np.linalg.norm(u)
        return u, np.cross(a, u)

    def polyline(self, n: int = 96) -> np.ndarray:
        u, v = self._basis()
        ang = self.a0 + np.linspace(0.0, self.sweep, max(2, int(n * self.sweep / (2 * np.pi))) + 1)
        return self.center + self.radius * (np.outer(np.cos(ang), u) + np.outer(np.sin(ang), v))

    def same_as(self, other) -> bool:
        if getattr(other, "kind", "") != "circle":
            return False
        if self.is_arc != other.is_arc:
            return False
        if self.is_arc and (float(self.axis @ other.axis) < 0.999 or abs(self.sweep - other.sweep) > 1e-3
                            or abs(math.remainder(self.a0 - other.a0, 2 * np.pi)) > 1e-3):
            return False
        return (abs(abs(float(self.axis @ other.axis)) - 1.0) < 1e-6 and abs(self.radius - other.radius) < 1e-4 * max(1.0, self.radius)
                and np.linalg.norm(self.center - other.center) < 1e-4 * max(1.0, self.radius))

    def ref(self):
        if self.is_arc:
            return ("arc", tuple(map(float, self.center)), tuple(map(float, self.axis)), float(self.radius),
                    float(self.a0), float(self.sweep))
        return ("circle", tuple(map(float, self.center)), tuple(map(float, self.axis)), float(self.radius))

@dataclass
class LoopEdge:
    """The whole outline of a flat face that mixes straight pieces and arcs (a plate with rounded corners,
    a slot ...), where the walls stand square on the face or lean (the top of a twisted extrude). Rounded or
    bevelled as one piece."""
    pts: np.ndarray      # (N, 3) points in order, the face on the left of the direction of travel (not closed)
    n: np.ndarray        # outward unit normal of the flat face
    convex: bool = True
    walls: Optional[np.ndarray] = None   # (N, 3) outward unit normal of the wall along piece i (point i to i+1); None = square

    kind = "loop"

    @property
    def perimeter(self) -> float:
        d = np.roll(self.pts, -1, axis=0) - self.pts
        return float(np.linalg.norm(d, axis=1).sum())

    @property
    def centroid(self) -> np.ndarray:
        return self.pts.mean(axis=0)

    def polyline(self, n: int = 0) -> np.ndarray:
        return np.vstack([self.pts, self.pts[:1]])

    def same_as(self, other) -> bool:
        if getattr(other, "kind", "") != "loop":
            return False
        tol = 1e-4 * max(1.0, self.perimeter)
        return (float(self.n @ other.n) > 0.999 and np.linalg.norm(self.centroid - other.centroid) < tol
                and abs(self.perimeter - other.perimeter) < tol)

    def contains_arc(self, edge) -> bool:
        """Whether this outline already includes the entire circular edge, using its actual chords.

        Fitted circle samples need not coincide with the mesh chords. Compare their radii and angular
        coverage instead; a nearby concentric arc or an arc with only its ends on the loop is not covered.
        """
        if edge.kind != "circle" or self.convex != edge.convex or float(self.n @ edge.axis) < 0.999:
            return False
        tol = 1e-5 * max(1.0, edge.radius)
        q = self.pts - edge.center
        on_circle = (np.abs(q @ edge.axis) < tol) & (np.abs(np.linalg.norm(q, axis=1) - edge.radius) < tol)
        u, v = edge._basis()
        angles = np.arctan2(q @ v, q @ u) - edge.a0
        intervals = []
        for i in range(len(q)):
            j = (i + 1) % len(q)
            if not (on_circle[i] and on_circle[j]):
                continue
            turn = math.remainder(float(angles[j] - angles[i]), 2 * math.pi)
            if abs(turn) > 1.5 * 2 * math.pi / max(edge.nseg, 6):
                continue  # a straight chord across the circle does not cover the arc
            a = float(angles[i]) % (2 * math.pi)
            lo, hi = sorted((a, a + turn))
            for shift in (-2 * math.pi, 0.0, 2 * math.pi):
                intervals.append((lo + shift, hi + shift))
        covered = 0.0
        angular_tol = tol / max(edge.radius, 1e-12)
        for lo, hi in sorted(intervals):
            if hi < 0:
                continue
            if lo > covered + angular_tol:
                break
            covered = max(covered, hi)
            if covered >= edge.sweep - angular_tol:
                return True
        return False

    def ref(self):
        return ("loop", tuple(map(float, self.centroid)), tuple(map(float, self.n)), float(self.perimeter))
