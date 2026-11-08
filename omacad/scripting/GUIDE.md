# Omacad scripting guide

An Omacad script is **one Python file** in the user's scripts folder. Omacad lists it under **Scripts** (Shift+S),
asks for its parameters in a panel, and runs it on the open model. Everything the script creates becomes ordinary
timeline steps (sketches, extrudes, boxes …), and the whole run is **one undo step**. If the script raises an
error, the model is put back exactly as it was.

## File format

```python
import math                      # see "Modules" below for what may be imported

NAME = "Gear generator"          # shown in the Scripts list (plain string literal)
OUTPUT_NAME = "Gear"             # optional: default for the Name field (what the made things are called)
FAMILY = ""                      # optional: "jar", "star_brackets" or "box_row" puts it in that tool's submenu
DESCRIPTION = "Involute spur gear with a centre bore."   # one or two sentences (plain string literal)
PARAMS = [                       # the values the user can set; plain data only (no expressions or variables)
    {"name": "teeth", "label": "Number of teeth", "type": "int", "default": 20, "min": 6, "max": 150},
    {"name": "module", "type": "float", "default": 2.0, "min": 0.3, "step": 0.1, "unit": "mm"},
    {"name": "hub", "type": "bool", "default": False},
    {"name": "style", "type": "choice", "default": "round", "choices": ["round", "square"]},
    {"name": "label", "type": "str", "default": "A1"},
]

def run(ctx, params):            # required; params is a dict {name: value} with every PARAMS name
    s = ctx.sketch("XY")
    s.circle((0, 0), params["module"] * params["teeth"] / 2)
    ctx.extrude(s, 8)
```

Rules:

- `NAME`, `DESCRIPTION`, `PARAMS`, `OUTPUT_NAME` and `FAMILY` are read **without running the file**, so they must
  be literal values.
- **Pictures:** Omacad saves a screenshot of the 3D view when creating a new script (`<script>.png` next to the script).
  An `IMAGE = "picture.png"` line or a picture next to the script is shown as an illustration in the script explanation
  in the tool panel when the user chooses the script.
- **Names:** the panel always has a **Name** field (default `OUTPUT_NAME`, else `NAME`); the script reads it as
  `ctx.name`. Name what you make from it, e.g. `ctx.solid(jar, ctx.name)` and `ctx.solid(lid, f"{ctx.name} lid")`,
  or `body.rename(ctx.name)`. Objects the script does not name get `ctx.name`, `ctx.name 2` … automatically.
- `PARAMS` keys: `name` (Python identifier, required), `type` (`"float"`, `"int"`, `"bool"`, `"choice"`, `"str"`;
  default `"float"`), `default` (required), `label`, `min`, `max`, `step`, `decimals`, `unit`, `choices`
  (required for `"choice"`, may hold numbers or strings), `help` (tooltip). No other keys.
- Values arrive already checked: numbers are clamped to `min`/`max`, ints are ints, a choice is one of `choices`.
- Put all geometry code inside `run` (or functions it calls). Top-level code runs every time the script runs.
- **Never** open windows, use `input()`, `print()` for results, `time.sleep`, threads, the network, or write files
  unless the user asked for it. Report with `ctx.log(...)`. Never import Qt or `omacad` internals; use only `ctx`.
- Check impossible combinations yourself and `raise ValueError("clear message for the user")`; the message is shown
  to the user with the line number.
- Keep it fast: a run should take seconds. Do not create thousands of bodies or steps; build a profile with
  `polyline` and extrude it once instead of extruding many small pieces.

## Modules

Import only these (the Windows app bundles exactly these): `math`, `cmath`, `random`, `statistics`, `fractions`,
`decimal`, `itertools`, `functools`, `collections`, `dataclasses`, `json`, `re`, `string`, `bisect`, `heapq`,
`numpy`, `shapely` and `manifold3d` (as `m3d`, for solids built in code and added with `ctx.solid`). Use `random.Random(seed)` with a seed parameter if the result should be repeatable.

## Units and coordinates

- Millimetres and degrees. World axes: **X right, Y back, Z up**. The ground is the XY plane.
- Sketch coordinates are `(u, v)` on the sketch plane: on `"XY"` u = X, v = Y; on `"XZ"` u = X, v = Z; on `"YZ"`
  u = Y, v = Z. A sketch's normal (the positive extrude direction): XY → +Z, XZ → −Y, YZ → +X.

## API reference (`ctx`)

### Sketches

`s = ctx.sketch(plane="XY", offset=0.0, name=None)` – a new sketch on `"XY"`, `"XZ"` or `"YZ"`, moved `offset` mm
along the plane's normal (e.g. `ctx.sketch("XY", offset=10)` draws at Z = 10). Starting a new sketch finishes the
previous one.

Drawing (all return the sketch, so calls can be chained; points are `(u, v)` tuples):

| Method | Draws |
|---|---|
| `s.line(p1, p2, construction=False)` | a straight line (with a length dimension) |
| `s.polyline(points, closed=True)` | straight lines through the points, no dimensions. **Best for computed outlines** (gear teeth, cams, text-free shapes). Points must not repeat or cross. |
| `s.rect(p1, p2)` | rectangle from two opposite corners |
| `s.center_rect(center, width, height)` | rectangle around a centre |
| `s.rounded_rect(p1, p2, radius)` | rectangle with rounded corners |
| `s.circle(center, radius)` | circle |
| `s.arc(start, mid, end)` | arc through three points |
| `s.polygon(center, radius, sides, angle=90)` | regular polygon, corners on a circle of `radius`, first corner at `angle` degrees |
| `s.slot(center1, center2, radius)` | slot (stadium) |
| `s.spline(points)` | smooth open curve through the points |

`construction=True` (line, rect, circle, arc, polygon, spline) draws helper geometry that is not part of profiles.

Closed outlines become **profiles** (regions). A circle inside a rectangle gives two profiles: the rectangle with a
hole, and the disc. `s.profiles` lists them (`Profile.index`, `.area`, `.centroid`, `.outline`, `.holes`,
`.contains((u, v))`). `s.to_world((u, v))` gives the 3D point. `s.finish()` ends drawing (extrude/revolve do it
automatically); you cannot draw in a sketch after extruding it – start a new sketch.

### Making solids from sketches

`ctx.extrude(sketch, distance, operation="new_body", profile=None, symmetric=False, distance2=None,
start_offset=0.0, twist=0.0)` → `Body`

- Extrudes along the sketch normal; a negative `distance` goes the other way.
- `operation`: `"new_body"`, `"join"` (add to the body it touches), `"cut"` (remove from what it overlaps),
  `"intersect"`, or `"auto"` (cut if it overlaps a body, join if it starts on a body face, else new body).
- `profile`: `None`/`"outer"` = every region that is not just the hole of another (a washer extrudes as a ring, not
  a disc); `"all"`; `"largest"`; an index; a `(u, v)` point (floats) inside the wanted region; or a list of these.
- `symmetric=True`: half the distance each side. `distance2`: also extrude that far in the opposite direction.
- `twist`: degrees of twist over the length (around the profile centre).
- Returns the new body (new_body) or the body that changed (join/cut); `None` and a log warning if nothing changed.

`ctx.revolve(sketch, axis="v", angle=360, operation="new_body", profile=None)` → `Body` – turns profiles around
`"u"` (the sketch's horizontal axis through its origin), `"v"` (vertical axis), or a line `((u1, v1), (u2, v2))`.
The profile must lie entirely on one side of the axis. Example: a vase = a closed outline on `"XZ"` with u ≥ 0,
revolved around `"v"` (the Z axis).

### Primitives

| Call | Makes |
|---|---|
| `ctx.box(length, width, height, at=(0,0,0), center=False, name=None)` | box along X, Y, Z; `at` = its min corner, or its centre with `center=True` |
| `ctx.cylinder(radius, height, at=(0,0,0), name=None)` | upright cylinder, bottom centre at `at` |
| `ctx.cone(radius, top_radius, height, at=(0,0,0), name=None)` | cone/frustum (top_radius 0 = point) |
| `ctx.sphere(radius, at=(0,0,0), name=None)` | sphere centred at `at` |

### Changing bodies

| Call | Does |
|---|---|
| `ctx.combine(target, tools, operation="join", keep_tools=False)` | join/cut/intersect one or more tool bodies with `target`; tools are used up unless `keep_tools` |
| `ctx.move(body, dx=0, dy=0, dz=0, rx=0, ry=0, rz=0, copy=False)` | move, and/or turn around the body's own centre (degrees about X, Y, Z); `copy=True` moves a copy and returns it |
| `ctx.fillet(body, radius, edges="all")` | round edges |
| `ctx.chamfer(body, size, edges="all")` | bevel edges (equal distances) |
| `ctx.shell(body, thickness, open_top=True)` | hollow to a wall thickness; `open_top` leaves the highest flat face open |
| `ctx.pattern(steps, kind="circular", count=2, angle=360, axis="z")` | copy what earlier steps did (e.g. a cut hole and its fillet) `count` times in total around `axis` (`"x"`, `"y"`, `"z"` through the body centre) |
| `ctx.pattern(steps, kind="linear", count=3, spacing=10, axis="x", count2=1, spacing2=10, axis2="y")` | copies in a row or grid |

`edges` for fillet/chamfer: `"all"`, `"top"` (flat edges at the highest Z), `"bottom"`, `"vertical"`,
`"horizontal"`, a function `Edge -> bool`, or a list of `Edge` objects from `body.edges`. An `Edge` has `kind`
(`"line"`, `"circle"`, `"loop"`), `start`, `end`, `points`, `zmin`, `zmax`, `length`, `convex` (outside corner),
`is_vertical`, `is_horizontal`, and for circles `center` and `radius`. Example:
`ctx.fillet(b, 1, edges=lambda e: e.kind == "circle" and e.zmax > 9.9)`.
Fillet works on straight edges between flat faces and on circular edges; keep the radius smaller than the faces
next to the edge. Do fillets and chamfers last.

`steps` for `pattern` are the `Body` objects returned by the operations to copy, e.g.
`hole = ctx.extrude(s, -3, operation="cut"); ctx.pattern([hole], count=6)`. Often a plain Python loop that draws
all copies in one sketch is simpler and more predictable – prefer that for holes and slots.

### Solids built in code (manifold3d)

For shapes the sketch tools can't make (threads, lattices, swept meshes, complex brackets), build a
`manifold3d.Manifold` yourself and add it with `ctx.solid(shape, name=None, lid=False)` → `Body` (one timeline step;
the shape is stored as a mesh, so change it by running the script again). `name` defaults to `ctx.name`; `lid=True`
lets the Lids button in the view hide it. Useful manifold3d calls: `m3d.Manifold.cube((x, y, z), center=False)`,
`m3d.Manifold.cylinder(height, r_bottom, r_top, circular_segments=ctx.circle_segments)`,
`m3d.Manifold.sphere(r, circular_segments=ctx.sphere_segments)`, `m3d.Manifold.extrude(m3d.CrossSection([pts]),
height, twist_degrees=..., scale_top=(sx, sy))`, `m3d.Manifold.revolve(m3d.CrossSection([pts]), circular_segments=...)`
(the outline is in (r, z), revolved around Z), `a + b` (join), `a - b` (cut), `a ^ b` (intersect),
`.translate((x, y, z))`, `.rotate((rx, ry, rz))` (degrees), `.mirror((nx, ny, nz))`, `.hull()`,
`m3d.Manifold.batch_hull([...])`, `m3d.Manifold(m3d.Mesh(vert_properties=float32 Nx3, tri_verts=uint32 Mx3))`.
Use `ctx.circle_segments` / `ctx.sphere_segments` for round things, so they match the model's smoothness.
Keep meshes lean (tens of thousands of triangles at most): Omacad analyses every face and edge of each body.

`ctx.group(name, bodies)` puts the bodies' objects in one group in the browser (one click selects them all).

### Bodies and the model

A `Body` has `id`, `name`, `volume` (mm³), `bounds` (`((xmin, ymin, zmin), (xmax, ymax, zmax))`), `edges`,
`exists`, and `rename(name)`. Handles stay valid when the model is rebuilt; a body used up by `combine` or a `cut`
no longer `exists`.

`ctx.bodies` (all bodies), `ctx.body("name")`, `ctx.selected_bodies` (what the user had selected – may be empty;
the script also runs on an empty model during the test).

### Other

- `ctx.name` – the Name the user gave in the panel (see Names above).
- `ctx.circle_segments`, `ctx.sphere_segments` – the model's curve smoothness, for manifold3d shapes.

- `ctx.parameter(name, value, comment="")` – add or change a named user parameter (Modify › Change Parameters).
- `ctx.log(*parts)` – a line in the run report.
- `ctx.checking` – `True` while Omacad test-runs the script on an empty model (rarely needed).
- `ctx.units` – `"mm"`.

## Versions of built-in tools

`jar_with_lid.py`, `star_brackets.py` and `box_in_a_row.py` in the scripts folder are script versions of the
built-in Jar with Lid, Star Brackets and Box in a Row tools, with all their geometry code (manifold3d +
`ctx.solid`). A changed copy keeps their `FAMILY` line so it appears in the same tool's submenu. Change only what
was asked; keep the rest of the code as it is.

## Errors

Mistakes in API use raise `ScriptError` with a message saying what to change (e.g. "Sketch 'Sketch 2' has no
closed profile"). Any exception stops the run, rolls the model back and is shown with the script's line number.

## Testing

Omacad test-runs a script on an **empty model with the default values** whenever the script file changes while
the user waits for an AI-written script, and writes `<script name>.check.txt` next to it: `RESULT: OK` with the
bodies, their sizes (mm) and volumes (mm³), or `RESULT: FAILED` with the error, the line and the traceback.
So the script must work on an empty model with its defaults. The same test can be run from a terminal:
`omacad --check-script path/to/script.py` (see the command given with the request).

## Complete example

```python
import math

NAME = "Flange"
DESCRIPTION = "Round flange with a centre hole and a circle of bolt holes, edges rounded."
PARAMS = [
    {"name": "diameter", "type": "float", "default": 60.0, "min": 10.0, "unit": "mm"},
    {"name": "thickness", "type": "float", "default": 6.0, "min": 1.0, "unit": "mm"},
    {"name": "center_hole", "type": "float", "default": 20.0, "min": 0.0, "unit": "mm"},
    {"name": "bolts", "label": "Bolt holes", "type": "int", "default": 6, "min": 0, "max": 36},
    {"name": "bolt_diameter", "type": "float", "default": 5.5, "min": 1.0, "unit": "mm"},
    {"name": "round_edges", "type": "bool", "default": True},
]

def run(ctx, params):
    r = params["diameter"] / 2
    hole_r = params["center_hole"] / 2
    bolt_r = params["bolt_diameter"] / 2
    circle_r = (r + hole_r) / 2                     # bolt circle halfway between the hole and the rim
    if hole_r and circle_r - bolt_r < hole_r + 1:
        raise ValueError("The bolt holes run into the centre hole: make the flange bigger or the holes smaller.")

    s = ctx.sketch("XY", name="Flange")
    s.circle((0, 0), r)
    if hole_r > 0:
        s.circle((0, 0), hole_r)
    for i in range(params["bolts"]):
        a = 2 * math.pi * i / params["bolts"]
        s.circle((circle_r * math.cos(a), circle_r * math.sin(a)), bolt_r)
    flange = ctx.extrude(s, params["thickness"])    # "outer": the disc with all its holes
    flange.rename("Flange")

    if params["round_edges"]:
        ctx.fillet(flange, min(1.0, params["thickness"] / 4),
                   edges=lambda e: e.kind == "circle" and abs(e.radius - r) < 1e-3)
    ctx.log(f"Bolt circle diameter {2 * circle_r:.1f} mm, volume {flange.volume:.0f} mm³")
```

### Easy mode

Optional metadata: `EASY_PARAMS = ["width", "height"]` lists parameters visible in Easy mode. An empty list hides all parameters; omitted metadata shows all. Advanced always shows every parameter. Hidden parameters retain their values. Users can edit this list through the script context menu, “Easy mode settings…”.

The order in `EASY_PARAMS` determines the field order in Easy mode. Drag entries in “Easy mode settings…” to reorder them. Advanced uses the original `PARAMS` order.
