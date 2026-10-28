"""
Omacad - Primitive Features (Box, Cylinder, Prism, Sphere) and SketchFeature
"""

import math

from typing import Dict, Any
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.sketch import Sketch
from omacad.model.features.base import Feature, Body


def _rect_cross_section(lx: float, wy: float, r: float, kind: str) -> m3d.CrossSection:
    """2D cross-section centered at (0, 0) of size lx x wy with corner fillet or chamfer `r`."""
    import math
    from omacad.model import quality
    hx, hy = lx / 2.0, wy / 2.0
    r = max(0.0, min(float(r), hx - 0.01, hy - 0.01))
    if r <= 1e-4:
        return m3d.CrossSection.square((lx, wy), center=True)
    if kind == "chamfer":
        pts = [
            (hx - r, -hy), (hx, -hy + r),
            (hx, hy - r), (hx - r, hy),
            (-hx + r, hy), (-hx, hy - r),
            (-hx, -hy + r), (-hx + r, -hy),
        ]
        return m3d.CrossSection([pts])
    n_arc = max(6, quality.circle_segments() // 4)
    pts = []
    corners = [
        (hx - r, -hy + r, -math.pi / 2.0, 0.0),
        (hx - r, hy - r, 0.0, math.pi / 2.0),
        (-hx + r, hy - r, math.pi / 2.0, math.pi),
        (-hx + r, -hy + r, math.pi, 1.5 * math.pi),
    ]
    for cx, cy, a0, a1 in corners:
        for k in range(n_arc + 1):
            a = a0 + (a1 - a0) * k / n_arc
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return m3d.CrossSection([pts])


def _rounded_prism(lx: float, wy: float, hz: float, r: float, kind: str, round_top: bool = True, taper: float = 0.0) -> m3d.Manifold:
    """Prism centered in XY, z in [0, hz], with vertical corners and bottom (plus optionally top) edges rounded/chamfered."""
    import math
    from omacad.model import quality
    hx, hy = lx / 2.0, wy / 2.0
    max_r = min(hx - 0.02, hy - 0.02, hx-hz*taper-0.02, hy-hz*taper-0.02,
                (hz / 2.0 if round_top else hz) - 0.02)
    r = max(0.0, min(float(r), max_r))
    if r <= 1e-4:
        return m3d.Manifold.extrude(_rect_cross_section(lx, wy, 0.0, kind), hz,
                                   scale_top=((lx-2*hz*taper)/lx, (wy-2*hz*taper)/wy))
    n_steps = 1 if kind == "chamfer" else max(6, quality.circle_segments() // 4)
    z_levels = [0.0]
    for k in range(1, n_steps + 1):
        if kind == "chamfer":
            z_levels.append(r * k / n_steps)
        else:
            theta = (math.pi / 2.0) * (1.0 - k / n_steps)
            z_levels.append(r * (1.0 - math.sin(theta)))
    if round_top:
        top_start = hz - r
        if top_start > z_levels[-1] + 1e-4:
            z_levels.append(top_start)
        for k in range(1, n_steps + 1):
            if kind == "chamfer":
                z_levels.append(hz - r * (1.0 - k / n_steps))
            else:
                theta = (math.pi / 2.0) * (k / n_steps)
                z_levels.append(hz - r * (1.0 - math.sin(theta)))
    else:
        if hz > z_levels[-1] + 1e-4:
            z_levels.append(hz)

    def inset_at(z: float) -> float:
        if z < r - 1e-6:
            dz = r - z
            return dz if kind == "chamfer" else (r - math.sqrt(max(0.0, r * r - dz * dz)))
        if round_top and z > hz - r + 1e-6:
            dz = z - (hz - r)
            return dz if kind == "chamfer" else (r - math.sqrt(max(0.0, r * r - dz * dz)))
        return 0.0

    # Build via convex hull of consecutive layer slabs for guaranteed watertight manifold
    slabs = []
    eps = 1e-3
    for i in range(len(z_levels) - 1):
        z0, z1 = z_levels[i], z_levels[i + 1]
        if z1 - z0 < 1e-6:
            continue
        ins0, ins1 = inset_at(z0), inset_at(z1)
        if abs(ins0 - ins1) < 1e-6 and abs(taper) < 1e-12:
            cs = _rect_cross_section(lx - 2 * ins0, wy - 2 * ins0, max(0.0, r - ins0), kind)
            slabs.append(m3d.Manifold.extrude(cs, z1 - z0).translate((0.0, 0.0, z0)))
        else:
            cs0 = _rect_cross_section(lx - 2 * ins0 - 2*z0*taper, wy - 2 * ins0 - 2*z0*taper, max(0.0, r - ins0), kind)
            cs1 = _rect_cross_section(lx - 2 * ins1 - 2*z1*taper, wy - 2 * ins1 - 2*z1*taper, max(0.0, r - ins1), kind)
            p0 = m3d.Manifold.extrude(cs0, eps).translate((0.0, 0.0, z0))
            p1 = m3d.Manifold.extrude(cs1, eps).translate((0.0, 0.0, z1 - eps))
            slabs.append((p0 + p1).hull())
    return m3d.Manifold.batch_boolean(slabs, m3d.OpType.Add) if len(slabs) > 1 else slabs[0]



def _tapered_primitive(feat, kind):
    """Inward draft from the bottom, with constant normal wall and floor thickness."""
    angle = feat.taper_angle
    if not math.isfinite(angle) or abs(angle) >= 89:
        raise ValueError("Taper angle must be between -89 and 89 degrees.")
    slope = math.tan(math.radians(angle))
    h = feat.height
    sizes = [feat.length/2, feat.width/2] if kind == "box" else [feat.radius]
    if min(min(sizes), min(size-h*slope for size in sizes)) <= 0.001:
        raise ValueError("Taper closes the top. Reduce the angle or height.")
    hollow = feat.wall_thickness > 1e-4

    def build(half_sizes, height, radius, rounding, top):
        if kind == "box":
            return _rounded_prism(2*half_sizes[0], 2*half_sizes[1], height, radius, rounding, top, taper=slope)
        return _rounded_cylinder(half_sizes[0], height, radius, rounding, top, taper=slope,
                                 sides=getattr(feat, "sides", 0))

    solid = build(sizes, h, feat.outer_round, feat.outer_round_kind, not hollow)
    if hollow:
        t = feat.wall_thickness
        if t >= h:
            raise ValueError("Shell thickness must be smaller than the height.")
        offset = t / math.cos(math.radians(angle))
        inner = [size-t*slope-offset for size in sizes]
        # Extend the cavity just beyond the top to guarantee a clean opening.
        cavity_h = h-t+0.001
        if min(min(inner), min(size-cavity_h*slope for size in inner)) <= 0.001:
            raise ValueError("Shell thickness and taper leave no opening. Reduce the thickness or angle.")
        cavity = build(inner, cavity_h, feat.inner_round, feat.inner_round_kind, False)
        solid -= cavity.translate((0., 0., t))
    return solid


class BoxFeature(Feature):
    def __init__(self, feature_id: str, name: str, length: float, width: float, height: float, center: Any = False,
                 plane_origin: Any = None, plane_normal: Any = None, plane_u: Any = None, plane_v: Any = None,
                 wall_thickness: float = 0.0, outer_round: float = 0.0, outer_round_kind: str = "fillet",
                 inner_round: float = 0.0, inner_round_kind: str = "fillet", taper_angle: float = 0.0,
                 translation: Any = None):
        super().__init__(feature_id, "box", name)
        self.length = float(length)
        self.width = float(width)
        self.height = float(height)
        self.center = center  # True (full center), False (corner), or "bottom_center" / "center" / "corner"
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.plane_u = [float(x) for x in plane_u] if plane_u is not None else None
        self.plane_v = [float(x) for x in plane_v] if plane_v is not None else None
        self.wall_thickness = float(wall_thickness)
        self.outer_round = float(outer_round)
        self.outer_round_kind = str(outer_round_kind or "fillet")
        self.inner_round = float(inner_round)
        self.inner_round_kind = str(inner_round_kind or "fillet")
        self.taper_angle = float(taper_angle)
        self.translation = [float(x) for x in ((0.0, 0.0, 0.0) if translation is None else translation)]

    def build_solid(self) -> m3d.Manifold:
        is_centered = (self.center is True or self.center == "center")
        is_bottom = (self.center == "bottom_center")
        hollow = self.wall_thickness > 1e-4
        has_smart = hollow or self.outer_round > 1e-4 or self.inner_round > 1e-4

        if self.taper_angle != 0.0:
            solid = _tapered_primitive(self, "box")
            if is_centered:
                solid = solid.translate((0., 0., -self.height/2))
            elif not is_bottom:
                solid = solid.translate((self.length/2, self.width/2, 0.))
        elif not has_smart:
            solid = CadKernel.create_box(self.length, self.width, self.height, is_centered)
            if is_bottom:
                solid = solid.translate((-self.length / 2.0, -self.width / 2.0, 0.0))
        else:
            # Build in bottom-centered coordinates (XY centered, Z in 0..height), then shift to requested center mode
            solid = _rounded_prism(self.length, self.width, self.height, self.outer_round, self.outer_round_kind,
                                   round_top=not hollow)
            if hollow:
                t = min(self.wall_thickness, min(self.length, self.width) * 0.45, self.height * 0.9)
                in_l = max(0.2, self.length - 2.0 * t)
                in_w = max(0.2, self.width - 2.0 * t)
                in_h = max(0.2, self.height - t) + 1.0
                cavity = _rounded_prism(in_l, in_w, in_h, self.inner_round, self.inner_round_kind, round_top=False)
                solid = solid - cavity.translate((0.0, 0.0, t))
            if is_centered:
                solid = solid.translate((0.0, 0.0, -self.height / 2.0))
            elif not is_bottom:
                solid = solid.translate((self.length / 2.0, self.width / 2.0, 0.0))

        if self.plane_origin is not None and self.plane_normal is not None:
            n = np.array(self.plane_normal, dtype=float)
            n_len = float(np.linalg.norm(n))
            if n_len > 1e-12:
                n = n / n_len
                if self.plane_u is not None and self.plane_v is not None:
                    u = np.array(self.plane_u, dtype=float)
                    u = u / max(float(np.linalg.norm(u)), 1e-12)
                    v = np.array(self.plane_v, dtype=float)
                    v = v / max(float(np.linalg.norm(v)), 1e-12)
                else:
                    hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                    u = hint - np.dot(hint, n) * n
                    u /= np.linalg.norm(u)
                    v = np.cross(n, u)
                mat = np.column_stack([u, v, n, np.array(self.plane_origin, dtype=float)]).astype(float)
                solid = solid.transform(mat)
        if any(abs(x) > 1e-12 for x in self.translation):
            solid = solid.translate(tuple(self.translation))
        return solid

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
            "length": self.length,
            "width": self.width,
            "height": self.height,
            "center": self.center,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
            "translation": self.translation,
            "taper_angle": self.taper_angle,
            "wall_thickness": self.wall_thickness,
            "outer_round": self.outer_round,
            "outer_round_kind": self.outer_round_kind,
            "inner_round": self.inner_round,
            "inner_round_kind": self.inner_round_kind,
        }


def _rounded_cylinder(radius: float, height: float, r: float, kind: str, round_top: bool = True, taper: float = 0.0,
                      sides: int = 0) -> m3d.Manifold:
    """Cylinder of `radius` and `height` (z in 0..height) with bottom (and optionally top) rim rounded/chamfered.
    `sides` >= 3 gives a regular prism instead (hexagon ...), `radius` being centre to flat and a flat facing +X:
    it is revolved with `sides` segments and scaled so every ring's flats sit at the profile's radius, so the wall,
    the rounds and the taper are measured square to the flats."""
    from omacad.model import quality
    if sides < 3:
        return _revolved_cylinder(radius, height, r, kind, round_top, taper, quality.circle_segments())
    k = 1.0 / math.cos(math.pi / sides)
    solid = _revolved_cylinder(radius, height, r, kind, round_top, taper, sides)
    return solid.rotate((0.0, 0.0, 180.0 / sides)).scale((k, k, 1.0))


def _revolved_cylinder(radius: float, height: float, r: float, kind: str, round_top: bool, taper: float,
                       segments: int) -> m3d.Manifold:
    from omacad.model import quality
    max_r = min(radius - 0.02, radius-height*taper-0.02,
                (height / 2.0 if round_top else height) - 0.02)
    r = max(0.0, min(float(r), max_r))
    if r <= 1e-4:
        return m3d.Manifold.cylinder(height, radius, radius-height*taper, circular_segments=segments)
    n_arc = 1 if kind == "chamfer" else max(6, quality.circle_segments() // 4)
    pts = [(0.0, 0.0), (radius - r, 0.0)]
    if kind == "chamfer":
        pts.append((radius, r))
    else:
        for k in range(1, n_arc + 1):
            a = -math.pi / 2.0 + (math.pi / 2.0) * k / n_arc
            pts.append((radius - r + r * math.cos(a), r + r * math.sin(a)))
    if round_top:
        if kind == "chamfer":
            pts.extend([(radius, height - r), (radius - r, height)])
        else:
            for k in range(n_arc + 1):
                a = (math.pi / 2.0) * k / n_arc
                pts.append((radius - r + r * math.cos(a), height - r + r * math.sin(a)))
    else:
        pts.append((radius, height))
    pts.append((0.0, height))
    pts = [(x-z*taper if x > 0 else 0., z) for x, z in pts]
    cs = m3d.CrossSection([pts])
    return m3d.Manifold.revolve(cs, circular_segments=segments)


class CylinderFeature(Feature):
    def __init__(self, feature_id: str, name: str, radius: float, height: float, center: Any = False,
                 plane_origin: Any = None, plane_normal: Any = None, plane_u: Any = None, plane_v: Any = None,
                 wall_thickness: float = 0.0, outer_round: float = 0.0, outer_round_kind: str = "fillet",
                 inner_round: float = 0.0, inner_round_kind: str = "fillet", taper_angle: float = 0.0,
                 translation: Any = None):
        super().__init__(feature_id, "cylinder", name)
        self.radius = float(radius)
        self.height = float(height)
        self.center = center  # True (full center), False / "bottom_center" (bottom centered on origin)
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.plane_u = [float(x) for x in plane_u] if plane_u is not None else None
        self.plane_v = [float(x) for x in plane_v] if plane_v is not None else None
        self.wall_thickness = float(wall_thickness)
        self.outer_round = float(outer_round)
        self.outer_round_kind = str(outer_round_kind or "fillet")
        self.inner_round = float(inner_round)
        self.inner_round_kind = str(inner_round_kind or "fillet")
        self.taper_angle = float(taper_angle)
        self.translation = [float(x) for x in ((0.0, 0.0, 0.0) if translation is None else translation)]
        self.sides = 0  # round; PrismFeature sets 3+

    def build_solid(self) -> m3d.Manifold:
        is_centered = (self.center is True or self.center == "center")
        hollow = self.wall_thickness > 1e-4
        has_smart = hollow or self.outer_round > 1e-4 or self.inner_round > 1e-4

        if self.taper_angle != 0.0:
            solid = _tapered_primitive(self, "cylinder")
            if is_centered:
                solid = solid.translate((0., 0., -self.height/2))
        elif not has_smart and not self.sides:
            solid = CadKernel.create_cylinder(self.radius, self.height, center=is_centered)
        else:
            solid = _rounded_cylinder(self.radius, self.height, self.outer_round, self.outer_round_kind,
                                      round_top=not hollow, sides=self.sides)
            if hollow:
                t = min(self.wall_thickness, self.radius * 0.9, self.height * 0.9)
                in_r = max(0.1, self.radius - t)
                in_h = max(0.2, self.height - t) + 1.0
                cavity = _rounded_cylinder(in_r, in_h, self.inner_round, self.inner_round_kind, round_top=False,
                                           sides=self.sides)
                solid = solid - cavity.translate((0.0, 0.0, t))
            if is_centered:
                solid = solid.translate((0.0, 0.0, -self.height / 2.0))
        return self._place(solid)

    def _place(self, solid: m3d.Manifold) -> m3d.Manifold:
        """The solid built round the Z axis moved onto its plane (a picked face) and shifted by the translation."""
        if self.plane_origin is not None and self.plane_normal is not None:
            n = np.array(self.plane_normal, dtype=float)
            n_len = float(np.linalg.norm(n))
            if n_len > 1e-12:
                n = n / n_len
                if self.plane_u is not None and self.plane_v is not None:
                    u = np.array(self.plane_u, dtype=float)
                    u = u / max(float(np.linalg.norm(u)), 1e-12)
                    v = np.array(self.plane_v, dtype=float)
                    v = v / max(float(np.linalg.norm(v)), 1e-12)
                else:
                    hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                    u = hint - np.dot(hint, n) * n
                    u /= np.linalg.norm(u)
                    v = np.cross(n, u)
                mat = np.column_stack([u, v, n, np.array(self.plane_origin, dtype=float)]).astype(float)
                solid = solid.transform(mat)
        if any(abs(x) > 1e-12 for x in self.translation):
            solid = solid.translate(tuple(self.translation))
        return solid

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
            "radius": self.radius,
            "height": self.height,
            "center": self.center,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "plane_u": self.plane_u,
            "plane_v": self.plane_v,
            "translation": self.translation,
            "taper_angle": self.taper_angle,
            "wall_thickness": self.wall_thickness,
            "outer_round": self.outer_round,
            "outer_round_kind": self.outer_round_kind,
            "inner_round": self.inner_round,
            "inner_round_kind": self.inner_round_kind,
        }



class ConeFeature(CylinderFeature):
    """A cone or frustum (Björn #46): bottom `radius`, `top_radius` (0 = a point) and height, placed like a Cylinder.
    Shell Wall hollows it with the wall square to the slanted side; the top stays open while there is room for it."""

    def __init__(self, feature_id: str, name: str, radius: float, height: float, center: Any = False,
                 top_radius: float = 0.0, **kw):
        kw.pop("taper_angle", None)
        super().__init__(feature_id, name, radius, height, center, **kw)
        self.feature_type = "cone"
        self.top_radius = max(0.0, float(top_radius))

    def build_solid(self) -> m3d.Manifold:
        r, rt, h = self.radius, self.top_radius, self.height
        if r <= 1e-6 or h <= 1e-6:
            raise ValueError("The cone needs a radius and a height.")
        from omacad.model import quality
        seg = quality.circle_segments()
        solid = m3d.Manifold.cylinder(h, r, rt, circular_segments=seg)
        t = self.wall_thickness
        if t > 1e-4:
            if t >= h or t >= r:
                raise ValueError("Shell wall must be thinner than the radius and the height.")
            slope = (r - rt) / h
            grow = t * math.sqrt(1.0 + slope * slope)        # wall square to the slanted side
            r_in = lambda z: r - z * slope - grow
            if r_in(t) <= 0.05:
                raise ValueError("Shell wall too thick for this cone.")
            if r_in(h) > 0.05:                                # open top, cut a hair past it
                cavity = m3d.Manifold.cylinder(h - t + 1e-3, r_in(t), r_in(h + 1e-3), circular_segments=seg)
            else:                                             # pointed: a closed hollow up to the inner tip
                tip = (r - grow) / slope
                cavity = m3d.Manifold.cylinder(tip - t, r_in(t), 0.0, circular_segments=seg)
            solid = solid - cavity.translate((0.0, 0.0, t))
        if self.center is True or self.center == "center":
            solid = solid.translate((0.0, 0.0, -h / 2.0))
        return self._place(solid)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["top_radius"] = self.top_radius
        return d


class PrismFeature(CylinderFeature):
    """A regular prism (hexagon by default) with every Cylinder option: shell, rounds, taper, placement.
    It is sized across flats; `radius` holds centre to flat, so the Cylinder maths measures to the flats."""

    def __init__(self, feature_id: str, name: str, across_flats: float, height: float, center: Any = False,
                 sides: int = 6, **kwargs):
        super().__init__(feature_id, name, float(across_flats) / 2.0, height, center, **kwargs)
        self.feature_type = "prism"
        self.sides = int(sides)
        if self.sides < 3:
            raise ValueError("A prism needs at least 3 sides.")

    @property
    def across_flats(self) -> float:
        return 2.0 * self.radius

    @across_flats.setter
    def across_flats(self, value: float) -> None:
        self.radius = float(value) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.pop("radius")
        d["across_flats"] = self.across_flats
        d["sides"] = self.sides
        return d

class SphereFeature(Feature):
    def __init__(self, feature_id: str, name: str, radius: float, translation: Any = None):
        super().__init__(feature_id, "sphere", name)
        self.radius = float(radius)
        self.translation = [float(x) for x in ((0.0, 0.0, 0.0) if translation is None else translation)]

    def execute(self, doc: Any) -> None:
        solid = CadKernel.create_sphere(self.radius).translate(tuple(self.translation))
        body = Body(body_id=f"body_{self.feature_id}", name=self.name, manifold=solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "radius": self.radius,
            "translation": self.translation,
        }


class SketchFeature(Feature):
    def __init__(self, feature_id: str, name: str, sketch: Sketch, reference_bodies=None):
        super().__init__(feature_id, "sketch", name)
        self.sketch = sketch
        # Bodies whose face outlines close the profiles; None = every body built so far. A copied object's sketch
        # sees only the copies of what the original saw, not the original body lying in the same place (#108).
        self.reference_bodies = list(reference_bodies) if reference_bodies is not None else None

    def execute(self, doc: Any) -> None:
        # Register sketch in doc; face outlines of the bodies built so far close its profiles
        doc.refresh_sketch_references(self.sketch, self.reference_bodies)
        doc.sketches[self.sketch.sketch_id] = self.sketch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "sketch": self.sketch.to_dict(),
            **({"reference_bodies": self.reference_bodies} if self.reference_bodies is not None else {}),
        }
