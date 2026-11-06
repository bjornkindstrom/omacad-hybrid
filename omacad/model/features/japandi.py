"""Japandi: half-round or rectangular ribs along whole outer round faces, straight or twisted. The wall may be a plain
cylinder or curved like a vase. The number of ribs stays the same all the way along, so they narrow with the wall."""

import math
from typing import Any, Dict, List, Tuple

import numpy as np
import manifold3d as m3d

from omacad.model.features.base import Feature, region_cross_section
from omacad.model.features.honeycomb import FULL_GAP, _cylinder_extent, _refitted
from omacad.model.features.offset_face import _frame
from omacad.model.features.revolved_surface import END_OVERSHOOT, RevolvedSurface, revolved_surface
from omacad.model.features.curved_surface import curved_wall, ensure_positive_volume
from omacad.model.kernel import CadKernel
from shapely.geometry import Polygon

SHAPES = ("half-round", "rectangular")
DIRECTIONS = ("outward", "inward")
MAX_FACETS = 2_000_000      # triangles in a tool: more would take minutes and be finer than a printer can show
# How far straight pieces may leave the true curve, in mm. Coarser than the rest of the model on purpose: a printer shows no
# less, and the face analysis after each step grows quickly with the triangles (a real pot took 20 s at a tenth of these).
SAG = 0.01                  # round the wall: under CLEAR, or a plain stretch between two grooves would be cut into
ROUND_SAG = 0.02            # across a half-round rib
PROFILE_SAG = 0.05          # along the wall's profile
TWIST_SAG = 0.05            # along a twisted rib
CLEAR = 0.02                # mm a tool's plain parts stay off the wall, so they never share its surface
BURIED = 0.05               # mm the back of an outward tool lies inside the wall
AIR = 1.0                   # mm the back of an inward tool stands off the wall
FREE_END = 1e-3             # mm outward ribs stop short of a free end, so they never share its plane
MAX_RINGS = 48              # rings along a wall, unless a twist needs more: a faceted wall's own rings are mostly noise
WALL_STEP = 1e-3            # share of a rib's period a rectangular side leans, as the tool's rings need distinct angles
SMALLEST_RADIUS = 0.15      # share of the largest radius where the ribs stop: below it they would run together


def rib_period(params: Dict[str, Any]) -> float:
    """mm from one rib to the next, as asked for."""
    width = 2.0 * params["radius"] if params["shape"] == "half-round" else params["width"]
    return width + params["spacing"]


def rib_count(radius: float, params: Dict[str, Any]) -> int:
    """Whole ribs round the largest circumference, as close to the asked spacing as they fit."""
    return max(3, int(round(2.0 * math.pi * radius / rib_period(params))))


def _flat_steps(width: float, radius: float) -> int:
    """Pieces a stretch of the wall this wide needs to follow its circle."""
    return max(1, math.ceil(width / math.sqrt(8.0 * radius * SAG)))


def rib_columns(params: Dict[str, Any], radius: float, ribs: int) -> Tuple[np.ndarray, np.ndarray]:
    """One period of the rib: (place in the period 0..1, height as a share of the rib's height)."""
    period = 2.0 * math.pi * radius / ribs
    scale = period / rib_period(params)     # the whole ribs that fit are a little wider or narrower than asked
    gap = params["spacing"] * scale
    if params["shape"] == "half-round":
        rib = 2.0 * params["radius"] * scale
        turn = math.acos(max(0.0, 1.0 - ROUND_SAG / params["radius"]))
        pieces = 2 * int(np.clip(math.ceil(math.pi / max(4.0 * turn, 1e-6)), 4, 24))     # even: one point on the crest
        angle = np.linspace(-math.pi / 2.0, math.pi / 2.0, pieces + 1)
        places, heights = (np.sin(angle) + 1.0) * rib / period / 2.0, np.cos(angle)
        heights[[0, -1]] = 0.0
        if gap > 0:
            rest = np.linspace(rib / period, 1.0, _flat_steps(gap, radius) + 1)[1:-1]
            return np.concatenate((places, rest)), np.concatenate((heights, np.zeros(len(rest))))
        return places[:-1], heights[:-1]
    rib = params["width"] * scale
    share = rib / period
    top = np.linspace(0.0, share, _flat_steps(rib, radius) + 1)
    foot = np.linspace(share + WALL_STEP, 1.0 - WALL_STEP, _flat_steps(gap, radius) + 1)
    return np.concatenate((top, foot)), np.concatenate((np.ones(len(top)), np.zeros(len(foot))))


def _wall(manifold: m3d.Manifold, ref: Dict[str, Any], M: np.ndarray) -> RevolvedSurface:
    """The wall under the face, reaching END_OVERSHOOT past its ends. Raises ValueError for a face that can't take ribs."""
    surface = revolved_surface(manifold, M, ref)
    if surface is not None:
        return surface
    radius = float(ref["radius"])
    extent = _cylinder_extent(manifold, np.linalg.inv(M), radius, float(ref["length"]), False)
    if extent is None:
        raise ValueError("The round face was not found on the body.")
    theta, (z0, z1) = extent
    if np.diff(np.append(theta, theta[0] + 2.0 * math.pi)).max() >= FULL_GAP:
        raise ValueError("Japandi needs a face that goes all the way round.")
    return RevolvedSurface(np.array([[radius, z0 - END_OVERSHOOT], [radius, z1 + END_OVERSHOOT]]), False)


def _stretch(surface: RevolvedSurface, margin: float, inward: bool) -> Tuple[float, float]:
    """(start, end) of the ribs along the wall's profile."""
    free = -END_OVERSHOOT if inward else FREE_END     # a cut runs out past a free end, a rib stops just short of it
    low = surface.s[0] + END_OVERSHOOT + (margin if margin > 0 else free)
    high = surface.s[-1] - END_OVERSHOOT - (margin if margin > 0 else free)
    usable = surface.usable(SMALLEST_RADIUS * surface.R)
    if usable is not None:
        low, high = max(low, usable[0]), min(high, usable[1])
    if high - low <= 1e-3:
        raise ValueError("The margin leaves no room for ribs.")
    return float(low), float(high)


def _profile_steps(surface: RevolvedSurface, low: float, high: float) -> np.ndarray:
    """Places along the wall between low and high where it needs a ring: the bends that show, not every ring it was read at."""
    s = np.concatenate(([low], surface.s[(surface.s > low) & (surface.s < high)], [high]))
    points = np.column_stack((np.interp(s, surface.s, surface.r), np.interp(s, surface.s, surface.z)))
    keep, stack = {0, len(s) - 1}, [(0, len(s) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        chord = points[b] - points[a]
        off = points[a + 1:b] - points[a]
        apart = np.abs(chord[0] * off[:, 1] - chord[1] * off[:, 0]) / max(float(np.linalg.norm(chord)), 1e-12)
        worst = int(np.argmax(apart))
        if apart[worst] > PROFILE_SAG:
            keep.add(a + 1 + worst)
            stack += [(a, a + 1 + worst), (a + 1 + worst, b)]
    return s[sorted(keep)]


def _tube(radii, zs, nr, nz, angles, near, far) -> m3d.Manifold:
    """The closed solid between the heights `near` and `far` off the wall (rows along the wall, columns round it)."""
    def layer(heights):
        radius = np.maximum(radii[:, None] + heights * nr[:, None], 1e-2)
        return np.stack((radius * np.cos(angles), radius * np.sin(angles), zs[:, None] + heights * nz[:, None]), axis=-1)

    rows, cols = angles.shape
    verts = np.concatenate((layer(near).reshape(-1, 3), layer(far).reshape(-1, 3)))
    i, j = np.meshgrid(np.arange(rows - 1), np.arange(cols), indexing="ij")
    i, j = i.ravel(), j.ravel()
    k = (j + 1) % cols
    at = lambda sheet, row, col: sheet * rows * cols + row * cols + col
    a, b, c, d = at(1, i, j), at(1, i, k), at(1, i + 1, k), at(1, i + 1, j)
    e, f, g, h = at(0, i, j), at(0, i, k), at(0, i + 1, k), at(0, i + 1, j)
    col = np.arange(cols)
    nxt = (col + 1) % cols
    low = [at(0, 0, col), at(0, 0, nxt), at(1, 0, nxt), at(1, 0, col)]
    top = rows - 1
    high = [at(0, top, nxt), at(0, top, col), at(1, top, col), at(1, top, nxt)]
    quads = [np.column_stack(q) for q in ((a, b, c, d), (f, e, h, g), low, high)]
    quads = np.concatenate(quads)
    tris = np.concatenate((quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]))
    solid = m3d.Manifold(m3d.Mesh64(vert_properties=verts, tri_verts=np.ascontiguousarray(tris, dtype=np.uint64)))
    if solid.status() != m3d.Error.NoError or solid.is_empty():
        raise ValueError("These values give no usable ribs on this face.")
    return solid


def surface_japandi_tool(manifold: m3d.Manifold, ref: Dict[str, Any], params: Dict[str, Any]) -> Tuple[m3d.Manifold, int]:
    wall = curved_wall(manifold, ref)
    if wall is None or wall.L < 1e-3 or wall.height < 1e-3:
        raise ValueError("The curved surface could not be analyzed.")
    half_round = params["shape"] == "half-round"
    inward = params["direction"] == "inward"
    if params["spacing"] < 0 or (half_round and params["radius"] <= 0):
        raise ValueError("The radius must be above zero, and the spacing not below it.")
    if not half_round and (params["width"] <= 0 or params["depth"] <= 0 or params["spacing"] <= 0):
        raise ValueError("Width, depth and spacing must all be above zero.")
    height = params["radius"] if half_round else params["depth"]
    margin = params["margin"]
    free = -END_OVERSHOOT if inward else FREE_END
    bottom = wall.z0 + (margin if margin > 0 else free)
    top = wall.z1 - (margin if margin > 0 else free)
    if top - bottom <= 1e-3:
        raise ValueError("The margin leaves no room for ribs.")
    h_span = top - bottom

    period = rib_period(params)
    ribs = max(1, int(round(wall.L / period)))
    equiv_R = wall.L / (2.0 * math.pi)
    places, shares = rib_columns(params, equiv_R, ribs)
    step_s = wall.L / ribs

    s_cols = (np.arange(ribs)[:, None] + places[None, :]).ravel() * step_s
    relief_cols = np.tile(shares * height, ribs)
    has_rib = relief_cols > 0

    if inward:
        t_bottom = np.where(has_rib, -relief_cols, CLEAR)
        t_top = np.full_like(t_bottom, AIR)
    else:
        t_bottom = np.full_like(relief_cols, -BURIED)
        t_top = np.where(has_rib, relief_cols, -CLEAR)

    poly_pts = []
    for s_val, t_val in zip(s_cols, t_bottom):
        poly_pts.append((s_val, t_val))
    for s_val, t_val in zip(reversed(s_cols), reversed(t_top)):
        poly_pts.append((s_val, t_val))

    poly = Polygon(poly_pts).buffer(0)
    cs = region_cross_section(poly)
    step = 0.5
    divisions = max(2, int(h_span / 2.0))
    prism = m3d.Manifold.extrude(cs, h_span, n_divisions=divisions).refine_to_length(step)

    twist = math.radians(params["twist"])

    def warp_fn(pts_arr: np.ndarray) -> np.ndarray:
        s_in = pts_arr[:, 0]
        t_in = pts_arr[:, 1]
        z_frac = pts_arr[:, 2] / max(h_span, 1e-6)
        z_in = bottom + pts_arr[:, 2]
        s_eff = s_in + twist * equiv_R * z_frac
        if wall.closed and wall.L > 1e-6:
            s_eff = np.mod(s_eff, wall.L)
        px = np.interp(s_eff, wall.s, wall.coords[:, 0])
        py = np.interp(s_eff, wall.s, wall.coords[:, 1])
        nx = np.interp(s_eff, wall.s, wall.normals[:, 0])
        ny = np.interp(s_eff, wall.s, wall.normals[:, 1])
        return np.column_stack([px + t_in * nx, py + t_in * ny, z_in])

    tool = prism.warp_batch(warp_fn).transform(wall.M[:3, :])
    return ensure_positive_volume(tool), ribs


def japandi_tool(manifold: m3d.Manifold, ref: Dict[str, Any], params: Dict[str, Any]) -> Tuple[m3d.Manifold, int]:
    """(the solid to add or cut away, ribs per turn) for one face. Raises ValueError saying why a face can't take them."""
    if ref.get("kind") == "surface":
        return surface_japandi_tool(manifold, ref, params)
    if ref.get("kind") != "cylinder" or ref.get("internal"):
        raise ValueError("Japandi ribs need an outer round or curved face.")
    half_round = params["shape"] == "half-round"
    inward = params["direction"] == "inward"
    if params["spacing"] < 0 or (half_round and params["radius"] <= 0):
        raise ValueError("The radius must be above zero, and the spacing not below it.")
    if not half_round and (params["width"] <= 0 or params["depth"] <= 0 or params["spacing"] <= 0):
        raise ValueError("Width, depth and spacing must all be above zero.")
    ref = _refitted(manifold, ref)
    M = _frame(ref["origin"], ref["axis"])
    surface = _wall(manifold, ref, M)
    height = params["radius"] if half_round else params["depth"]
    if inward and height >= surface.R:
        raise ValueError(f"A depth of {height:g} mm doesn't fit in a radius of {surface.R:g} mm.")
    low, high = _stretch(surface, params["margin"], inward)

    ribs = rib_count(surface.R, params)
    places, shares = rib_columns(params, surface.R, ribs)
    step = 2.0 * math.pi / ribs
    columns = (np.arange(ribs)[:, None] + places[None, :]).ravel() * step
    shares = np.tile(shares, ribs)

    # steps along the wall: its own profile, and short enough to follow a twisted rib
    twist = math.radians(params["twist"])
    turn = min(step, 2.0 * math.acos(max(0.0, 1.0 - TWIST_SAG / surface.R)))
    pieces = max(1, math.ceil(abs(twist) / turn))
    even = np.linspace(low, high, pieces + 1)
    gap = (high - low) / max(MAX_RINGS, pieces)
    bends = _profile_steps(surface, low, high)
    bends = bends[[np.abs(even - b).min() >= gap / 2.0 for b in bends]]     # a twist's rings serve for the bends beside them
    s = np.unique(np.concatenate((even, bends)))
    s = s[np.concatenate(([True], np.diff(s) >= gap / 2.0))]
    s[-1] = high
    if 4 * len(columns) * len(s) > MAX_FACETS:
        raise ValueError("Ribs this fine are too many for a face this large. Use wider ribs or less twist.")

    radii, zs = np.interp(s, surface.s, surface.r), np.interp(s, surface.s, surface.z)
    nr, nz = np.interp(s, surface.s, surface.nr), np.interp(s, surface.s, surface.nz)
    length = np.maximum(np.hypot(nr, nz), 1e-12)
    nr, nz = nr / length, nz / length
    angles = columns[None, :] + twist * ((s - low) / (high - low))[:, None]
    # a half-round rib keeps its shape as the wall narrows; a rectangular one keeps its depth
    size = (height * radii / surface.R if half_round else np.full(len(s), height))[:, None]
    relief = shares[None, :] * size
    has_rib = shares[None, :] > 0
    if inward:
        near = np.where(has_rib, -relief, CLEAR)
        tool = _tube(radii, zs, nr, nz, angles, near, np.full(near.shape, AIR))
    else:
        far = np.where(has_rib, relief, -CLEAR)
        tool = _tube(radii, zs, nr, nz, angles, np.full(far.shape, -BURIED), far)
    return tool.transform(M[:3, :]), ribs


def apply_japandi(manifold: m3d.Manifold, faces: List[Dict[str, Any]], params: Dict[str, Any]):
    """(new manifold, ribs per turn in all faces, why any face was left out)."""
    tools, ribs, notes = [], 0, []
    for ref in faces:
        try:
            tool, count = japandi_tool(manifold, ref, params)
        except ValueError as e:         # one odd face must not break the history; the panel shows the reason
            notes.append(str(e))
            continue
        tools.append(tool)
        ribs += count
    if not tools:
        return manifold, 0, notes
    together = m3d.Manifold.batch_boolean(tools, m3d.OpType.Add)
    result = manifold - together if params["direction"] == "inward" else manifold + together
    return CadKernel.drop_slivers(result), ribs, notes


class JapandiFeature(Feature):
    """Ribs or grooves along the chosen round faces of one body."""

    PARAMS = ("shape", "direction", "radius", "width", "depth", "spacing", "twist", "margin")

    def __init__(self, feature_id: str, name: str, target_body_id: str, faces=None, shape: str = "half-round",
                 direction: str = "outward", radius: float = 1.5, width: float = 2.0, depth: float = 2.0,
                 spacing: float = 0.0, twist: float = 0.0, margin: float = 0.0):
        super().__init__(feature_id, "japandi", name)
        self.target_body_id = target_body_id
        self.faces = list(faces or [])
        self.shape = shape if shape in SHAPES else SHAPES[0]
        self.direction = direction if direction in DIRECTIONS else DIRECTIONS[0]
        self.radius, self.width, self.depth = float(radius), float(width), float(depth)
        self.spacing, self.twist, self.margin = float(spacing), float(twist), float(margin)
        self.ribs = 0
        self.notes: List[str] = []

    def params(self) -> Dict[str, Any]:
        return {key: getattr(self, key) for key in self.PARAMS}

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        target.manifold, self.ribs, self.notes = apply_japandi(target.manifold, self.faces, self.params())
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
                "suppressed": self.suppressed, "target_body_id": self.target_body_id, "faces": self.faces,
                **self.params()}
