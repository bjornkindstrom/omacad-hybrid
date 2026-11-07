"""Japandi: half-round or rectangular ribs along whole outer round faces, straight, twisted, or bent in one curve or a wave.
The wall may be a plain cylinder or curved like a vase. The number of ribs stays the same all the way along, so they narrow
with the wall."""

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
PATHS = ("straight", "curve", "wave")
HEIGHTS = ("even", "arch")
RIMS = ("none", "straight", "chamfer", "round")
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


def path_shape(params: Dict[str, Any]) -> Tuple[float, float]:
    """(radians the ribs swing to the side at most, radians of the sine over the ribs' whole length)."""
    path = params.get("path", "straight")
    if path == "curve":
        return math.radians(params.get("bend", 0.0)), math.pi
    if path == "wave":
        return math.radians(params.get("bend", 0.0)), 2.0 * math.pi * params.get("waves", 1.0)
    return 0.0, 0.0


def path_turn(params: Dict[str, Any], along: np.ndarray) -> np.ndarray:
    """Radians the ribs stand to the side at each place along them, from 0 at the start to 1 at the end."""
    bend, sweep = path_shape(params)
    return bend * np.sin(sweep * np.asarray(along))


def _path_pieces(params: Dict[str, Any], radius: float) -> int:
    """Steps along the ribs that keep a bent path within TWIST_SAG of its sine on the unrolled wall."""
    bend, sweep = path_shape(params)
    return math.ceil(abs(sweep) * math.sqrt(abs(bend) * radius / (8.0 * TWIST_SAG)))


def _arch(params: Dict[str, Any], height: float, length: float) -> Tuple[float, float, float]:
    """(end share of the height, rise in mm, radius of the arc) of an arched rib; rise 0 when the ribs are even."""
    if params.get("height_profile", "even") != "arch":
        return 1.0, 0.0, 0.0
    end = float(np.clip(params.get("end_height", 20.0) / 100.0, 0.01, 1.0))
    rise = height * (1.0 - end)
    return end, rise, (length * length / 4.0 + rise * rise) / (2.0 * rise) if rise > 1e-9 else 0.0


def height_share(params: Dict[str, Any], height: float, length: float, along: np.ndarray) -> np.ndarray:
    """Share of the rib's height at each place along it (0 at the start, 1 at the end). Arch: seen from the side the top
    of the rib is one circular arc, highest in the middle and `end_height` percent of that at both ends."""
    along = np.asarray(along, dtype=float)
    end, rise, radius = _arch(params, height, length)
    if rise <= 1e-9:
        return np.ones_like(along)
    off_middle = (along - 0.5) * length
    return end + (np.sqrt(np.maximum(radius * radius - off_middle * off_middle, 0.0)) - (radius - rise)) / height


def _arch_pieces(params: Dict[str, Any], height: float, length: float) -> int:
    """Steps along the ribs that keep the arc within PROFILE_SAG."""
    _, rise, radius = _arch(params, height, length)
    return math.ceil(length / math.sqrt(8.0 * radius * PROFILE_SAG)) if rise > 1e-9 else 1


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

    return _strip(layer(near), layer(far))


def _strip(near: np.ndarray, far: np.ndarray, closed: bool = True) -> m3d.Manifold:
    """Watertight band between two sampled sheets, with caps also on an open wall's ends."""
    rows, cols = near.shape[:2]
    verts = np.concatenate((near.reshape(-1, 3), far.reshape(-1, 3)))
    i, j = np.meshgrid(np.arange(rows - 1), np.arange(cols if closed else cols - 1), indexing="ij")
    i, j = i.ravel(), j.ravel()
    k = (j + 1) % cols
    at = lambda sheet, row, col: sheet * rows * cols + row * cols + col
    a, b, c, d = at(1, i, j), at(1, i, k), at(1, i + 1, k), at(1, i + 1, j)
    e, f, g, h = at(0, i, j), at(0, i, k), at(0, i + 1, k), at(0, i + 1, j)
    col = np.arange(cols if closed else cols - 1)
    nxt = (col + 1) % cols
    low = [at(0, 0, col), at(0, 0, nxt), at(1, 0, nxt), at(1, 0, col)]
    top = rows - 1
    high = [at(0, top, nxt), at(0, top, col), at(1, top, col), at(1, top, nxt)]
    quads = [np.column_stack(q) for q in ((a, b, c, d), (f, e, h, g), low, high)]
    if not closed:
        row = np.arange(rows - 1)
        for col, reverse in ((0, False), (cols - 1, True)):
            cap = np.column_stack((at(0, row, col), at(1, row, col),
                                   at(1, row + 1, col), at(0, row + 1, col)))
            quads.append(cap[:, ::-1] if reverse else cap)
    quads = np.concatenate(quads)
    tris = np.concatenate((quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]))
    solid = m3d.Manifold(m3d.Mesh64(vert_properties=verts, tri_verts=np.ascontiguousarray(tris, dtype=np.uint64)))
    if solid.status() != m3d.Error.NoError or solid.is_empty():
        raise ValueError("These values give no usable ribs on this face.")
    return ensure_positive_volume(solid)


def _rim_rows(params):
    """Distance from a free edge toward the ribs and added relief at that distance."""
    margin, depth = float(params["margin"]), float(params.get("rim_depth", 2.0))
    if margin <= 0 or depth <= 0:
        raise ValueError("A rim needs a margin and a rim depth above zero.")
    kind = params.get("rim", "none")
    pieces = max(16, 2 * math.ceil(math.pi * math.sqrt(depth / (8. * PROFILE_SAG)) / 2.))
    u = np.linspace(0., 1., pieces + 1) if kind == "round" else np.array([0., 1.])
    relief = depth * (np.sin(math.pi * u) if kind == "round" else (1. - u if kind == "chamfer" else np.ones_like(u)))
    return u * margin, np.maximum(relief, 0.)


def _rim_columns(params, radius, ribs, end, length, distances, relief, scale=1.):
    """Use the ribs' own columns and endpoint phase so the band meets every crest and valley."""
    places, shares = rib_columns(params, radius, ribs)
    columns = (np.arange(ribs)[:, None] + places).ravel() / ribs
    turn = math.radians(params["twist"]) * end + float(path_turn(params, np.array(end)))
    columns = columns + turn / (2. * math.pi)
    height = params["radius"] if params["shape"] == "half-round" else params["depth"]
    end_relief = np.tile(shares, ribs) * height * scale * float(height_share(params, height, length, np.array(end)))
    u = distances / distances[-1]
    return columns, relief[:, None] + u[:, None] * end_relief[None, :]


def _wall_band(coords, normals, zs, relief, closed):
    """Follow every segment of a ruled wall, including the seam of a closed perimeter."""
    coords, normals = np.asarray(coords), np.asarray(normals)
    if closed and np.linalg.norm(coords[-1] - coords[0]) < 1e-6:
        coords, normals = coords[:-1], normals[:-1]
    normals = normals / np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    near_xy = coords - BURIED * normals
    far_xy = coords[None, :, :] + (relief[:, None] if relief.ndim == 1 else relief)[:, :, None] * normals[None, :, :]
    near = np.empty((len(zs), len(coords), 3))
    near[:, :, :2], near[:, :, 2] = near_xy, np.asarray(zs)[:, None]
    far = near.copy()
    far[:, :, :2] = far_xy
    return _strip(near, far, closed)


def _inner_rims(manifold, M, bottom, top, distances, relief):
    """Optional matching round lip inside a hollow, ruled body. Solid bodies have no inner contour."""
    from shapely.geometry.polygon import orient
    local = manifold.transform(np.linalg.inv(M)[:3, :])
    tools = []
    for edge, sign in ((bottom, 1.), (top, -1.)):
        sample = edge + sign * min(float(distances[-1]) / 2., (top - bottom) / 4.)
        # CrossSection contours use negative signed area for holes.
        for ring in local.slice(sample).to_polygons():
            pts = np.asarray(ring)
            area = np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - pts[:, 1] * np.roll(pts[:, 0], -1))
            if area >= 0:
                continue
            pts = np.asarray(orient(Polygon(pts), sign=1.).exterior.coords)[:-1]
            tangent = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
            normals = np.column_stack((-tangent[:, 1], tangent[:, 0]))
            tools.append(_wall_band(pts, normals, edge + sign * distances, relief, True).transform(M[:3, :]))
    return tools


def japandi_rims(manifold, ref, params):
    """Add continuous end bands independently of the ribs' shape, twist, path or direction."""
    if params.get("rim", "none") == "none":
        return []
    distances, relief = _rim_rows(params)
    tools = []
    follow = (params.get("rim_follow", False) and params["direction"] == "outward"
              and params.get("rim") in ("chamfer", "round"))
    if ref.get("kind") == "surface":
        wall = curved_wall(manifold, ref)
        if wall is None:
            raise ValueError("The curved surface could not be analyzed for the rim.")
        if 2. * distances[-1] >= wall.height:
            raise ValueError("The margin leaves no room for ribs.")
        M, bottom, top = wall.M, wall.z0, wall.z1
        for edge, sign in ((bottom, 1.), (top, -1.)):
            coords, normals, heights = wall.coords, wall.normals, relief
            if follow:
                radius = wall.L / (2. * math.pi)
                ribs = max(1, int(round(wall.L / rib_period(params))))
                columns, heights = _rim_columns(params, radius, ribs, 0. if sign > 0 else 1.,
                                                wall.height - 2. * distances[-1], distances, relief)
                positions = columns * wall.L
                positions = np.mod(positions, wall.L) if wall.closed else np.clip(positions, 0., wall.L)
                if wall.closed:
                    # Resolve bends between rib columns at least as finely as the warped rib prism.
                    order = np.argsort(positions)
                    positions, heights = positions[order], heights[:, order]
                    samples = np.unique(np.concatenate((positions, wall.s[:-1],
                                                        np.linspace(0., wall.L, math.ceil(wall.L / 0.25), endpoint=False))))
                    heights = np.array([np.interp(samples, positions, row, period=wall.L) for row in heights])
                    positions = samples
                coords = np.column_stack([np.interp(positions, wall.s, wall.coords[:, i]) for i in (0, 1)])
                normals = np.column_stack([np.interp(positions, wall.s, wall.normals[:, i]) for i in (0, 1)])
            tools.append(_wall_band(coords, normals, edge + sign * distances,
                                    heights, wall.closed).transform(M[:3, :]))
    else:
        ref = _refitted(manifold, ref)
        M = _frame(ref["origin"], ref["axis"])
        wall = _wall(manifold, ref, M)
        low, high = wall.s[0] + END_OVERSHOOT, wall.s[-1] - END_OVERSHOOT
        bottom, top = np.interp([low, high], wall.s, wall.z)
        count = max(64, int(math.ceil(2. * math.pi / math.sqrt(8. * SAG / wall.R))))
        angles = np.broadcast_to(np.arange(count) * 2. * math.pi / count, (len(distances), count))
        for edge, sign in ((low, 1.), (high, -1.)):
            along = edge + sign * distances
            radii, zs = np.interp(along, wall.s, wall.r), np.interp(along, wall.s, wall.z)
            nr, nz = np.interp(along, wall.s, wall.nr), np.interp(along, wall.s, wall.nz)
            size = np.maximum(np.hypot(nr, nz), 1e-12)
            band_angles = angles
            far = np.broadcast_to(relief[:, None], angles.shape)
            if follow:
                join_radius = float(np.interp(along[-1], wall.s, wall.r))
                scale = join_radius / wall.R if params["shape"] == "half-round" else 1.
                columns, far = _rim_columns(params, wall.R, rib_count(wall.R, params), 0. if sign > 0 else 1.,
                                            high - low - 2. * distances[-1], distances, relief, scale)
                band_angles = np.broadcast_to(columns * 2. * math.pi, far.shape)
            near = np.full(far.shape, -BURIED)
            tools.append(_tube(radii, zs, nr / size, nz / size, band_angles, near, far).transform(M[:3, :]))
    if params.get("rim_inside", False) and params.get("rim") == "round":
        tools.extend(_inner_rims(manifold, M, bottom, top, distances, relief))
    return tools


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
        on_rib = t_in < 0.0 if inward else t_in > 0.0       # the back of the tool stays where it is
        t_in = np.where(on_rib, t_in * height_share(params, height, h_span, z_frac), t_in)
        s_eff = s_in + equiv_R * (twist * z_frac + path_turn(params, z_frac))
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

    # steps along the wall: its own profile, and short enough to follow a twisted or bent rib
    twist = math.radians(params["twist"])
    turn = min(step, 2.0 * math.acos(max(0.0, 1.0 - TWIST_SAG / surface.R)))
    bend, sweep = path_shape(params)
    travel = abs(twist) + abs(bend * sweep) * 2.0 / math.pi      # the angle a rib passes, there and back for a bend
    pieces = max(1, math.ceil(travel / turn), _path_pieces(params, surface.R), _arch_pieces(params, height, high - low))
    even = np.linspace(low, high, pieces + 1)
    gap = (high - low) / max(MAX_RINGS, pieces)
    bends = _profile_steps(surface, low, high)
    bends = bends[[np.abs(even - b).min() >= gap / 2.0 for b in bends]]     # a twist's rings serve for the bends beside them
    s = np.unique(np.concatenate((even, bends)))
    s = s[np.concatenate(([True], np.diff(s) >= gap / 2.0))]
    s[-1] = high
    if 4 * len(columns) * len(s) > MAX_FACETS:
        raise ValueError("Ribs this fine are too many for a face this large. Use wider ribs, less twist or a smaller bend.")

    radii, zs = np.interp(s, surface.s, surface.r), np.interp(s, surface.s, surface.z)
    nr, nz = np.interp(s, surface.s, surface.nr), np.interp(s, surface.s, surface.nz)
    length = np.maximum(np.hypot(nr, nz), 1e-12)
    nr, nz = nr / length, nz / length
    along = (s - low) / (high - low)
    angles = columns[None, :] + (twist * along + path_turn(params, along))[:, None]
    # a half-round rib keeps its shape as the wall narrows; a rectangular one keeps its depth
    size = (height * radii / surface.R if half_round else np.full(len(s), height))
    size = (size * height_share(params, height, high - low, along))[:, None]
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
    tools, rim_tools, ribs, notes = [], [], 0, []
    for ref in faces:
        try:
            tool, count = japandi_tool(manifold, ref, params)
            rims = japandi_rims(manifold, ref, params)
        except ValueError as e:         # one odd face must not break the history; the panel shows the reason
            notes.append(str(e))
            continue
        tools.append(tool)
        rim_tools.extend(rims)
        ribs += count
    if not tools:
        return manifold, 0, notes
    together = m3d.Manifold.batch_boolean(tools, m3d.OpType.Add)
    result = manifold - together if params["direction"] == "inward" else manifold + together
    if rim_tools:
        result += m3d.Manifold.batch_boolean(rim_tools, m3d.OpType.Add)
    return CadKernel.drop_slivers(result), ribs, notes


class JapandiFeature(Feature):
    """Ribs or grooves along the chosen round faces of one body."""

    PARAMS = ("shape", "direction", "radius", "width", "depth", "spacing", "twist", "margin", "path", "bend", "waves",
              "height_profile", "end_height", "rim", "rim_depth", "rim_inside", "rim_follow")

    def __init__(self, feature_id: str, name: str, target_body_id: str, faces=None, shape: str = "half-round",
                 direction: str = "outward", radius: float = 1.5, width: float = 2.0, depth: float = 2.0,
                 spacing: float = 0.0, twist: float = 0.0, margin: float = 0.0, path: str = "straight",
                 bend: float = 20.0, waves: float = 2.0, height_profile: str = "even", end_height: float = 20.0,
                 rim: str = "none", rim_depth: float = 2.0, rim_inside: bool = False, rim_follow: bool = False):
        super().__init__(feature_id, "japandi", name)
        self.target_body_id = target_body_id
        self.faces = list(faces or [])
        self.shape = shape if shape in SHAPES else SHAPES[0]
        self.direction = direction if direction in DIRECTIONS else DIRECTIONS[0]
        self.radius, self.width, self.depth = float(radius), float(width), float(depth)
        self.spacing, self.twist, self.margin = float(spacing), float(twist), float(margin)
        self.path = path if path in PATHS else PATHS[0]
        self.bend, self.waves = float(bend), float(waves)
        self.height_profile = height_profile if height_profile in HEIGHTS else HEIGHTS[0]
        self.end_height = float(end_height)
        self.rim = rim if rim in RIMS else RIMS[0]
        self.rim_depth, self.rim_inside = float(rim_depth), bool(rim_inside)
        self.rim_follow = bool(rim_follow)
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
