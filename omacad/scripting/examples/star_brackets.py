"""Omacad script: Star Brackets - 3D printable brackets for square aluminium tubes (a five-point advent star).

A copy of Omacad's built-in Star Brackets tool with all its geometry code, so you (or an AI) can change anything:
the bracket shape, the holes, the reinforcement web ... Use "Modify with AI…" in the Star Brackets menu to make a
changed copy; this file stays as it is."""
import math
from typing import List, Optional, Tuple

import manifold3d as m3d
import numpy as np

NAME = "Star Brackets (script)"
FAMILY = "star_brackets"      # listed in the Star Brackets submenu
OUTPUT_NAME = "Star brackets"
DESCRIPTION = "Outer and inner brackets plus a sample tube for a star of square aluminium tubes; or the whole star assembled."
PARAMS = [
    {"name": "tube_size", "label": "Tube size", "type": "float", "default": 10.0, "min": 2.0, "max": 100.0, "unit": "mm",
     "help": "Outside width of the square tube."},
    {"name": "tube_length", "label": "Tube length", "type": "float", "default": 250.0, "min": 20.0, "max": 5000.0, "unit": "mm"},
    {"name": "clearance", "label": "Clearance", "type": "float", "default": 0.25, "min": 0.0, "max": 2.0, "step": 0.05,
     "unit": "mm", "help": "Play between the tube and the socket."},
    {"name": "wall_thickness", "label": "Wall thickness", "type": "float", "default": 2.5, "min": 0.8, "max": 20.0, "unit": "mm"},
    {"name": "socket_depth", "label": "Socket depth", "type": "float", "default": 25.0, "min": 5.0, "max": 200.0, "unit": "mm"},
    {"name": "hole_diameter", "label": "Screw hole diameter", "type": "float", "default": 3.5, "min": 1.0, "max": 20.0, "unit": "mm"},
    {"name": "hole_offset", "label": "Screw hole offset", "type": "float", "default": 12.0, "min": 2.0, "max": 200.0, "unit": "mm"},
    {"name": "double_holes", "label": "Two screw holes per arm", "type": "bool", "default": False},
    {"name": "hole_spacing", "label": "Hole spacing", "type": "float", "default": 15.0, "min": 2.0, "max": 200.0, "unit": "mm"},
    {"name": "reinforcement", "label": "Reinforcement web", "type": "bool", "default": True},
    {"name": "post", "label": "Connecting post", "type": "bool", "default": False},
    {"name": "post_height", "label": "Post height", "type": "float", "default": 25.0, "min": 5.0, "max": 200.0, "unit": "mm"},
    {"name": "second_star", "label": "Second star (3D)", "type": "bool", "default": False},
    {"name": "cross_tube_length", "label": "Tubes between the stars", "type": "float", "default": 150.0, "min": 10.0,
     "max": 2000.0, "unit": "mm"},
    {"name": "outer_angle", "label": "Point angle (outer)", "type": "float", "default": 36.0, "min": 10.0, "max": 160.0, "unit": "°"},
    {"name": "inner_angle", "label": "Valley angle (inner)", "type": "float", "default": 108.0, "min": 10.0, "max": 170.0, "unit": "°",
     "help": "For a regular five-point star: point angle + 72."},
    {"name": "assembled", "label": "Show the whole star", "type": "bool", "default": False,
     "help": "Off: one of each part laid out for printing."},
    {"name": "spacing", "label": "Gap between parts", "type": "float", "default": 30.0, "min": 0.0, "max": 500.0, "unit": "mm"},
    # used only by the foot builder, kept so the copied code runs unchanged
    {"name": "foot_width", "type": "float", "default": 40.0, "min": 10.0, "max": 500.0, "unit": "mm"},
    {"name": "foot_length", "type": "float", "default": 70.0, "min": 10.0, "max": 500.0, "unit": "mm"},
    {"name": "foot_thickness", "type": "float", "default": 4.0, "min": 1.0, "max": 50.0, "unit": "mm"},
    {"name": "foot_tube_angle", "type": "float", "default": 36.0, "min": 10.0, "max": 160.0, "unit": "°"},
]


def star_radii(tube_len: float, tube_s: float, clr: float, wall_t: float, outer_a: float, inner_a: Optional[float] = None) -> Tuple[float, float, float, float]:
    """Computes outer tip radius, inner valley radius, and stop offsets along tube using exact 5-point star trigonometry."""
    out_a = max(10.0, min(160.0, float(outer_a)))
    in_a = max(10.0, min(170.0, (out_a + 72.0) if inner_a is None else float(inner_a)))
    inner_s = tube_s + clr
    half_out = math.radians(out_a / 2.0)
    x_inner_out = (inner_s / 2.0) / math.tan(half_out)
    stop_margin = max(2.0, wall_t)
    x_stop_out = x_inner_out + stop_margin

    half_in = math.radians(in_a / 2.0)
    x_inner_in = (inner_s / 2.0) / math.tan(half_in)
    x_stop_in = x_inner_in + stop_margin

    D = max(10.0, tube_len) + x_stop_out + x_stop_in
    sin_36 = math.sin(math.radians(36.0))
    R_out = D * math.sin(math.radians(144.0 - out_a / 2.0)) / sin_36
    R_in = D * math.sin(half_out) / sin_36
    return R_out, R_in, x_stop_out, x_stop_in



class Bracket:
    """One part (outer/inner bracket, foot, tube) built from the values - the same geometry code as Omacad's
    Star Brackets tool, so every detail can be changed here."""

    def __init__(self, part_type, p):
        self.part_type = part_type
        for key in ("tube_size", "tube_length", "clearance", "wall_thickness", "socket_depth", "hole_diameter",
                    "hole_offset", "double_holes", "hole_spacing", "reinforcement", "post", "post_height",
                    "second_star", "cross_tube_length", "outer_angle", "inner_angle", "foot_width", "foot_length",
                    "foot_thickness", "foot_tube_angle", "assembled"):
            setattr(self, key, p[key])
        self.post = bool(p["post"]) or bool(p["second_star"])
        self.angle = {"outer": self.outer_angle, "inner": self.inner_angle, "foot": self.foot_tube_angle}.get(part_type, 0.0)
        self.translation = [0.0, 0.0, 0.0]

    def build_solid(self):
        inner_s = max(1.0, self.tube_size + self.clearance)
        wall = max(0.8, self.wall_thickness)
        outer_s = inner_s + 2.0 * wall
        depth = max(5.0, self.socket_depth)
        h_dia = max(1.0, self.hole_diameter)
        h_off = max(2.0, min(depth - 2.0, self.hole_offset))
        if self.assembled:
            build = {"outer": self._build_assembled_outer, "inner": self._build_assembled_inner,
                     "foot": self._build_assembled_feet, "tubes": self._build_assembled_tubes}.get(self.part_type,
                                                                                                   self._build_v_bracket)
            return build(inner_s, wall, outer_s, depth, h_dia, h_off)
        if self.part_type == "foot":
            return self._build_foot(inner_s, wall, outer_s, depth, h_dia, h_off)
        if self.part_type == "tubes":
            t_len = min(max(20.0, self.tube_length), 100.0)
            t_s = max(2.0, self.tube_size)
            return m3d.Manifold.cube([t_len, t_s, t_s], center=False).translate([0.0, -t_s / 2.0, 0.0])
        return self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off)

    def _build_v_bracket(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float,
                          bracket_angle: Optional[float] = None, translation: Optional[List[float]] = None) -> m3d.Manifold:
        ang = max(10.0, min(170.0, self.angle if bracket_angle is None else bracket_angle))
        half_a = math.radians(ang / 2.0)

        # Cavity inner corner - where inner corners of the two tube cavities meet
        x_cav_inner = (inner_s / 2.0) / math.tan(half_a)
        stop_margin = max(2.0, wall)
        x_stop = x_cav_inner + stop_margin
        x_end = x_stop + depth

        x_outer = -(outer_s / 2.0) / math.tan(half_a)
        arm_len = x_end - x_outer

        outer_box = m3d.Manifold.cube([arm_len, outer_s, outer_s], center=False).translate([x_outer, -outer_s / 2.0, 0.0])

        arm1_out = outer_box.rotate([0, 0, math.degrees(half_a)])
        arm2_out = outer_box.rotate([0, 0, -math.degrees(half_a)])
        solid = arm1_out + arm2_out

        # Truncate unnecessary fishtail / needle beak behind the waist (x = 0 for acute
        # brackets) while keeping at least stop_margin of solid wall behind the cavity (#164, #171).
        if ang < 90.0:
            x_cav_back = x_stop * math.cos(half_a) - (inner_s / 2.0) * math.sin(half_a)
            x_tip_limit = min(0.0, x_cav_back - stop_margin)
        else:
            x_tip_limit = -(inner_s / 2.0) / math.tan(half_a) - stop_margin
        x_back_min = x_outer * math.cos(half_a) - (outer_s / 2.0) * math.sin(half_a)
        if x_back_min < x_tip_limit:
            clip_box = m3d.Manifold.cube([200.0, 200.0, outer_s + 10.0], center=False).translate([x_tip_limit - 200.0, -100.0, -5.0])
            solid = solid - clip_box

        # Connector post on top of the plate (#167): needs the web to stand on, shifted
        # forward (#169, #170) so the post and its base chamfer clear the inner screw holes.
        want_post = self.post or self.second_star
        post_s = outer_s
        flare = max(1.0, wall * 0.75)
        post_h = max(10.0, self.post_height)
        hs = post_s / 2.0
        hb = hs + flare
        post_shift = 4.0
        x_vertex = (outer_s / 2.0) / math.sin(half_a)
        want_web = self.reinforcement or want_post
        web_len = min(depth * 0.5, 20.0)
        # The web's arm-side corners must stay inside the arms: along an arm the corner
        # lies at x/cos(a) - k*sin(a) and may not pass the arm end (spike, #166).
        k_embed = (outer_s / 2.0) / math.cos(half_a) - (wall * 0.5) / math.cos(half_a)
        x_front_max = math.cos(half_a) * (x_end - 1.0 + k_embed * math.sin(half_a))
        if want_post:
            web_len = max(web_len, post_s + 2.0 * flare + post_shift)
        else:
            web_len = max(1.0, min(web_len, x_front_max - x_vertex))

        # Reinforcement web between arms on both brackets (#165). Its arm-side corners end
        # half-way inside the arm walls so they never poke out as a spike (#166), while the
        # middle section extends forward when needed to carry the shifted post (#169, #170).
        if want_web:
            x_front = x_vertex + web_len
            x_arm = min(x_front, x_front_max)
            y_gap = x_arm * math.tan(half_a) - (outer_s / 2.0) / math.cos(half_a)
            y_embed = max(0.0, y_gap) + (wall * 0.5) / math.cos(half_a)
            x_in_end = x_end * math.cos(half_a) + (outer_s / 2.0) * math.sin(half_a)
            y_in_end = x_end * math.sin(half_a) - (outer_s / 2.0) * math.cos(half_a)
            if x_front > x_in_end and y_in_end > hb:
                pts = np.array([
                    [x_vertex - 0.5, 0.0],
                    [x_arm, -y_embed],
                    [x_in_end, -y_in_end],
                    [x_front, -hb],
                    [x_front, hb],
                    [x_in_end, y_in_end],
                    [x_arm, y_embed],
                ])
            elif x_front > x_arm + 1e-6:
                y_front = max(hb, x_front * math.tan(half_a) - (outer_s / 2.0) / math.cos(half_a))
                pts = np.array([
                    [x_vertex - 0.5, 0.0],
                    [x_arm, -y_embed],
                    [x_front, -y_front],
                    [x_front, y_front],
                    [x_arm, y_embed],
                ])
            else:
                pts = np.array([
                    [x_vertex - 0.5, 0.0],
                    [x_front, -y_embed],
                    [x_front, y_embed]
                ])
            cs = m3d.CrossSection([pts])
            web = m3d.Manifold.extrude(cs, outer_s)
            solid = solid + web

        post_cut = None
        if want_post:
            x_c = min(x_vertex + hb + post_shift, x_vertex + web_len - hb)
            z0 = outer_s - 0.01
            sleeve = m3d.Manifold.cube([post_s, post_s, post_h + 0.01], center=False).translate([x_c - hs, -hs, z0])
            base_pts = []
            for sx in (-1, 1):
                for sy in (-1, 1):
                    base_pts.append([x_c + sx * hb, sy * hb, z0])
                    base_pts.append([x_c + sx * hs, sy * hs, z0 + flare + 0.01])
            chamfer = m3d.Manifold.hull_points(np.array(base_pts))
            solid = solid + sleeve + chamfer
            z_top = outer_s + post_h
            socket = m3d.Manifold.cube([inner_s, inner_s, post_h + 1.0], center=False).translate(
                [x_c - inner_s / 2.0, -inner_s / 2.0, outer_s])
            z_hole = outer_s + max(flare + 2.0 + h_dia / 2.0, post_h * 0.5)
            z_hole = min(z_hole, z_top - h_dia / 2.0 - 2.0)
            side_hole = m3d.Manifold.cylinder(post_s + 2.0 * flare + 4.0, h_dia / 2.0, h_dia / 2.0, 32).rotate(
                [90, 0, 0]).translate([x_c, (post_s + 2.0 * flare + 4.0) / 2.0, z_hole])
            post_cut = socket + side_hole

        cav_len = depth + 1.0
        cavity = m3d.Manifold.cube([cav_len, inner_s, inner_s], center=False).translate([x_stop, -inner_s / 2.0, wall])

        # Screw holes (with optional double holes, #165)
        holes = []
        hole_x1 = x_end - h_off
        hole_h = outer_s + 4.0 + (flare + 1.0 if want_post else 0.0)
        h1 = m3d.Manifold.cylinder(hole_h, h_dia / 2.0, h_dia / 2.0, 32).translate([hole_x1, 0.0, -2.0])
        holes.append(h1)
        if self.double_holes:
            hole_x2 = hole_x1 - self.hole_spacing
            if hole_x2 >= x_stop + 3.0:
                h2 = m3d.Manifold.cylinder(hole_h, h_dia / 2.0, h_dia / 2.0, 32).translate([hole_x2, 0.0, -2.0])
                holes.append(h2)

        hole_solid = m3d.Manifold.batch_boolean(holes, m3d.OpType.Add) if len(holes) > 1 else holes[0]
        cutter1 = (cavity + hole_solid).rotate([0, 0, math.degrees(half_a)])
        cutter2 = (cavity + hole_solid).rotate([0, 0, -math.degrees(half_a)])

        result = solid - cutter1 - cutter2
        if post_cut is not None:
            result = result - post_cut
        trans = self.translation if translation is None else translation
        if any(abs(x) > 1e-9 for x in trans):
            result = result.translate(tuple(trans))
        return result

    def _build_foot(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float,
                    translation: Optional[List[float]] = None) -> m3d.Manifold:
        fw = max(15.0, self.foot_width)
        fl = max(20.0, self.foot_length)
        ft = max(2.0, self.foot_thickness)
        ang = max(5.0, min(85.0, self.foot_tube_angle))
        rad = math.radians(ang)

        base = m3d.Manifold.cube([fw, fl, ft], center=False).translate([-fw / 2.0, -fl / 2.0, 0.0])

        mount_hole_1 = m3d.Manifold.cylinder(ft + 2.0, 2.0, 2.0, 24).translate([0.0, -fl / 2.0 + 8.0, -1.0])
        mount_hole_2 = m3d.Manifold.cylinder(ft + 2.0, 2.0, 2.0, 24).translate([0.0, fl / 2.0 - 8.0, -1.0])
        base = base - mount_hole_1 - mount_hole_2

        socket_len = depth + 10.0
        socket_box = m3d.Manifold.cube([socket_len, outer_s, outer_s], center=False).translate([0.0, -outer_s / 2.0, 0.0])
        rot_socket = socket_box.rotate([0, -ang, 0]).translate([-fw / 4.0, 0.0, ft])

        gusset_len = socket_len * math.cos(rad)
        gusset_h = socket_len * math.sin(rad)
        gusset = m3d.Manifold.cube([gusset_len, outer_s, gusset_h], center=False).translate([-fw / 4.0, -outer_s / 2.0, ft])

        solid = base + rot_socket + gusset

        cavity = m3d.Manifold.cube([depth + 1.0, inner_s, inner_s], center=False).translate([socket_len - depth, -inner_s / 2.0, wall])
        holes = []
        hole1 = m3d.Manifold.cylinder(outer_s + 4.0, h_dia / 2.0, h_dia / 2.0, 32).rotate([90, 0, 0]).translate([socket_len - h_off, (outer_s + 4.0) / 2.0, outer_s / 2.0])
        holes.append(hole1)
        if self.double_holes:
            h2_x = socket_len - h_off - self.hole_spacing
            if h2_x >= socket_len - depth + 3.0:
                hole2 = m3d.Manifold.cylinder(outer_s + 4.0, h_dia / 2.0, h_dia / 2.0, 32).rotate([90, 0, 0]).translate([h2_x, (outer_s + 4.0) / 2.0, outer_s / 2.0])
                holes.append(hole2)
        hole_solid = m3d.Manifold.batch_boolean(holes, m3d.OpType.Add) if len(holes) > 1 else holes[0]

        cutter = (cavity + hole_solid).rotate([0, -ang, 0]).translate([-fw / 4.0, 0.0, ft])

        clip_box = m3d.Manifold.cube([fw * 3.0, fl * 3.0, 50.0], center=False).translate([-fw * 1.5, -fl * 1.5, -50.0])
        solid = (solid - clip_box) - cutter

        trans = self.translation if translation is None else translation
        if any(abs(x) > 1e-9 for x in trans):
            solid = solid.translate(tuple(trans))
        return solid

    def _post_center_x(self, outer_s: float, wall: float, depth: float, bracket_angle: float) -> float:
        ang = max(10.0, min(170.0, bracket_angle))
        half_a = math.radians(ang / 2.0)
        flare = max(1.0, wall * 0.75)
        hs = outer_s / 2.0
        hb = hs + flare
        post_shift = 4.0
        x_vertex = (outer_s / 2.0) / math.sin(half_a)
        web_len = max(min(depth * 0.5, 20.0), outer_s + 2.0 * flare + post_shift)
        return min(x_vertex + hb + post_shift, x_vertex + web_len - hb)

    def _build_assembled_outer(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float) -> m3d.Manifold:
        R_out, R_in, xs_out, xs_in = star_radii(self.tube_length, self.tube_size, self.clearance, self.wall_thickness, self.outer_angle, self.inner_angle)
        proto = self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off, bracket_angle=self.outer_angle, translation=[0, 0, 0])
        proto_top = None
        if self.second_star:
            cross_L = max(10.0, self.cross_tube_length)
            proto_top = proto.rotate([180.0, 0.0, 0.0]).translate([0.0, 0.0, 2.0 * outer_s + cross_L])
        brackets = []
        for k in range(5):
            a_deg = 90.0 - k * 72.0
            rad = math.radians(a_deg)
            tx = R_out * math.cos(rad)
            ty = R_out * math.sin(rad)
            placed = proto.rotate([0, 0, 180.0 + a_deg]).translate([tx, ty, 0.0])
            brackets.append(placed)
            if proto_top is not None:
                brackets.append(proto_top.rotate([0, 0, 180.0 + a_deg]).translate([tx, ty, 0.0]))
        return m3d.Manifold.batch_boolean(brackets, m3d.OpType.Add)

    def _build_assembled_inner(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float) -> m3d.Manifold:
        R_out, R_in, xs_out, xs_in = star_radii(self.tube_length, self.tube_size, self.clearance, self.wall_thickness, self.outer_angle, self.inner_angle)
        proto = self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off, bracket_angle=self.inner_angle, translation=[0, 0, 0])
        proto_top = None
        if self.second_star:
            cross_L = max(10.0, self.cross_tube_length)
            proto_top = proto.rotate([180.0, 0.0, 0.0]).translate([0.0, 0.0, 2.0 * outer_s + cross_L])
        brackets = []
        for k in range(5):
            a_deg = 90.0 - 36.0 - k * 72.0
            rad = math.radians(a_deg)
            vx = R_in * math.cos(rad)
            vy = R_in * math.sin(rad)
            placed = proto.rotate([0, 0, a_deg]).translate([vx, vy, 0.0])
            brackets.append(placed)
            if proto_top is not None:
                brackets.append(proto_top.rotate([0, 0, a_deg]).translate([vx, vy, 0.0]))
        return m3d.Manifold.batch_boolean(brackets, m3d.OpType.Add)

    def _build_assembled_tubes(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float) -> m3d.Manifold:
        R_out, R_in, xs_out, xs_in = star_radii(self.tube_length, self.tube_size, self.clearance, self.wall_thickness, self.outer_angle, self.inner_angle)
        tips = []
        valleys = []
        for k in range(5):
            a_tip = math.radians(90.0 - k * 72.0)
            tips.append((R_out * math.cos(a_tip), R_out * math.sin(a_tip)))
            a_val = math.radians(90.0 - 36.0 - k * 72.0)
            valleys.append((R_in * math.cos(a_val), R_in * math.sin(a_val)))

        t_len = max(10.0, self.tube_length)
        t_s = max(2.0, self.tube_size)
        tube_box = m3d.Manifold.cube([t_len, t_s, t_s], center=False).translate([0.0, -t_s / 2.0, wall + self.clearance / 2.0])

        tubes = []
        for k in range(5):
            t_pt = np.array(tips[k])
            v_pt = np.array(valleys[k])
            vec1 = v_pt - t_pt
            ang1 = math.degrees(math.atan2(vec1[1], vec1[0]))
            p1 = t_pt + (vec1 / np.linalg.norm(vec1)) * xs_out
            tubes.append(tube_box.rotate([0, 0, ang1]).translate([p1[0], p1[1], 0.0]))

            t_next = np.array(tips[(k + 1) % 5])
            vec2 = t_next - v_pt
            ang2 = math.degrees(math.atan2(vec2[1], vec2[0]))
            p2 = v_pt + (vec2 / np.linalg.norm(vec2)) * xs_in
            tubes.append(tube_box.rotate([0, 0, ang2]).translate([p2[0], p2[1], 0.0]))

        if self.second_star:
            cross_L = max(10.0, self.cross_tube_length)
            z_shift = outer_s + cross_L
            top_tubes = [tb.translate([0.0, 0.0, z_shift]) for tb in tubes]
            tubes.extend(top_tubes)

            vert_h = max(1.0, cross_L - self.clearance)
            vert_z = outer_s + self.clearance / 2.0
            xc_out = self._post_center_x(outer_s, wall, depth, self.outer_angle)
            xc_in = self._post_center_x(outer_s, wall, depth, self.inner_angle)
            v_out_proto = m3d.Manifold.cube([t_s, t_s, vert_h], center=False).translate([xc_out - t_s / 2.0, -t_s / 2.0, vert_z])
            v_in_proto = m3d.Manifold.cube([t_s, t_s, vert_h], center=False).translate([xc_in - t_s / 2.0, -t_s / 2.0, vert_z])
            for k in range(5):
                a_out_deg = 90.0 - k * 72.0
                tx, ty = tips[k]
                tubes.append(v_out_proto.rotate([0, 0, 180.0 + a_out_deg]).translate([tx, ty, 0.0]))
                a_in_deg = 90.0 - 36.0 - k * 72.0
                vx, vy = valleys[k]
                tubes.append(v_in_proto.rotate([0, 0, a_in_deg]).translate([vx, vy, 0.0]))

        return m3d.Manifold.batch_boolean(tubes, m3d.OpType.Add)

    def _build_assembled_feet(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float) -> m3d.Manifold:
        R_out, R_in, xs_out, xs_in = star_radii(self.tube_length, self.tube_size, self.clearance, self.wall_thickness, self.outer_angle, self.inner_angle)
        v2 = np.array([0.0, -R_in])
        a2 = math.radians(-54.0)
        t2 = np.array([R_out * math.cos(a2), R_out * math.sin(a2)])
        a3 = math.radians(-126.0)
        t3 = np.array([R_out * math.cos(a3), R_out * math.sin(a3)])

        p_r = v2 + 0.65 * (t2 - v2)
        p_l = v2 + 0.65 * (t3 - v2)

        proto = self._build_foot(inner_s, wall, outer_s, depth, h_dia, h_off, translation=[0, 0, 0])
        foot_r = proto.translate([p_r[0], p_r[1], 0.0])
        foot_l = proto.scale([-1.0, 1.0, 1.0]).translate([p_l[0], p_l[1], 0.0])
        return foot_r + foot_l



def run(ctx, params):
    p = dict(params)
    inner_s = p["tube_size"] + p["clearance"]
    span_outer = (inner_s / 2.0) / math.tan(math.radians(max(10.0, p["outer_angle"]) / 2.0)) + p["socket_depth"] + 10.0
    span_inner = (inner_s / 2.0) / math.tan(math.radians(max(10.0, p["inner_angle"]) / 2.0)) + p["socket_depth"] + 10.0
    step1 = span_outer + p["spacing"]
    step2 = step1 + span_inner + p["spacing"]
    many = "10x" if p["second_star"] else "5x"
    tubes = "30x" if p["second_star"] else "10x"
    if p["assembled"]:
        parts = [("outer", f"outer brackets ({many})", 0.0), ("inner", f"inner brackets ({many})", 0.0),
                 ("tubes", f"aluminium tubes ({tubes})", 0.0)]
    else:
        parts = [("outer", "outer bracket", 0.0), ("inner", "inner bracket", step1), ("tubes", "tube (sample)", step2)]
    bodies = []
    for part, label, dx in parts:
        shape = Bracket(part, p).build_solid()
        if dx:
            shape = shape.translate((dx, 0.0, 0.0))
        bodies.append(ctx.solid(shape, f"{ctx.name} - {label}"))
    ctx.group(ctx.name, bodies)
    R_out, R_in, _, _ = star_radii(p["tube_length"], p["tube_size"], p["clearance"], p["wall_thickness"],
                                   p["outer_angle"], p["inner_angle"])
    ctx.log(f"Star: tip radius {R_out:.1f} mm, valley radius {R_in:.1f} mm. Print 5 outer and 5 inner brackets"
            + (" (10 + 10 for two stars)." if p["second_star"] else "."))
