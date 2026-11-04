"""The cell patterns of Surface Texture beyond the plain lattices: Voronoi in several styles, on flat, round and revolved
faces, and the Opening and Rounding that shape any cell afterwards. All of it is drawn from indexes and the seed, not from
a random stream, so a file rebuilds alike on any machine."""

import math
from typing import Optional

import numpy as np
import shapely
from shapely import affinity, delaunay_triangles, maximum_inscribed_circle, voronoi_polygons
from shapely.geometry import MultiPoint, Polygon
from shapely.strtree import STRtree

from omacad.model.features.revolved_surface import RevolvedSurface

VORONOI_MAX_SITES = 20000
VORONOI_MAX_JITTER = 0.45       # of the cell spacing, at 100 % randomness: keeps two sites from nearly coinciding
VORONOI_MIN_AREA = 0.05         # of size²: a smaller cell would only be a speck in the wall
VORONOI_STYLES = ("even", "gradient", "hotspot", "radial", "nested", "triangles")
TRIANGLE_SIDE = 2.0 / math.sqrt(3.0)
MIN_OPENING = 0.05              # a smaller opening is left out
MAX_ROUND = 0.95                # of the inscribed radius at 100 % rounding: a cell can't vanish in being rounded
ROUND_SEGMENTS = 6
HOLE_SHAPES = ("cell", "circle", "square", "star", "triangle", "pentagon", "hexagon", "octagon")
HOLE_CORNERS = {"circle": 48, "square": 4, "triangle": 3, "pentagon": 5, "hexagon": 6, "octagon": 8}
STAR_INNER = 0.45              # the inner corners of a star, of its outer radius
MAX_RELAXATION = 50
TRIANGLE_JITTER = 0.4          # of the usual amount: more gives long slivers


def _site_random(i: np.ndarray, j: np.ndarray, seed: int, salt: int) -> np.ndarray:
    """A number in [0, 1) for each lattice index (splitmix64). It depends only on the index and the seed, not on how
    many sites are drawn, so a cell stays where it is when the face grows, and files rebuild alike on any machine."""
    z = (i.astype(np.int64).astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
         ^ j.astype(np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
         ^ np.uint64((int(seed) * 0x165667B19E3779F9 + salt) & 0xFFFFFFFFFFFFFFFF))
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return (z ^ (z >> np.uint64(31))).astype(np.float64) / 2.0 ** 64


def voronoi_cells(size: float, wall: float, angle: float, bounds, anchor, period: Optional[float] = None,
                  randomness: float = 100.0, seed: int = 1):
    """Voronoi cells of a hexagonal lattice of sites moved at random, each shrunk wall/2, so two neighbours are always
    `wall` apart. At 0 % randomness they are hexagons `size` across their flats; `size` stays the average width.
    With `period` the indices repeat round the cylinder, so the pattern closes without a seam (and is not turned)."""
    ax, ay = float(anchor[0]), float(anchor[1])
    minx, miny, maxx, maxy = bounds
    pitch = size + wall
    columns = max(1, int(round(period / pitch))) if period is not None else 0
    step_x = period / columns if period is not None else pitch
    step_y = pitch * math.sqrt(3) / 2.0
    pad = 3.0 * pitch               # sites past the edge: the cells inside must be bounded by their real neighbours
    if period is not None:
        reach_x, reach_y = period / 2.0 + pad, max(maxy - ay, ay - miny) + pad
    else:
        reach_x = reach_y = math.hypot(max(maxx - ax, ax - minx), max(maxy - ay, ay - miny)) + pad
    ni, nj = int(reach_x / step_x) + 1, int(reach_y / step_y) + 1
    if (2 * ni + 1) * (2 * nj + 1) > VORONOI_MAX_SITES:
        raise ValueError(f"{(2 * ni + 1) * (2 * nj + 1)} Voronoi cells is too many. Use a larger cell size.")
    jj, ii = np.meshgrid(np.arange(-nj, nj + 1), np.arange(-ni, ni + 1), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()
    wrapped = np.mod(ii, columns) if period is not None else ii
    reach = np.clip(randomness, 0.0, 100.0) / 100.0 * VORONOI_MAX_JITTER * pitch * np.sqrt(_site_random(wrapped, jj, seed, 1))
    turn = 2.0 * math.pi * _site_random(wrapped, jj, seed, 2)
    x = step_x * (ii + 0.5 * np.mod(jj, 2)) + reach * np.cos(turn)
    y = step_y * jj + reach * np.sin(turn)
    if period is None and angle:
        rad = math.radians(angle)
        x, y = x * math.cos(rad) - y * math.sin(rad), x * math.sin(rad) + y * math.cos(rad)
    x, y = x + ax, y + ay
    sites = MultiPoint(np.column_stack((x, y)))
    outlines = voronoi_polygons(sites, extend_to=sites.envelope.buffer(pitch), ordered=True).geoms
    if period is not None:
        keep = (x >= ax - period / 2.0 - 1e-6) & (x < ax + period / 2.0 - 1e-6)
    else:
        keep = np.ones(len(x), dtype=bool)
    cells, area = [], VORONOI_MIN_AREA * size * size
    for outline, kept in zip(outlines, keep):
        if not kept:
            continue
        x0, y0, x1, y1 = outline.bounds
        if y1 < miny or y0 > maxy or (period is None and (x1 < minx or x0 > maxx)):
            continue
        cell = outline.buffer(-wall / 2.0, join_style="mitre", mitre_limit=10.0) if wall > 0 else outline
        if cell.geom_type == "Polygon" and cell.area >= area:
            cells.append(cell)
    return cells


def revolved_voronoi_cells(surface: RevolvedSurface, s_low: float, s_high: float, size: float, wall: float,
                           randomness: float = 100.0, seed: int = 1):
    """Voronoi cells on the flat pattern of a surface of revolution, of even true size everywhere: every row has as many
    sites as fit its own circumference, and each cell shrinks by the wall at its own scale."""
    pitch = size + wall
    row = pitch * math.sqrt(3) / 2.0
    middle = (s_low + s_high) / 2.0
    rows = int((s_high - s_low) / 2.0 / row) + 4
    xs, ys, scales = [], [], []
    for j in range(-rows, rows + 1):
        s = middle + j * row
        radius = float(surface.radius_at(np.clip(s, s_low, s_high)))
        columns = max(3, int(round(2.0 * math.pi * radius / pitch)))
        ii = np.arange(columns)
        jj = np.full(columns, j)
        scale = radius / surface.R
        reach = np.clip(randomness, 0.0, 100.0) / 100.0 * VORONOI_MAX_JITTER * pitch * np.sqrt(_site_random(ii, jj, seed, 1))
        turn = 2.0 * math.pi * _site_random(ii, jj, seed, 2)
        xs.append((ii + 0.5 * (j % 2)) / columns * surface.period + reach * np.cos(turn) / scale)
        ys.append(surface.y_at(s) + reach * np.sin(turn) / scale)
        scales.append(np.full(columns, scale))
    x, y, scale = np.concatenate(xs), np.concatenate(ys), np.concatenate(scales)
    count = len(x)
    if 3 * count > VORONOI_MAX_SITES:
        raise ValueError(f"{count} Voronoi cells is too many. Use a larger cell size.")
    # a turn on either side, so the pattern closes round the surface; only the middle turn is kept
    tiled = MultiPoint(np.column_stack((np.concatenate((x, x - surface.period, x + surface.period)), np.tile(y, 3))))
    outlines = voronoi_polygons(tiled, extend_to=tiled.envelope.buffer(pitch), ordered=True).geoms
    cells = []
    for outline, local in zip(list(outlines)[:count], scale):
        cell = outline.buffer(-wall / 2.0 / local, join_style="mitre", mitre_limit=10.0) if wall > 0 else outline
        if cell.geom_type == "Polygon" and cell.area * local * local >= VORONOI_MIN_AREA * size * size:
            cells.append(cell)
    return cells


def grade(params, bounds, anchor, period: Optional[float] = None, surface: Optional[RevolvedSurface] = None):
    """A function (x, y) -> t in 0..1 over the face. Gradient and fades run along the pattern's up direction (Rotation
    turns it; a round face only has along its axis, and 180° flips it). Hotspot and Radial run from their centres out."""
    style, flip = params.get("style", "even"), math.cos(math.radians(params.get("angle", 0.0))) < 0
    minx, miny, maxx, maxy = bounds
    if surface is not None:
        low, high = float(surface.s_at(miny)), float(surface.s_at(maxy))
        if style in ("hotspot", "radial"):
            middle, half = (low + high) / 2.0, max((high - low) / 2.0, 1e-9)   # a band round the middle of the wall
            return lambda x, y: np.clip(np.abs(surface.s_at(y) - middle) / half, 0.0, 1.0)
        span = max(high - low, 1e-9)
        return lambda x, y: np.clip((high - surface.s_at(y) if flip else surface.s_at(y) - low) / span, 0.0, 1.0)
    if period is not None:
        minx, maxx = anchor[0] - period / 2.0, anchor[0] + period / 2.0
    if style in ("hotspot", "radial"):
        spots = hotspot_positions(params, (minx, miny, maxx, maxy), anchor)
        corners = [(a, b) for a in (minx, maxx) for b in (miny, maxy)]
        reach = max(max(math.hypot(a - sx, b - sy) for a, b in corners) for sx, sy in spots) if period is None else \
            max(math.hypot(period / 2.0, max(maxy - sy, sy - miny)) for sx, sy in spots)
        return lambda x, y: np.clip(_spot_distance(x, y, spots, period)[0] / max(reach, 1e-9), 0.0, 1.0)
    rad = math.radians(params.get("angle", 0.0)) if period is None else (math.pi if flip else 0.0)
    dx, dy = -math.sin(rad), math.cos(rad)
    along = [a * dx + b * dy for a in (minx, maxx) for b in (miny, maxy)]
    if period is not None:
        along = [b * dy for b in (miny, maxy)]
        dx = 0.0
    low, span = min(along), max(max(along) - min(along), 1e-9)
    return lambda x, y: np.clip((np.asarray(x) * dx + np.asarray(y) * dy - low) / span, 0.0, 1.0)


def hotspot_positions(params, bounds, anchor) -> list:
    """The face's centre, then further spots drawn from the seed."""
    count = max(1, int(round(params.get("hotspots", 1))))
    seed = int(round(params.get("seed", 1)))
    index = np.arange(1, count)
    minx, miny, maxx, maxy = bounds
    xs = minx + _site_random(index, index, seed, 3) * (maxx - minx)
    ys = miny + _site_random(index, index, seed, 4) * (maxy - miny)
    return [(float(anchor[0]), float(anchor[1]))] + [(float(a), float(b)) for a, b in zip(xs, ys)]


def _spot_distance(x, y, spots, period):
    """(distance to the nearest spot, its index) for each point; round a cylinder the short way."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    d = []
    for sx, sy in spots:
        dx = x - sx
        if period is not None:
            dx = dx - period * np.round(dx / period)
        d.append(np.hypot(dx, y - sy))
    d = np.stack(d)
    return d.min(axis=0), d.argmin(axis=0)


def _jittered(ii, jj, seed, reach):
    amount = reach * np.sqrt(_site_random(ii, jj, seed, 1))
    turn = 2.0 * math.pi * _site_random(ii, jj, seed, 2)
    return amount * np.cos(turn), amount * np.sin(turn)


def _graded_rows(params, bounds, anchor, period, grade_at, fine, coarse):
    """Rows across the up direction, each as far from the last and with its sites as far apart as the pitch there.
    Returns site arrays (x, y, pitch)."""
    seed, jitter = int(round(params.get("seed", 1))), np.clip(params.get("randomness", 100.0), 0.0, 100.0) / 100.0 * VORONOI_MAX_JITTER
    if params.get("style") == "triangles":
        jitter *= TRIANGLE_JITTER
    rad = 0.0 if period is not None else math.radians(params.get("angle", 0.0))
    ux, uy, vx, vy = math.cos(rad), math.sin(rad), -math.sin(rad), math.cos(rad)
    minx, miny, maxx, maxy = bounds
    if period is not None:
        minx, maxx = anchor[0] - period / 2.0, anchor[0] + period / 2.0
    corners = [(a, b) for a in (minx, maxx) for b in (miny, maxy)]
    us, vs = [a * ux + b * uy for a, b in corners], [a * vx + b * vy for a, b in corners]
    pad = 3.0 * coarse
    xs, ys, pitches, total = [], [], [], 0
    v, j = min(vs) - pad, 0
    while v <= max(vs) + pad:
        mid_u = (min(us) + max(us)) / 2.0
        at = (mid_u * ux + v * vx, mid_u * uy + v * vy)
        pitch = fine + (coarse - fine) * float(grade_at(np.array([at[0]]), np.array([at[1]]))[0])
        if period is not None:
            columns = max(3, int(round(period / pitch)))
            pitch_u = period / columns
            start = minx
        else:
            columns = int((max(us) - min(us) + 2.0 * pad) / pitch) + 1
            pitch_u = pitch
            start = min(us) - pad
        total += columns
        if 3 * total > VORONOI_MAX_SITES:
            raise ValueError("Too many Voronoi cells. Use a larger cell size.")
        ii, jj = np.arange(columns), np.full(columns, j)
        ox, oy = _jittered(ii, jj, seed, jitter * pitch)
        u = start + (ii + 0.5 * (j % 2)) * pitch_u + ox
        w = v + oy
        xs.append(u * ux + w * vx)
        ys.append(u * uy + w * vy)
        pitches.append(np.full(columns, pitch))
        v += pitch * math.sqrt(3.0) / 2.0
        j += 1
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(pitches)


def _ring_sites(params, bounds, anchor, period, fine, coarse):
    """Rings round each spot. Hotspot: the pitch grows outward at a fixed gap. Radial: a fixed number of spokes, so the
    cells grow with the radius, halving the spokes inward whenever they would get smaller than the finest cell."""
    style = params.get("style")
    seed = int(round(params.get("seed", 1)))
    jitter = np.clip(params.get("randomness", 100.0), 0.0, 100.0) / 100.0 * VORONOI_MAX_JITTER
    if style == "radial":
        jitter *= 0.25          # more would hide the rings and spokes
    minx, miny, maxx, maxy = bounds
    if period is not None:
        minx, maxx = anchor[0] - period / 2.0, anchor[0] + period / 2.0
    spots = hotspot_positions(params, (minx, miny, maxx, maxy), anchor) if style == "hotspot" else [tuple(map(float, anchor))]
    corners = [(a, b) for a in (minx, maxx) for b in (miny, maxy)]
    xs, ys, pitches, total = [], [], [], 0
    for index, (sx, sy) in enumerate(spots):
        reach = max(math.hypot(a - sx, b - sy) for a, b in corners)
        limit = reach + 3.0 * coarse
        rings = []          # (radius, sites on it, pitch)
        if style == "radial":
            spokes = max(6, int(round(2.0 * math.pi * reach / coarse)))
            r = limit
            while r > fine * 0.75:
                if 2.0 * math.pi * r / spokes < fine and spokes > 6:
                    spokes = max(6, spokes // 2)
                rings.append((r, spokes, 2.0 * math.pi * r / spokes))
                r /= 1.0 + 2.0 * math.pi / spokes
        else:
            r = fine * math.sqrt(3.0) / 2.0
            while r <= limit:
                pitch = fine + (coarse - fine) * min(1.0, 1.3 * r / max(reach, 1e-9))
                rings.append((r, max(3, int(round(2.0 * math.pi * r / pitch))), pitch))
                r += pitch * math.sqrt(3.0) / 2.0
        rows = [(float(sx), float(sy), fine)]
        for j, (radius, count, pitch) in enumerate(rings):
            total += count
            if 3 * total > VORONOI_MAX_SITES:
                raise ValueError("Too many Voronoi cells. Use a larger cell size.")
            ii, jj = np.arange(count), np.full(count, j + 1000 * index + 1)
            turn = 2.0 * math.pi * (ii + 0.5 * (j % 2)) / count
            ox, oy = _jittered(ii, jj, seed, jitter * pitch)
            xs.append(sx + radius * np.cos(turn) + ox)
            ys.append(sy + radius * np.sin(turn) + oy)
            pitches.append(np.full(count, pitch))
        xs.append(np.array([rows[0][0]]))
        ys.append(np.array([rows[0][1]]))
        pitches.append(np.array([rows[0][2]]))
        if len(spots) > 1:      # each spot keeps the sites nearest to it, so two sets of rings don't overlap
            keep = _spot_distance(np.concatenate(xs[-len(rings) - 1:]), np.concatenate(ys[-len(rings) - 1:]), spots, period)[1] == index
            x, y, p = (np.concatenate(a[-len(rings) - 1:])[keep] for a in (xs, ys, pitches))
            del xs[-len(rings) - 1:], ys[-len(rings) - 1:], pitches[-len(rings) - 1:]
            xs.append(x), ys.append(y), pitches.append(p)
    x, y, pitch = np.concatenate(xs), np.concatenate(ys), np.concatenate(pitches)
    if period is not None:      # one turn only: the tiling in _cells_of closes it
        keep = np.abs(x - anchor[0]) < period / 2.0
        x, y, pitch = x[keep], y[keep], pitch[keep]
    return x, y, pitch


def _revolved_rows(params, surface: RevolvedSurface, s_low, s_high, grade_at, fine, coarse):
    """Rows up a revolved wall: the same as _graded_rows in true sizes, closing round every row. Radial keeps its
    number of sites from row to row, so the cells follow the wall's radius."""
    style = params.get("style")
    seed = int(round(params.get("seed", 1)))
    jitter = np.clip(params.get("randomness", 100.0), 0.0, 100.0) / 100.0 * VORONOI_MAX_JITTER
    if style == "radial":
        jitter *= 0.25
    elif style == "triangles":
        jitter *= TRIANGLE_JITTER
    spokes = max(6, int(round(surface.period / coarse)))
    xs, ys, pitches, scales, total = [], [], [], [], 0
    s, j = s_low - 3.0 * coarse, 0
    while s <= s_high + 3.0 * coarse:
        radius = float(surface.radius_at(np.clip(s, s_low, s_high)))
        scale = radius / surface.R
        if style == "radial":
            columns = spokes
            while 2.0 * math.pi * radius / columns < fine and columns > 6:
                columns = max(6, columns // 2)
            pitch = 2.0 * math.pi * radius / columns
        else:
            y = surface.y_at(float(np.clip(s, s_low, s_high)))
            pitch = fine + (coarse - fine) * float(grade_at(np.array([0.0]), np.array([y]))[0])
            columns = max(3, int(round(2.0 * math.pi * radius / pitch)))
        total += columns
        if 3 * total > VORONOI_MAX_SITES:
            raise ValueError("Too many Voronoi cells. Use a larger cell size.")
        ii, jj = np.arange(columns), np.full(columns, j)
        ox, oy = _jittered(ii, jj, seed, jitter * pitch)
        xs.append((ii + 0.5 * (j % 2)) / columns * surface.period + ox / scale)
        ys.append(surface.y_at(s) + oy / scale)
        pitches.append(np.full(columns, pitch))
        scales.append(np.full(columns, scale))
        s += pitch * math.sqrt(3.0) / 2.0
        j += 1
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(pitches), np.concatenate(scales)


def _relaxed(x, y, period, rounds: int, bounds):
    """Lloyd relaxation: each site moves to the middle of its cell, which evens the cells out. Sites outside `bounds`
    stay, so the pattern doesn't spread; round a cylinder the turn is tiled, so it stays closed."""
    x, y = x.copy(), y.copy()
    count = len(x)
    minx, miny, maxx, maxy = bounds
    for _ in range(min(int(rounds), MAX_RELAXATION)):
        ax, ay = (x, y) if period is None else (np.concatenate((x, x - period, x + period)), np.tile(y, 3))
        sites = MultiPoint(np.column_stack((ax, ay)))
        outlines = voronoi_polygons(sites, extend_to=sites.envelope, ordered=True).geoms
        middles = shapely.centroid(np.array(list(outlines)[:count], dtype=object))
        nx, ny = shapely.get_x(middles), shapely.get_y(middles)
        inside = (y >= miny) & (y <= maxy) & (np.ones(count, bool) if period is not None else (x >= minx) & (x <= maxx))
        x, y = np.where(inside, nx, x), np.where(inside, ny, y)
    return x, y


def _cells_of(x, y, pitch, scale, wall, period, triangles=False):
    """The Voronoi cells (or the Delaunay triangles) of the sites, each shrunk wall/2 at its own scale. With `period`
    the sites are tiled a turn each way, so the pattern closes round the face; only the middle turn is kept."""
    count = len(x)
    if period is not None:
        x, y = np.concatenate((x, x - period, x + period)), np.tile(y, 3)
    sites = MultiPoint(np.column_stack((x, y)))
    made = []
    if triangles:
        mid = None if period is None else (float(x[:count].min()), float(x[:count].max()))
        tree_points = np.column_stack((x[:count], y[:count]))
        for tri in delaunay_triangles(sites).geoms:
            c = tri.centroid
            if mid is not None and not (mid[0] <= c.x < mid[0] + period):
                continue
            nearest = int(np.argmin((tree_points[:, 0] - c.x) ** 2 + (tree_points[:, 1] - c.y) ** 2))
            made.append((tri, float(scale[nearest]), float(pitch[nearest])))
    else:
        outlines = voronoi_polygons(sites, extend_to=sites.envelope.buffer(float(np.max(pitch))), ordered=True).geoms
        made = list(zip(list(outlines)[:count], map(float, scale), map(float, pitch)))
    cells = []
    for outline, local, p in made:
        cell = outline.buffer(-wall / 2.0 / local, join_style="mitre", mitre_limit=10.0) if wall > 0 else outline
        if cell.geom_type != "Polygon":
            continue
        size = max(p - wall, 1e-6)
        if cell.area * local * local >= VORONOI_MIN_AREA * size * size * (0.3 if triangles else 1.0):
            cells.append(cell)
    return cells


def _nested(parents, children, min_area) -> list:
    """The small cells clipped to the big ones, so the big cells' walls stay thick and unbroken between them."""
    tree = STRtree(parents)
    out = []
    for child in children:
        for index in tree.query(child, predicate="intersects"):
            piece = child.intersection(parents[int(index)])
            for part in getattr(piece, "geoms", [piece]):
                if part.geom_type == "Polygon" and part.area >= min_area:
                    out.append(part)
    return out


def styled_cells(params, bounds, anchor, period: Optional[float] = None) -> list:
    """Voronoi cells in the chosen style, for a flat face or a cylinder's unrolled wall."""
    style, size, wall = params.get("style", "even"), params["size"], params["wall"]
    fine_size = min(max(params.get("fine_size", 2.0), 0.1), size)
    randomness, seed = params.get("randomness", 100.0), int(round(params.get("seed", 1)))
    if style == "nested":
        parents = (styled_cells(dict(params, style="even"), bounds, anchor, period) if params.get("relaxation", 0) > 0 else
                   voronoi_cells(size, wall, params["angle"], bounds, anchor, period, randomness, seed))
        inner = params.get("inner_wall", 0.8)
        children = voronoi_cells(fine_size, inner, params["angle"], bounds, anchor, period, randomness, seed + 1)
        return _nested(parents, children, VORONOI_MIN_AREA * fine_size * fine_size)
    fine, coarse = fine_size + wall, size + wall
    if style == "even":             # a relaxed Even: rows of one pitch
        fine = coarse
    if style == "triangles":        # a triangle is narrower than its side: this keeps Cell size its height
        fine, coarse = fine * TRIANGLE_SIDE, coarse * TRIANGLE_SIDE
    if style in ("hotspot", "radial"):
        x, y, pitch = _ring_sites(params, bounds, anchor, period, fine, coarse)
    else:
        grade_at = grade(dict(params, style="gradient"), bounds, anchor, period)
        x, y, pitch = _graded_rows(params, bounds, anchor, period, grade_at, fine, coarse)
    if period is not None:
        low = anchor[0] - period / 2.0
        x = low + np.mod(x - low, period)
    x, y = _relaxed(x, y, period, params.get("relaxation", 0), bounds)
    return _cells_of(x, y, pitch, np.ones(len(x)), wall, period, style == "triangles")


def revolved_styled_cells(params, surface: RevolvedSurface, s_low: float, s_high: float) -> list:
    """The same on the flat pattern of a surface of revolution, in true sizes."""
    style, size, wall = params.get("style", "even"), params["size"], params["wall"]
    fine_size = min(max(params.get("fine_size", 2.0), 0.1), size)
    randomness, seed = params.get("randomness", 100.0), int(round(params.get("seed", 1)))
    if style == "nested":
        parents = (revolved_styled_cells(dict(params, style="even"), surface, s_low, s_high) if params.get("relaxation", 0) > 0 else
                   revolved_voronoi_cells(surface, s_low, s_high, size, wall, randomness, seed))
        children = revolved_voronoi_cells(surface, s_low, s_high, fine_size, params.get("inner_wall", 0.8), randomness, seed + 1)
        out = []
        for part in _nested(parents, children, 0.0):
            local = float(surface.scale_at_y(part.centroid.y))
            if part.area * local * local >= VORONOI_MIN_AREA * fine_size * fine_size:
                out.append(part)
        return out
    fine, coarse = fine_size + wall, size + wall
    if style == "even":
        fine = coarse
    if style == "triangles":
        fine, coarse = fine * TRIANGLE_SIDE, coarse * TRIANGLE_SIDE
    bounds = (0.0, surface.y_at(s_low), surface.period, surface.y_at(s_high))
    grade_at = grade(params, bounds, (surface.period / 2.0, (bounds[1] + bounds[3]) / 2.0), None, surface)
    x, y, pitch, scale = _revolved_rows(params, surface, s_low, s_high, grade_at, fine, coarse)
    x = np.mod(x, surface.period)
    x, y = _relaxed(x, y, surface.period, params.get("relaxation", 0), bounds)
    if params.get("relaxation", 0) > 0:     # the sites moved along the wall; past its narrow end they keep the end's scale
        scale = np.clip(surface.scale_at_y(y), scale.min(), 1.0)
    return _cells_of(x, y, pitch, scale, wall, surface.period, style == "triangles")


def _symbol(hole: str, x: float, y: float, radius: float, angle: float) -> Polygon:
    """A hole shape round (x, y) that stays inside the circle of `radius`."""
    if hole == "star":
        count = 5
        radii = np.tile([radius, radius * STAR_INNER], count)
        turns = np.arange(2 * count) * math.pi / count
    else:
        count = HOLE_CORNERS[hole]
        radii = np.full(count, radius)
        turns = np.arange(count) * 2.0 * math.pi / count
    turns = turns + math.radians(angle) + (math.pi / count if hole == "square" else math.pi / 2.0)
    return Polygon(np.column_stack((x + radii * np.cos(turns), y + radii * np.sin(turns))))


def finish_cells(cells, params, bounds, anchor, period: Optional[float] = None, surface: Optional[RevolvedSurface] = None) -> list:
    """Hole shape (a symbol in the largest circle that fits the cell), Opening (its size, or the cell scaled round its
    middle, from one value to another across the face) and Rounding (corners rounded, up to almost a circle). At their
    defaults the cells are returned as they are."""
    start, end = params.get("opening", 100.0), params.get("opening_end", 100.0)
    rounding = np.clip(params.get("rounding", 0.0), 0.0, 100.0) / 100.0
    hole = params.get("hole", "cell")
    if start >= 100.0 and end >= 100.0 and rounding <= 0.0 and hole == "cell":
        return cells
    grade_at = grade(params, bounds, anchor, period, surface)
    angle = params.get("angle", 0.0)
    out = []
    for cell in cells:
        c = cell.centroid
        share = (start + (end - start) * float(grade_at(np.array([c.x]), np.array([c.y]))[0])) / 100.0
        if share < MIN_OPENING:
            continue
        if hole != "cell":
            line = maximum_inscribed_circle(cell, tolerance=0.02 * math.sqrt(cell.area))
            (px, py), radius = line.coords[0], line.length
            shaped = _symbol(hole, px, py, radius * share, angle)
        else:
            shaped = affinity.scale(cell, share, share, origin=(c.x, c.y)) if share < 1.0 else cell
        if rounding > 0.0:
            line = maximum_inscribed_circle(shaped, tolerance=0.002 * math.sqrt(shaped.area))
            radius = rounding * MAX_ROUND * line.length
            eroded = shaped.buffer(-radius, join_style="mitre", mitre_limit=10.0)
            if eroded.is_empty:         # the circle is an estimate: on the rare thin cell, round a little less
                radius *= 0.8
                eroded = shaped.buffer(-radius, join_style="mitre", mitre_limit=10.0)
            if eroded.is_empty:
                out.append(shaped)
                continue
            shaped = eroded.buffer(radius, quad_segs=ROUND_SEGMENTS)
            if shaped.geom_type != "Polygon":
                shaped = max(shaped.geoms, key=lambda g: g.area)
        out.append(shaped)
    return out
