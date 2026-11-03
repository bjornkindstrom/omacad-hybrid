"""
Omacad - Star Bracket Feature
Parametric 3D printable brackets and foot supports for square aluminum tubes (e.g. advent stars).
Supports both print layout (individual parts) and full assembled view (10 tubes + 10 brackets + 2 feet).
"""

import math
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import manifold3d as m3d
from omacad.model.features.base import Feature, Body


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


class StarBracketFeature(Feature):
    def __init__(
        self,
        feature_id: str,
        name: str,
        part_type: str = "outer",  # "outer", "inner", "foot", "tubes"
        tube_size: float = 10.0,
        tube_length: float = 250.0,
        clearance: float = 0.25,
        wall_thickness: float = 2.5,
        socket_depth: float = 25.0,
        hole_diameter: float = 3.5,
        hole_offset: float = 12.0,
        double_holes: bool = False,
        hole_spacing: float = 15.0,
        reinforcement: bool = True,
        post: bool = False,
        post_height: float = 25.0,
        angle: float = 36.0,
        outer_angle: Optional[float] = None,
        inner_angle: Optional[float] = None,
        foot_width: float = 40.0,
        foot_length: float = 70.0,
        foot_thickness: float = 4.0,
        foot_tube_angle: float = 36.0,
        assembled: bool = False,
        translation: Any = None,
        **kwargs,
    ):
        super().__init__(feature_id, "star_bracket", name)
        self.part_type = str(part_type)
        self.tube_size = float(tube_size)
        self.tube_length = float(tube_length)
        self.clearance = float(clearance)
        self.wall_thickness = float(wall_thickness)
        self.socket_depth = float(socket_depth)
        self.hole_diameter = float(hole_diameter)
        self.hole_offset = float(hole_offset)
        self.double_holes = bool(double_holes)
        self.hole_spacing = float(hole_spacing)
        self.reinforcement = bool(reinforcement)
        self.post = bool(post)
        self.post_height = float(post_height)

        if outer_angle is not None:
            self.outer_angle = float(outer_angle)
        elif "outer_angle" in kwargs:
            self.outer_angle = float(kwargs["outer_angle"])
        elif part_type == "outer":
            self.outer_angle = float(angle)
        elif part_type == "inner":
            self.outer_angle = float(angle) - 72.0
        elif "inner_angle" in kwargs:
            self.outer_angle = float(kwargs["inner_angle"]) - 72.0
        else:
            self.outer_angle = float(angle) if float(angle) != 0.0 else 36.0

        if inner_angle is not None:
            self.inner_angle = float(inner_angle)
        elif "inner_angle" in kwargs:
            self.inner_angle = float(kwargs["inner_angle"])
        elif part_type == "inner":
            self.inner_angle = float(angle)
        else:
            self.inner_angle = self.outer_angle + 72.0

        if part_type == "outer":
            self.angle = self.outer_angle
        elif part_type == "inner":
            self.angle = self.inner_angle
        elif part_type == "foot":
            self.angle = float(foot_tube_angle)
        else:
            self.angle = float(angle)

        self.foot_width = float(foot_width)
        self.foot_length = float(foot_length)
        self.foot_thickness = float(foot_thickness)
        self.foot_tube_angle = float(foot_tube_angle)
        self.assembled = bool(assembled)
        self.translation = [float(x) for x in ((0.0, 0.0, 0.0) if translation is None else translation)]

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

        # Truncate needle beak if unnecessarily long (past outer cavity corner + stop margin) (#164)
        x_tip_limit = -(inner_s / 2.0) / math.tan(half_a) - stop_margin
        if x_outer < x_tip_limit:
            clip_box = m3d.Manifold.cube([100.0, 200.0, outer_s + 10.0], center=False).translate([x_tip_limit - 100.0, -100.0, -5.0])
            solid = solid - clip_box

        # Connector post on top of the plate (#167): needs the web to stand on, shifted
        # forward (#169, #170) so the post and its base chamfer clear the inner screw holes.
        post_s = outer_s
        flare = max(1.0, wall * 0.75)
        post_h = max(10.0, self.post_height)
        hs = post_s / 2.0
        hb = hs + flare
        post_shift = 4.0
        x_vertex = (outer_s / 2.0) / math.sin(half_a)
        want_web = self.reinforcement or self.post
        web_len = min(depth * 0.5, 20.0)
        # The web's arm-side corners must stay inside the arms: along an arm the corner
        # lies at x/cos(a) - k*sin(a) and may not pass the arm end (spike, #166).
        k_embed = (outer_s / 2.0) / math.cos(half_a) - (wall * 0.5) / math.cos(half_a)
        x_front_max = math.cos(half_a) * (x_end - 1.0 + k_embed * math.sin(half_a))
        if self.post:
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
        if self.post:
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
        hole_h = outer_s + 4.0 + (flare + 1.0 if self.post else 0.0)
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

    def _build_assembled_outer(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float) -> m3d.Manifold:
        R_out, R_in, xs_out, xs_in = star_radii(self.tube_length, self.tube_size, self.clearance, self.wall_thickness, self.outer_angle, self.inner_angle)
        proto = self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off, bracket_angle=self.outer_angle, translation=[0, 0, 0])
        brackets = []
        for k in range(5):
            a_deg = 90.0 - k * 72.0
            rad = math.radians(a_deg)
            tx = R_out * math.cos(rad)
            ty = R_out * math.sin(rad)
            placed = proto.rotate([0, 0, 180.0 + a_deg]).translate([tx, ty, 0.0])
            brackets.append(placed)
        return m3d.Manifold.batch_boolean(brackets, m3d.OpType.Add)

    def _build_assembled_inner(self, inner_s: float, wall: float, outer_s: float, depth: float, h_dia: float, h_off: float) -> m3d.Manifold:
        R_out, R_in, xs_out, xs_in = star_radii(self.tube_length, self.tube_size, self.clearance, self.wall_thickness, self.outer_angle, self.inner_angle)
        proto = self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off, bracket_angle=self.inner_angle, translation=[0, 0, 0])
        brackets = []
        for k in range(5):
            a_deg = 90.0 - 36.0 - k * 72.0
            rad = math.radians(a_deg)
            vx = R_in * math.cos(rad)
            vy = R_in * math.sin(rad)
            placed = proto.rotate([0, 0, a_deg]).translate([vx, vy, 0.0])
            brackets.append(placed)
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

    def build_solid(self) -> m3d.Manifold:
        inner_s = max(1.0, self.tube_size + self.clearance)
        wall = max(0.8, self.wall_thickness)
        outer_s = inner_s + 2.0 * wall
        depth = max(5.0, self.socket_depth)
        h_dia = max(1.0, self.hole_diameter)
        h_off = max(2.0, min(depth - 2.0, self.hole_offset))

        if self.assembled:
            if self.part_type == "outer":
                return self._build_assembled_outer(inner_s, wall, outer_s, depth, h_dia, h_off)
            elif self.part_type == "inner":
                return self._build_assembled_inner(inner_s, wall, outer_s, depth, h_dia, h_off)
            elif self.part_type == "foot":
                return self._build_assembled_feet(inner_s, wall, outer_s, depth, h_dia, h_off)
            elif self.part_type == "tubes":
                return self._build_assembled_tubes(inner_s, wall, outer_s, depth, h_dia, h_off)
            else:
                return self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off)
        else:
            if self.part_type == "foot":
                return self._build_foot(inner_s, wall, outer_s, depth, h_dia, h_off)
            elif self.part_type == "tubes":
                t_len = min(max(20.0, self.tube_length), 100.0)
                t_s = max(2.0, self.tube_size)
                res = m3d.Manifold.cube([t_len, t_s, t_s], center=False).translate([0.0, -t_s / 2.0, 0.0])
                if any(abs(x) > 1e-9 for x in self.translation):
                    res = res.translate(tuple(self.translation))
                return res
            else:
                return self._build_v_bracket(inner_s, wall, outer_s, depth, h_dia, h_off)

    def execute(self, doc: Any) -> None:
        solid = self.build_solid()
        body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "part_type": self.part_type,
            "tube_size": self.tube_size,
            "tube_length": self.tube_length,
            "clearance": self.clearance,
            "wall_thickness": self.wall_thickness,
            "socket_depth": self.socket_depth,
            "hole_diameter": self.hole_diameter,
            "hole_offset": self.hole_offset,
            "double_holes": self.double_holes,
            "hole_spacing": self.hole_spacing,
            "reinforcement": self.reinforcement,
            "post": self.post,
            "post_height": self.post_height,
            "angle": self.angle,
            "outer_angle": self.outer_angle,
            "inner_angle": self.inner_angle,
            "foot_width": self.foot_width,
            "foot_length": self.foot_length,
            "foot_thickness": self.foot_thickness,
            "foot_tube_angle": self.foot_tube_angle,
            "assembled": self.assembled,
            "translation": list(self.translation),
            "exprs": dict(self.exprs),
        }
