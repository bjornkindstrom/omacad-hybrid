"""Closed nonplanar contours on cylindrical surfaces, including wrapped emboss rims."""
from collections import defaultdict
from dataclasses import dataclass
import math

import manifold3d as m3d
import numpy as np


@dataclass
class WrappedLoopEdge:
    pts: np.ndarray
    axis: np.ndarray
    origin: np.ndarray
    radius: float
    u: np.ndarray
    v: np.ndarray
    convex: bool
    patches: tuple

    kind = "wrapped"

    @property
    def centroid(self):
        return self.pts.mean(axis=0)

    @property
    def perimeter(self):
        return float(np.linalg.norm(np.roll(self.pts, -1, axis=0)-self.pts, axis=1).sum())

    @property
    def n(self):
        radial = self.centroid-self.origin
        radial -= np.dot(radial, self.axis)*self.axis
        return radial/max(np.linalg.norm(radial), 1e-12)

    def polyline(self, n=0):
        return np.vstack((self.pts, self.pts[:1]))

    def ref(self):
        return ("wrapped", tuple(map(float, self.centroid)), tuple(map(float, self.axis)),
                self.perimeter, bool(self.convex))

    def matches(self, ref, reach=None):
        tol = 1e-3*max(1., self.perimeter)
        return (ref[0] == self.kind and self.convex == bool(ref[4])
                and abs(float(self.axis @ np.asarray(ref[2]))) > .999
                and np.linalg.norm(self.centroid-np.asarray(ref[1])) < (tol if reach is None else reach)
                and (abs(self.perimeter-ref[3]) < tol if reach is None else .4 < self.perimeter/max(ref[3], 1e-9) < 2.5))

    def same_as(self, other):
        return getattr(other, "kind", "") == self.kind and self.matches(other.ref())


def cylindrical_contours(v, f, tm):
    """Find sharp closed boundaries of smooth patches, retaining only cylinder-wrapped ones."""
    from omacad.model.faces import PlanarFace

    parents = np.arange(len(f))
    def root(a):
        while parents[a] != a:
            parents[a] = parents[parents[a]]
            a = parents[a]
        return int(a)

    adj, angles = tm.face_adjacency, tm.face_adjacency_angles
    for (a, b), angle in zip(adj, angles):
        if angle < math.radians(25):
            parents[root(a)] = root(b)
    labels = np.array([root(i) for i in range(len(f))])
    parts, boundaries = defaultdict(list), defaultdict(list)
    for i, label in enumerate(labels):
        parts[int(label)].append(i)
    for i, ((a, b), edge) in enumerate(zip(adj, tm.face_adjacency_edges)):
        ra, rb = int(labels[a]), int(labels[b])
        if ra != rb:
            boundaries[tuple(sorted((ra, rb)))].append((edge, int(a), int(b), bool(tm.face_adjacency_convex[i])))

    candidates = []
    for pair, segments in boundaries.items():
        ids = np.unique([entry[0] for entry in segments])
        points = v[ids]
        if len(points) < 8:
            continue
        singular = np.linalg.svd(points-points.mean(axis=0), compute_uv=False)
        if singular[-1]/math.sqrt(len(points)) < .001:  # planar outlines already have edge types
            continue
        if len({flag for _, _, _, flag in segments}) != 1:
            continue
        degree = defaultdict(int)
        for edge, *_ in segments:
            for point in edge:
                degree[int(point)] += 1
        if any(n != 2 for n in degree.values()):
            continue
        candidates.append((pair, segments))
    if not candidates:
        return []

    # A broad cylindrical patch supplies a stable axis even if a small deboss floor
    # has too little angular coverage to determine its axis independently.
    frames = []
    for ids in parts.values():
        if len(ids) < 8:
            continue
        normals = tm.face_normals[ids]
        if np.ptp(normals, axis=0).max() < .15:
            continue
        _, singular, vh = np.linalg.svd(normals, full_matrices=False)
        if singular[-1]/max(singular[0], 1e-12) > .01:
            continue
        axis = vh[-1].copy()
        if axis[np.argmax(abs(axis))] < 0:
            axis = -axis
        u = np.cross(axis, [1., 0., 0.] if abs(axis[0]) < .9 else [0., 1., 0.])
        u /= np.linalg.norm(u)
        vv = np.cross(axis, u)
        points = v[np.unique(f[ids])]
        center = points.mean(axis=0)
        xy = np.column_stack(((points-center) @ u, (points-center) @ vv))
        a = np.column_stack((2*xy, np.ones(len(points))))
        sol = np.linalg.lstsq(a, np.einsum("ij,ij->i", xy, xy), rcond=None)[0]
        r2 = sol[2]+np.dot(sol[:2], sol[:2])
        if r2 <= 0:
            continue
        radius = math.sqrt(r2)
        if np.max(abs(np.linalg.norm(xy-sol[:2], axis=1)-radius)) > max(.001, radius*.001):
            continue
        frames.append((axis, center+sol[0]*u+sol[1]*vv, u, vv))

    patch_cache = {}
    def patch(label):
        if label not in patch_cache:
            ids = parts[label]
            normal = tm.face_normals[ids[0]].copy()
            patch_cache[label] = PlanarFace("", -label-1, normal,
                v[f[ids[0], 0]].copy(), float(tm.area_faces[ids].sum()), v[f[ids]].copy())
        return patch_cache[label]

    result = []
    for pair, segments in candidates:
        match = None
        for axis, origin, u, vv in frames:
            for label in pair:
                ids = parts[label]
                pts = v[np.unique(f[ids])]
                delta = pts-origin
                radial = delta-np.outer(delta @ axis, axis)
                lengths = np.linalg.norm(radial, axis=1)
                radius = float(np.median(lengths))
                if radius <= .01 or np.ptp(lengths) > max(.002, radius*.001):
                    continue
                centers = v[f[ids]].mean(axis=1)-origin
                outward = centers-np.outer(centers @ axis, axis)
                if np.einsum("ij,ij->i", outward, tm.face_normals[ids]).mean() <= 0:
                    continue  # internal cylinders require opposite radial section orientation
                match = (axis, origin, radius, u, vv, label)
                break
            if match:
                break
        if match is None:
            continue
        axis, origin, radius, u, vv, label = match
        following = {}
        for edge, a, b, _ in segments:
            tri = f[a if labels[a] == label else b]
            start, end = map(int, edge)
            if tri[(list(tri).index(start)+1) % 3] != end:
                start, end = end, start
            following[start] = end
        while following:
            start = next(iter(following))
            chain, current = [], start
            while current in following:
                chain.append(current)
                current = following.pop(current)
            if current == start and len(chain) >= 8:
                result.append(WrappedLoopEdge(v[chain].copy(), axis.copy(), origin.copy(),
                    radius, u.copy(), vv.copy(), segments[0][3], tuple(patch(r) for r in pair)))
    return result


def wrapped_round_tool(edge, size, kind):
    """Unroll a cylindrical rim, round its flat outline, then wrap the tool back."""
    from omacad.model.faces import LoopEdge
    from omacad.model.kernel import CadKernel

    delta = edge.pts-edge.origin
    theta = np.unwrap(np.arctan2(delta @ edge.v, delta @ edge.u))
    if abs(theta[-1]-theta[0]) > math.pi:
        raise ValueError("A wrapped rounding contour must not encircle the entire cylinder.")
    points = np.column_stack((theta*edge.radius, delta @ edge.axis, np.zeros(len(delta))))
    flat = LoopEdge(points, np.array([0., 0., 1.]), edge.convex)
    tool = CadKernel.loop_round_tool(flat, size, kind)
    def warp(points):
        angle = points[:, 0]/edge.radius
        radial = np.cos(angle)[:, None]*edge.u + np.sin(angle)[:, None]*edge.v
        return edge.origin + points[:, 1, None]*edge.axis + (edge.radius+points[:, 2, None])*radial
    # Boolean union of the flat bands can merge collinear segments into long
    # triangles. Subdivide again before bending, otherwise their chords cut
    # across the cylinder instead of following its surface.
    from omacad.model import quality
    spacing = max(.05, min(float(size), edge.radius*2*math.pi/quality.circle_segments()))
    result = tool.refine_to_length(spacing).warp_batch(warp)
    if result.is_empty() or result.status() != m3d.Error.NoError:
        raise ValueError("Could not build the wrapped rounding at this radius.")
    return result
