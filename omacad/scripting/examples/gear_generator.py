"""Omacad example script: an involute spur gear, ready to 3D print.

Change the values in the panel that opens when you run it (Scripts > Gear generator)."""
import math

NAME = "Gear generator"
OUTPUT_NAME = "Gear"          # default for the Name field: what the made gear is called
DESCRIPTION = "Involute spur gear with a centre bore and optional hub. Size it by module and number of teeth."
PARAMS = [
    {"name": "teeth", "label": "Number of teeth", "type": "int", "default": 20, "min": 6, "max": 150},
    {"name": "module", "label": "Module", "type": "float", "default": 2.0, "min": 0.3, "max": 20.0, "step": 0.1,
     "unit": "mm", "help": "Pitch diameter / teeth. Gears that mesh need the same module."},
    {"name": "thickness", "label": "Thickness", "type": "float", "default": 8.0, "min": 0.5, "max": 200.0, "unit": "mm"},
    {"name": "pressure_angle", "label": "Pressure angle", "type": "choice", "default": 20.0,
     "choices": [14.5, 20.0, 25.0], "help": "20° is the common standard."},
    {"name": "backlash", "label": "Backlash", "type": "float", "default": 0.1, "min": 0.0, "max": 1.0, "step": 0.05,
     "unit": "mm", "help": "Play between meshing teeth (thins each tooth by half of it). 0.1-0.2 mm for printing."},
    {"name": "bore", "label": "Bore diameter", "type": "float", "default": 5.0, "min": 0.0, "max": 500.0, "unit": "mm",
     "help": "0 = no hole."},
    {"name": "hub", "label": "Hub", "type": "bool", "default": False},
    {"name": "hub_diameter", "label": "Hub diameter", "type": "float", "default": 14.0, "min": 1.0, "max": 500.0,
     "unit": "mm"},
    {"name": "hub_height", "label": "Hub height", "type": "float", "default": 6.0, "min": 0.5, "max": 200.0, "unit": "mm"},
]

POINTS_PER_FLANK = 10


def involute_xy(base_r, t):
    """Point on the involute of a circle of radius base_r at roll angle t (radians)."""
    return base_r * (math.cos(t) + t * math.sin(t)), base_r * (math.sin(t) - t * math.cos(t))


def gear_outline(teeth, module, pressure_angle_deg, backlash):
    """Closed outline (list of (x, y)) of the gear, counter-clockwise, centred on the origin."""
    pa = math.radians(pressure_angle_deg)
    pitch_r = module * teeth / 2
    base_r = pitch_r * math.cos(pa)
    tip_r = pitch_r + module
    root_r = max(pitch_r - 1.25 * module, 0.5 * module)

    # half the tooth's angular width at the pitch circle, thinned by half the backlash
    half_tooth = math.pi / (2 * teeth) - (backlash / 2) / pitch_r
    inv = lambda a: math.tan(a) - a                       # involute function
    # angle of the flank's start (on the base circle) relative to the tooth centre line
    flank_offset = half_tooth + inv(pa)
    t_tip = math.sqrt(max((tip_r / base_r) ** 2 - 1, 0.0))
    t_start = math.sqrt(max((root_r / base_r) ** 2 - 1, 0.0)) if root_r > base_r else 0.0

    def flank(sign):
        """One flank (sign +1 = the tooth's left side) from root to tip, in the tooth's own frame."""
        pts = []
        if root_r < base_r:                               # straight radial bit below the base circle
            pts.append((root_r * math.cos(sign * flank_offset), root_r * math.sin(sign * flank_offset)))
        for k in range(POINTS_PER_FLANK + 1):
            t = t_start + (t_tip - t_start) * k / POINTS_PER_FLANK
            x, y = involute_xy(base_r, t)
            a = math.atan2(y, x)
            r = math.hypot(x, y)
            ang = sign * (flank_offset - a)
            pts.append((r * math.cos(ang), r * math.sin(ang)))
        return pts

    right = flank(-1)                                     # root -> tip on the clockwise side
    left = list(reversed(flank(+1)))                      # tip -> root on the counter-clockwise side
    tooth = right + left
    pitch = 2 * math.pi / teeth
    outline = []
    for i in range(teeth):
        c, s = math.cos(i * pitch), math.sin(i * pitch)
        for x, y in tooth:
            outline.append((x * c - y * s, x * s + y * c))
        # root arc to the next tooth
        a0 = i * pitch + flank_offset
        a1 = (i + 1) * pitch - flank_offset
        for k in range(1, 4):
            a = a0 + (a1 - a0) * k / 4
            outline.append((root_r * math.cos(a), root_r * math.sin(a)))
    return outline, pitch_r, tip_r, root_r


def run(ctx, params):
    teeth, module = params["teeth"], params["module"]
    outline, pitch_r, tip_r, root_r = gear_outline(teeth, module, float(params["pressure_angle"]), params["backlash"])
    bore_r = params["bore"] / 2
    if bore_r >= root_r - module * 0.5:
        raise ValueError(f"The bore ({params['bore']} mm) is too big for this gear; keep it under "
                         f"{2 * (root_r - module * 0.5):.1f} mm.")

    s = ctx.sketch("XY", name="Gear profile")
    s.polyline(outline, closed=True)
    if bore_r > 0:
        s.circle((0, 0), bore_r)
    gear = ctx.extrude(s, params["thickness"], profile="outer")
    gear.rename(ctx.name)                                 # the Name field in the panel ("Gear")

    if params["hub"]:
        hub_r = params["hub_diameter"] / 2
        if hub_r <= bore_r:
            raise ValueError("The hub diameter must be larger than the bore.")
        h = ctx.sketch("XY", offset=params["thickness"], name="Hub profile")
        h.circle((0, 0), hub_r)
        if bore_r > 0:
            h.circle((0, 0), bore_r)
        ctx.extrude(h, params["hub_height"], operation="join", profile="outer")

    ctx.log(f"Pitch diameter {2 * pitch_r:.2f} mm, outside diameter {2 * tip_r:.2f} mm, "
            f"root diameter {2 * root_r:.2f} mm.")
    ctx.log(f"Centre distance to a gear with N teeth (same module): {module:g} × ({teeth} + N) / 2 mm.")
