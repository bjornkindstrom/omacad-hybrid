"""Omacad script: Jar with Lid - a threaded jar and its screw lid, ready to 3D print.

A script version of Omacad's built-in Jar with Lid tool. All geometry is in this file - the jar, its hollow inside
with chamfers, the thread, the lid with the matching inner thread and its tolerance, the 45° lead-in chamfers - so
you (or an AI) can change anything. Use "Modify with AI…" in the Jar with Lid menu to make a changed copy; this file
stays as it is.

How it is built (all with manifold3d):
- jar = outside cylinder + neck cylinder + thread, minus the inside (a revolved outline with the chamfers);
- thread = the tooth's outline swept along a helix (a mesh built ring by ring), fading in and out at the ends;
- lid = cylinder minus (neck + the same thread grown by the tolerance), minus a 45° cone in its mouth."""
import math

import manifold3d as m3d

NAME = "Jar with Lid (script)"
FAMILY = "jar"                # listed in the Jar with Lid submenu
OUTPUT_NAME = "Jar"
DESCRIPTION = "Threaded jar with a screw lid laid beside it for printing. Thread, tolerance and chamfers adjustable."
PARAMS = [
    {"name": "diameter", "label": "Diameter", "type": "float", "default": 40.0, "min": 10.0, "max": 500.0, "unit": "mm",
     "help": "Outside of the jar and the lid."},
    {"name": "height", "label": "Height", "type": "float", "default": 40.0, "min": 5.0, "max": 500.0, "unit": "mm",
     "help": "The jar up to its shoulder; the neck comes on top."},
    {"name": "wall", "label": "Wall", "type": "float", "default": 2.0, "min": 0.6, "max": 20.0, "unit": "mm"},
    {"name": "inside_chamfer", "label": "Inside chamfer", "type": "float", "default": 4.0, "min": 0.0, "max": 50.0, "unit": "mm",
     "help": "45° inside the jar at the bottom and under the shoulder (no overhang when printing)."},
    {"name": "neck_diameter", "label": "Neck diameter", "type": "float", "default": 32.0, "min": 5.0, "max": 490.0, "unit": "mm"},
    {"name": "neck_height", "label": "Neck height", "type": "float", "default": 10.0, "min": 3.0, "max": 100.0, "unit": "mm",
     "help": "Also the thread's length."},
    {"name": "pitch", "label": "Thread pitch", "type": "float", "default": 4.0, "min": 1.0, "max": 20.0, "unit": "mm"},
    {"name": "profile", "label": "Thread profile", "type": "choice", "default": "trapezoidal_45",
     "choices": ["trapezoidal_45", "round", "iso_60"], "help": "trapezoidal_45 prints without support."},
    {"name": "tolerance", "label": "Thread tolerance", "type": "float", "default": -0.2, "min": -2.0, "max": 0.0, "step": 0.05,
     "unit": "mm", "help": "Minus = more room in the lid (looser)."},
    {"name": "thread_chamfer", "label": "Thread chamfer", "type": "float", "default": 1.0, "min": 0.0, "max": 10.0, "unit": "mm",
     "help": "45° lead-in on the jar's top thread and in the lid's mouth (0 = none)."},
    {"name": "lid_top", "label": "Lid top", "type": "float", "default": 2.0, "min": 0.6, "max": 20.0, "unit": "mm"},
    {"name": "lid_beside", "label": "Lid beside the jar", "type": "bool", "default": True,
     "help": "Upside down beside the jar, ready to print. Off: screwed on."},
]

GAP_BESIDE = 10.0       # mm between the jar and the lid laid out for printing
THREAD_GAP = 0.5        # mm of plain neck under the thread
DIG = 0.3               # the tooth reaches this far into the core, so the two always join


def tooth(profile, pitch):
    """(radial height, half width at the crest, half width at the root) of the thread tooth, in mm."""
    if profile == "round":
        return 0.22 * pitch, 0.0, 0.28 * pitch
    if profile == "iso_60":
        height = 0.30 * pitch
        crest = 0.06 * pitch
        return height, crest, crest + height * math.tan(math.radians(30.0))
    height = 0.25 * pitch                      # trapezoidal 45°: the flanks rise one for one
    crest = 0.10 * pitch
    return height, crest, crest + height


def tooth_height(u, profile, pitch, grow=0.0):
    """Height of the tooth at axial distance u from its centre line (grow: thicker on every side)."""
    h, crest, root = tooth(profile, pitch)
    u = abs(u)
    if profile == "round":
        a = root + grow
        return (h + grow) * math.sqrt(max(0.0, 1.0 - (u / a) ** 2)) if u < a else 0.0
    crest, root = crest + grow, root + grow
    if u <= crest:
        return h + grow
    if u < root:
        return (h + grow) * (root - u) / (root - crest)
    return 0.0


def tooth_outline(profile, pitch, grow=0.0, fade=1.0):
    """The tooth's cross-section as (radial offset from the core surface, axial offset) points, convex, running
    round once. It reaches DIG mm into the core so the thread always joins it. fade (0..1) lowers the tooth."""
    h, crest, root = tooth(profile, pitch)
    top = (h + grow) * fade
    if profile == "round":
        a = root + grow
        arc = [(top * math.sin(math.pi * k / 12), -a * math.cos(math.pi * k / 12)) for k in range(13)]
        return [(-DIG, -a)] + arc + [(-DIG, a)]
    w_root, w_crest = root + grow, crest + grow
    return [(-DIG, -w_root), (0.0, -w_root), (top, -w_crest), (top, w_crest), (0.0, w_root), (-DIG, w_root)]


def thread_solid(radius, pitch, length, profile, grow=0.0, segments=96, fade_turns=0.75):
    """A helical thread on a core of `radius`: the tooth outline swept along the helix (one ring of points per
    1/segments turn), z from 0 to `length`. The tooth fades in and out over `fade_turns` at the ends. `grow` makes
    it thicker on every side (and the core bigger) - used for the lid's room with its tolerance."""
    turns = max(0.25, (length - 2.0 * tooth(profile, pitch)[2]) / pitch)   # the tooth stays inside 0..length
    n = max(8, int(round(turns * segments)))
    fade_n = max(1, int(round(fade_turns * segments)))
    w = tooth(profile, pitch)[2] + grow
    base = radius + grow
    verts, rings = [], []
    for i in range(n + 1):
        f = min(1.0, i / fade_n, (n - i) / fade_n)
        f = max(0.02, math.sin(0.5 * math.pi * f) ** 2)
        a = 2.0 * math.pi * turns * i / n
        z = w + pitch * turns * i / n
        ring = []
        for dr, du in tooth_outline(profile, pitch, grow, f):
            r = base + dr
            ring.append(len(verts))
            verts.append((r * math.cos(a), r * math.sin(a), z + du))
        rings.append(ring)
    tris = []
    m = len(rings[0])
    for i in range(n):
        a_, b_ = rings[i], rings[i + 1]
        for k in range(m):
            k2 = (k + 1) % m
            tris += [(a_[k], b_[k], b_[k2]), (a_[k], b_[k2], a_[k2])]
    for k in range(1, m - 1):                       # end caps (the outline is convex)
        tris.append((rings[0][0], rings[0][k], rings[0][k + 1]))
        tris.append((rings[-1][0], rings[-1][k + 1], rings[-1][k]))
    import numpy as np
    mesh = m3d.Mesh(vert_properties=np.array(verts, dtype=np.float32), tri_verts=np.array(tris, dtype=np.uint32))
    coil = m3d.Manifold(mesh)
    if coil.status() != m3d.Error.NoError or coil.volume() <= 0:     # wound the other way round: flip the faces
        mesh = m3d.Mesh(vert_properties=np.array(verts, dtype=np.float32),
                        tri_verts=np.array([(a, c, b) for a, b, c in tris], dtype=np.uint32))
        coil = m3d.Manifold(mesh)
    core = m3d.Manifold.cylinder(length, base, base, circular_segments=segments)
    return core + coil


def cone(r_bottom, r_top, height, z, segments):
    return m3d.Manifold.cylinder(height, r_bottom, max(0.0, r_top), circular_segments=segments).translate((0.0, 0.0, z))


def run(ctx, params):
    p = dict(params)
    seg = ctx.circle_segments
    D, H, w = p["diameter"], p["height"], p["wall"]
    R, rn, nh = D / 2.0, p["neck_diameter"] / 2.0, p["neck_height"]
    top = H + nh
    t_h, _, _ = tooth(p["profile"], p["pitch"])
    crest = rn + t_h
    slack = max(0.0, -p["tolerance"])

    # what makes the jar impossible (same checks as the built-in tool)
    if rn - w < 0.5:
        raise ValueError("The neck is too narrow for the wall: no opening is left.")
    if R - crest - slack < 0.8:
        raise ValueError(f"The lid's wall outside the thread is only {R - crest - slack:.1f} mm: "
                         "make the jar wider or the neck narrower.")
    if rn >= R:
        raise ValueError("The neck must be narrower than the jar.")
    if H <= w:
        raise ValueError("The jar is not taller than its bottom.")
    c_in = min(p["inside_chamfer"], R - rn)
    if c_in > 0 and 2 * c_in >= H - 2 * w:
        raise ValueError("The inside chamfer is too big for the jar's height.")

    # ---- the jar ----------------------------------------------------------------------------------------------
    jar = m3d.Manifold.cylinder(H, R, R, circular_segments=seg)
    jar += m3d.Manifold.cylinder(nh + 0.01, rn, rn, circular_segments=seg).translate((0.0, 0.0, H - 0.01))
    thread_len = max(0.5, nh - THREAD_GAP)
    jar += thread_solid(rn, p["pitch"], thread_len, p["profile"], segments=seg).translate((0.0, 0.0, H + THREAD_GAP))
    ri = R - w
    inside = [(0.0, w), (ri - c_in, w), (ri, w + c_in), (ri, H - w - c_in), (ri - c_in, H - w),
              (rn - w, H - w), (rn - w, top + 1.0), (0.0, top + 1.0)]
    jar -= m3d.Manifold.revolve(m3d.CrossSection([inside]), circular_segments=seg)

    # 45° lead-in at the top of the thread: cut away what lies outside a cone through the neck's rim
    c = max(0.0, min(p["thread_chamfer"], w / 2.0, nh - t_h - 1.5, R - crest - 0.4))
    if c > 1e-3:
        z0 = top - c - t_h - 1.0
        h = top + 1.0 - z0
        ring = m3d.Manifold.cylinder(h, crest + 3.0, crest + 3.0, circular_segments=seg).translate((0.0, 0.0, z0))
        jar -= ring - cone(crest + 1.0, crest + 1.0 - h, h, z0, seg)

    # ---- the lid (built screwed on, over the neck) ------------------------------------------------------------
    lid_h = nh + p["lid_top"]
    lid = m3d.Manifold.cylinder(lid_h, R, R, circular_segments=seg).translate((0.0, 0.0, H))
    room = m3d.Manifold.cylinder(nh + 1.0, rn + slack, rn + slack, circular_segments=seg).translate((0.0, 0.0, H - 1.0))
    room += thread_solid(rn, p["pitch"], thread_len + 0.01, p["profile"], grow=slack, segments=seg).translate(
        (0.0, 0.0, H + THREAD_GAP))
    lid -= room
    if c > 1e-3:   # a cone c wider than the crest at the mouth, so the lid finds the thread
        rise = c + t_h + w / 2.0 + 1.5
        lid -= cone(crest + c + 1.0, crest + c + 1.0 - rise, rise, H - 1.0, seg)

    if p["lid_beside"]:   # upside down, its top on the bed, beside the jar
        lid = lid.translate((0.0, 0.0, -H - lid_h)).rotate((180.0, 0.0, 0.0)).translate((D + GAP_BESIDE, 0.0, 0.0))

    jar_body = ctx.solid(jar, ctx.name)
    lid_body = ctx.solid(lid, f"{ctx.name} lid", lid=True)
    ctx.group(ctx.name, [jar_body, lid_body])
    ctx.log(f"Inside: Ø{2 * ri:.1f} mm, opening Ø{2 * (rn - w):.1f} mm, about {_volume_ml(ri, H, w):.0f} ml.")
    ctx.log(f"Thread: pitch {p['pitch']:g} mm, tooth {t_h:.2f} mm, lid {slack:.2f} mm looser.")


def _volume_ml(ri, H, w):
    return math.pi * ri * ri * (H - 2 * w) / 1000.0
