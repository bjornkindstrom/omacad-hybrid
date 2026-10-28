"""Honeycomb: cuts a lattice of cells (hexagons, circles, squares, diamonds or triangles) into picked flat and
cylindrical faces of one body. The cells keep a fixed wall between them and a margin to the face's edges (and to
holes already in the face). Depth is either a number or Through, which goes on to the air behind each cell, so a
box wall is pierced without touching the wall opposite it."""

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import manifold3d as m3d
from shapely import affinity, segmentize
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from omacad.model.features.base import Feature, region_cross_section
from omacad.model.features.offset_face import _frame, cylinder_face_ref, find_plane_face

SHAPES = ("hexagon", "circle", "square", "diamond", "triangle")
AIR = 0.05          # the tool starts this far out in the air: never a face coinciding with the body's
OVERSHOOT = 0.05    # and a Through cell ends this far past the far side
FULL_GAP = math.radians(22.5)   # a cylinder whose widest angular gap is smaller than this goes all the way round


def _templates(shape: str, size: float, wall: float):
    """(cell outlines centred on 0, lattice points as (x, y, template) generator data) before rotation.
    `size` is the width of a cell across its flats (the diameter for a circle)."""
    p = size + wall
    if shape in ("hexagon", "circle"):
        cell = (Polygon([(size / math.sqrt(3) * math.cos(math.radians(90 + 60 * k)),
                          size / math.sqrt(3) * math.sin(math.radians(90 + 60 * k))) for k in range(6)])
                if shape == "hexagon" else Point(0.0, 0.0).buffer(size / 2.0, quad_segs=8))
        return [cell], ((p, 0.0), (p / 2.0, p * math.sqrt(3) / 2.0)), [(0.0, 0.0, 0)], (p, p * math.sqrt(3))
    if shape in ("square", "diamond"):
        h = size / 2.0
        return [box(-h, -h, h, h)], ((p, 0.0), (0.0, p)), [(0.0, 0.0, 0)], (p, p)
    # triangle: up and down cells of a triangular tiling, each shrunk wall/2 from its tile
    rho, rho_t = size / 2.0, size / 2.0 + wall / 2.0
    up = Polygon([(2 * rho * math.cos(math.radians(a)), 2 * rho * math.sin(math.radians(a))) for a in (90, 210, 330)])
    s, hgt = 2.0 * math.sqrt(3) * rho_t, 3.0 * rho_t
    down = affinity.rotate(up, 180.0, origin=(0, 0))
    # basis: along the row, and to the next row (half a tile over); the down cell sits half a tile on, one third up
    return [up, down], ((s, 0.0), (s / 2.0, hgt)), [(0.0, 0.0, 0), (s / 2.0, rho_t, 1)], (s, 2.0 * hgt)


def lattice(shape: str, size: float, wall: float, angle: float, bounds, anchor, period: Optional[float] = None):
    """Cells (shapely polygons) covering `bounds` with one cell centred on `anchor`. With `period` (the length of a
    cylinder's circumference) the lattice is fitted to repeat exactly along x, and only one turn is made."""
    templates, (a1, a2), motif, (px, py) = _templates(shape, size, wall)
    a1, a2 = np.array(a1), np.array(a2)
    ax, ay = float(anchor[0]), float(anchor[1])
    stretch = 1.0
    if period is not None:
        angle = 90.0 * round(angle / 90.0)               # a turned lattice cannot close round a cylinder
        step = px * math.sqrt(2) if shape == "diamond" else px if round(angle / 90.0) % 2 == 0 else py
        stretch = period / (max(1, int(period / step + 1e-9)) * step)   # whole cells round; walls only widen
    if shape == "diamond":
        angle += 45.0
    rad = math.radians(angle)
    rot = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
    minx, miny, maxx, maxy = bounds
    reach = math.hypot(max(maxx - ax, ax - minx), max(maxy - ay, ay - miny)) + 2.0 * (size + wall)
    if period is not None:
        reach = max(reach, period)
    det = abs(a1[0] * a2[1] - a1[1] * a2[0])
    k = int(reach * max(np.linalg.norm(a1), np.linalg.norm(a2)) / det) + 2
    ii, jj = np.meshgrid(np.arange(-k, k + 1), np.arange(-k, k + 1))
    base = ii.reshape(-1, 1) * a1 + jj.reshape(-1, 1) * a2
    shaped = [affinity.rotate(t, angle, origin=(0, 0)) for t in templates]
    cells = []
    pad = size + wall
    for mx, my, ti in motif:
        pts = (base + (mx, my)) @ rot.T
        pts[:, 0] = pts[:, 0] * stretch + ax
        pts[:, 1] += ay
        if period is not None:
            keep = (pts[:, 0] >= ax - period / 2.0 - 1e-6) & (pts[:, 0] < ax + period / 2.0 - 1e-6)
        else:
            keep = (pts[:, 0] > minx - pad) & (pts[:, 0] < maxx + pad)
        keep &= (pts[:, 1] > miny - pad) & (pts[:, 1] < maxy + pad)
        cells += [affinity.translate(shaped[ti], float(x), float(y)) for x, y in pts[keep]]
    return cells


def fit_cells(cells, room, partial: bool, min_share: float = 0.25):
    """The cells inside `room`; with `partial`, cells cut by its edge too (pieces under min_share are dropped)."""
    from shapely.prepared import prep
    inside = prep(room)
    out = []
    for c in cells:
        if inside.contains(c):
            out.append(c)
        elif partial and inside.intersects(c):
            piece = c.intersection(room)
            if piece.area >= min_share * c.area:
                out.append(piece)
    return out


def best_fit(params, room, anchor, period=None):
    """The cells of the lattice placement that fits the most of them in `room`: centred on a cell, or shifted half
    a step along and/or across (a wall that takes two rows when centred between them). Ties keep the centred one."""
    half = (params["size"] + params["wall"]) / 2.0
    best = []
    for dx, dy in ((0.0, 0.0), (0.0, half), (half, 0.0), (half, half)):
        cells = fit_cells(lattice(params["shape"], params["size"], params["wall"], params["angle"], room.bounds,
                                  (anchor[0] + dx, anchor[1] + dy), period), room, params["partial"])
        if len(cells) > len(best):
            best = cells
    return best


class _Rays:
    """Ray casts against one body: the distance to the next surface along a direction."""

    def __init__(self, manifold):
        mesh = manifold.to_mesh()
        v = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
        t = v[np.asarray(mesh.tri_verts, dtype=np.int64)]
        self.v0, self.e1, self.e2 = t[:, 0], t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
        self.lo, self.hi = t.min(axis=1), t.max(axis=1)

    def hit(self, o, d) -> Optional[Tuple[float, bool]]:
        """(distance to the nearest surface, whether the ray enters the material there) or None."""
        o, d = np.asarray(o, dtype=float), np.asarray(d, dtype=float)
        # only triangles whose box the ray can reach (cheap prefilter on the two axes across the ray)
        far = o + d * 1e6
        lo, hi = np.minimum(o, far) - 1e-6, np.maximum(o, far) + 1e-6
        near = np.all((self.hi >= lo) & (self.lo <= hi), axis=1)
        v0, e1, e2 = self.v0[near], self.e1[near], self.e2[near]
        if not len(v0):
            return None
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
        k = int(np.argmin(np.where(hit, t, np.inf)))
        return float(t[k]), bool(det[k] > 0.0)      # det = -d . (e1 x e2): positive against an outward face


def _depths(points, inward, rays: _Rays, depth: Optional[float]) -> List[float]:
    """How deep each cell goes: `depth`, or (Through) to the far side of the material behind it."""
    if depth is not None:
        return [float(depth)] * len(points)
    out = []
    for p, d in zip(points, inward):
        # from the air in front (a faceted cylinder lies a hair inside its true radius): in, then out again
        d = np.asarray(d, dtype=float)
        start = np.asarray(p, dtype=float) - AIR * d
        first = rays.hit(start, d)
        if first is not None and not first[1]:
            # already in the material (a face that bulges past the picked surface): only on to where it ends,
            # never across the hollow behind it into the wall opposite
            out.append(first[0] - AIR + OVERSHOOT)
            continue
        t_in = first[0] if first is not None else None
        second = rays.hit(start + (t_in + 1e-5) * d, d) if t_in is not None else None
        out.append(t_in + 1e-5 + second[0] - AIR + OVERSHOOT if second is not None else 0.0)
    return out


def _grouped(cells, depths):
    groups: Dict[float, list] = {}
    for c, d in zip(cells, depths):
        if d > 1e-4:
            groups.setdefault(round(d, 3), []).append(c)
    return groups


def _plane_frame(normal, origin) -> np.ndarray:
    """Face frame with x level (along the world floor) where possible, so rows run horizontally on a wall."""
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    u = np.cross([0.0, 0.0, 1.0], n) if abs(n[2]) < 0.99 else np.array([1.0, 0.0, 0.0])
    u = u / np.linalg.norm(u)
    M = np.eye(4)
    M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = u, np.cross(n, u), n, np.asarray(origin, dtype=float)
    return M


def plane_tool(manifold, ref, params, rays: _Rays) -> Tuple[Optional[m3d.Manifold], int]:
    face = find_plane_face(manifold, ref)
    if face is None:
        return None, 0
    M = _plane_frame(face.normal, face.origin)
    inv = np.linalg.inv(M)
    pts = np.asarray(face.tris, dtype=float).reshape(-1, 3)
    local = pts @ inv[:3, :3].T + inv[:3, 3]
    region = unary_union([Polygon(local[i:i + 3, :2]) for i in range(0, len(local), 3)
                          if Polygon(local[i:i + 3, :2]).area > 1e-12]).buffer(1e-6).buffer(-1e-6)
    room = region.buffer(-params["margin"], join_style=2) if params["margin"] > 0 else region
    if room.is_empty:
        return None, 0
    minx, miny, maxx, maxy = room.bounds
    cells = best_fit(params, room, ((minx + maxx) / 2.0, (miny + maxy) / 2.0))
    if not cells:
        return None, 0
    centres = [(M @ np.array([c.centroid.x, c.centroid.y, 0.0, 1.0]))[:3] for c in cells]
    n = M[:3, 2]
    depths = _depths(centres, [-n] * len(cells), rays, None if params["through"] else params["depth"])
    tools = []
    for d, group in _grouped(cells, depths).items():
        cs = region_cross_section(unary_union(group))
        tools.append(m3d.Manifold.extrude(cs, d + AIR).translate((0.0, 0.0, -d)).transform(M[:3, :]))
    return (m3d.Manifold.compose(tools) if tools else None), len(cells)


def _cylinder_extent(manifold, M_inv, r: float, length: float, internal: bool):
    """(angles of the surface's corners, z range) of the cylindrical surface in its local frame."""
    mesh = manifold.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3] @ M_inv[:3, :3].T + M_inv[:3, 3]
    t = np.asarray(mesh.tri_verts, dtype=np.int64)
    tol = 0.02 * r + 1e-3
    rad = np.hypot(v[:, 0], v[:, 1])
    on = (np.abs(rad - r) < tol) & (v[:, 2] > -tol) & (v[:, 2] < length + tol)
    tri = t[on[t].all(axis=1)]
    if not len(tri):
        return None
    a, b, c = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    nrm = np.cross(b - a, c - a)
    mid = (a + b + c) / 3.0
    radial = mid[:, :2] / np.maximum(np.linalg.norm(mid[:, :2], axis=1), 1e-12)[:, None]
    facing = np.einsum("ij,ij->i", nrm[:, :2], radial) / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
    tri = tri[(facing < -0.8) if internal else (facing > 0.8)]
    if not len(tri):
        return None
    vs = np.unique(tri.ravel())
    theta = np.sort(np.mod(np.arctan2(v[vs, 1], v[vs, 0]), 2 * math.pi))
    return theta, (float(v[vs, 2].min()), float(v[vs, 2].max()))


def _refitted(manifold, ref):
    """The saved cylinder fitted again to the body's own wall. A pick could tilt the axis half a degree, and then
    the cells on one side start inside the wall and miss its inner face at their edges."""
    from types import SimpleNamespace
    from omacad.model.faces_hit_tests import detect_cylinder_surface
    mesh = manifold.to_mesh()
    tri = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3][np.asarray(mesh.tri_verts, dtype=np.int64)]
    M = _frame(ref["origin"], ref["axis"])
    M_inv = np.linalg.inv(M)
    mid = tri.mean(axis=1) @ M_inv[:3, :3].T + M_inv[:3, 3]
    r, length = float(ref["radius"]), float(ref["length"])
    # a triangle on the wall, away from the rounds at its ends
    off = np.abs(np.hypot(mid[:, 0], mid[:, 1]) - r) + np.maximum(np.abs(mid[:, 2] - length / 2.0) - length / 4.0, 0)
    cyl = detect_cylinder_surface(SimpleNamespace(vertices=tri.reshape(-1, 3)), int(off.argmin()))
    if (cyl is None or bool(cyl["is_internal"]) != bool(ref.get("internal", False))
            or abs(float(np.dot(cyl["axis"], M[:3, 2]))) < math.cos(math.radians(5.0))
            or abs(cyl["radius"] - r) > 0.05 * r):
        return ref
    return cylinder_face_ref(cyl)


def cylinder_tool(manifold, ref, params, rays: _Rays) -> Tuple[Optional[m3d.Manifold], int]:
    ref = _refitted(manifold, ref)
    r, internal = float(ref["radius"]), bool(ref.get("internal", False))
    M = _frame(ref["origin"], ref["axis"])
    M_inv = np.linalg.inv(M)
    ext = _cylinder_extent(manifold, M_inv, r, float(ref["length"]), internal)
    if ext is None:
        return None, 0
    theta, (z0, z1) = ext
    gaps = np.diff(np.append(theta, theta[0] + 2 * math.pi))
    g = int(gaps.argmax())
    full = gaps[g] < FULL_GAP
    margin = params["margin"]
    if full:
        circ = 2 * math.pi * r
        room = box(-circ, z0 + margin, 2 * circ, z1 - margin)
        anchor, period = (circ / 2.0, (z0 + z1) / 2.0), circ
    else:
        start = float(theta[(g + 1) % len(theta)])
        s0, s1 = r * start, r * (start + 2 * math.pi - gaps[g])
        room = box(s0 + margin, z0 + margin, s1 - margin, z1 - margin)
        anchor, period = ((s0 + s1) / 2.0, (z0 + z1) / 2.0), None
    if room.is_empty or room.area < 1e-9:
        return None, 0
    cells = best_fit(params, room, anchor, period)
    if not cells:
        return None, 0
    out = -1.0 if internal else 1.0       # from the surface into the air
    centres, inward = [], []
    for c in cells:
        th = c.centroid.x / r
        radial = M[:3, :3] @ np.array([math.cos(th), math.sin(th), 0.0])
        centres.append((M @ np.array([r * math.cos(th), r * math.sin(th), c.centroid.y, 1.0]))[:3])
        inward.append(-out * radial)
    depths = _depths(centres, inward, rays, None if params["through"] else params["depth"])
    step = max(0.2, r * math.radians(3.0))
    tools = []
    for d, group in _grouped(cells, depths).items():
        r_in, r_out = (r - d, r + AIR) if not internal else (r - AIR, r + d)
        r_in = max(r_in, 0.01)
        cs = region_cross_section(segmentize(unary_union(group), max_segment_length=step))
        prism = m3d.Manifold.extrude(cs, height=1.0, n_divisions=2).refine_to_length(step)

        def warp(pts, r_in=r_in, r_out=r_out):
            th = pts[:, 0] / r
            rad = r_in + pts[:, 2] * (r_out - r_in)
            return np.column_stack([rad * np.cos(th), rad * np.sin(th), pts[:, 1]])

        tools.append(prism.warp_batch(warp).transform(M[:3, :]))
    return (m3d.Manifold.compose(tools) if tools else None), len(cells)


class HoneycombFeature(Feature):
    """Cuts a lattice of cells into the chosen faces of one body."""

    PARAMS = ("shape", "size", "wall", "margin", "depth", "through", "angle", "partial")

    def __init__(self, feature_id: str, name: str, target_body_id: str, faces=None, shape: str = "hexagon",
                 size: float = 6.0, wall: float = 1.5, margin: float = 3.0, depth: float = 1.0, through: bool = True,
                 angle: float = 0.0, partial: bool = False):
        super().__init__(feature_id, "honeycomb", name)
        self.target_body_id = target_body_id
        self.faces = list(faces or [])
        self.shape = shape if shape in SHAPES else "hexagon"
        self.size, self.wall, self.margin = float(size), float(wall), float(margin)
        self.depth, self.through = float(depth), bool(through)
        self.angle, self.partial = float(angle), bool(partial)
        self.cells = 0
        self.skipped = 0

    def params(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.PARAMS}

    @staticmethod
    def compute(manifold, faces, params) -> Tuple[m3d.Manifold, int, int]:
        """(new manifold, number of cells, faces that got no cells)."""
        if params["size"] <= 0.05 or params["wall"] < 0 or (not params["through"] and params["depth"] <= 1e-4):
            return manifold, 0, len(faces)
        rays = _Rays(manifold)
        tools, cells, skipped = [], 0, 0
        for ref in faces:
            make = plane_tool if ref.get("kind") == "plane" else cylinder_tool if ref.get("kind") == "cylinder" else None
            try:
                tool, n = make(manifold, ref, params, rays) if make else (None, 0)
            except Exception as e:     # one odd face must not break the history
                print(f"HoneycombFeature: {e}")
                tool, n = None, 0
            if tool is None:
                skipped += 1
            else:
                tools.append(tool)
                cells += n
        if not tools:
            return manifold, 0, skipped
        return manifold - m3d.Manifold.batch_boolean(tools, m3d.OpType.Add), cells, skipped

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        # A picked face can move when an upstream feature is edited (box height is the common
        # case). If its old plane no longer exists, attach it to the nearest parallel planar face.
        # Keep the saved reference intact so later recomputes can track the same moving face.
        faces = self.faces
        if any(ref.get("kind") == "plane" and find_plane_face(target.manifold, ref) is None for ref in self.faces):
            from omacad.model.faces import compute_planar_faces
            planar = compute_planar_faces(target.manifold, self.target_body_id)
            faces = []
            for ref in self.faces:
                if ref.get("kind") != "plane" or find_plane_face(target.manifold, ref) is not None:
                    faces.append(ref)
                    continue
                n, origin = np.asarray(ref["normal"], dtype=float), np.asarray(ref["origin"], dtype=float)
                candidates = [f for f in planar if float(f.normal @ n) > 0.999]
                if candidates:
                    nearest = min(candidates, key=lambda f: abs(float(f.normal @ (origin - f.origin))))
                    faces.append({**ref, "origin": [float(x) for x in nearest.origin]})
                else:
                    faces.append(ref)
        target.manifold, self.cells, self.skipped = self.compute(target.manifold, faces, self.params())
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "target_body_id": self.target_body_id, "faces": self.faces,
                **self.params()}
