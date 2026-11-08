"""Omacad script: Box in a Row - boxes side by side, optionally with sliding lids, honeycomb and rounded corners.

A copy of Omacad's built-in Box in a Row tool with all its geometry code (the box, its lid rails, the sliding lid
with its thumb slot, the honeycomb), so you (or an AI) can change anything. Use "Modify with AI…" in the Box in a
Row menu to make a changed copy; this file stays as it is."""
import math

import manifold3d as m3d
import numpy as np
from shapely.geometry import Polygon, box as sbox
from shapely.geometry.polygon import orient

NAME = "Box in a Row (script)"
FAMILY = "box_row"            # listed in the Box in a Row submenu
OUTPUT_NAME = "Box"
DESCRIPTION = "Boxes in a row with optional sliding lids (printable rails), rounded or chamfered corners and honeycomb."
PARAMS = [
    {"name": "count", "label": "Number of boxes", "type": "int", "default": 2, "min": 1, "max": 30},
    {"name": "length", "label": "Length (X)", "type": "float", "default": 60.0, "min": 5.0, "max": 1000.0, "unit": "mm"},
    {"name": "width", "label": "Width (Y)", "type": "float", "default": 40.0, "min": 5.0, "max": 1000.0, "unit": "mm"},
    {"name": "height", "label": "Inside height (Z)", "type": "float", "default": 30.0, "min": 2.0, "max": 1000.0, "unit": "mm",
     "help": "Free height inside, from the floor up to the lid (or the rim without a lid)."},
    {"name": "spacing", "label": "Spacing", "type": "float", "default": 0.0, "min": 0.0, "max": 500.0, "unit": "mm"},
    {"name": "wall_thickness", "label": "Wall thickness", "type": "float", "default": 2.0, "min": 0.4, "max": 50.0, "unit": "mm"},
    {"name": "bottom_thickness", "label": "Bottom thickness", "type": "float", "default": 2.0, "min": 0.4, "max": 50.0, "unit": "mm"},
    {"name": "outer_round", "label": "Outer round", "type": "float", "default": 0.0, "min": 0.0, "max": 100.0, "unit": "mm"},
    {"name": "outer_round_kind", "label": "Outer corners", "type": "choice", "default": "fillet", "choices": ["fillet", "chamfer"]},
    {"name": "inner_round", "label": "Inner round", "type": "float", "default": 0.0, "min": 0.0, "max": 100.0, "unit": "mm"},
    {"name": "inner_round_kind", "label": "Inner corners", "type": "choice", "default": "fillet", "choices": ["fillet", "chamfer"]},
    {"name": "honeycomb", "label": "Honeycomb", "type": "bool", "default": False},
    {"name": "honeycomb_size", "label": "Cell size", "type": "float", "default": 5.0, "min": 1.0, "max": 100.0, "unit": "mm"},
    {"name": "honeycomb_wall", "label": "Cell wall", "type": "float", "default": 1.2, "min": 0.4, "max": 20.0, "unit": "mm"},
    {"name": "honeycomb_margin", "label": "Cell margin", "type": "float", "default": 2.0, "min": 0.0, "max": 50.0, "unit": "mm"},
    {"name": "has_lid", "label": "Sliding lid", "type": "bool", "default": False},
    {"name": "lip_height", "label": "Lid groove height", "type": "float", "default": 6.0, "min": 0.5, "max": 50.0, "unit": "mm"},
    {"name": "lip_step", "label": "Lid rail depth", "type": "float", "default": 1.0, "min": 0.1, "max": 10.0, "unit": "mm"},
    {"name": "clearance", "label": "Print clearance", "type": "float", "default": 0.2, "min": 0.0, "max": 2.0, "step": 0.05, "unit": "mm"},
    {"name": "lid_top", "label": "Lid thickness", "type": "float", "default": 2.0, "min": 0.4, "max": 20.0, "unit": "mm"},
    {"name": "tab_size", "label": "Thumb slot size", "type": "float", "default": 4.0, "min": 0.5, "max": 50.0, "unit": "mm"},
    {"name": "slot_length", "label": "Slot length (0 = auto)", "type": "float", "default": 0.0, "min": 0.0, "max": 500.0, "unit": "mm"},
    {"name": "slot_width", "label": "Slot width (0 = auto)", "type": "float", "default": 0.0, "min": 0.0, "max": 100.0, "unit": "mm"},
]

SEGMENTS = {"circle": 96, "sphere": 72}     # set from the model's curve smoothness in run()
LOG = print                                 # ctx.log in run()


def circle_segments():
    return SEGMENTS["circle"]


def sphere_segments():
    return SEGMENTS["sphere"]


def profile_cross_section(profile):
    """CrossSection (with holes) of a polygon given as .exterior_pts / .interior_holes."""
    poly = orient(Polygon(profile.exterior_pts, profile.interior_holes), sign=1.0)
    cs = m3d.CrossSection([list(poly.exterior.coords)[:-1]])
    for h in poly.interiors:
        ring = list(h.coords)[:-1]
        if Polygon(ring).exterior.is_ccw is False:
            ring.reverse()
        cs = cs - m3d.CrossSection([ring])
    return cs


def region_cross_section(geom):
    """CrossSection of a shapely polygon or multipolygon (holes included)."""
    from types import SimpleNamespace
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    cs = None
    for poly in polys:
        if poly.is_empty or poly.area < 1e-9:
            continue
        part = profile_cross_section(SimpleNamespace(exterior_pts=list(poly.exterior.coords)[:-1],
                                                     interior_holes=[list(r.coords)[:-1] for r in poly.interiors]))
        cs = part if cs is None else cs + part
    return cs if cs is not None else m3d.CrossSection([])


def hex_cells(size, wall, room):
    """Hexagonal cells `size` across the flats with `wall` between them, the whole ones inside `room` (one cell
    centred on the origin)."""
    from shapely import affinity
    from shapely.prepared import prep
    p = size + wall
    cell = Polygon([(size / math.sqrt(3) * math.cos(math.radians(90 + 60 * k)),
                     size / math.sqrt(3) * math.sin(math.radians(90 + 60 * k))) for k in range(6)])
    a1, a2 = np.array((p, 0.0)), np.array((p / 2.0, p * math.sqrt(3) / 2.0))
    minx, miny, maxx, maxy = room.bounds
    reach = math.hypot(max(abs(maxx), abs(minx)), max(abs(maxy), abs(miny))) + 2.0 * p
    k = int(reach * p / abs(a1[0] * a2[1] - a1[1] * a2[0])) + 2
    inside = prep(room)
    out = []
    for i in range(-k, k + 1):
        for j in range(-k, k + 1):
            x, y = i * a1 + j * a2
            if minx - p < x < maxx + p and miny - p < y < maxy + p:
                c = affinity.translate(cell, float(x), float(y))
                if inside.contains(c):
                    out.append(c)
    return out


def _rect_cross_section(lx: float, wy: float, r: float, kind: str) -> m3d.CrossSection:
    """2D cross-section centered at (0, 0) of size lx x wy with corner fillet or chamfer `r`."""
    import math
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
    n_arc = max(6, circle_segments() // 4)
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


def _rounded_box(lx: float, wy: float, hz: float, r: float, round_top: bool) -> m3d.Manifold:
    """Straight box with a rolling-ball round `r` on every bottom edge, the vertical corners and (if `round_top`)
    the top edges. Each corner gets a ball, and the hull of the balls is the box: the same shape as the Fillet
    tool gives, as a few thousand smooth triangles instead of a stack of slabs."""
    seg = sphere_segments()
    hx, hy = lx / 2.0 - r, wy / 2.0 - r
    parts = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            x, y = sx * hx, sy * hy
            parts.append(m3d.Manifold.sphere(r, circular_segments=seg).translate((x, y, r)))
            if round_top:
                parts.append(m3d.Manifold.sphere(r, circular_segments=seg).translate((x, y, hz - r)))
            else:
                parts.append(m3d.Manifold.cylinder(hz - r, r, r, circular_segments=seg).translate((x, y, r)))
    return m3d.Manifold.batch_hull(parts)


def _rounded_prism(lx: float, wy: float, hz: float, r: float, kind: str, round_top: bool = True, taper: float = 0.0) -> m3d.Manifold:
    """Prism centered in XY, z in [0, hz], with vertical corners and bottom (plus optionally top) edges rounded/chamfered."""
    import math
    hx, hy = lx / 2.0, wy / 2.0
    max_r = min(hx - 0.02, hy - 0.02, hx-hz*taper-0.02, hy-hz*taper-0.02,
                (hz / 2.0 if round_top else hz) - 0.02)
    r = max(0.0, min(float(r), max_r))
    if r <= 1e-4:
        return m3d.Manifold.extrude(_rect_cross_section(lx, wy, 0.0, kind), hz,
                                   scale_top=((lx-2*hz*taper)/lx, (wy-2*hz*taper)/wy))
    if kind != "chamfer" and abs(taper) < 1e-12:
        return _rounded_box(lx, wy, hz, r, round_top)
    n_steps = 1 if kind == "chamfer" else max(6, circle_segments() // 4)
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



def _lid_xy_mask_poly(x_min, x_max, y_half, r_back, r_front, kind_back="fillet", kind_front="fillet", n_seg=16):
    import numpy as np
    from shapely.geometry import Polygon, box as sbox
    rb = max(0.0, min(r_back, y_half - 0.1, (x_max - x_min) * 0.4))
    rf = max(0.0, min(r_front, y_half - 0.1, (x_max - x_min) * 0.4))
    if rb < 0.05 and rf < 0.05:
        return sbox(x_min, -y_half, x_max, y_half)
    pts = []
    if rf >= 0.05:
        if kind_front == "chamfer":
            pts.extend([(x_max - rf, y_half), (x_max, y_half - rf)])
            pts.extend([(x_max, -y_half + rf), (x_max - rf, -y_half)])
        else:
            for a in np.linspace(np.pi / 2, 0, n_seg):
                pts.append((x_max - rf + rf * np.cos(a), y_half - rf + rf * np.sin(a)))
            for a in np.linspace(0, -np.pi / 2, n_seg):
                pts.append((x_max - rf + rf * np.cos(a), -y_half + rf + rf * np.sin(a)))
    else:
        pts.extend([(x_max, y_half), (x_max, -y_half)])
    if rb >= 0.05:
        if kind_back == "chamfer":
            pts.extend([(x_min + rb, -y_half), (x_min, -y_half + rb)])
            pts.extend([(x_min, y_half - rb), (x_min + rb, y_half)])
        else:
            for a in np.linspace(-np.pi / 2, -np.pi, n_seg):
                pts.append((x_min + rb + rb * np.cos(a), -y_half + rb + rb * np.sin(a)))
            for a in np.linspace(np.pi, np.pi / 2, n_seg):
                pts.append((x_min + rb + rb * np.cos(a), y_half - rb + rb * np.sin(a)))
    else:
        pts.extend([(x_min, -y_half), (x_min, y_half)])
    return Polygon(pts)



def box_row_outer_height(
    inner_z: float,
    bottom_thickness: float = 2.0,
    wall_thickness: float = 2.0,
    has_lid: bool = False,
    lip_height: float = 6.0,
    clearance: float = 0.2,
) -> float:
    """Computes total outer box height so that clear vertical space from the inside box
    floor to the underside of the lid (or top rim if no lid) equals inner_z exactly."""
    t = wall_thickness if wall_thickness > 1e-4 else 2.0
    tb = bottom_thickness if bottom_thickness > 1e-4 else t
    if has_lid:
        h_lip = lip_height if lip_height > 1e-4 else 6.0
        c = clearance
        return float(tb + inner_z - c / 2.0 + h_lip)
    else:
        return float(tb + inner_z)


class BoxPart:
    """One box or one lid, from the values - the same build code as Omacad's Box (with its box-in-a-row options)."""

    def __init__(self, length, width, height, translation, **opts):
        self.length, self.width, self.height = float(length), float(width), float(height)
        self.center = "bottom_center"
        self.plane_origin = self.plane_normal = self.plane_u = self.plane_v = None
        self.taper_angle = 0.0
        self.translation = [float(x) for x in translation]
        defaults = dict(wall_thickness=0.0, outer_round=0.0, outer_round_kind="fillet", inner_round=0.0,
                        inner_round_kind="fillet", lip_height=0.0, lip_step=0.0, bottom_thickness=0.0, honeycomb=False,
                        honeycomb_size=4.0, honeycomb_wall=1.2, honeycomb_margin=2.0, is_lid=False, clearance=0.2,
                        lid_top=2.0, tab_size=4.0, snap_size=0.6, slot_length=0.0, slot_width=0.0)
        defaults.update(opts)
        for key, value in defaults.items():
            setattr(self, key, value)

    def _lid_back_chamfer(self) -> float:
        """Size of the lid's chamfered back corners; the box groove matches it (#161)."""
        r_out = self.outer_round
        return max(1.5, self.inner_round if (self.inner_round > 1e-4 and self.inner_round_kind == "chamfer") else min(2.0, max(1.5, r_out)))


    def build_solid(self) -> m3d.Manifold:
        is_centered = (self.center is True or self.center == "center")
        is_bottom = (self.center == "bottom_center")
        hollow = self.wall_thickness > 1e-4
        has_smart = hollow or self.outer_round > 1e-4 or self.inner_round > 1e-4

        if self.is_lid:
            # Cool small box slide lid (Björn, report 20261101-202026)
            # Sliding plate with side V-grooves matching the triangular wall rails,
            # corner filleting/chamfering matching the box corners,
            # compliant thumb slot
            from shapely.geometry import Polygon, box as sbox

            t = min(self.wall_thickness if self.wall_thickness > 1e-4 else 2.0, min(self.length, self.width) * 0.45, self.height * 0.9)
            tb = self.bottom_thickness if self.bottom_thickness > 1e-4 else t
            c = self.clearance
            h_lip = self.lip_height if self.lip_height > 1e-4 else 2.2
            t_lid = self.lid_top if self.lid_top > 1e-4 else max(1.2, h_lip - c)
            r_out = self.outer_round
            r_in = self.inner_round if self.inner_round > 1e-4 else max(0.2, r_out - t)
            tab_sz = getattr(self, "tab_size", 4.0) or 4.0

            in_l = max(0.2, self.length - 2.0 * t)
            in_w = max(0.2, self.width - 2.0 * t)

            z_shelf = self.height - h_lip
            z_shelf = max(tb + 1.0, min(self.height - t_lid - 0.2, z_shelf))

            d_shelf = min(self.lip_step if self.lip_step > 1e-4 else 0.75, t * 0.5)
            d_triangle = min(d_shelf * 1.6, t * 0.7)

            h_step = min(0.20, t_lid * 0.15)
            h_tri = max(0.2, t_lid - 2.0 * h_step)
            z_peak = z_shelf + h_step + h_tri / 2.0

            y_shelf = in_w / 2.0 + d_shelf
            y_peak = y_shelf - d_triangle

            lid_z = z_shelf + c / 2.0
            y_shelf_lid = y_shelf - c
            y_peak_lid = y_peak - c / 2.0

            poly_lid_yz = Polygon([
                (-y_shelf_lid, lid_z),
                (y_shelf_lid, lid_z),
                (y_shelf_lid, lid_z + h_step),
                (y_peak_lid, z_peak),
                (y_shelf_lid, lid_z + h_step + h_tri),
                (y_shelf_lid, lid_z + t_lid),
                (-y_shelf_lid, lid_z + t_lid),
                (-y_shelf_lid, lid_z + h_step + h_tri),
                (-y_peak_lid, z_peak),
                (-y_shelf_lid, lid_z + h_step),
            ])
            cs_lid_yz = region_cross_section(poly_lid_yz)
            x_back = -in_l / 2.0
            x_back_lid = x_back + c
            x_front_lid = self.length / 2.0 - c
            lid_len = max(0.2, x_front_lid - x_back_lid)
            lid_plate = m3d.Manifold.extrude(cs_lid_yz, lid_len).rotate((90, 0, 90)).translate((x_back_lid, 0.0, 0.0))

            # XY corner rounding/chamfer mask
            # The back corners are inserted first into the box. A lead-in chamfer
            # facilitates insertion into the tracks without catching (report 20261102-183235).
            r_back = self._lid_back_chamfer()
            kind_back = "chamfer"

            poly_xy_mask = _lid_xy_mask_poly(
                x_back_lid, x_front_lid, y_shelf_lid,
                r_back, r_out - c,
                kind_back, self.outer_round_kind,
            )
            cs_mask = region_cross_section(poly_xy_mask)
            lid_mask = m3d.Manifold.extrude(cs_mask, t_lid + 2.0).translate((0.0, 0.0, lid_z - 1.0))
            lid_plate = lid_plate ^ lid_mask

            # Thumb slot (compliant flexure)
            solid = lid_plate
            if in_l > 12.0 and in_w > 8.0:
                user_w = float(getattr(self, "slot_width", 0.0) or 0.0)
                user_l = float(getattr(self, "slot_length", 0.0) or 0.0)
                slot_w = min(3.5, max(1.5, tab_sz * 0.75), in_l * 0.15)
                slot_l = min(max(6.0, tab_sz * 4.0), in_w * 0.65)
                if user_w > 1e-4:
                    slot_w = min(user_w, in_l * 0.5)
                if user_l > 1e-4:
                    slot_l = min(user_l, in_w - 2.0)
                slot_l = max(slot_l, slot_w)
                r_slot = min(slot_w / 2.0, 1.5)
                if user_w > 1e-4:
                    r_slot = slot_w / 2.0  # a requested slot is a full capsule
                bridge_len = max(2.5, min(8.0, in_l * 0.15))
                slot_x = self.length / 2.0 - t - slot_w - bridge_len
                hw = max(slot_w / 2.0 - r_slot, 1e-6)
                hl = max(slot_l / 2.0 - r_slot, 1e-6)
                slot_poly = sbox(slot_x - hw, -hl, slot_x + hw, hl).buffer(r_slot)
                cs_slot = region_cross_section(slot_poly)
                slot_cutter = m3d.Manifold.extrude(cs_slot, t_lid + 2.0).translate((0.0, 0.0, lid_z - 1.0))
                solid = solid - slot_cutter
            else:
                slot_poly = None

            if self.honeycomb:
                # Honeycomb in the lid too (report #155), kept clear of the thumb slot.
                try:
                    from shapely.ops import unary_union
                    m_hc = max(self.honeycomb_margin, 1.5)
                    room = sbox(x_back_lid + m_hc, -(y_shelf_lid - m_hc), x_front_lid - m_hc, y_shelf_lid - m_hc)
                    if slot_poly is not None:
                        room = room.difference(slot_poly.buffer(m_hc))
                    if not room.is_empty and room.area > self.honeycomb_size ** 2:
                        cells = hex_cells(self.honeycomb_size, self.honeycomb_wall, room)
                        if cells:
                            cs = region_cross_section(unary_union(cells))
                            solid = solid - m3d.Manifold.extrude(cs, t_lid + 2.0).translate((0.0, 0.0, lid_z - 1.0))
                except Exception as exc:
                    LOG(f"Lid honeycomb: {exc}")

            if is_centered:
                solid = solid.translate((0.0, 0.0, -self.height / 2.0))
            elif not is_bottom:
                solid = solid.translate((self.length / 2.0, self.width / 2.0, 0.0))
        elif self.lip_height > 1e-4 and self.lip_step > 1e-4:
            # Cool small box with sliding lid rails (Björn, report 20261101-202026)
            # Outer box with rounded/chamfered corners, inner cavity,
            # triangular rails on side walls, lowered front sill, and solid back wall
            from shapely.geometry import Polygon
            box_outer = _rounded_prism(self.length, self.width, self.height, self.outer_round, self.outer_round_kind, round_top=False)
            t = min(self.wall_thickness, min(self.length, self.width) * 0.45, self.height * 0.9)
            tb = self.bottom_thickness if self.bottom_thickness > 1e-4 else t
            c = self.clearance
            h_lip = self.lip_height if self.lip_height > 1e-4 else 2.2
            t_lid = self.lid_top if self.lid_top > 1e-4 else max(1.2, h_lip - c)
            r_in = self.inner_round if self.inner_round > 1e-4 else max(0.2, self.outer_round - t)

            in_l = max(0.2, self.length - 2.0 * t)
            in_w = max(0.2, self.width - 2.0 * t)

            z_shelf = self.height - h_lip
            z_shelf = max(tb + 1.0, min(self.height - t_lid - 0.2, z_shelf))

            d_shelf = min(self.lip_step if self.lip_step > 1e-4 else 0.75, t * 0.5)
            d_triangle = min(d_shelf * 1.6, t * 0.7)

            h_step = min(0.20, t_lid * 0.15)
            h_tri = max(0.2, t_lid - 2.0 * h_step)
            z_peak = z_shelf + h_step + h_tri / 2.0
            z_top_rail = z_shelf + h_step + h_tri

            y_shelf = in_w / 2.0 + d_shelf
            y_peak = y_shelf - d_triangle

            cavity = _rounded_prism(in_l, in_w, self.height - tb + 1.0, r_in, self.inner_round_kind, round_top=False).translate((0.0, 0.0, tb))

            poly_rail_cutter_yz = Polygon([
                (-y_shelf, z_shelf),
                (y_shelf, z_shelf),
                (y_shelf, z_shelf + h_step),
                (y_peak, z_peak),
                (y_shelf, z_top_rail),
                (y_shelf, self.height + 1.0),
                (-y_shelf, self.height + 1.0),
                (-y_shelf, z_top_rail),
                (-y_peak, z_peak),
                (-y_shelf, z_shelf + h_step),
            ])
            cs_channel = region_cross_section(poly_rail_cutter_yz)
            x_back = -in_l / 2.0
            x_front = self.length / 2.0 + 1.0
            channel_len = x_front - x_back
            channel_cutter = m3d.Manifold.extrude(cs_channel, channel_len).rotate((90, 0, 90)).translate((x_back, 0.0, 0.0))

            # The groove's back corners are chamfered like the lid's back corners, so the box
            # meets the lid with a chamfer - only up at lid level, not in the whole box (#161).
            d_ch = min(self._lid_back_chamfer() + c * (2.0 - math.sqrt(2.0)), y_shelf, channel_len * 0.4)
            ch_poly = Polygon([
                (x_back + d_ch, -y_shelf), (x_front, -y_shelf), (x_front, y_shelf),
                (x_back + d_ch, y_shelf), (x_back, y_shelf - d_ch), (x_back, -y_shelf + d_ch),
            ])
            ch_mask = m3d.Manifold.extrude(region_cross_section(ch_poly), self.height + 2.0).translate((0.0, 0.0, -1.0))
            channel_cutter = channel_cutter ^ ch_mask

            solid = box_outer - cavity - channel_cutter

            # The rails stop where the front wall starts: left running through the front
            # corners they poke out as a triangular stub (report 20261101-205314).
            r_front = min(r_in, t)
            x_clear = self.length / 2.0 - t - r_front
            front_clear = m3d.Manifold.cube((self.length / 2.0 + 1.0 - x_clear, 2.0 * y_shelf, self.height + 1.0 - z_shelf)).translate((x_clear, -y_shelf, z_shelf))
            solid = solid - front_clear

            if self.honeycomb:
                try:
                    from shapely.geometry import box as sbox
                    from shapely.ops import unary_union
                    margin = self.honeycomb_margin
                    room_l = in_l - 2.0 * margin
                    room_w = in_w - 2.0 * margin
                    if room_l > self.honeycomb_size and room_w > self.honeycomb_size:
                        room = sbox(-room_l / 2.0, -room_w / 2.0, room_l / 2.0, room_w / 2.0)
                        cells = hex_cells(self.honeycomb_size, self.honeycomb_wall, room)
                        if cells:
                            cs = region_cross_section(unary_union(cells))
                            cutter = m3d.Manifold.extrude(cs, tb + 1.0).translate((0.0, 0.0, -0.5))
                            solid = solid - cutter
                except Exception as exc:
                    LOG(f"Box honeycomb floor: {exc}")

                # Honeycomb in the side walls and the back wall, below the lid groove (report #155)
                try:
                    from shapely.geometry import box as sbox
                    from shapely.ops import unary_union
                    m_hc = max(self.honeycomb_margin, 1.5)
                    z0, z1 = tb + m_hc, z_shelf - m_hc
                    if z1 - z0 > self.honeycomb_size:
                        def cells_in(u0, u1):
                            room = sbox(u0, z0, u1, z1)
                            cells = hex_cells(self.honeycomb_size, self.honeycomb_wall, room)
                            return region_cross_section(unary_union(cells)) if cells else None
                        x0, x1 = -in_l / 2.0 + m_hc, x_clear - m_hc
                        if x1 - x0 > self.honeycomb_size:
                            cs = cells_in(x0, x1)
                            if cs is not None:
                                span = self.width + 2.0
                                sides = m3d.Manifold.extrude(cs, span).rotate((90, 0, 0)).translate((0.0, span / 2.0, 0.0))
                                solid = solid - sides
                        y1 = in_w / 2.0 - m_hc
                        if 2.0 * y1 > self.honeycomb_size:
                            cs = cells_in(-y1, y1)
                            if cs is not None:
                                back = m3d.Manifold.extrude(cs, t + 2.0).rotate((90, 0, 90)).translate((-self.length / 2.0 - 1.0, 0.0, 0.0))
                                solid = solid - back
                except Exception as exc:
                    LOG(f"Box honeycomb walls: {exc}")

            if is_centered:
                solid = solid.translate((0.0, 0.0, -self.height / 2.0))
            elif not is_bottom:
                solid = solid.translate((self.length / 2.0, self.width / 2.0, 0.0))
        elif not has_smart:
            solid = m3d.Manifold.cube([self.length, self.width, self.height], center=is_centered)
            if is_bottom:
                solid = solid.translate((-self.length / 2.0, -self.width / 2.0, 0.0))
        else:
            # Build in bottom-centered coordinates (XY centered, Z in 0..height), then shift to requested center mode
            solid = _rounded_prism(self.length, self.width, self.height, self.outer_round, self.outer_round_kind,
                                   round_top=not hollow)
            if hollow:
                t = min(self.wall_thickness, min(self.length, self.width) * 0.45, self.height * 0.9)
                tb = self.bottom_thickness if self.bottom_thickness > 1e-4 else t
                in_l = max(0.2, self.length - 2.0 * t)
                in_w = max(0.2, self.width - 2.0 * t)
                in_h = max(0.2, self.height - tb) + 1.0
                cavity = _rounded_prism(in_l, in_w, in_h, self.inner_round, self.inner_round_kind, round_top=False)
                solid = solid - cavity.translate((0.0, 0.0, tb))

                if self.honeycomb:
                    try:
                        from shapely.geometry import box as sbox
                        from shapely.ops import unary_union
                        margin = self.honeycomb_margin
                        room_l = in_l - 2.0 * margin
                        room_w = in_w - 2.0 * margin
                        if room_l > self.honeycomb_size and room_w > self.honeycomb_size:
                            room = sbox(-room_l / 2.0, -room_w / 2.0, room_l / 2.0, room_w / 2.0)
                            cells = hex_cells(self.honeycomb_size, self.honeycomb_wall, room)
                            if cells:
                                cs = region_cross_section(unary_union(cells))
                                cutter = m3d.Manifold.extrude(cs, tb + 1.0).translate((0.0, 0.0, -0.5))
                                solid = solid - cutter
                    except Exception as exc:
                        LOG(f"Box honeycomb floor: {exc}")

            if is_centered:
                solid = solid.translate((0.0, 0.0, -self.height / 2.0))
            elif not is_bottom:
                solid = solid.translate((self.length / 2.0, self.width / 2.0, 0.0))

        if False:   # (placing on a picked plane is left out of the script)
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


def run(ctx, params):
    global LOG
    LOG = ctx.log
    SEGMENTS.update(circle=ctx.circle_segments, sphere=ctx.sphere_segments)
    p = dict(params)
    n = p["count"]
    step_x = p["length"] + p["spacing"]
    first_x = -((n - 1) * step_x) / 2.0                 # the row is centred on the origin
    outer_h = box_row_outer_height(p["height"], bottom_thickness=p["bottom_thickness"],
                                   wall_thickness=p["wall_thickness"], has_lid=p["has_lid"],
                                   lip_height=p["lip_height"], clearance=p["clearance"])
    common = dict(wall_thickness=p["wall_thickness"], outer_round=p["outer_round"],
                  outer_round_kind=p["outer_round_kind"], inner_round=p["inner_round"],
                  inner_round_kind=p["inner_round_kind"], honeycomb=p["honeycomb"],
                  honeycomb_size=p["honeycomb_size"], honeycomb_wall=p["honeycomb_wall"],
                  honeycomb_margin=p["honeycomb_margin"], tab_size=p["tab_size"],
                  slot_length=p["slot_length"], slot_width=p["slot_width"])
    bodies = []
    for i in range(n):
        at = (first_x + i * step_x, 0.0, 0.0)
        label = ctx.name if n == 1 else f"{ctx.name} {i + 1}"
        box = BoxPart(p["length"], p["width"], outer_h, at, bottom_thickness=p["bottom_thickness"],
                      lip_height=p["lip_height"] if p["has_lid"] else 0.0,
                      lip_step=p["lip_step"] if p["has_lid"] else 0.0, **common)
        bodies.append(ctx.solid(box.build_solid(), label))
        if p["has_lid"]:
            lid = BoxPart(p["length"], p["width"], outer_h, at, lip_height=p["lip_height"], lip_step=p["lip_step"],
                          clearance=p["clearance"], lid_top=p["lid_top"], is_lid=True, **common)
            bodies.append(ctx.solid(lid.build_solid(), f"{label} lid", lid=True))
    if len(bodies) > 1:
        ctx.group(ctx.name, bodies)
    ctx.log(f"Outside of each box: {p['length']:g} × {p['width']:g} × {outer_h:.2f} mm")
