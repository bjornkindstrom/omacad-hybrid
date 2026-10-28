"""Sketch entity creation, editing, and reference operations."""

from typing import List, Tuple, Optional, Dict
import math
from omacad.model.sketch_entities import _hermite
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, Point, MultiPoint
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union, snap
from omacad.model.sketch_entities import (
    SketchEntity, SketchLine, SketchRect, SketchCenterRect, SketchCircle, SketchArc, SketchSlot, SketchSpline, SketchText,
    ref_id, ref_segment, point_of, rotate_point, move_entity, rotate_entity, entity_key_points
)
from omacad.model.sketch_types import SketchConstraint, SketchDimension
from omacad.model.sketch_fillet_curves import corner_point, end_tangent, fillet_points, trim_end
from omacad.model.sketch_fillet_curves import ends as fillet_ends


def _snap_ends(segs, tol: float):
    """End points closer than `tol` become one point. Edges read from two tessellations of the same outline stop a
    hair (~1e-3 mm) apart, so the outline never closed and was dropped as mesh seams (Björn #103)."""
    pts = np.array([p for ab in segs for p in ab], dtype=float)
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid: Dict[tuple, list] = {}
    for i, (x, y) in enumerate(pts):
        gx, gy = int(math.floor(x / tol)), int(math.floor(y / tol))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if abs(pts[j][0] - x) <= tol and abs(pts[j][1] - y) <= tol:
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[ri] = rj
        grid.setdefault((gx, gy), []).append(i)
    rep = [tuple(pts[find(i)]) for i in range(len(pts))]
    return [(rep[2 * k], rep[2 * k + 1]) for k in range(len(segs)) if rep[2 * k] != rep[2 * k + 1]]


def _outline_rings(segs, tol: float = 5e-3):
    """Splits reference segments into the closed rings of the region they enclose (outer outlines and holes, as
    simplified point lists) and the segments that are not part of such an outline (returned as they are)."""
    if not segs:
        return [], segs
    try:
        noded = unary_union([LineString([a, b]) for a, b in _snap_ends(segs, 0.5 * tol)])
        cells = [c.buffer(0) for c in polygonize(noded)]
    except Exception:
        return [], segs
    if not cells or len(cells) > 2000:
        return [], segs
    # A closed loop of edges also encloses a cell where there is a hole: count how many outlines each cell lies in;
    # even = material of the face, odd = a hole (a boss inside a hole is even again). Specks under 0.01 mm² are
    # seams of the mesh (two tessellations of a corner crossing), never holes anyone drew: they count as material.
    filled = [Polygon(c.exterior) for c in cells]
    material = []
    for i, c in enumerate(cells):
        if c.area < 1e-2:
            material.append(c)
            continue
        p = c.representative_point()
        depth = sum(1 for j, f in enumerate(filled) if j != i and f.area > c.area and f.contains(p))
        if depth % 2 == 0:
            material.append(c)
    region = unary_union(material)
    polys = [g for g in (region.geoms if hasattr(region, "geoms") else [region]) if not g.is_empty and g.area > tol * tol]
    if not polys:
        return [], segs
    rings = []
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.simplify(tol).coords)[:-1]
            if len(pts) >= 3:
                rings.append([(float(x), float(y)) for x, y in pts])
    # what is left: edges outside the enclosed region (dangling ones). Those on its outline are in the rings, and
    # those inside it are seams of the mesh (tiny triangles where two tessellations of a corner overlap)
    covered = unary_union(polys).buffer(10 * tol)
    rest = [(a, b) for a, b in segs if not covered.contains(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))]
    return rings, rest


def _ring_pieces(ring, max_turn_deg: float = 20.0, length_ratio: float = 3.0):
    """("line", a, b) / ("arc", start, mid, end) / ("circle", centre, r) pieces for a closed ring of points: runs of short, evenly turning pieces that fit one circle become an
    arc (the whole ring a circle), everything else straight lines with collinear pieces merged. A run ends at a sharp
    turn or where the piece length jumps (a straight edge running tangent into a rounded corner)."""
    pts = np.asarray(ring, dtype=float)
    n = len(pts)
    seg = np.roll(pts, -1, axis=0) - pts                     # piece i runs from point i to point i+1
    length = np.linalg.norm(seg, axis=1)
    ang = np.arctan2(seg[:, 1], seg[:, 0])
    turn = (ang - np.roll(ang, 1) + np.pi) % (2 * np.pi) - np.pi     # turn at point i (from piece i-1 to piece i)
    prev_len = np.roll(length, 1)
    ratio = np.maximum(length, prev_len) / np.maximum(np.minimum(length, prev_len), 1e-12)
    breaks = [i for i in range(n) if abs(math.degrees(turn[i])) > max_turn_deg or ratio[i] > length_ratio]

    def fit(points):
        A = np.c_[2 * points[:, 0], 2 * points[:, 1], np.ones(len(points))]
        sol, *_ = np.linalg.lstsq(A, (points ** 2).sum(axis=1), rcond=None)
        c = sol[:2]
        r = float(np.sqrt(max(sol[2] + c @ c, 0.0)))
        return c, r, float(np.abs(np.linalg.norm(points - c, axis=1) - r).max())

    if not breaks:                                           # one even curve all round: a circle
        c, r, res = fit(pts)
        if n >= 6 and r > 1e-6 and res < max(2e-3 * r, 5e-3):
            return [("circle", (float(c[0]), float(c[1])), r)]
        breaks = [0]
    out = []
    for k, b0 in enumerate(breaks):
        b1 = breaks[(k + 1) % len(breaks)]
        idx = list(range(b0, b1 + 1)) if b1 > b0 else list(range(b0, n)) + list(range(0, b1 + 1))
        run = pts[idx]
        if len(run) >= 4:                                    # three or more pieces: an arc?
            c, r, res = fit(run)
            turning = abs(float(np.sum(turn[idx[1:-1]])))
            if r > 1e-6 and res < max(2e-3 * r, 5e-3) and turning > math.radians(5.0) and r < 1e4:
                out.append(("arc", tuple(map(float, run[0])), tuple(map(float, run[len(run) // 2])), tuple(map(float, run[-1]))))
                continue
        start = run[0]
        for i in range(1, len(run)):
            if i < len(run) - 1:
                d1, d2 = run[i] - run[i - 1], run[i + 1] - run[i]
                n1, n2 = np.linalg.norm(d1), np.linalg.norm(d2)
                if n1 > 1e-12 and n2 > 1e-12 and abs(float(d1 @ d2) / (n1 * n2) - 1.0) < 1e-6:
                    continue
            if np.linalg.norm(run[i] - start) > 1e-6:
                out.append(("line", tuple(map(float, start)), tuple(map(float, run[i]))))
            start = run[i]
    return out


class SketchEditingMixin:
    """Entity editing and geometry construction methods inherited by :class:`Sketch`."""

    def offset_entities(self, ids, distance: float) -> list:
        """Parallel copies of the given elements, `distance` mm away: outward for closed shapes and circles
        (negative = inward), to the left of the drawing direction for open curves. Returns the new elements."""
        from shapely.geometry import LineString, Polygon
        from shapely.ops import linemerge
        ids = set(ids)
        new = []
        segs = []
        for ent in self.entities:
            if ent.entity_id not in ids or ent.is_construction:
                continue
            if isinstance(ent, SketchCircle):
                r = ent.radius + distance
                if r > 1e-6:
                    c = SketchCircle(self._new_entity_id("circle"), ent.center, r)
                    self.entities.append(c)
                    new.append(c)
            elif isinstance(ent, (SketchRect, SketchCenterRect, SketchSlot)):
                segs.extend(ent.to_lines())
            elif isinstance(ent, SketchSpline):
                from omacad.model.sketch_offset import offset_spline
                for points in offset_spline(ent, distance):
                    spline = SketchSpline(self._new_entity_id("spline"), points)
                    self.entities.append(spline)
                    new.append(spline)
        # lines and arcs: whole chains, radii follow along, joints are remade
        from omacad.model.sketch_offset import offset_entities_chains
        chain_in = [e for e in self.entities if e.entity_id in ids and not e.is_construction and isinstance(e, (SketchLine, SketchArc))]
        pieces, _ = offset_entities_chains(chain_in, distance)
        for seg in pieces:
            if seg.kind == "line":
                n = SketchLine(self._new_entity_id("line"), seg.p, seg.q)
            else:
                n = SketchArc(self._new_entity_id("arc"), seg.p, seg.mid(), seg.q)
            self.entities.append(n)
            new.append(n)
        if segs:
            merged = linemerge([LineString([a, b]) for a, b in segs])
            for geom in (merged.geoms if hasattr(merged, "geoms") else [merged]):
                coords = list(geom.coords)
                if geom.is_ring and len(coords) >= 4:
                    res = Polygon(coords).buffer(distance, join_style=2, mitre_limit=10.0)
                    outs = [res.exterior.coords] if not res.is_empty and res.geom_type == "Polygon" else []
                    if not res.is_empty and res.geom_type == "Polygon":
                        outs += [h.coords for h in res.interiors]
                    for ring in outs:
                        new.extend(self.add_loop(list(ring)[:-1], closed=True))
                else:
                    off = geom.offset_curve(distance, join_style=2, mitre_limit=10.0)
                    for part in (off.geoms if hasattr(off, "geoms") else [off]):
                        if not part.is_empty and len(part.coords) >= 2:
                            new.extend(self.add_loop(list(part.coords), closed=False))
        self.solve_profiles()
        return new

    def _bind_texts(self) -> None:
        for e in self.entities:
            if isinstance(e, SketchText):
                e.sketch = self

    def text_profile_indices(self) -> List[int]:
        """Indices of the profiles that are the letters themselves (not the counters inside an O or A): everything
        Emboss or Extrude should take to make the text."""
        from shapely.ops import unary_union
        glyphs = [p for e in self.entities if isinstance(e, SketchText) for p in e.polygons()]
        if not glyphs:
            return []
        area = unary_union(glyphs)
        return [i for i, prof in enumerate(self.profiles)
                if area.contains(Polygon(prof.exterior_pts, prof.interior_holes).buffer(0).representative_point())]

    def explode_text(self, entity_id: str) -> list:
        """Fusion's Explode: the text becomes ordinary lines (its outlines) and stops being editable text."""
        ent = next((e for e in self.entities if e.entity_id == entity_id and isinstance(e, SketchText)), None)
        if ent is None:
            return []
        lines = []
        for p1, p2 in ent.to_lines():
            if abs(p1[0] - p2[0]) > 1e-9 or abs(p1[1] - p2[1]) > 1e-9:
                lines.append(SketchLine(self._new_entity_id("line"), p1, p2, is_construction=ent.is_construction))
                self.entities.append(lines[-1])
        self.entities.remove(ent)
        self.solve_profiles()
        return lines

    def add_text(self, text: str, anchor: Tuple[float, float] = (0.0, 0.0), **params) -> "SketchText":
        """Text at `anchor` (see SketchText for the options); `path_id` makes it run along a circle, arc or line."""
        ent = SketchText(self._new_entity_id("text"), text, anchor, **params)
        ent.sketch = self
        self.entities.append(ent)
        self.solve_profiles()
        return ent

    def mirror_entities(self, ids, a, b) -> list:
        """Mirror copies of the given elements across the line through points a and b (the originals stay).
        Lines, circles, arcs, slots and text; the copies carry no dimensions or constraints."""
        ax, ay = a
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return []
        dx, dy = dx / L, dy / L

        def mp(q):
            wx, wy = q[0] - ax, q[1] - ay
            t = wx * dx + wy * dy
            fx, fy = ax + dx * t, ay + dy * t   # foot of the perpendicular
            return (2 * fx - q[0], 2 * fy - q[1])

        ids = set(ids)
        new = []
        for ent in list(self.entities):
            if ent.entity_id not in ids:
                continue
            c = ent.is_construction
            if isinstance(ent, SketchLine):
                n = SketchLine(self._new_entity_id("line"), mp(ent.p1), mp(ent.p2), is_construction=c)
            elif isinstance(ent, SketchCircle):
                n = SketchCircle(self._new_entity_id("circle"), mp(ent.center), ent.radius, is_construction=c)
            elif isinstance(ent, SketchArc):
                n = SketchArc(self._new_entity_id("arc"), mp(ent.p_start), mp(ent.p_mid), mp(ent.p_end), is_construction=c)
            elif isinstance(ent, SketchSpline):
                n = SketchSpline(self._new_entity_id("spline"), [mp(p) for p in ent.points], is_construction=c,
                                 tangents={k: tuple(a - b for a, b in zip(mp(v), mp((0.0, 0.0)))) for k, v in ent.tangents.items()})
            elif isinstance(ent, SketchSlot):
                n = SketchSlot(self._new_entity_id("slot"), mp(ent.center1), mp(ent.center2), ent.radius, is_construction=c)
            elif isinstance(ent, SketchText):
                # a reflection is a turn by 2*phi - angle of the mirrored letters (flip_v): Rot(2phi) Flip_y Rot(a) F = Rot(2phi-a) F[fy toggled]
                phi = math.degrees(math.atan2(dy, dx))
                n = SketchText.from_dict(dict(ent.to_dict(), entity_id=self._new_entity_id("text"),
                                              anchor=list(mp(ent.anchor)), angle=2.0 * phi - ent.angle,
                                              flip_v=not ent.flip_v))
                n.sketch = self
            else:
                continue
            self.entities.append(n)
            new.append(n)
        self.solve_profiles()
        return new

    def include_reference_edges(self, segments=None) -> list:
        """Fusion's Project / Include: the body edges lying in this sketch plane (the outline of the face the sketch is
        on) become real sketch elements - lines, full circles and arcs - that can be offset, trimmed, snapped to and
        drawn on like anything drawn here. They are marked `projected` (drawn in another colour, not draggable).
        Returns the new elements."""
        segs = [(tuple(a), tuple(b)) for a, b in (self.reference_segments if segments is None else segments)
                if abs(a[0] - b[0]) > 1e-9 or abs(a[1] - b[1]) > 1e-9]
        # ignore what is already here (included before, or drawn by hand on top of the edge)
        have = set()
        for e in self.entities:
            for a, b in e.to_lines():
                have.add((round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)))
                have.add((round(b[0], 3), round(b[1], 3), round(a[0], 3), round(a[1], 3)))

        def key(p):
            return (round(p[0], 3), round(p[1], 3))

        new = []

        def add(ent):
            ent.projected = True
            self.entities.append(ent)
            new.append(ent)

        # The face outline as closed rings first: a tessellated body gives a rounded corner as dozens of tiny
        # pieces (sometimes two slightly different tessellations on top of each other, and pieces that stop
        # 0.01 mm short of the straight edge). Read as one outline, each ring becomes lines and arcs sharing their
        # end points, so the outline is closed and an offset keeps the radius (Björn #58).
        rings, segs = _outline_rings(segs)
        for ring in rings:
            for kind, *geo in _ring_pieces(ring):
                if kind == "line":
                    a_, b_ = geo
                    if (round(a_[0], 3), round(a_[1], 3), round(b_[0], 3), round(b_[1], 3)) not in have:
                        add(SketchLine(self._new_entity_id("line"), a_, b_))
                elif kind == "arc":
                    add(SketchArc(self._new_entity_id("arc"), *geo))
                elif (round(geo[0][0], 3), round(geo[0][1], 3), round(geo[1], 3)) not in {
                        (round(e.center[0], 3), round(e.center[1], 3), round(e.radius, 3))
                        for e in self.entities if e.entity_type == "circle"}:
                    add(SketchCircle(self._new_entity_id("circle"), *geo))

        adj: Dict[tuple, list] = {}
        for a, b in segs:
            adj.setdefault(key(a), []).append((b, a))
            adj.setdefault(key(b), []).append((a, b))
        pos = {key(p): p for ab in segs for p in ab}
        used = set()
        chains = []

        def walk(start, first):
            chain = [start]
            prev, cur = start, first
            while True:
                chain.append(cur)
                ks = (key(prev), key(cur))
                used.add(ks); used.add(ks[::-1])
                nxt = [q for q, _ in adj[key(cur)] if key(q) != key(prev) and (key(cur), key(q)) not in used]
                if len(adj[key(cur)]) != 2 or not nxt or key(cur) == key(start):
                    break
                prev, cur = cur, nxt[0]
            return chain

        for k0, nbrs in adj.items():          # chains start at junctions and free ends first, then closed loops
            if len(nbrs) != 2:
                for q, _ in nbrs:
                    if (k0, key(q)) not in used:
                        chains.append(walk(pos[k0], q))
        for k0, nbrs in adj.items():
            for q, _ in nbrs:
                if (k0, key(q)) not in used:
                    chains.append(walk(pos[k0], q))

        for chain in chains:
            pts = np.array(chain, dtype=float)
            closed = key(chain[0]) == key(chain[-1])
            if len(pts) >= 6:                   # a curve? (many short pieces round one centre)
                body = pts[:-1] if closed else pts
                A = np.c_[2 * body[:, 0], 2 * body[:, 1], np.ones(len(body))]
                sol, *_ = np.linalg.lstsq(A, (body ** 2).sum(axis=1), rcond=None)
                c = sol[:2]
                r = float(np.sqrt(max(sol[2] + c @ c, 0.0)))
                res = np.abs(np.linalg.norm(body - c, axis=1) - r)
                if r > 1e-6 and float(res.max()) < max(2e-3 * r, 2e-3):
                    if closed:
                        if (round(c[0], 3), round(c[1], 3), round(r, 3)) not in {(round(e.center[0], 3), round(e.center[1], 3), round(e.radius, 3)) for e in self.entities if e.entity_type == "circle"}:
                            add(SketchCircle(self._new_entity_id("circle"), (float(c[0]), float(c[1])), r))
                    else:
                        mid = pts[len(pts) // 2]
                        add(SketchArc(self._new_entity_id("arc"), tuple(pts[0]), tuple(mid), tuple(pts[-1])))
                    continue
            # straight pieces: merge consecutive collinear segments
            run_start = pts[0]
            for i in range(1, len(pts)):
                last = i == len(pts) - 1
                if not last:
                    d1, d2 = pts[i] - pts[i - 1], pts[i + 1] - pts[i]
                    n1, n2 = np.linalg.norm(d1), np.linalg.norm(d2)
                    if n1 > 1e-12 and n2 > 1e-12 and abs(float(d1 @ d2) / (n1 * n2) - 1.0) < 1e-6:
                        continue
                a, b = tuple(run_start), tuple(pts[i])
                if (round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)) not in have and math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
                    add(SketchLine(self._new_entity_id("line"), a, b))
                run_start = pts[i]
        self.solve_profiles()
        return new

    @staticmethod
    def polygon_points(center, vertex, sides: int):
        """Corners of a regular polygon: one corner at `vertex`, the others evenly round `center`."""
        cx, cy = center
        r = math.hypot(vertex[0] - cx, vertex[1] - cy)
        a0 = math.atan2(vertex[1] - cy, vertex[0] - cx)
        return [(cx + r * math.cos(a0 + 2 * math.pi * k / sides), cy + r * math.sin(a0 + 2 * math.pi * k / sides))
                for k in range(sides)]

    def add_polygon(self, center, vertex, sides: int, is_construction: bool = False) -> list:
        """A regular polygon (triangle, hexagon ...). It is built so it stays regular when dimensioned: its
        corners lie on a construction circle around the centre (so the centre can be measured from, as with a
        circle), the sides are equal and joined end to end."""
        n = max(3, int(sides))
        pts = self.polygon_points(center, vertex, n)
        gid = self._new_group_id()
        circle = SketchCircle(self._new_entity_id("circle"), center, math.hypot(vertex[0] - center[0], vertex[1] - center[1]),
                              is_construction=True)
        circle.group = gid
        self.entities.append(circle)
        lines = []
        for i, a in enumerate(pts):
            b = pts[(i + 1) % n]
            line = SketchLine(self._new_entity_id("line"), a, b, is_construction=is_construction)
            line.group = gid
            self.entities.append(line)
            lines.append(line)
        for i, ln in enumerate(lines):
            nxt = lines[(i + 1) % n]
            self.constraints.append(SketchConstraint(self.new_constraint_id(), "COINCIDENT", [ln.entity_id, nxt.entity_id], ["p2", "p1"]))
            self.constraints.append(SketchConstraint(self.new_constraint_id(), "POINT_ON_CIRCLE", [circle.entity_id, ln.entity_id], ["p1"]))
            if i:
                self.constraints.append(SketchConstraint(self.new_constraint_id(), "EQUAL", [lines[0].entity_id, ln.entity_id]))
        side = math.hypot(lines[0].p2[0] - lines[0].p1[0], lines[0].p2[1] - lines[0].p1[1])
        self.add_dimension("LENGTH", lines[0].entity_id, side, offset_distance=12.0, name="Side")
        self.solve_profiles()
        return lines

    def _new_group_id(self) -> str:
        used = {getattr(e, "group", None) for e in self.entities}
        n = 1
        while f"poly_{n}" in used:
            n += 1
        return f"poly_{n}"

    def group_entities(self, entity) -> list:
        """The other elements built together with this one (a polygon's sides and its centre circle)."""
        g = getattr(entity, "group", None)
        return [e for e in self.entities if g and getattr(e, "group", None) == g]

    def add_loop(self, points, closed: bool = True) -> List[SketchLine]:
        """A polyline as plain lines (no dimensions or constraints); used to turn a face outline into a sketch."""
        pts = [tuple(map(float, p)) for p in points]
        out = []
        n = len(pts)
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                continue
            line = SketchLine(self._new_entity_id("line"), a, b)
            self.entities.append(line)
            out.append(line)
        self.solve_profiles()
        return out

    def _add_rect_lines(self, c0, c1, c2, c3, is_construction: bool, width: float, height: float,
                        offset: float = 10.0) -> List[SketchLine]:
        """A rectangle is four lines held by Horizontal/Vertical/Coincident constraints plus
        a width and a height dimension - exactly what Fusion 360 creates."""
        corners = [c0, c1, c2, c3]
        lines = []
        for i in range(4):
            line = SketchLine(self._new_entity_id("line"), corners[i], corners[(i + 1) % 4],
                              is_construction=is_construction)
            self.entities.append(line)
            lines.append(line)
        ids = [ln.entity_id for ln in lines]
        for i, kind in enumerate(("HORIZONTAL", "VERTICAL", "HORIZONTAL", "VERTICAL")):
            self.constraints.append(SketchConstraint(self.new_constraint_id(), kind, [ids[i]]))
        for i in range(4):  # start of the next line meets the end of this one
            self.constraints.append(SketchConstraint(
                self.new_constraint_id(), "COINCIDENT", [ids[(i + 1) % 4], ids[i]], ["p1", "p2"]))
        # a LENGTH dimension sits on the left of its line (p1 -> p2); the corners run counter-clockwise when the
        # signed area is positive, so left is inside: put the width and height outside, as Fusion does
        area = sum(corners[i][0] * corners[(i + 1) % 4][1] - corners[(i + 1) % 4][0] * corners[i][1] for i in range(4))
        outside = -abs(offset) if area > 0 else abs(offset)
        self.add_dimension("LENGTH", ids[0], width, offset_distance=outside, name="Width")
        self.add_dimension("LENGTH", ids[1], height, offset_distance=outside, name="Height")
        self.solve_profiles()
        return lines

    def add_rect(self, p1: Tuple[float, float], p2: Tuple[float, float], is_construction: bool = False) -> List[SketchLine]:
        (x1, y1), (x2, y2) = p1, p2
        return self._add_rect_lines((x1, y1), (x2, y1), (x2, y2), (x1, y2), is_construction,
                                    abs(x2 - x1), abs(y2 - y1))

    def add_rounded_rect(self, p1: Tuple[float, float], p2: Tuple[float, float], radius: float,
                         is_construction: bool = False) -> List[SketchLine]:
        """A rectangle with all four corners filleted in one step. The radius is capped just under
        half the shorter side, so the straight pieces never vanish."""
        lines = self.add_rect(p1, p2, is_construction)
        r = self.corner_radius_limit(p1, p2, radius)
        if r > 0.001:
            for pt, la, lb, _ea, _eb in self.find_corners(lines):
                arc, _msg = self.fillet_corner(la, lb, r, pt)
                if arc is not None:
                    self._corner_guides(arc)
            self._outer_size_dimensions(lines)
        return lines

    def _corner_guides(self, arc: "SketchArc") -> List[SketchLine]:
        """Construction lines that carry both sides of a rounded corner on to the sharp corner, where
        they meet: a point to snap a pivot, a dimension or a line to. The fillet owns them
        (fillet_info["guides"]) and _update_fillet_arc re-seats them with the arc."""
        guides = []
        for _ in range(2):
            guides.append(SketchLine(self._new_entity_id("line"), (0.0, 0.0), (0.0, 0.0), is_construction=True))
            self.entities.append(guides[-1])
        arc.fillet_info["guides"] = [g.entity_id for g in guides]
        self._seat_corner_guides(arc)
        self.solve_profiles()
        return guides

    def corner_guide_walls(self) -> Dict[str, str]:
        """{guide line id: the wall line it carries on}. A guide is re-seated from its wall after every solve, so
        anything measured from a guide must be measured from the wall (same line) or it does not follow."""
        walls = {}
        for arc in self.entities:
            info = getattr(arc, "fillet_info", None) or {}
            for gid, side_key in zip(info.get("guides", ()), ("line_a", "line_b")):
                if info.get(side_key):
                    walls[gid] = info[side_key]
        return walls

    def _seat_corner_guides(self, arc: "SketchArc") -> None:
        info = arc.fillet_info
        corner = (float(info["corner"][0]), float(info["corner"][1]))
        for gid, side_key, end_key in zip(info.get("guides", ()), ("line_a", "line_b"), ("end_a", "end_b")):
            guide, side = self.get_entity(gid), self.get_entity(info[side_key])
            if isinstance(guide, SketchLine) and isinstance(side, SketchLine):
                guide.p1 = tuple(getattr(side, info[end_key]))
                guide.p2 = corner

    def _outer_size_dimensions(self, lines) -> None:
        """After the corners are rounded the width/height dimensions of the straight pieces would measure the flats,
        not the part. Replace them by the overall width (left wall to right wall) and height (bottom to top wall),
        so the size can be changed with the corner radii and anything measured from the walls following along."""
        bottom, right, top, left = lines
        old = [d for d in self.dimensions if d.target_entity_id in (bottom.entity_id, right.entity_id) and d.dim_type == "LENGTH"]
        self.dimensions = [d for d in self.dimensions if not any(d is o for o in old)]
        # wall to opposite wall, square to them: right also when the rectangle is turned
        self.add_dimension("PT_LINE_DIST", right.entity_id, abs(right.p1[0] - left.p1[0]),
                           offset_distance=self._outside_offset(right.p1, left, lines), name="Width",
                           refs=[left.entity_id], pts=["p1"])
        self.add_dimension("PT_LINE_DIST", top.entity_id, abs(top.p1[1] - bottom.p1[1]),
                           offset_distance=self._outside_offset(top.p1, bottom, lines), name="Height",
                           refs=[bottom.entity_id], pts=["p1"])

    @staticmethod
    def _outside_offset(point, ref: "SketchLine", lines, gap: float = 10.0) -> float:
        """Offset for a point-to-line dimension that draws it `gap` beyond the figure: it is drawn shifted along the
        reference line from the point by pt_line_base_shift + offset - PT_LINE_DEFAULT_OFFSET."""
        from omacad.model.dim_layout import PT_LINE_DEFAULT_OFFSET, pt_line_base_shift
        d = np.subtract(ref.p2, ref.p1)
        d = d / max(float(np.linalg.norm(d)), 1e-12)
        far = max(float(np.dot(p, d)) for ln in lines for p in (ln.p1, ln.p2))
        shift = far + gap - float(np.dot(point, d))
        return shift - pt_line_base_shift(ref) + PT_LINE_DEFAULT_OFFSET

    def add_center_rect(self, center: Tuple[float, float], corner: Tuple[float, float], is_construction: bool = False) -> List[SketchLine]:
        cx, cy = center
        dx, dy = abs(corner[0] - cx), abs(corner[1] - cy)
        return self.add_rect((cx - dx, cy - dy), (cx + dx, cy + dy), is_construction)

    def add_center_rounded_rect(self, center: Tuple[float, float], corner: Tuple[float, float], radius: float,
                                is_construction: bool = False) -> List[SketchLine]:
        """A rounded rectangle drawn from its centre out to one corner."""
        cx, cy = center
        dx, dy = abs(corner[0] - cx), abs(corner[1] - cy)
        return self.add_rounded_rect((cx - dx, cy - dy), (cx + dx, cy + dy), radius, is_construction)

    def _migrate_legacy_rects(self) -> None:
        """Old files stored rectangles as one entity; turn them into lines + constraints."""
        legacy = [e for e in self.entities if isinstance(e, (SketchRect, SketchCenterRect))]
        for rect in legacy:
            if isinstance(rect, SketchRect):
                (x1, y1), (x2, y2) = rect.p1, rect.p2
                c0, c1, c2, c3 = (x1, y1), (x2, y1), (x2, y2), (x1, y2)
            else:
                c0, c1, c2, c3 = rect.get_corners()
            self.entities.remove(rect)
            self.dimensions = [d for d in self.dimensions if d.target_entity_id != rect.entity_id]
            width = math.hypot(c1[0] - c0[0], c1[1] - c0[1])
            height = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
            self._add_rect_lines(c0, c1, c2, c3, rect.is_construction, width, height)

    def add_circle(self, center: Tuple[float, float], radius: float, is_construction: bool = False) -> SketchCircle:
        ent_id = self._new_entity_id("circle")
        circle = SketchCircle(ent_id, center, radius, is_construction=is_construction)
        self.entities.append(circle)
        self.add_dimension("DIAMETER", ent_id, radius * 2.0, offset_distance=12.0, name="Diameter")
        self.solve_profiles()
        return circle

    def add_arc(self, p_start: Tuple[float, float], p_mid: Tuple[float, float], p_end: Tuple[float, float], is_construction: bool = False) -> SketchArc:
        ent_id = self._new_entity_id("arc")
        arc = SketchArc(ent_id, p_start, p_mid, p_end, is_construction=is_construction)
        self.entities.append(arc)
        params = arc.get_circle_params()
        if params:
            self.add_dimension("RADIUS", ent_id, params[1], offset_distance=12.0, name="Radius")
        self.solve_profiles()
        return arc

    def add_spline(self, points, is_construction: bool = False) -> SketchSpline:
        if len(points) < 2:
            raise ValueError("A spline needs at least two points.")
        spline = SketchSpline(self._new_entity_id("spline"), points, is_construction=is_construction)
        self.entities.append(spline)
        self.solve_profiles()
        return spline

    def _editable_spline(self, entity_id: str) -> SketchSpline:
        ent = next((e for e in self.entities if e.entity_id == entity_id), None)
        if not isinstance(ent, SketchSpline):
            raise ValueError("Not a spline.")
        if getattr(ent, "projected", False):
            raise ValueError("A projected spline cannot be edited.")
        return ent

    def move_spline_point(self, entity_id: str, index: int, pos) -> None:
        ent = self._editable_spline(entity_id)
        ent.points[index] = (float(pos[0]), float(pos[1]))
        self.solve_profiles()

    def set_spline_tangent(self, entity_id: str, index: int, vec) -> None:
        ent = self._editable_spline(entity_id)
        if not 0 <= index < len(ent.points):
            raise IndexError(index)
        ent.tangents[index] = (float(vec[0]), float(vec[1]))
        self.solve_profiles()

    def insert_spline_point(self, entity_id: str, pos) -> int:
        """Inserts a fit point at the curve sample nearest `pos`, keeping the curve unchanged. Returns its index."""
        ent = self._editable_spline(entity_id)
        n = len(ent.points)
        samples = 16
        pts = ent.get_points(samples)
        k = min(range(len(pts) - 1), key=lambda i: _seg_dist(pts[i], pts[i + 1], pos))
        span = min(k // samples, n - 2)
        a, b = pts[k], pts[k + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        f = 0.0 if L == 0 else max(0.0, min(1.0, ((pos[0]-a[0])*dx + (pos[1]-a[1])*dy) / L))
        t = (k - span * samples + f) / samples
        p1, p2 = ent.points[span], ent.points[span + 1]
        m1, m2 = ent.tangent_at(span), ent.tangent_at(span + 1)
        newp = _hermite(p1, p2, m1, m2, t)
        # tangent of the curve at the new point, taken per half span (a span is parameter length 1 -> halve it)
        h = 1e-4
        q0, q1 = _hermite(p1, p2, m1, m2, max(0.0, t - h)), _hermite(p1, p2, m1, m2, min(1.0, t + h))
        sc = 0.5 / (min(1.0, t + h) - max(0.0, t - h))
        d = ((q1[0] - q0[0]) * sc, (q1[1] - q0[1]) * sc)
        # existing explicit tangents keep their point; shift indices after the insert
        ent.tangents = {(k2 + 1 if k2 > span else k2): v for k2, v in ent.tangents.items()}
        ent.points.insert(span + 1, newp)
        ent.tangents[span + 1] = d
        self.solve_profiles()
        return span + 1

    def add_slot(self, center1: Tuple[float, float], center2: Tuple[float, float], radius: float, is_construction: bool = False) -> SketchSlot:
        ent_id = self._new_entity_id("slot")
        slot = SketchSlot(ent_id, center1, center2, radius, is_construction=is_construction)
        self.entities.append(slot)
        length = math.hypot(center2[0] - center1[0], center2[1] - center1[1])
        self.add_dimension("LENGTH", ent_id, length, offset_distance=12.0, name="Length")
        self.add_dimension("DIAMETER", ent_id, radius * 2.0, offset_distance=10.0, name="Width")
        self.solve_profiles()
        return slot

    def _update_fillet_arc(self, arc: SketchArc, new_radius: float) -> bool:
        """Parametrically updates a fillet arc and its connected lines when the fillet dimension changes."""
        info = getattr(arc, "fillet_info", None)
        if not info or new_radius <= 0.001:
            return False
        line_a = self.get_entity(info.get("line_a"))
        line_b = self.get_entity(info.get("line_b"))
        V = info.get("corner")
        end_a = info.get("end_a")
        end_b = info.get("end_b")
        if not (line_a is not None and line_b is not None and V and end_a and end_b):
            return False
        if not (isinstance(line_a, SketchLine) and isinstance(line_b, SketchLine)):
            return self._update_curve_fillet(arc, line_a, end_a, line_b, end_b, V, new_radius)

        Pa = line_a.p2 if end_a == "p1" else line_a.p1
        Pb = line_b.p2 if end_b == "p1" else line_b.p1

        va = np.array([Pa[0] - V[0], Pa[1] - V[1]], dtype=float)
        vb = np.array([Pb[0] - V[0], Pb[1] - V[1]], dtype=float)
        la, lb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if la < 1e-5 or lb < 1e-5:
            return False

        ua, ub = va / la, vb / lb
        cos_th = float(np.dot(ua, ub))
        if abs(cos_th) > 0.9999:
            return False

        half_ang = math.acos(max(-1.0, min(1.0, cos_th))) * 0.5
        tan_half = math.tan(half_ang)
        sin_half = math.sin(half_ang)

        d = new_radius / tan_half
        max_d = min(la, lb) * 0.995
        if d > max_d:
            return False

        Ta = tuple(np.array(V) + d * ua)
        Tb = tuple(np.array(V) + d * ub)

        bsum = ua + ub
        b = bsum / np.linalg.norm(bsum)
        C = np.array(V) + (new_radius / sin_half) * b
        M = tuple(C - new_radius * b)

        setattr(line_a, end_a, Ta)
        setattr(line_b, end_b, Tb)
        arc.p_start = Ta
        arc.p_mid = M
        arc.p_end = Tb
        self._seat_corner_guides(arc)

        # Update length dimensions on trimmed lines
        for line in (line_a, line_b):
            new_len = math.hypot(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1])
            for dim in self.dimensions:
                if dim.dim_type == "LENGTH" and dim.target_entity_id == line.entity_id:
                    dim.value = float(new_len)
        return True

    def _update_curve_fillet(self, arc, ent_a, end_a, ent_b, end_b, near, new_radius: float) -> bool:
        """A fillet where a line meets an arc (or two arcs) takes a new radius: rebuilt from the corner the two
        curves make when carried on, so it can grow as well as shrink."""
        V = corner_point(ent_a, end_a, ent_b, end_b, near)
        pts, _msg = fillet_points(ent_a, end_a, ent_b, end_b, V, new_radius) if V else (None, "")
        if pts is None:
            return False
        self._trim_to_fillet(ent_a, end_a, ent_b, end_b, pts)
        arc.p_start, arc.p_mid, arc.p_end = pts
        arc.fillet_info["corner"] = V
        return True

    def _trim_to_fillet(self, ent_a, end_a, ent_b, end_b, pts) -> None:
        """Trims both sides to the fillet (Ta, M, Tb) and keeps their length dimensions true."""
        trim_end(ent_a, end_a, pts[0])
        trim_end(ent_b, end_b, pts[2])
        for line in (ent_a, ent_b):
            if isinstance(line, SketchLine):
                new_len = math.hypot(line.p2[0] - line.p1[0], line.p2[1] - line.p1[1])
                for dim in self.dimensions:
                    if dim.dim_type == "LENGTH" and dim.target_entity_id == line.entity_id:
                        dim.value = float(new_len)

    def refit_fillets(self) -> None:
        """Re-seats every fillet arc after the solver moved its lines (arcs are not solver entities):
        the corner becomes the intersection of the two lines, then the arc and the line ends are
        rebuilt there with the arc's own radius."""
        for arc in self.entities:
            corner = self.sharp_corner(arc)
            params = arc.get_circle_params() if corner else None
            if not params:
                continue
            arc.fillet_info["corner"] = corner
            self._update_fillet_arc(arc, params[1])

    def sharp_corner(self, arc) -> Optional[Tuple[float, float]]:
        """The sharp corner a fillet arc rounds: where its two lines meet when carried on (None if it is no fillet)."""
        info = getattr(arc, "fillet_info", None)
        if not (isinstance(arc, SketchArc) and info):
            return None
        la, lb = self.get_entity(info.get("line_a")), self.get_entity(info.get("line_b"))
        if not (isinstance(la, SketchLine) and isinstance(lb, SketchLine)):
            return None
        da = (la.p2[0] - la.p1[0], la.p2[1] - la.p1[1])
        db = (lb.p2[0] - lb.p1[0], lb.p2[1] - lb.p1[1])
        den = da[0] * db[1] - da[1] * db[0]
        if abs(den) < 1e-9:
            return None
        t = ((lb.p1[0] - la.p1[0]) * db[1] - (lb.p1[1] - la.p1[1]) * db[0]) / den
        return (la.p1[0] + t * da[0], la.p1[1] + t * da[1])

    def find_corners(self, entities: Optional[List[SketchEntity]] = None) -> List[Tuple[Tuple[float, float], SketchEntity, SketchEntity, str, str]]:
        """Returns all corner vertices (point, ent_a, ent_b, end_a, end_b) where two lines or arcs meet at an angle
        (not tangentially)."""
        corners = []
        cands = [e for e in (entities or self.entities) if isinstance(e, (SketchLine, SketchArc)) and not e.is_construction]
        tol = 1e-3
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                la, lb = cands[i], cands[j]
                for ea, pa in fillet_ends(la):
                    for eb, pb in fillet_ends(lb):
                        if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < tol:
                            ta, tb = end_tangent(la, ea, pa), end_tangent(lb, eb, pa)
                            if ta is not None and tb is not None and abs(float(np.dot(ta, tb))) < 0.9999:
                                corners.append((pa, la, lb, ea, eb))
                            break
        return corners

    def fillet_corner(self, line_a: SketchLine, line_b: SketchLine, radius: float,
                      corner_pt: Optional[Tuple[float, float]] = None) -> Tuple[Optional[SketchArc], str]:
        """Rounds the corner where line_a and line_b (lines, or a line and an arc, or two arcs) meet with a
        circular arc of given radius."""
        if radius <= 0.001:
            return None, "The radius must be larger than 0."

        tol = 1e-3
        end_a, end_b = None, None
        V = None

        if corner_pt is not None:
            best_d = 1e9
            for ea, pa in fillet_ends(line_a):
                for eb, pb in fillet_ends(line_b):
                    d_meeting = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                    if d_meeting < tol:
                        d_c = math.hypot(pa[0] - corner_pt[0], pa[1] - corner_pt[1])
                        if d_c < best_d:
                            best_d = d_c
                            end_a, end_b = ea, eb
                            V = pa
        if end_a is None:
            for ea, pa in fillet_ends(line_a):
                for eb, pb in fillet_ends(line_b):
                    if math.hypot(pa[0] - pb[0], pa[1] - pb[1]) < tol:
                        end_a, end_b = ea, eb
                        V = pa
                        break
                if end_a:
                    break

        if end_a is None or V is None:
            return None, "The lines do not meet in a common corner."
        if not (isinstance(line_a, SketchLine) and isinstance(line_b, SketchLine)):
            pts, msg = fillet_points(line_a, end_a, line_b, end_b, V, radius)
            if pts is None:
                return None, msg
            return self._add_fillet_arc(line_a, end_a, line_b, end_b, V, pts, radius), "OK"

        Pa = line_a.p2 if end_a == "p1" else line_a.p1
        Pb = line_b.p2 if end_b == "p1" else line_b.p1

        va = np.array([Pa[0] - V[0], Pa[1] - V[1]], dtype=float)
        vb = np.array([Pb[0] - V[0], Pb[1] - V[1]], dtype=float)
        la, lb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if la < 1e-5 or lb < 1e-5:
            return None, "One of the lines is too short."

        ua, ub = va / la, vb / lb
        cos_th = float(np.dot(ua, ub))
        if abs(cos_th) > 0.9999:
            return None, "The lines are parallel or collinear."

        half_ang = math.acos(max(-1.0, min(1.0, cos_th))) * 0.5
        tan_half = math.tan(half_ang)
        sin_half = math.sin(half_ang)

        d = radius / tan_half
        max_d = min(la, lb) * 0.995
        if d > max_d:
            max_r = max_d * tan_half
            return None, f"The radius is too large for this corner (max {max_r:.1f} mm)."

        Ta = tuple(np.array(V) + d * ua)
        Tb = tuple(np.array(V) + d * ub)

        bsum = ua + ub
        b = bsum / np.linalg.norm(bsum)
        C = np.array(V) + (radius / sin_half) * b
        M = tuple(C - radius * b)
        return self._add_fillet_arc(line_a, end_a, line_b, end_b, V, (Ta, M, Tb), radius), "OK"

    def _add_fillet_arc(self, line_a, end_a, line_b, end_b, V, pts, radius: float) -> SketchArc:
        """Trims both sides to the fillet (Ta, M, Tb) and adds the arc, tied to them, with its radius dimension."""
        Ta, M, Tb = pts
        self._trim_to_fillet(line_a, end_a, line_b, end_b, pts)

        # Remove coincident constraint between line_a and line_b at this corner
        self.constraints = [
            c for c in self.constraints
            if not (c.ctype == "COINCIDENT" and set(c.refs) == {line_a.entity_id, line_b.entity_id})
        ]

        # Create fillet arc
        arc_id = self._new_entity_id("arc")
        arc = SketchArc(arc_id, Ta, M, Tb, is_construction=line_a.is_construction and line_b.is_construction)
        arc.fillet_info = {
            "line_a": line_a.entity_id,
            "line_b": line_b.entity_id,
            "corner": (float(V[0]), float(V[1])),
            "end_a": end_a,
            "end_b": end_b,
        }
        self.entities.append(arc)

        # Add coincident constraints to connect lines with arc endpoints
        self.constraints.append(SketchConstraint(self.new_constraint_id(), "COINCIDENT", [line_a.entity_id, arc.entity_id], [end_a, "p_start"]))
        self.constraints.append(SketchConstraint(self.new_constraint_id(), "COINCIDENT", [line_b.entity_id, arc.entity_id], [end_b, "p_end"]))

        # Add dimension for fillet radius
        self.add_dimension("RADIUS", arc_id, radius, offset_distance=12.0, name="Fillet")

        self.solve_profiles()
        return arc


def _seg_dist(a, b, p) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    f = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(a[0] + f * dx - p[0], a[1] + f * dy - p[1])
