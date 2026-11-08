"""The stable script API: what `run(ctx, params)` can call. It is a thin layer over `Document`, so scripts keep working
when the internals change. Everything a script makes ends up as ordinary timeline steps (sketches, extrudes, boxes ...),
and the runner wraps the whole run in one undo step.

Units are millimetres and degrees. World axes: X right, Y back, Z up. Sketch coordinates are (u, v) on the sketch's
plane: XY -> (x, y), XZ -> (x, z), YZ -> (y, z)."""
import math
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

from omacad.scripting.loader import ScriptError

Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]
OPERATIONS = ("new_body", "join", "cut", "intersect", "auto")
PLANES = ("XY", "XZ", "YZ")


def _pt2(p, what="point") -> Point2:
    try:
        u, v = p
        return float(u), float(v)
    except (TypeError, ValueError):
        raise ScriptError(f"{what} must be (u, v), got {p!r}.")


def _pt3(p, what="point") -> Point3:
    try:
        x, y, z = p
        return float(x), float(y), float(z)
    except (TypeError, ValueError):
        raise ScriptError(f"{what} must be (x, y, z), got {p!r}.")


def _positive(value, what) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0:
        raise ScriptError(f"{what} must be larger than 0 (got {value!r}).")
    return v


class Profile:
    """A closed region of a sketch that can be extruded or revolved."""

    def __init__(self, index: int, raw):
        self.index = index
        self.area = float(raw.area)
        self.outline: List[Point2] = [tuple(map(float, p)) for p in raw.exterior_pts]
        self.holes: List[List[Point2]] = [[tuple(map(float, p)) for p in h] for h in raw.interior_holes]
        self._raw = raw

    @property
    def centroid(self) -> Point2:
        from shapely.geometry import Polygon
        c = Polygon(self.outline, self.holes).centroid
        return float(c.x), float(c.y)

    def contains(self, point) -> bool:
        u, v = _pt2(point)
        return bool(self._raw.contains_point(u, v))

    def __repr__(self):
        return f"Profile(index={self.index}, area={self.area:.3f}, holes={len(self.holes)})"


class Edge:
    """A body edge, for choosing what to fillet or chamfer."""

    def __init__(self, raw):
        self._raw = raw
        self.kind: str = getattr(raw, "kind", "line")       # "line", "circle", "loop" or "curve"
        if self.kind == "line":
            pts = np.array([raw.p0, raw.p1], dtype=float)
        elif self.kind == "circle":
            pts = np.asarray(raw.polyline(), dtype=float) if hasattr(raw, "polyline") else np.array([raw.center])
        else:
            pts = np.asarray(raw.pts, dtype=float)
        self.points = pts
        self.start: Point3 = tuple(map(float, pts[0]))
        self.end: Point3 = tuple(map(float, pts[-1]))
        self.zmin, self.zmax = float(pts[:, 2].min()), float(pts[:, 2].max())
        self.length = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum()) if len(pts) > 1 else 0.0
        self.convex: bool = bool(getattr(raw, "convex", True))
        self.radius: Optional[float] = float(raw.radius) if self.kind == "circle" else None
        self.center: Optional[Point3] = tuple(map(float, raw.center)) if self.kind == "circle" else None

    @property
    def is_vertical(self) -> bool:
        if self.kind != "line":
            return False
        d = np.asarray(self.end) - np.asarray(self.start)
        n = np.linalg.norm(d)
        return n > 1e-9 and abs(d[2]) / n > 0.999

    @property
    def is_horizontal(self) -> bool:
        return self.zmax - self.zmin < 1e-6

    def __repr__(self):
        return f"Edge({self.kind}, z={self.zmin:.3f}..{self.zmax:.3f}, length={self.length:.3f})"


class Body:
    """A solid in the model. Look it up again after later operations: the model is rebuilt and bodies are replaced,
    but this handle always reads the current one by its id."""

    def __init__(self, ctx: "ScriptContext", body_id: str, step: Optional[str] = None):
        self._ctx = ctx
        self.id = body_id
        self.step = step         # the timeline step that last made or changed it (for ctx.pattern)

    @property
    def _body(self):
        b = self._ctx._doc.bodies.get(self.id)
        if b is None:
            raise ScriptError(f"Body {self.id!r} no longer exists (was it used up by a combine or a cut?).")
        return b

    @property
    def exists(self) -> bool:
        return self.id in self._ctx._doc.bodies

    @property
    def name(self) -> str:
        return self._body.name

    @property
    def volume(self) -> float:
        return float(self._body.manifold.volume())

    @property
    def bounds(self) -> Tuple[Point3, Point3]:
        """((xmin, ymin, zmin), (xmax, ymax, zmax))."""
        bb = self._body.manifold.bounding_box()
        return tuple(map(float, bb[:3])), tuple(map(float, bb[3:]))

    @property
    def edges(self) -> List[Edge]:
        return [Edge(e) for e in self._body.edges]

    def rename(self, name: str) -> "Body":
        """Names the body, its step and its object (the row in the browser)."""
        self._ctx._name_body(self.id, str(name))
        return self

    def __repr__(self):
        return f"Body({self.id!r})"


class Sketch:
    """A 2D sketch on a plane. Draw with the methods below, then pass it to ctx.extrude / ctx.revolve."""

    def __init__(self, ctx: "ScriptContext", raw):
        self._ctx = ctx
        self._raw = raw
        self.id = raw.sketch_id

    @property
    def name(self) -> str:
        return self._raw.name

    def _check_open(self):
        if self._ctx._doc.active_sketch is not self._raw:
            raise ScriptError(f"Sketch {self.name!r} is finished; draw in it before you extrude or revolve it.")

    def line(self, p1, p2, construction: bool = False):
        self._check_open()
        a, b = _pt2(p1, "p1"), _pt2(p2, "p2")
        if a == b:
            raise ScriptError("A line needs two different points.")
        self._raw.add_line(a, b, is_construction=construction)
        return self

    def polyline(self, points: Sequence, closed: bool = True):
        """Straight lines through the points (no dimensions); closed=True joins the last point to the first.
        Best for computed outlines such as gear teeth or cams."""
        self._check_open()
        pts = [_pt2(p) for p in points]
        if len(pts) < (3 if closed else 2):
            raise ScriptError(f"A {'closed ' if closed else ''}polyline needs at least {3 if closed else 2} points.")
        self._raw.add_loop(pts, closed=closed)
        return self

    def rect(self, p1, p2, construction: bool = False):
        """Rectangle from two opposite corners."""
        self._check_open()
        a, b = _pt2(p1, "p1"), _pt2(p2, "p2")
        if abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9:
            raise ScriptError("A rectangle needs a width and a height.")
        self._raw.add_rect(a, b, is_construction=construction)
        return self

    def center_rect(self, center, width: float, height: float, construction: bool = False):
        cu, cv = _pt2(center, "center")
        w, h = _positive(width, "width") / 2, _positive(height, "height") / 2
        return self.rect((cu - w, cv - h), (cu + w, cv + h), construction)

    def rounded_rect(self, p1, p2, radius: float):
        self._check_open()
        self._raw.add_rounded_rect(_pt2(p1, "p1"), _pt2(p2, "p2"), _positive(radius, "radius"))
        return self

    def circle(self, center, radius: float, construction: bool = False):
        self._check_open()
        self._raw.add_circle(_pt2(center, "center"), _positive(radius, "radius"), is_construction=construction)
        return self

    def arc(self, start, mid, end, construction: bool = False):
        """Arc through three points (start, a point on the arc, end)."""
        self._check_open()
        self._raw.add_arc(_pt2(start, "start"), _pt2(mid, "mid"), _pt2(end, "end"), is_construction=construction)
        return self

    def polygon(self, center, radius: float, sides: int, angle: float = 90.0, construction: bool = False):
        """Regular polygon with its corners on a circle of `radius`; the first corner at `angle` degrees."""
        self._check_open()
        cu, cv = _pt2(center, "center")
        r = _positive(radius, "radius")
        if int(sides) < 3:
            raise ScriptError("A polygon needs at least 3 sides.")
        a = math.radians(angle)
        self._raw.add_polygon((cu, cv), (cu + r * math.cos(a), cv + r * math.sin(a)), int(sides), is_construction=construction)
        return self

    def slot(self, center1, center2, radius: float):
        """Slot (stadium) between two centre points."""
        self._check_open()
        self._raw.add_slot(_pt2(center1, "center1"), _pt2(center2, "center2"), _positive(radius, "radius"))
        return self

    def spline(self, points: Sequence, construction: bool = False):
        """Smooth curve through the points (open). Close an outline with lines or by repeating the first point."""
        self._check_open()
        pts = [_pt2(p) for p in points]
        if len(pts) < 2:
            raise ScriptError("A spline needs at least two points.")
        self._raw.add_spline(pts, is_construction=construction)
        return self

    @property
    def profiles(self) -> List[Profile]:
        return [Profile(i, p) for i, p in enumerate(self._raw.solve_profiles())]

    def to_world(self, point) -> Point3:
        u, v = _pt2(point)
        return tuple(map(float, self._raw.plane.uv_to_world(u, v)))

    def finish(self) -> "Sketch":
        """Ends drawing. Done automatically by extrude/revolve and at the end of the script."""
        if self._ctx._doc.active_sketch is self._raw:
            self._ctx._finish_open_sketch()
        return self

    def __repr__(self):
        return f"Sketch({self.name!r})"


ProfileChoice = Union[None, int, str, Tuple[float, float], Sequence[int]]


class ScriptContext:
    """`ctx` in `run(ctx, params)`."""

    units = "mm"

    def __init__(self, doc, log: Optional[Callable[[str], None]] = None, checking: bool = False, name: str = "Script"):
        self._doc = doc
        self._log_fn = log
        self.messages: List[str] = []
        self.checking = checking      # True while Omacad test-runs the script on an empty model
        self.name = str(name).strip() or "Script"   # what the user called the things this run makes (the Name field)
        self._named: set = set()      # body ids the script named itself
        self._objects_before = set(self._object_ids())

    # ---- quality ------------------------------------------------------------------------------------------------
    @property
    def circle_segments(self) -> int:
        """Flat pieces around a full circle at the model's curve smoothness (use for manifold3d circles/cylinders)."""
        from omacad.model import quality
        return quality.circle_segments()

    @property
    def sphere_segments(self) -> int:
        from omacad.model import quality
        return quality.sphere_segments()

    # ---- output -------------------------------------------------------------------------------------------------
    def log(self, *parts: Any) -> None:
        """A line for the run report (shown after the run and in the .check.txt file)."""
        text = " ".join(str(p) for p in parts)
        self.messages.append(text)
        if self._log_fn:
            self._log_fn(text)

    # ---- reading the model --------------------------------------------------------------------------------------
    @property
    def bodies(self) -> List[Body]:
        return [Body(self, bid) for bid in self._doc.bodies]

    def body(self, name_or_id: str) -> Body:
        for bid, b in self._doc.bodies.items():
            if bid == name_or_id or b.name == name_or_id:
                return Body(self, bid)
        raise ScriptError(f"No body called {name_or_id!r}. Bodies: {[b.name for b in self._doc.bodies.values()]}")

    @property
    def selected_bodies(self) -> List[Body]:
        return [Body(self, bid) for bid in self._doc.selected_body_ids if bid in self._doc.bodies]

    # ---- sketches -----------------------------------------------------------------------------------------------
    def sketch(self, plane: str = "XY", offset: float = 0.0, name: Optional[str] = None) -> Sketch:
        """A new sketch on an origin plane ("XY", "XZ", "YZ"), moved `offset` mm along the plane's normal
        (XY: +Z, XZ: -Y, YZ: +X)."""
        from omacad.model.sketch_entities import SketchPlane
        key = str(plane).upper()
        if key not in PLANES:
            raise ScriptError(f"plane must be one of {list(PLANES)} (got {plane!r}).")
        self._finish_open_sketch()
        off = float(offset)
        if abs(off) < 1e-12:
            raw = self._doc.start_sketch(key)
        else:
            base = SketchPlane.create_named(key)
            shifted = SketchPlane(name="PLANE", origin=(base.origin + base.normal * off).astype(np.float32),
                                  u_axis=base.u_axis, v_axis=base.v_axis, normal=base.normal)
            raw = self._doc.start_sketch_on_plane(shifted)
        if name:
            raw.name = str(name)
        # only what the script draws makes profiles: edges of bodies lying in the plane would add regions that
        # depend on what the model happens to contain (and shift profile indices)
        raw.reference_segments = []
        raw.solve_profiles()
        return Sketch(self, raw)

    def _finish_open_sketch(self) -> None:
        raw = self._doc.active_sketch
        if raw is None:
            return
        self._doc.finish_sketch()
        for f in self._doc.timeline.features:
            if getattr(f, "sketch", None) is raw and hasattr(f, "reference_bodies"):
                f.reference_bodies = []          # keeps body edges out on every rebuild too
        raw.reference_segments = []
        raw.solve_profiles()

    def _profiles(self, sketch: Sketch, profile: ProfileChoice) -> List[int]:
        if not isinstance(sketch, Sketch):
            raise ScriptError("Pass the sketch returned by ctx.sketch(...).")
        profs = sketch._raw.solve_profiles()
        if not profs:
            raise ScriptError(f"Sketch {sketch.name!r} has no closed profile (are all outlines closed?).")
        n = len(profs)
        if profile is None or profile == "outer":
            return _outer_profiles(profs)
        if profile == "all":
            return list(range(n))
        if profile == "largest":
            return [max(range(n), key=lambda i: profs[i].area)]
        if isinstance(profile, bool):
            raise ScriptError("profile must be None, an index, 'all', 'outer', 'largest', a (u, v) point or a list.")
        if isinstance(profile, int):
            if not 0 <= profile < n:
                raise ScriptError(f"profile {profile} does not exist; sketch {sketch.name!r} has {n} profiles (0..{n - 1}).")
            return [profile]
        if isinstance(profile, (tuple, list)) and len(profile) == 2 and all(isinstance(x, float) for x in profile):
            u, v = profile
            hits = [i for i, p in enumerate(profs) if p.contains_point(u, v)]
            if not hits:
                raise ScriptError(f"No profile of sketch {sketch.name!r} contains the point {tuple(profile)}.")
            return [min(hits, key=lambda i: profs[i].area)]
        if isinstance(profile, (tuple, list)):
            out = []
            for p in profile:
                out += self._profiles(sketch, p)
            return list(dict.fromkeys(out))
        raise ScriptError("profile must be None, an index, 'all', 'outer', 'largest', a (u, v) point (floats) or a list.")

    # ---- features -----------------------------------------------------------------------------------------------
    def _run_step(self, fn) -> Tuple[Any, Optional[str], List[str], List[str]]:
        """Runs one Document operation; returns (result, new step id, new body ids, changed body ids)."""
        doc = self._doc
        steps_before = [f.feature_id for f in doc.timeline.features]
        bodies_before = {bid: b.manifold for bid, b in doc.bodies.items()}
        result = fn()
        new_steps = [f for f in doc.timeline.features if f.feature_id not in steps_before]
        step = new_steps[-1] if new_steps else None
        problem = getattr(step, "problem", "") if step is not None else ""
        if problem:
            raise ScriptError(f"{step.name}: {problem}")
        new = [bid for bid in doc.bodies if bid not in bodies_before]
        changed = [bid for bid, b in doc.bodies.items() if bid in bodies_before and b.manifold is not bodies_before[bid]]
        return result, step.feature_id if step is not None else None, new, changed

    def _body_result(self, what: str, step, new, changed) -> Optional[Body]:
        ids = new or changed
        if not ids:
            self.log(f"warning: {what} changed nothing in the model.")
            return None
        return Body(self, ids[0], step)

    def extrude(self, sketch: Sketch, distance: float, operation: str = "new_body", profile: ProfileChoice = None,
                symmetric: bool = False, distance2: Optional[float] = None, taper: float = 0.0,
                start_offset: float = 0.0, twist: float = 0.0) -> Optional[Body]:
        """Extrudes profiles of `sketch` along its normal. Negative distance goes the other way.
        operation: "new_body", "join", "cut", "intersect" or "auto" (decides like the Extrude panel).
        profile: None/"outer" = every region that is not a hole of another, "all", "largest", an index,
        a (u, v) point inside the region, or a list of these. symmetric: half on each side.
        distance2: a second distance the other way (two sides). Returns the new or changed body."""
        op = self._operation(operation)
        if abs(float(distance)) < 1e-9 and not symmetric:
            raise ScriptError("distance must not be 0.")
        idx = self._profiles(sketch, profile)
        sketch.finish()
        direction = "symmetric" if symmetric else ("two_sides" if distance2 is not None else "one_side")
        if abs(float(taper)) > 1e-9:
            raise ScriptError("taper is not supported by scripts yet; use ctx.revolve or a polyline for tapered shapes.")

        def go():
            return self._doc.extrude_profile(sketch.id, idx[0], float(distance), op, direction=direction,
                                             distance2=float(distance2 or 0.0), extra_profiles=idx[1:],
                                             start_offset=float(start_offset), twist=float(twist))
        _, step, new, changed = self._run_step(go)
        return self._body_result("extrude", step, new, changed)

    def revolve(self, sketch: Sketch, axis: Union[str, Tuple[Point2, Point2]] = "v", angle: float = 360.0,
                operation: str = "new_body", profile: ProfileChoice = None) -> Optional[Body]:
        """Turns profiles around an axis in the sketch: "u" (the sketch's horizontal axis), "v" (vertical axis), or
        ((u1, v1), (u2, v2)) any line, added as a construction line. The profile must lie on one side of the axis."""
        op = self._operation(operation)
        idx = self._profiles(sketch, profile)
        if axis in ("u", "v"):
            ax = (axis,)
        else:
            try:
                a, b = axis
                line = sketch._raw.add_line(_pt2(a, "axis start"), _pt2(b, "axis end"), is_construction=True)
            except (TypeError, ValueError):
                raise ScriptError("axis must be 'u', 'v' or ((u1, v1), (u2, v2)).")
            ax = ("line", line.entity_id)
            idx = self._profiles(sketch, profile)
        sketch.finish()
        _, step, new, changed = self._run_step(lambda: self._doc.add_revolve(
            sketch.id, idx[0], axis=ax, angle=float(angle), operation=op, extra_profiles=idx[1:]))
        return self._body_result("revolve", step, new, changed)

    def box(self, length: float, width: float, height: float, at=(0.0, 0.0, 0.0), center: bool = False,
            name: Optional[str] = None) -> Body:
        """Box along X (length), Y (width), Z (height). Its lower-left-bottom corner at `at`, or its centre at `at`
        with center=True (the bottom stays on `at`'s Z when center is False)."""
        l, w, h = _positive(length, "length"), _positive(width, "width"), _positive(height, "height")
        x, y, z = _pt3(at, "at")
        mode, tx = (True, (x, y, z)) if center else ("bottom_center", (x + l / 2, y + w / 2, z))
        body, step, new, _ = self._run_step(lambda: self._doc.add_box(l, w, h, center=mode, name=name,
                                                                       translation=list(tx)))
        return self._made(new[0] if new else body.body_id, step, name)

    def cylinder(self, radius: float, height: float, at=(0.0, 0.0, 0.0), name: Optional[str] = None) -> Body:
        """Upright cylinder (along +Z) with its bottom centre at `at`."""
        r, h = _positive(radius, "radius"), _positive(height, "height")
        body, step, new, _ = self._run_step(lambda: self._doc.add_cylinder(r, h, name=name, translation=list(_pt3(at, "at"))))
        return self._made(new[0] if new else body.body_id, step, name)

    def cone(self, radius: float, top_radius: float, height: float, at=(0.0, 0.0, 0.0), name: Optional[str] = None) -> Body:
        """Upright cone or frustum; top_radius 0 = a point."""
        r, h = _positive(radius, "radius"), _positive(height, "height")
        tr = float(top_radius)
        if tr < 0:
            raise ScriptError("top_radius must be 0 or more.")
        body, step, new, _ = self._run_step(lambda: self._doc.add_cone(r, tr, h, name=name, translation=list(_pt3(at, "at"))))
        return self._made(new[0] if new else body.body_id, step, name)

    def sphere(self, radius: float, at=(0.0, 0.0, 0.0), name: Optional[str] = None) -> Body:
        r = _positive(radius, "radius")
        body, step, new, _ = self._run_step(lambda: self._doc.add_sphere(r, name=name, translation=list(_pt3(at, "at"))))
        return self._made(new[0] if new else body.body_id, step, name)

    def combine(self, target: Body, tools: Union[Body, Iterable[Body]], operation: str = "join",
                keep_tools: bool = False) -> Body:
        """Join / cut / intersect `tools` with `target`. The tools are used up unless keep_tools=True."""
        if operation not in ("join", "cut", "intersect"):
            raise ScriptError("combine operation must be 'join', 'cut' or 'intersect'.")
        tools = [tools] if isinstance(tools, Body) else list(tools)
        step = None
        for t in tools:
            if not isinstance(t, Body) or not isinstance(target, Body):
                raise ScriptError("combine takes Body objects (what box/cylinder/extrude return).")
            if t.id == target.id:
                raise ScriptError("A body can't be combined with itself.")
            target._body, t._body          # both must exist (raises a clear error otherwise)
            _, step, _, _ = self._run_step(lambda t=t: self._doc.combine_bodies(target.id, t.id, operation,
                                                                                keep_tool=keep_tools))
        return Body(self, target.id, step)

    def move(self, body: Body, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, rx: float = 0.0, ry: float = 0.0,
             rz: float = 0.0, copy: bool = False) -> Body:
        """Moves (and/or turns around its own centre, degrees about X, Y, Z) a body. copy=True moves a copy."""
        before = set(self._doc.bodies)
        _, step, new, _ = self._run_step(lambda: self._doc.move_body(body.id, float(dx), float(dy), float(dz), float(rx),
                                                                     float(ry), float(rz), copy_body=bool(copy)))
        made = [b for b in self._doc.bodies if b not in before]
        return Body(self, made[0] if copy and made else body.id, step)

    def fillet(self, body: Body, radius: float, edges: Union[str, Callable[[Edge], bool], Sequence[Edge]] = "all",
               chamfer: bool = False) -> Body:
        """Rounds (or with chamfer=True bevels) edges of `body`. edges: "all", "top", "bottom", "vertical",
        "horizontal", a function Edge -> bool, or a list of Edge objects from body.edges."""
        size = _positive(radius, "radius")
        chosen = self._pick_edges(body, edges)
        if not chosen:
            raise ScriptError(f"No edges of {body.name!r} match {edges!r}.")
        _, step, _, _ = self._run_step(lambda: self._doc.add_fillet([e._raw.ref() for e in chosen], size,
                                                                    "chamfer" if chamfer else "fillet"))
        return Body(self, body.id, step)

    def chamfer(self, body: Body, size: float, edges="all") -> Body:
        return self.fillet(body, size, edges, chamfer=True)

    def _pick_edges(self, body: Body, edges) -> List[Edge]:
        all_edges = [e for e in body.edges if e.kind != "curve"]
        if isinstance(edges, str):
            if not all_edges:
                return []
            top = max(e.zmax for e in all_edges)
            bottom = min(e.zmin for e in all_edges)
            tests = {"all": lambda e: True,
                     "top": lambda e: e.is_horizontal and abs(e.zmax - top) < 1e-4,
                     "bottom": lambda e: e.is_horizontal and abs(e.zmin - bottom) < 1e-4,
                     "vertical": lambda e: e.is_vertical,
                     "horizontal": lambda e: e.is_horizontal}
            if edges not in tests:
                raise ScriptError(f"edges must be one of {list(tests)}, a function or a list (got {edges!r}).")
            return [e for e in all_edges if tests[edges](e)]
        if callable(edges):
            return [e for e in all_edges if edges(e)]
        return [e for e in edges if isinstance(e, Edge)]

    def shell(self, body: Body, thickness: float, open_top: bool = True) -> Body:
        """Hollows a body to a wall thickness; open_top leaves its highest flat face open."""
        t = _positive(thickness, "thickness")
        faces = []
        if open_top:
            b = body._body
            ups = [f for f in b.faces if float(np.asarray(f.normal)[2]) > 0.999]
            if ups:
                top = max(ups, key=lambda f: float(np.asarray(f.tris).reshape(-1, 3)[:, 2].max()))
                pts = np.asarray(top.tris, dtype=float).reshape(-1, 3)
                faces = [{"normal": [float(x) for x in top.normal], "origin": [float(x) for x in pts.mean(axis=0)],
                          "body_id": body.id}]
        _, step, _, _ = self._run_step(lambda: self._doc.add_shell(body.id, t, open_faces=faces or None))
        return Body(self, body.id, step)

    def pattern(self, steps: Sequence[Body], kind: str = "circular", count: int = 2, spacing: float = 10.0,
                axis: str = "z", angle: float = 360.0, count2: int = 1, spacing2: float = 10.0,
                axis2: str = "y") -> Body:
        """Copies what the given steps did (a hole, a boss and its fillets ...), using the Body objects the steps
        returned. kind "circular": `count` copies in total around `axis` ("x", "y", "z", through the body centre)
        over `angle`. kind "linear": `count` along `axis` every `spacing` mm, optionally `count2` along `axis2`."""
        ids = [s.step for s in steps if isinstance(s, Body) and s.step]
        if not ids:
            raise ScriptError("pattern needs the Body objects returned by the steps to copy (e.g. a cut extrude).")
        if kind not in ("circular", "linear"):
            raise ScriptError("pattern kind must be 'circular' or 'linear'.")
        if int(count) < 2:
            raise ScriptError("count must be at least 2.")
        if kind == "circular":
            params = dict(count1=int(count), angle=float(angle), rotation_axis=str(axis).lower())
        else:
            params = dict(axis1=str(axis).lower(), count1=int(count), spacing1=float(spacing),
                          axis2=str(axis2).lower(), count2=int(count2), spacing2=float(spacing2))
        _, step, new, changed = self._run_step(lambda: self._doc.add_pattern(ids, kind, **params))
        return self._body_result("pattern", step, new, changed) or steps[-1]

    # ---- parameters ---------------------------------------------------------------------------------------------
    def parameter(self, name: str, value: Union[float, str], comment: str = "") -> None:
        """Adds or changes a named user parameter (Modify > Change Parameters)."""
        from omacad.model.document import Parameter
        params = [Parameter(p.name, p.expr, p.comment) for p in self._doc.parameters]
        for p in params:
            if p.name == name:
                p.expr, p.comment = str(value), comment or p.comment
                break
        else:
            params.append(Parameter(str(name), str(value), comment))
        problems = self._doc.set_parameters(params)
        if problems:
            raise ScriptError("Parameter problem: " + "; ".join(map(str, problems)))

    def _made(self, body_id: str, step, name: Optional[str]) -> Body:
        if name:
            self._name_body(body_id, str(name))
        return Body(self, body_id, step)

    # ---- finished solids and groups ------------------------------------------------------------------------------
    def solid(self, shape, name: Optional[str] = None, lid: bool = False) -> Body:
        """Adds a finished manifold3d.Manifold (built by the script itself) as a body, as one timeline step.
        `name` defaults to ctx.name. lid=True marks it as a lid (the Lids button in the view shows/hides it)."""
        import manifold3d as m3d
        if not isinstance(shape, m3d.Manifold):
            raise ScriptError(f"ctx.solid needs a manifold3d.Manifold, got {type(shape).__name__}.")
        if shape.is_empty() or shape.volume() <= 1e-9:
            raise ScriptError("ctx.solid got an empty shape (no volume): check the booleans that built it.")
        mesh = shape.to_mesh()
        verts = np.asarray(mesh.vert_properties, dtype=float)[:, :3].tolist()
        tris = np.asarray(mesh.tri_verts, dtype=int).tolist()
        label = str(name).strip() if name else self.name
        feat, step, new, _ = self._run_step(lambda: self._doc.import_mesh(label, verts, tris, source_file="script"))
        bid = new[0] if new else getattr(feat, "created_body_id", f"body_{feat.feature_id}")
        if lid and hasattr(self._doc, "lids"):
            self._doc.lids.add(bid)
            if bid in self._doc.bodies:
                self._doc.bodies[bid].is_lid = True
        if name:
            self._name_body(bid, label)
        return Body(self, bid, step)

    def group(self, name: str, bodies: Sequence[Body]) -> None:
        """Puts the objects of these bodies in one group in the browser (a click selects them all)."""
        oids = []
        for b in bodies:
            oid = self._object_of(b.id)
            if oid and oid not in oids:
                oids.append(oid)
        if oids:
            self._doc.create_object_group(str(name), oids)

    # ---- names --------------------------------------------------------------------------------------------------
    def _object_ids(self):
        hist = getattr(self._doc, "object_history", None)
        return list(hist.objects) if hist is not None else []

    def _object_of(self, body_id: str) -> Optional[str]:
        hist = getattr(self._doc, "object_history", None)
        if hist is None:
            return None
        hist.sync(self._doc)
        return next((oid for oid, o in hist.objects.items() if body_id in o.body_ids), None)

    def _name_body(self, body_id: str, name: str) -> None:
        name = name.strip()
        if not name:
            raise ScriptError("A name can't be empty.")
        self._doc.rename_item("body", body_id, name)
        oid = self._object_of(body_id)
        if oid:
            self._doc.object_history.names[oid] = name
            self._doc.object_history.objects[oid].name = name
        self._named.add(body_id)
        self._doc.notify_changed()

    def _name_new_objects(self) -> None:
        """Objects this run made that the script did not name get ctx.name ("Gear", "Gear 2" ...)."""
        hist = getattr(self._doc, "object_history", None)
        if hist is None:
            return
        hist.sync(self._doc)
        n = 0
        for oid, obj in hist.objects.items():
            if oid in self._objects_before or not obj.body_ids or any(b in self._named for b in obj.body_ids):
                continue
            n += 1
            label = self.name if n == 1 else f"{self.name} {n}"
            hist.names[oid] = obj.name = label
            for bid in obj.body_ids:
                if bid in self._doc.bodies:
                    self._doc.rename_item("body", bid, label)
        if n:
            self._doc.notify_changed()

    def finish(self) -> None:
        """Called by the runner after run(): ends a sketch left open and names what the script did not name."""
        self._finish_open_sketch()
        self._name_new_objects()

    # ---- helpers ------------------------------------------------------------------------------------------------
    @staticmethod
    def _operation(op: str) -> str:
        if op not in OPERATIONS:
            raise ScriptError(f"operation must be one of {list(OPERATIONS)} (got {op!r}).")
        return op


def _outer_profiles(profs) -> List[int]:
    """Every profile that is not exactly the hole of another one (a washer = the ring, not the disc in its middle)."""
    from shapely.geometry import Polygon
    holes = [Polygon(h) for p in profs for h in p.interior_holes if len(h) >= 3]
    out = []
    for i, p in enumerate(profs):
        poly = Polygon(p.exterior_pts)
        if any(abs(poly.area - h.area) < 1e-6 * max(1.0, h.area) and h.contains(poly.representative_point())
               for h in holes):
            continue
        out.append(i)
    return out or list(range(len(profs)))
