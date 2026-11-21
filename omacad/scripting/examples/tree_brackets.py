"""Omacad script: Tree Brackets - 3D printable brackets for a pyramid Christmas tree of square aluminium tubes.

Four base tubes make a square on the ground, four legs lean in and meet at the top. Print 4 corner brackets and
1 top bracket. You choose the tube lengths (cut lengths, square ends); the script works out the height and the
angles, and keeps the brackets as short as the tubes allow."""
import math
from typing import Callable, List

import manifold3d as m3d
import numpy as np

NAME = "Tree Brackets (script)"
FAMILY = "star_brackets"      # listed in the Star Brackets submenu, next to the star
OUTPUT_NAME = "Tree brackets"
DESCRIPTION = "Corner and top brackets for a pyramid tree of square aluminium tubes; or the whole tree assembled."
PARAMS = [
    {"name": "base_tube_length", "label": "Base tube length", "type": "float", "default": 400.0, "min": 30.0,
     "max": 5000.0, "unit": "mm", "help": "Cut length of each of the 4 tubes in the square on the ground."},
    {"name": "leg_tube_length", "label": "Leg tube length", "type": "float", "default": 1000.0, "min": 50.0,
     "max": 5000.0, "unit": "mm", "help": "Cut length of each of the 4 tubes from a corner up to the top."},
    {"name": "tube_size", "label": "Tube size", "type": "float", "default": 10.0, "min": 2.0, "max": 100.0, "unit": "mm",
     "help": "Outside width of the square tube."},
    {"name": "clearance", "label": "Clearance", "type": "float", "default": 0.25, "min": 0.0, "max": 2.0, "step": 0.05,
     "unit": "mm", "help": "Play between the tube and the socket."},
    {"name": "wall_thickness", "label": "Wall thickness", "type": "float", "default": 2.5, "min": 0.8, "max": 20.0, "unit": "mm"},
    {"name": "socket_depth", "label": "Socket depth", "type": "float", "default": 25.0, "min": 5.0, "max": 200.0, "unit": "mm"},
    {"name": "hole_diameter", "label": "Screw hole diameter", "type": "float", "default": 3.5, "min": 0.0, "max": 20.0,
     "unit": "mm", "help": "0 = no screw holes."},
    {"name": "hole_offset", "label": "Screw hole offset", "type": "float", "default": 12.0, "min": 2.0, "max": 200.0,
     "unit": "mm", "help": "From the socket's open end."},
    {"name": "corner_web", "label": "Corner web", "type": "bool", "default": True,
     "help": "A solid triangular web in the inside corner between the two base tubes: a much stiffer corner."},
    {"name": "corner_web_size", "label": "Corner web size", "type": "float", "default": 20.0, "min": 2.0, "max": 200.0,
     "unit": "mm", "help": "How far the web reaches along each base tube from the inside corner."},
    {"name": "leg_support", "label": "Leg support", "type": "choice", "default": "pyramid",
     "choices": ["pyramid", "fins", "collar", "block", "none"],
     "help": "How the leg socket is carried down into the corner: pyramid = a wide foot tapering up into the socket; "
             "fins = two knee braces from the leg down along the base tubes; collar = a thicker sleeve round the "
             "socket's lower part; block = the corner filled solid up the socket; none = no support. All stop "
             "below the leg's screw hole and clear of the base tubes' screw holes."},
    {"name": "assembled", "label": "Show the whole tree", "type": "bool", "default": False,
     "help": "Off: one of each bracket laid out for printing."},
    {"name": "spacing", "label": "Gap between parts", "type": "float", "default": 30.0, "min": 0.0, "max": 500.0, "unit": "mm"},
]

UP = np.array([0.0, 0.0, 1.0])
LEG_TWISTS = (0.0, 45.0)      # leg tube roll about its own axis: level faces, or a face towards the next leg


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def _frame(axis, roll, origin=(0.0, 0.0, 0.0)) -> np.ndarray:
    """3x4 matrix: local x along `axis`, local y along `roll` (made perpendicular), placed at `origin`."""
    x = _unit(axis)
    y = np.asarray(roll, dtype=float)
    y = _unit(y - x * np.dot(x, y))
    z = np.cross(x, y)
    return np.column_stack([x, y, z, np.asarray(origin, dtype=float)])


def _roll_for(axis, twist: float = 0.0) -> np.ndarray:
    """Side direction of a square tube along `axis`: horizontal (a face stays level), turned `twist` degrees."""
    d = _unit(axis)
    side = np.cross(UP, d)
    side = _unit(side) if np.linalg.norm(side) > 1e-9 else np.array([0.0, 1.0, 0.0])
    t = math.radians(twist)
    return math.cos(t) * side + math.sin(t) * np.cross(d, side)


def _box(frame: np.ndarray, x0: float, length: float, half: float) -> m3d.Manifold:
    """A square box along the frame's x axis from x0, `half` wide each side."""
    return m3d.Manifold.cube([length, 2 * half, 2 * half]).translate([x0, -half, -half]).transform(frame)


def _join(parts: List[m3d.Manifold]) -> m3d.Manifold:
    parts = [q for q in parts if q is not None]
    return m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if len(parts) > 1 else parts[0]


def _shortest_clear(keep_out: Callable[[float], m3d.Manifold], obstacles: m3d.Manifold, lo: float) -> float:
    """Smallest stop t >= lo where the socket's keep-out (cavity plus half a wall) no longer touches `obstacles`."""
    def clear(t):
        return (keep_out(t) ^ obstacles).volume() < 1e-6
    if clear(lo):
        return lo
    hi = lo * 2.0 + 10.0
    while not clear(hi):
        hi *= 2.0
        if hi > 1e5:
            raise ValueError("Could not fit the sockets apart; check the tube size and lengths.")
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if clear(mid) else (mid, hi)
    return hi


class Sizes:
    """Every derived measure of the tree, from the tube lengths. The stops (how far a tube end sits from the joint
    point) are the shortest that keep a full wall between the sockets, found geometrically; they depend on the
    angles and the angles on the height, so the height is found by a few rounds of fixed-point iteration."""

    def __init__(self, p):
        self.inner = max(1.0, p["tube_size"] + p["clearance"])
        self.wall = max(0.8, p["wall_thickness"])
        self.outer = self.inner + 2.0 * self.wall
        self.depth = max(5.0, p["socket_depth"])
        self.margin = max(2.0, self.wall)
        self.keep = self.inner / 2.0 + self.wall / 2.0       # cavity + half a wall: two keep-outs apart = one wall
        self.base_len = max(10.0, p["base_tube_length"])
        self.leg_len = max(10.0, p["leg_tube_length"])
        self.stop_base = self.inner / 2.0 + self.margin      # two base sockets at 90 degrees
        self.a = self.base_len / 2.0 + self.stop_base        # half side of the tube centre-line square
        best = None
        for twist in LEG_TWISTS:
            solved = self._solve(twist)
            if best is None or solved[2] < best[2]:
                best = solved
        self.twist, self.stop_leg, self.stop_top, self.h = best
        self.n = math.sqrt(2.0 * self.a ** 2 + self.h ** 2)
        self.lean = math.degrees(math.atan2(self.a * math.sqrt(2.0), self.h))    # leg tilt from vertical

    def _stops(self, h, twist):
        a, keep, depth = self.a, self.keep, self.depth
        # corner: the leg leans in towards (+x, +y); keep clear of both base sockets and of the floor
        d = _unit([a, a, h])
        fr = _frame(d, _roll_for(d, twist))
        obstacles = _join([_box(_frame([1, 0, 0], [0, 1, 0]), self.stop_base, depth + 1.0, keep),
                           _box(_frame([0, 1, 0], [-1, 0, 0]), self.stop_base, depth + 1.0, keep),
                           m3d.Manifold.cube([4 * depth + 100, 4 * depth + 100, 50.0]).translate(
                               [-2 * depth - 50, -2 * depth - 50, -self.outer / 2.0 + self.wall / 2.0 - 50.0])])
        stop_leg = _shortest_clear(lambda t: _box(fr, t, depth + 1.0, keep), obstacles, self.margin)
        # top: four legs pointing down; each keeps clear of the other three
        downs = [_unit([sx * a, sy * a, -h]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        frames = [_frame(q, _roll_for(q, twist)) for q in downs]
        stop_top = self._top_stop(frames)
        return stop_leg, stop_top

    def _top_stop(self, frames):
        depth, keep = self.depth, self.keep

        def others(t):
            return _join([_box(f, t, depth + 1.0, keep) for f in frames[1:]])

        def clear(t):
            return (_box(frames[0], t, depth + 1.0, keep) ^ others(t)).volume() < 1e-6
        lo = self.margin
        if clear(lo):
            return lo
        hi = lo * 2.0 + 10.0
        while not clear(hi):
            hi *= 2.0
            if hi > 1e5:
                raise ValueError("Could not fit the top sockets apart; check the tube size and lengths.")
        for _ in range(24):
            mid = 0.5 * (lo + hi)
            lo, hi = (lo, mid) if clear(mid) else (mid, hi)
        return hi

    def _solve(self, twist):
        h = self.leg_len
        stop_leg = stop_top = self.margin
        for _ in range(40):
            stop_leg, stop_top = self._stops(h, twist)
            reach = self.leg_len + stop_leg + stop_top
            if reach <= self.a * math.sqrt(2.0) + 1.0:
                raise ValueError("The legs are too short for that base: make the leg tubes longer or the base shorter.")
            h_new = math.sqrt(reach ** 2 - 2.0 * self.a ** 2)
            done = abs(h_new - h) < 1e-4
            h = h_new
            if done:
                break
        stop_leg, stop_top = self._stops(h, twist)
        reach = self.leg_len + stop_leg + stop_top
        h = math.sqrt(reach ** 2 - 2.0 * self.a ** 2)       # the lengths add up exactly at the final stops
        return twist, stop_leg, stop_top, h


def _socket(s: Sizes, frame: np.ndarray, stop: float):
    """(outer box, cavity, stub for the hub) of one socket along the frame's x axis."""
    o, i = s.outer / 2.0, s.inner / 2.0
    return _box(frame, 0.0, stop + s.depth, o), _box(frame, stop, s.depth + 1.0, i), _box(frame, 0.0, stop, o)


def _screw_hole(s: Sizes, p, frame: np.ndarray, stop: float):
    d = p["hole_diameter"]
    if d <= 0.0:
        return None
    x = stop + s.depth - max(2.0, min(s.depth - 2.0, p["hole_offset"]))
    h = s.outer + 4.0
    return m3d.Manifold.cylinder(h, d / 2.0, d / 2.0, 32).translate([x, 0.0, -h / 2.0]).transform(frame)


def _corner_web(s: Sizes, p):
    """Triangular web in the inside corner between the two base sockets, full socket height, its sides sunk half a
    wall into the sockets so it is one piece with them."""
    if not p["corner_web"]:
        return None
    c = s.outer / 2.0 - s.wall / 2.0
    far = s.outer / 2.0 + max(2.0, p["corner_web_size"])
    cs = m3d.CrossSection([np.array([[c, c], [far, c], [c, far]])])
    return m3d.Manifold.extrude(cs, s.outer).translate([0.0, 0.0, -s.outer / 2.0])


def _support_reach(s: Sizes, p, stop: float):
    """(length up the leg socket, reach along the base tubes) a support may use: below the leg's screw hole and
    short of the base tubes' screw holes (without holes: 60 % of the sockets)."""
    o = s.outer / 2.0
    hd = p["hole_diameter"]
    if hd > 0.0:
        off = max(2.0, min(s.depth - 2.0, p["hole_offset"]))
        length = stop + s.depth - off - hd / 2.0 - s.wall
        reach = s.stop_base + s.depth - off - hd / 2.0 - s.wall
    else:
        length = stop + 0.6 * s.depth
        reach = s.stop_base + 0.6 * s.depth
    return max(stop + 2.0, min(length, stop + s.depth)), max(o + s.wall, min(reach, o + 2.0 * s.outer))


def _leg_support(s: Sizes, p, frame: np.ndarray, stop: float):
    """Carries the leg socket down into the corner, in the style chosen by `leg_support` (see PARAMS)."""
    style = p["leg_support"]
    if style not in ("pyramid", "fins", "collar", "block"):
        return None
    o = s.outer / 2.0
    length, reach = _support_reach(s, p, stop)
    ring = np.array([[length, y, z, 1.0] for y in (-o, o) for z in (-o, o)]) @ frame.T     # socket section up top
    if style == "pyramid":
        foot = [[x, y, z] for x in (-o, reach) for y in (-o, reach) for z in (-o, o)]
        return m3d.Manifold.hull_points(np.vstack([ring, np.array(foot)]))
    if style == "block":
        z_top = float(ring[:, 2].min())
        return m3d.Manifold.cube([reach + o, reach + o, z_top + o]).translate([-o, -o, -o])
    inside = m3d.Manifold.cube([reach + o, reach + o, 4.0 * (length + s.outer)]).translate([-o, -o, -o])
    if style == "collar":
        flare = max(3.0, 0.5 * s.outer)
        w = o + flare
        low = np.array([[stop, y, z, 1.0] for y in (-w, w) for z in (-w, w)]) @ frame.T
        return m3d.Manifold.hull_points(np.vstack([ring, low])) ^ inside
    # fins: a knee brace along the inside top edge of each base socket (beside its screw hole, so it can run
    # almost to the socket's end), rising to the leg socket
    t = max(2.0, 1.5 * s.wall)
    fin_reach = s.stop_base + s.depth - 2.0
    top = np.array([length, 0.0, 0.0, 1.0]) @ frame.T
    fins = []
    for k in (0, 1):                                     # 0: along x, inside edge at +y; 1: along y, at +x
        pts = []
        for c in (o - t, o):
            for x, z in ((0.0, o - 0.5), (fin_reach, o - 0.5), (float(top[k]), float(top[2]))):
                pts.append([x, c, z] if k == 0 else [c, x, z])
        fins.append(m3d.Manifold.hull_points(np.array(pts)))
    clip = m3d.Manifold.cube([fin_reach + o, fin_reach + o, 4.0 * (length + s.outer)]).translate([-o, -o, -o])
    return _join(fins) ^ clip


def corner_bracket(s: Sizes, p) -> m3d.Manifold:
    """Corner at the origin (tube centre line), base tubes along +x and +y, leg leaning in towards (+x, +y).
    The bottom is flat at z = -outer/2, so it prints as it stands."""
    leg = _unit([s.a, s.a, s.h])
    frames = [(_frame([1, 0, 0], [0, 1, 0]), s.stop_base), (_frame([0, 1, 0], [-1, 0, 0]), s.stop_base),
              (_frame(leg, _roll_for(leg, s.twist)), s.stop_leg)]
    boxes, cuts, stubs = [], [], []
    for fr, stop in frames:
        box, cav, stub = _socket(s, fr, stop)
        boxes.append(box)
        stubs.append(stub)
        cuts += [cav, _screw_hole(s, p, fr, stop)]
    hub = m3d.Manifold.hull(_join(stubs + [m3d.Manifold.cube([s.outer] * 3, center=True)]))
    solid = _join([hub, _corner_web(s, p), _leg_support(s, p, frames[2][0], s.stop_leg)] + boxes)
    floor = -s.outer / 2.0
    big = 4.0 * (s.depth + s.stop_leg + s.outer)
    solid = solid - m3d.Manifold.cube([2 * big, 2 * big, big]).translate([-big, -big, floor - big])
    return solid - _join(cuts)


def top_bracket(s: Sizes, p) -> m3d.Manifold:
    """Top point at the origin, four sockets pointing down along the legs, cut flat at z = outer/2."""
    boxes, cuts, stubs = [], [], []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        d = _unit([sx * s.a, sy * s.a, -s.h])
        fr = _frame(d, _roll_for(d, s.twist))
        box, cav, stub = _socket(s, fr, s.stop_top)
        boxes.append(box)
        stubs.append(stub)
        cuts += [cav, _screw_hole(s, p, fr, s.stop_top)]
    hub = m3d.Manifold.hull(_join(stubs + [m3d.Manifold.cube([s.outer] * 3, center=True)]))
    solid = _join([hub] + boxes)
    big = 4.0 * (s.depth + s.stop_top + s.outer)
    solid = solid - m3d.Manifold.cube([2 * big, 2 * big, big]).translate([-big, -big, s.outer / 2.0])
    return solid - _join(cuts)


def _corner_places(s: Sizes):
    """(x, y, rotation about z) of the four corners; each corner's +x/+y point along its two base tubes."""
    a = s.a
    return [(-a, -a, 0.0), (a, -a, 90.0), (a, a, 180.0), (-a, a, 270.0)]


def assembled_tubes(s: Sizes, tube_s: float) -> m3d.Manifold:
    z0 = s.outer / 2.0
    half = tube_s / 2.0
    tubes = []
    for x, y, rot in _corner_places(s):
        c = math.radians(rot)
        dx = np.array([math.cos(c), math.sin(c), 0.0])
        corner = np.array([x, y, z0])
        tubes.append(_box(_frame(dx, _roll_for(dx), corner + dx * s.stop_base), 0.0, s.base_len, half))
        leg = _unit(np.array([0.0, 0.0, z0 + s.h]) - corner)
        tubes.append(_box(_frame(leg, _roll_for(leg, s.twist), corner + leg * s.stop_leg), 0.0, s.leg_len, half))
    return _join(tubes)


def run(ctx, params):
    p = dict(params)
    p["tube_size"] = max(2.0, p["tube_size"])
    s = Sizes(p)
    corner = corner_bracket(s, p)
    top = top_bracket(s, p)
    z0 = s.outer / 2.0
    if p["assembled"]:
        corners = [corner.rotate([0, 0, rot]).translate([x, y, z0]) for x, y, rot in _corner_places(s)]
        parts = [(_join(corners), "corner brackets (4x)"), (top.translate([0.0, 0.0, z0 + s.h]), "top bracket"),
                 (assembled_tubes(s, p["tube_size"]), "aluminium tubes (8x)")]
    else:
        # corner as it stands; top bracket upside down so its flat top is on the bed
        top_print = top.rotate([180.0, 0.0, 0.0])
        top_print = top_print.translate([0.0, 0.0, -top_print.bounding_box()[2]])
        corner_print = corner.translate([0.0, 0.0, -corner.bounding_box()[2]])
        dx = corner_print.bounding_box()[3] + p["spacing"] - top_print.bounding_box()[0]
        parts = [(corner_print, "corner bracket"), (top_print.translate([dx, 0.0, 0.0]), "top bracket")]
    bodies = [ctx.solid(shape, f"{ctx.name} - {label}") for shape, label in parts]
    ctx.group(ctx.name, bodies)
    total = z0 + s.h + s.outer / 2.0
    side = 2.0 * s.a + s.outer
    ctx.log(f"Tree: about {total:.0f} mm tall, base {side:.0f} x {side:.0f} mm, legs lean {s.lean:.1f} deg in. "
            f"Print 4 corner brackets and 1 top bracket; cut 4 tubes of {s.base_len:.0f} mm and 4 of {s.leg_len:.0f} mm.")
