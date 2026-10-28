"""
Omacad - Pattern Features (Linear, Circular, Mirror, Fill)
Copies history steps parametrically (linear, circular, mirror or fill lattice).
"""

import math

from typing import Dict, Any, List
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
import manifold3d as m3d
from omacad.model import quality
from omacad.model.kernel import CadKernel
from omacad.model.features.base import Feature

_LATTICE_CACHE: Dict[Any, Any] = {}


def _polygon_corners(foot):
    """Corner count of `foot` when it is a convex polygon of 3..8 sides, else 0."""
    try:
        hull = foot.convex_hull
        if hull.geom_type != "Polygon" or foot.area < 0.97 * hull.area:
            return 0
        bx0, by0, bx1, by1 = hull.bounds
        pts = list(hull.simplify(1e-3 * max(bx1 - bx0, by1 - by0, 1e-6)).exterior.coords)[:-1]
        return len(pts) if 3 <= len(pts) <= 8 else 0
    except Exception:
        return 0


def _tight_lattice(shape, gap, odd=False, refine=True, n_samples=720):
    """Densest lattice (v1, v2, area) of `shape` copies with `gap` mm between neighbours. Two copies are
    closer than `gap` when their offset lies inside K = (hull - hull) grown by gap; the densest lattice
    packing then puts u, v and v - u on the boundary of K, so it is searched along that boundary."""
    from shapely import affinity
    from shapely.geometry import MultiPoint
    pts = np.array(shape.convex_hull.exterior.coords)[:-1]
    diff = MultiPoint([tuple(p - q) for p in pts for q in pts]).convex_hull
    K = diff.buffer(gap * 1.0005, quad_segs=64)
    ring = K.exterior
    total = ring.length

    def at(frac):
        u = ring.interpolate(frac * total)
        u = np.array([u.x, u.y])
        cut = ring.intersection(affinity.translate(K, u[0], u[1]).exterior)
        best = None
        for q in getattr(cut, "geoms", [cut]):
            if q.geom_type != "Point":
                continue
            v = np.array([q.x, q.y])
            area = abs(u[0] * v[1] - u[1] * v[0])
            if area > 1e-9 and (best is None or area < best[2]):
                best = (u, v, area)
        return best

    best, best_f = None, 0.0
    for k in range(n_samples):
        r = at(k / n_samples)
        if r is not None and (best is None or r[2] < best[2] - 1e-9):
            best, best_f = r, k / n_samples
    if best is not None and refine:
        step = 1.0 / n_samples
        while step > 1e-7:
            for f in (best_f - step, best_f + step):
                r = at(f % 1.0)
                if r is not None and r[2] < best[2] - 1e-9:
                    best, best_f = r, f % 1.0
            step /= 2.0
    return best


def _best_pattern(foot, gap):
    """(members, v1, v2): copies per lattice cell as (turned 180 degrees?, offset) plus the lattice. Triangles,
    pentagons and heptagons also try pairs of a copy and one turned 180 degrees next to it."""
    from shapely import affinity
    key = (foot.wkb_hex, round(gap, 6))
    if key in _LATTICE_CACHE:
        return _LATTICE_CACHE[key]
    n = _polygon_corners(foot)
    res = None
    odd = n % 2 == 1
    single = _tight_lattice(foot, gap, odd)
    if single is not None:
        res = ([(False, (0.0, 0.0))], single[0], single[1])
        best_per = single[2]
        if odd:
            c = foot.centroid
            inv = affinity.rotate(foot, 180, origin=(c.x, c.y))
            pts = np.array(orient(foot.convex_hull, 1.0).exterior.coords)[:-1]   # counter-clockwise
            cands = []
            for k in range(len(pts)):
                e = pts[(k + 1) % len(pts)] - pts[k]
                ln = float(np.hypot(*e))
                if ln < 1e-9:
                    continue
                d = np.array([e[1], -e[0]]) / ln
                lo_, hi_ = 0.0, float(np.hypot(*np.ptp(pts, axis=0))) * 2 + gap
                for _ in range(40):
                    mid = (lo_ + hi_) / 2.0
                    lo_, hi_ = (lo_, mid) if foot.distance(affinity.translate(inv, d[0] * mid, d[1] * mid)) >= gap - 1e-9 else (mid, hi_)
                for shift in np.linspace(-0.5, 0.5, 11):   # slide the turned copy along the shared edge too
                    w = d * hi_ + np.array([-d[1], d[0]]) * ln * shift
                    if foot.distance(affinity.translate(inv, w[0], w[1])) < gap - 1e-6:
                        continue
                    pr = foot.union(affinity.translate(inv, w[0], w[1]))
                    lat = _tight_lattice(pr, gap, True, refine=False, n_samples=120)
                    if lat is not None:
                        cands.append((lat[2], w, pr))
            for _, w, pr in sorted(cands, key=lambda t: t[0])[:2]:
                lat = _tight_lattice(pr, gap, True)
                if lat is not None and lat[2] / 2.0 < best_per - 1e-6:
                    best_per = lat[2] / 2.0
                    res = ([(False, (0.0, 0.0)), (True, (float(w[0]), float(w[1])))], lat[0], lat[1])
    _LATTICE_CACHE[key] = res
    if len(_LATTICE_CACHE) > 64:
        _LATTICE_CACHE.pop(next(iter(_LATTICE_CACHE)))
    return res


class PatternFeature(Feature):
    """Copies what some earlier steps did to a body (a hole and its chamfers, a boss ...) to other places:
    evenly spaced (linear), mirrored around the body (e.g. one corner hole -> all four corners) or around
    an axis (circular). The copies are the difference between the body before and after those steps, so
    anything they changed is copied, chamfers and fillets included."""

    AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}

    def __init__(self, feature_id: str, name: str, source_ids, kind: str = "linear", **params):
        super().__init__(feature_id, "pattern", name)
        self.source_ids = list(source_ids)
        self.kind = kind                    # "linear", "mirror", "circular", "fill" (gap = spacing1, margin = spacing2, layout in mirror_mode)
        self.axis1, self.count1, self.spacing1 = params.get("axis1", "x"), float(params.get("count1", 2)), float(params.get("spacing1", 20.0))
        self.axis2, self.count2, self.spacing2 = params.get("axis2", "y"), float(params.get("count2", 1)), float(params.get("spacing2", 20.0))
        self.mirror_mode = params.get("mirror_mode", "auto")   # auto, x, y, xy
        self.about = params.get("about", "body")                # body (its centre) or origin
        self.angle = float(params.get("angle", 360.0))
        self.rotation_axis = params.get("rotation_axis", "z")
        self.axis_origin = list(map(float, params["axis_origin"])) if params.get("axis_origin") is not None else None
        self.axis_direction = list(map(float, params["axis_direction"])) if params.get("axis_direction") is not None else None
        self.copies = 0
        self._keep = None   # circular pattern on a round body: the intersection the body is cut down to

    def _transforms(self, centre, feature_centre, size):
        """Functions turning the changed region into each copy."""
        c = np.array(centre, dtype=float)
        out = []

        def mirror(vec):
            return lambda m: m.translate(tuple(-c)).mirror(vec).translate(tuple(c))

        if self.kind == "linear":
            d1, d2 = self.AXES.get(self.axis1, self.AXES["x"]), self.AXES.get(self.axis2, self.AXES["y"])
            for i in range(max(1, int(round(self.count1)))):
                for j in range(max(1, int(round(self.count2)))):
                    if i == 0 and j == 0:
                        continue
                    off = tuple(i * self.spacing1 * np.array(d1) + j * self.spacing2 * np.array(d2))
                    out.append(lambda m, off=off: m.translate(off))
        elif self.kind == "mirror" and self.mirror_mode.startswith("plane:"):
            pl = getattr(self, "_mirror_plane", None)   # (point, unit normal), resolved in compute()
            if pl is not None:
                p0, nrm = np.array(pl[0], dtype=float), tuple(pl[1])
                out.append(lambda m: m.translate(tuple(-p0)).mirror(nrm).translate(tuple(p0)))
        elif self.kind == "mirror":
            mode = self.mirror_mode
            if mode == "auto" and getattr(self, "_round_body", False):
                mode = "diameter"   # a round body has no corners: the copy goes to the other end of the diameter
            if mode == "diameter":   # evenly spaced around the round body; 2 = the other end of the diameter
                n = max(2, int(round(self.count1)))
                for k in range(1, n):
                    deg = 360.0 * k / n
                    out.append(lambda m, deg=deg: m.translate(tuple(-c)).rotate((0.0, 0.0, deg)).translate(tuple(c)))
            elif mode == "auto":  # mirror across each mid-plane the feature is off-centre in
                ax = abs(feature_centre[0] - c[0]) > 0.02 * size[0] + 1e-6
                ay = abs(feature_centre[1] - c[1]) > 0.02 * size[1] + 1e-6
                mode = "xy" if ax and ay else "x" if ax else "y" if ay else ""
            mx, my = mirror((1.0, 0.0, 0.0)), mirror((0.0, 1.0, 0.0))
            if "x" in mode:
                out.append(mx)
            if "y" in mode:
                out.append(my)
            if mode == "xy":
                out.append(lambda m: my(mx(m)))
        elif self.kind == "circular":
            n = max(2, int(round(self.count1)))
            step = self.angle / n if abs(abs(self.angle) - 360.0) < 1e-6 else self.angle / (n - 1)
            c, axis = self._circular_axis(c)
            x, y, z = axis
            skew = np.array([[0., -z, y], [z, 0., -x], [-y, x, 0.]])
            for k in range(1, n):
                angle = math.radians(k*step)
                rotation = np.eye(3)*math.cos(angle) + (1-math.cos(angle))*np.outer(axis, axis) + math.sin(angle)*skew
                matrix = np.column_stack((rotation, np.zeros(3)))
                out.append(lambda m, matrix=matrix, c=c.copy(): m.translate(tuple(-c)).transform(matrix).translate(tuple(c)))
        return out

    def _circular_axis(self, centre):
        """(point, unit direction) of the circular pattern's rotation axis."""
        c = np.asarray(centre, dtype=float)
        if self.rotation_axis == "picked":
            if self.axis_origin is None or self.axis_direction is None:
                raise ValueError("Choose a circular edge or cylindrical face for the pattern axis.")
            c = np.asarray(self.axis_origin, dtype=float)
            axis = np.asarray(self.axis_direction, dtype=float)
        else:
            axis = np.asarray(self.AXES.get(self.rotation_axis, self.AXES["z"]), dtype=float)
        length = np.linalg.norm(axis)
        if not np.isfinite(length) or length < 1e-9:
            raise ValueError("The pattern axis must have a nonzero direction.")
        return c, axis/length

    @staticmethod
    def _radial_scale(m, c, axis, factor):
        """`m` scaled by `factor` away from the axis (lengths along the axis unchanged)."""
        proj = np.outer(axis, axis)
        mat = proj + factor * (np.eye(3) - proj)
        return m.translate(tuple(-c)).transform(np.column_stack((mat, np.zeros(3)))).translate(tuple(c))

    @staticmethod
    def _round_about(body, funcs, c, axis):
        """True when every rotation maps the body onto itself up to tessellation: what one rotation leaves
        uncovered is then only a skin thinner than 1 % of the radius (a chord's sag), never a corner."""
        r = np.linalg.norm((body.to_mesh().vert_properties[:, :3] - c) @ (np.eye(3) - np.outer(axis, axis)), axis=1)
        limit = 0.01 * float(r.max())
        for f in funcs:
            gap = body - f(body)
            if not gap.is_empty() and 2.0 * gap.volume() / max(gap.surface_area(), 1e-12) > limit:
                return False
        return True

    @staticmethod
    def _outside_band(body, regions, c, axis, margin=0.05):
        """Everything around `body` except the ring the copies sweep: the slab across the axis that `regions` span
        (plus `margin`), from just inside their nearest point to the axis outwards. A thread or bore further in is
        not round about the axis, so it must stay out of the round test and the intersection."""
        def along(m):
            return (m.to_mesh().vert_properties[:, :3] - c) @ axis
        t = np.concatenate([along(r) for r in regions])
        tb = along(body)
        size = float(np.ptp(body.to_mesh().vert_properties[:, :3], axis=0).max()) + float(np.abs(tb).max()) + 1.0
        lo, hi = float(t.min()) - margin, float(t.max()) + margin
        u = np.cross(axis, [1.0, 0.0, 0.0] if abs(axis[0]) < 0.9 else [0.0, 1.0, 0.0])
        u /= np.linalg.norm(u)
        frame = np.column_stack((u, np.cross(axis, u), axis, c))   # local z = the axis, origin = c
        def slab(a, b):
            return m3d.Manifold.cube((2*size, 2*size, b - a)).translate((-size, -size, a)).transform(frame)
        out = slab(-2*size, lo) + slab(hi, 2*size)
        radial = np.eye(3) - np.outer(axis, axis)
        r_in = min(float(np.linalg.norm((r.to_mesh().vert_properties[:, :3] - c) @ radial, axis=1).min())
                   for r in regions) - 4 * margin
        if r_in > 4 * margin:
            core = m3d.Manifold.cylinder(hi - lo, r_in, r_in, quality.circle_segments()).translate((0.0, 0.0, lo))
            out = out + core.transform(frame)
        return out

    def _source_plane(self, doc, before=None, removed=None, added=None):
        for f in doc.timeline.features:
            if f.feature_id in self.source_ids:
                sk = getattr(f, "sketch", None) or doc.sketches.get(getattr(f, "sketch_id", None))
                if sk is not None:
                    return sk.plane
                edges = getattr(f, "edges", None)
                if edges and before is not None:
                    from omacad.model.faces import compute_planar_faces
                    from omacad.model.sketch import SketchPlane
                    pts = []
                    for e in edges:
                        if e and isinstance(e, (list, tuple)) and len(e) == 2 and isinstance(e[0], (list, tuple)) and isinstance(e[1], (list, tuple)):
                            pts.extend([e[0], e[1]])
                    if len(pts) >= 3:
                        for face in compute_planar_faces(before):
                            dists = [abs(float((np.array(p) - face.origin) @ face.normal)) for p in pts]
                            if max(dists) < 1e-3:
                                return SketchPlane.from_face(face.normal, face.origin).centered_on(face.tris)
        if before is not None and (removed is not None or added is not None):
            from omacad.model.faces import compute_planar_faces
            from omacad.model.sketch import SketchPlane
            bf_faces = compute_planar_faces(before)
            best_face = None
            best_area = -1.0
            for m in (removed, added):
                if m is None or m.is_empty():
                    continue
                for rf in compute_planar_faces(m):
                    for bf in bf_faces:
                        if abs(abs(float(rf.normal @ bf.normal)) - 1.0) < 1e-3 and abs(float((rf.origin - bf.origin) @ bf.normal)) < 1e-3:
                            if rf.area > best_area:
                                best_area = rf.area
                                best_face = bf
            if best_face is not None:
                return SketchPlane.from_face(best_face.normal, best_face.origin).centered_on(best_face.tris)
        return None

    @staticmethod
    def _room_prism(clip, before):
        """The allowed region of the face as a tall prism (through the whole body) in world space."""
        room, o, ua, va, n = clip
        bb = before.bounding_box()
        h = 2.0 * float(np.max(np.array(bb[3:]) - np.array(bb[:3]))) + 10.0
        cs = None
        for poly in (room.geoms if hasattr(room, "geoms") else [room]):
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            poly = orient(poly, sign=1.0)
            part = m3d.CrossSection([list(poly.exterior.coords)[:-1]])
            for hole in poly.interiors:
                ring = list(hole.coords)[:-1]
                if Polygon(ring).exterior.is_ccw is False:
                    ring.reverse()
                part = part - m3d.CrossSection([ring])
            cs = part if cs is None else cs + part
        if cs is None:
            return None
        mat = np.column_stack([ua, va, n, o]).astype(float)
        return m3d.Manifold.extrude(cs, height=h).translate((0, 0, -h / 2.0)).transform(mat)

    def _fill_funcs(self, doc, before, removed, added, now=None, other_bodies=None):
        """Fill the flat face the source sketch is on."""
        from shapely.ops import unary_union
        from shapely import affinity
        from omacad.model.faces import compute_planar_faces
        plane = self._source_plane(doc, before=before, removed=removed, added=added)
        if plane is None:
            return []
        gap, margin = max(self.spacing1, 0.0), max(self.spacing2, 0.0)
        o = np.asarray(plane.origin, dtype=float)
        n = np.asarray(plane.normal, dtype=float)
        ua, va = np.asarray(plane.u_axis, dtype=float), np.asarray(plane.v_axis, dtype=float)
        inv = np.linalg.inv(np.vstack([plane.get_transform_matrix_3x4(), [0, 0, 0, 1]]))[:3]
        shapes = []
        for m in (removed, added):
            if not m.is_empty():
                for ring in m.transform(inv).project().to_polygons():
                    if len(ring) >= 3:
                        shapes.append(Polygon(ring).buffer(0))
        shapes = [sh for sh in shapes if not sh.is_empty]
        if not shapes:
            return []
        foot = unary_union(shapes)
        c0 = foot.representative_point()

        now_bodies = ([now] if now is not None and not now.is_empty() else []) + [b for b in (other_bodies or []) if not b.is_empty()]
        # Only material standing on the face is in the way: a band just above it, as high as the copies reach.
        # A body further up (a lid parked above a box) cast its whole outline onto the floor and left no room (#59).
        reach_up = 1.0
        if not added.is_empty():
            reach_up = max(reach_up, float(added.transform(inv).bounding_box()[5]))
        obs_polys = []
        for b in now_bodies:
            m_plane = b.transform(inv)
            above = m_plane.trim_by_plane([0.0, 0.0, 1.0], 0.05).trim_by_plane([0.0, 0.0, -1.0], -(reach_up + 0.05))
            if not above.is_empty():
                # even-odd over the outline's rings: the walls of a box are a ring with a hole, not a filled block
                shadow = Polygon()
                for ring in above.project().to_polygons():
                    if len(ring) >= 3:
                        shadow = shadow.symmetric_difference(Polygon(ring).buffer(0))
                if shadow.is_valid and shadow.area > 1e-6:
                    obs_polys.append(shadow)
        all_obs = unary_union(obs_polys).difference(foot.buffer(0.02)) if obs_polys else Polygon()

        regions = []
        for face in compute_planar_faces(now if now is not None else before):
            if abs(abs(float(face.normal @ n)) - 1.0) > 1e-3 or abs(float((face.origin - o) @ n)) > 1e-3:
                continue
            for tri in face.tris:
                pg = Polygon([(float((v - o) @ ua), float((v - o) @ va)) for v in tri])
                if pg.is_valid and pg.area > 1e-9:
                    regions.append(pg)
        if not regions:
            return []
        raw_face = unary_union(regions + [foot.buffer(1e-4)])
        raw_face = raw_face.buffer(0.02, join_style=2).buffer(-0.02, join_style=2)
        parts = [p for p in (raw_face.geoms if hasattr(raw_face, "geoms") else [raw_face]) if p.area > 1e-6]
        if not parts:
            return []
        outline = unary_union([Polygon(p.exterior) for p in parts])
        inner = unary_union([Polygon(i) for p in parts for i in p.interiors] + ([all_obs] if all_obs and not all_obs.is_empty else []))
        # The original sets the precedent: a margin wider than its own distance to the edge would
        # leave no room for its row (a 10 mm margin on a 22 mm wall gave two clipped slivers).
        margin = min(margin, max(float(outline.boundary.distance(foot)) - 1e-3, 0.0))
        self.margin_used = margin
        room = outline.buffer(-margin) if margin > 0 else outline
        if not inner.is_empty:
            room = room.difference(inner.buffer(gap) if gap > 0 else inner)
        room = unary_union([p for p in (room.geoms if hasattr(room, "geoms") else [room]) if p.area > 1e-6])
        if room.is_empty:
            return []
        minx, miny, maxx, maxy = foot.bounds
        bw, bh = maxx - minx, maxy - miny

        tri_info = None
        if self.mirror_mode in ("stagger", "triangular"):
            coords = list(foot.exterior.coords)[:-1] if hasattr(foot, "exterior") else []
            if len(coords) == 3:
                p0, p1, p2 = np.array(coords[0]), np.array(coords[1]), np.array(coords[2])
                d01, d12, d20 = np.linalg.norm(p1 - p0), np.linalg.norm(p2 - p1), np.linalg.norm(p0 - p2)
                s_tri = float((d01 + d12 + d20) / 3.0)
                if s_tri > 1e-4 and max(abs(d01 - s_tri), abs(d12 - s_tri), abs(d20 - s_tri)) < 0.08 * s_tri:
                    c_tri = (p0 + p1 + p2) / 3.0
                    v0 = p0 - c_tri
                    if np.linalg.norm(v0) > 1e-5:
                        a0 = float(np.arctan2(v0[1], v0[0]))
                        tri_info = (s_tri, c_tri, a0)

        funcs = []
        min_frac = max(0.0, min(100.0, float(self.count1))) / 100.0
        self._fill_clip = (room, o, ua, va, n) if min_frac > 0 else None
        foot_area = max(foot.area, 1e-9)
        from shapely.prepared import prep
        prepared = prep(room)
        room_parts = list(room.geoms) if hasattr(room, "geoms") else [room]
        holes = unary_union([Polygon(g.exterior) for g in room_parts]).difference(room)
        prepared_holes = prep(holes) if not holes.is_empty else None

        def clear_of_holes(m):
            return prepared_holes is None or not prepared_holes.intersects(m) or m.intersection(holes).area < 1e-6

        if tri_info is not None:
            s_tri, c_tri, a0 = tri_info
            u_edge = np.array([-np.sin(a0), np.cos(a0)])
            v_edge = np.array([np.cos(a0), np.sin(a0)])
            dx = s_tri + np.sqrt(3) * gap
            dy = dx * np.sqrt(3) / 2.0
            v1 = dx * u_edge
            v2 = (dx / 2.0) * u_edge + dy * v_edge
            v_inv = (dx / 2.0) * u_edge + (dx / (2.0 * np.sqrt(3))) * v_edge

            M = np.eye(4)
            M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = ua, va, n, o
            M_inv = np.linalg.inv(M)

            foot_inv = affinity.rotate(foot, 180, origin=tuple(c_tri))
            rx0, ry0, rx1, ry1 = room.bounds
            reach_x = max(abs(rx1 - c0.x), abs(rx0 - c0.x)) + bw
            reach_y = max(abs(ry1 - c0.y), abs(ry0 - c0.y)) + bh
            step_sz = max(min(dx, dy), 1e-3)
            imax = int(reach_x / step_sz) + 2
            jmax = int(reach_y / step_sz) + 2

            for j in range(-jmax, jmax + 1):
                for i in range(-imax, imax + 1):
                    p_up = i * v1 + j * v2
                    if not (i == 0 and j == 0):
                        m_up = affinity.translate(foot, *p_up)
                        if min_frac > 0:
                            if prepared.intersects(m_up) and clear_of_holes(m_up) and m_up.intersection(room).area >= min_frac * foot_area:
                                vec = tuple(ua * p_up[0] + va * p_up[1])
                                funcs.append(lambda m, vec=vec: m.translate(vec))
                        elif prepared.contains(m_up):
                            vec = tuple(ua * p_up[0] + va * p_up[1])
                            funcs.append(lambda m, vec=vec: m.translate(vec))

                    p_inv = i * v1 + j * v2 + v_inv
                    m_inv = affinity.translate(foot_inv, *p_inv)
                    if min_frac > 0:
                        if prepared.intersects(m_inv) and clear_of_holes(m_inv) and m_inv.intersection(room).area >= min_frac * foot_area:
                            T_plane = np.eye(4)
                            T_plane[0, 0] = -1.0; T_plane[1, 1] = -1.0
                            T_plane[0, 3] = 2.0 * c_tri[0] + p_inv[0]
                            T_plane[1, 3] = 2.0 * c_tri[1] + p_inv[1]
                            T_world = (M @ T_plane @ M_inv)[:3]
                            funcs.append(lambda m, mat=T_world: m.transform(mat))
                    elif prepared.contains(m_inv):
                        T_plane = np.eye(4)
                        T_plane[0, 0] = -1.0; T_plane[1, 1] = -1.0
                        T_plane[0, 3] = 2.0 * c_tri[0] + p_inv[0]
                        T_plane[1, 3] = 2.0 * c_tri[1] + p_inv[1]
                        T_world = (M @ T_plane @ M_inv)[:3]
                        funcs.append(lambda m, mat=T_world: m.transform(mat))

                    if len(funcs) >= 1500:
                        return funcs
            return funcs

        if self.mirror_mode in ("stagger", "triangular") and _polygon_corners(foot):
            pat = _best_pattern(foot, gap)
            if pat is not None:
                members, v1, v2 = pat
                cc = foot.centroid
                M = np.eye(4)
                M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = ua, va, n, o
                M_inv = np.linalg.inv(M)
                foot_inv = affinity.rotate(foot, 180, origin=(cc.x, cc.y))
                rx0, ry0, rx1, ry1 = room.bounds
                reach = max(abs(rx1 - c0.x), abs(rx0 - c0.x), abs(ry1 - c0.y), abs(ry0 - c0.y)) + bw + bh
                step_sz = max(min(float(np.hypot(*v1)), float(np.hypot(*v2))) * abs(v1[0] * v2[1] - v1[1] * v2[0]) / max(float(np.hypot(*v1)) * float(np.hypot(*v2)), 1e-9), 1e-3)
                imax = int(reach / step_sz) + 2
                for j in range(-imax, imax + 1):
                    for i in range(-imax, imax + 1):
                        for mi, (inverted, off) in enumerate(members):
                            if i == 0 and j == 0 and mi == 0:
                                continue
                            px, py = i * v1[0] + j * v2[0] + off[0], i * v1[1] + j * v2[1] + off[1]
                            moved = affinity.translate(foot_inv if inverted else foot, px, py)
                            if min_frac > 0:
                                if not (prepared.intersects(moved) and clear_of_holes(moved) and moved.intersection(room).area >= min_frac * foot_area):
                                    continue
                            elif not prepared.contains(moved):
                                continue
                            if inverted:
                                T = np.eye(4)
                                T[0, 0] = -1.0; T[1, 1] = -1.0
                                T[0, 3] = 2.0 * cc.x + px
                                T[1, 3] = 2.0 * cc.y + py
                                mat = (M @ T @ M_inv)[:3]
                                funcs.append(lambda m, mat=mat: m.transform(mat))
                            else:
                                vec = tuple(ua * px + va * py)
                                funcs.append(lambda m, vec=vec: m.translate(vec))
                            if len(funcs) >= 1500:
                                return funcs
                return funcs

        def clear_dx(ax, ay, hi):
            lo_, hi_ = 0.0, hi
            for _ in range(40):
                mid = (lo_ + hi_) / 2.0
                if foot.distance(affinity.translate(foot, ax * mid, ay * mid)) >= gap - 1e-9:
                    hi_ = mid
                else:
                    lo_ = mid
            return hi_

        stagger = self.mirror_mode in ("stagger", "triangular")
        dx = clear_dx(1.0, 0.0, bw + gap + 1e-6)
        dy_grid = clear_dx(0.0, 1.0, bh + gap + 1e-6)
        if stagger:
            sx = dx / 2.0
            lo_, hi_ = 0.0, bh + gap + 1e-6
            for _ in range(40):
                mid = (lo_ + hi_) / 2.0
                if foot.distance(affinity.translate(foot, sx, mid)) >= gap - 1e-9:
                    hi_ = mid
                else:
                    lo_ = mid
            dy = max(hi_, dy_grid / 2.0)
        else:
            sx, dy = 0.0, dy_grid
        if dx < 1e-6 or dy < 1e-6:
            return []
        rx0, ry0, rx1, ry1 = room.bounds
        reach_x = max(abs(rx1 - c0.x), abs(rx0 - c0.x)) + bw
        reach_y = max(abs(ry1 - c0.y), abs(ry0 - c0.y)) + bh
        imax, jmax = int(reach_x / dx) + 2, int(reach_y / dy) + 2
        for j in range(-jmax, jmax + 1):
            off = sx if (j % 2) else 0.0
            for i in range(-imax, imax + 1):
                a, b = i * dx + off, j * dy
                if i == 0 and j == 0:
                    continue
                moved = affinity.translate(foot, a, b)
                if min_frac > 0:
                    if not prepared.intersects(moved) or not clear_of_holes(moved) or moved.intersection(room).area < min_frac * foot_area:
                        continue
                elif not prepared.contains(moved):
                    continue
                vec = tuple(ua * a + va * b)
                funcs.append(lambda m, vec=vec: m.translate(vec))
                if len(funcs) >= 1500:
                    return funcs
        return funcs

    @staticmethod
    def _is_round(body) -> bool:
        """True when the body's outline (seen from above) is a circle."""
        try:
            bb = body.bounding_box()
            z = (bb[2] + bb[5]) / 2.0
            polys = body.slice(z).to_polygons()
            if not polys:
                return False
            pts = max(polys, key=len)
            c = (np.array(bb[:2]) + np.array(bb[3:5])) / 2.0
            r = np.linalg.norm(pts - c, axis=1)
            return len(pts) >= 16 and float(r.std()) < 0.01 * float(r.mean()) and abs((bb[3] - bb[0]) - (bb[4] - bb[1])) < 0.02 * (bb[3] - bb[0])
        except Exception:
            return False

    @staticmethod
    def _reach_out(removed, before):
        """Where a cut leaves the body, reach a hair further out."""
        if removed.is_empty():
            return removed
        bb = removed.bounding_box()
        ext = np.array(bb[3:]) - np.array(bb[:3])
        axis = int(np.argmax(ext))
        eps = 0.03
        out = removed
        for sgn in (1.0, -1.0):
            d = [0.0, 0.0, 0.0]
            d[axis] = sgn * eps
            shifted = removed.translate(tuple(d))
            piece = shifted - removed
            if piece.is_empty():
                continue
            if (piece - before).volume() > 0.25 * piece.volume():
                out = PatternFeature._extend_end(out, axis, sgn, eps)
        return out

    @staticmethod
    def _extend_end(solid, axis, sgn, eps):
        """Pushes the vertices of the end face on one side out by eps. Unlike a union with a shifted copy this
        leaves no coplanar walls to cross, which used to leave zero-thickness fins in hole walls."""
        bb = solid.bounding_box()
        edge = bb[3 + axis] if sgn > 0 else bb[axis]

        def push(v):
            v = np.array(v, dtype=float)
            if abs(v[axis] - edge) < 1e-6:
                v[axis] += sgn * eps
            return v
        return solid.warp(push)

    def _resolve_plane(self, doc):
        """(point, unit normal) of the plane named in mirror_mode 'plane:<id>'."""
        pid = self.mirror_mode.split(":", 1)[1]
        if pid in doc.construction_planes:
            c = doc.construction_planes[pid]
            o, n = c["origin"], c["normal"]
        elif pid in doc.origin_planes:
            o, n = doc.origin_planes[pid].origin, doc.origin_planes[pid].normal
        else:
            return None
        n = np.asarray(n, dtype=float)
        ln = float(np.linalg.norm(n))
        return (np.asarray(o, dtype=float), n / ln) if ln > 1e-9 else None

    @staticmethod
    def _enclosed_voids(body):
        """What is missing from the body's bounding box and does not reach its sides."""
        lo, hi = np.array(body.bounding_box()[:3]), np.array(body.bounding_box()[3:])
        voids = m3d.Manifold.cube(tuple(hi - lo)).translate(tuple(lo)) - body
        keep = []
        for part in voids.decompose():
            b = part.bounding_box()
            if (b[0] > lo[0] + 1e-6 and b[1] > lo[1] + 1e-6 and b[3] < hi[0] - 1e-6 and b[4] < hi[1] - 1e-6):
                keep.append(part)
        return m3d.Manifold.batch_boolean(keep, m3d.OpType.Add) if keep else m3d.Manifold()

    def _selected_changes(self, doc, positions, body_id):
        """Compose only selected deltas: a fillet trims its rib instead of copying an unfilleted rib too."""
        removed, added = m3d.Manifold(), m3d.Manifold()
        empty = m3d.Manifold()
        for index in positions:
            before = doc.step_states.get(index, {}).get(body_id, empty)
            after = doc.step_states.get(index+1, {}).get(body_id, empty)
            cut, join = CadKernel.clean_difference(before, after), CadKernel.clean_difference(after, before)
            removed, added = ((removed-join)+(cut-added),
                              (added-cut)+(join-removed))
        return removed, added

    def compute(self, doc, body_id: str):
        """(removed copies, added copies) for one body, or None if there is nothing to copy."""
        idx = doc.timeline.features.index(self) if self in doc.timeline.features else doc.timeline.marker_index
        pos = [i for i, f in enumerate(doc.timeline.features) if f.feature_id in self.source_ids and i < idx]
        if not pos:
            return None
        before = doc.step_states.get(min(pos), {}).get(body_id)
        after = doc.step_states.get(max(pos) + 1, {}).get(body_id)
        if after is None:
            return None
        whole_body = False
        if self.kind == "linear" and (before is None or before.is_empty()):
            # Selecting the body-creating step copies the solid, including its holes.
            removed, added = m3d.Manifold(), after
            before = after
            whole_body = True
        elif self.kind == "circular":
            removed, added = self._selected_changes(doc, pos, body_id)
            whole_body = before is None or before.is_empty()
            if whole_body:
                before = after
        elif before is None or before.is_empty():
            voids = self._enclosed_voids(after)
            if not voids.is_empty():
                removed, added = voids, m3d.Manifold()
                before = after + removed
            else:
                removed, added = m3d.Manifold(), after
                before = after
                whole_body = True
        else:
            removed, added = CadKernel.clean_difference(before, after), CadKernel.clean_difference(after, before)
        removed, added = CadKernel.drop_slivers(removed), CadKernel.drop_slivers(added)
        removed = self._reach_out(removed, before)
        regions = [m for m in (removed, added) if not m.is_empty()]
        if not regions:
            return None
        lo = np.min([np.array(r.bounding_box()[:3]) for r in regions], axis=0)
        hi = np.max([np.array(r.bounding_box()[3:]) for r in regions], axis=0)
        bb = before.bounding_box()
        bmin, bmax = np.array(bb[:3]), np.array(bb[3:])
        centre = (bmin + bmax) / 2.0 if (self.about == "body" and not whole_body) else np.zeros(3)
        self._round_body = self._is_round(before) and not whole_body
        self._mirror_plane = self._resolve_plane(doc) if self.mirror_mode.startswith("plane:") else None
        if self.kind == "fill":
            step_bodies = doc.step_states.get(idx, {})
            now = step_bodies.get(body_id, before)
            other_bodies = [m for bid, m in step_bodies.items() if bid != body_id and not m.is_empty()]
            funcs = self._fill_funcs(doc, before, removed, added, now, other_bodies=other_bodies)
        else:
            funcs = self._transforms(centre, (lo + hi) / 2.0, bmax - bmin)
        if not funcs:
            self.copies = 0
            return None
        self._keep = None
        if self.kind == "circular" and not whole_body and pos == list(range(min(pos), idx)):
            c, axis = self._circular_axis(centre)
            outside = self._outside_band(before, regions, c, axis)
            if self._round_about(before - outside, funcs, c, axis):
                # Rotated cuts never land exactly on the round body's facets and leave paper-thin skin strips.
                # On a round body the result is instead what every rotated copy keeps; bosses sink a hair into it.
                kept = before ^ after
                self._keep = m3d.Manifold.batch_boolean([kept] + [f(kept) for f in funcs], m3d.OpType.Intersect)
                if not added.is_empty():
                    r = np.linalg.norm((added.to_mesh().vert_properties[:, :3] - c) @ (np.eye(3) - np.outer(axis, axis)), axis=1)
                    added = added + (self._radial_scale(added, c, axis, 1.0 - 0.03 / max(float(r.max()), 1e-6)) ^ before)
                    self._keep = self._keep + added   # the original boss stays
                # Only the height the copies occupy is trimmed: a thread or flat elsewhere is not round
                # about the axis and the intersection would erase it.
                self._keep = self._keep + outside
        rem = add = None
        if not removed.is_empty():
            parts = [f(removed) for f in funcs]
            rem = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if len(parts) > 1 else parts[0]
        if not added.is_empty():
            parts = [f(added) for f in funcs]
            add = m3d.Manifold.batch_boolean(parts, m3d.OpType.Add) if len(parts) > 1 else parts[0]
        clip = getattr(self, "_fill_clip", None) if self.kind == "fill" else None
        if clip is not None:
            prism = self._room_prism(clip, before)
            if prism is not None:
                rem = (rem ^ prism) if rem is not None else None
                add = (add ^ prism) if add is not None else None
        self.copies = len(funcs)
        return rem, add

    def execute(self, doc: Any) -> None:
        self.copies = 0
        for bid, body in list(doc.bodies.items()):
            res = self.compute(doc, bid)
            if res is None:
                continue
            rem, add = res
            result = body.manifold
            if self._keep is not None:
                result = result ^ self._keep
            elif rem is not None:
                result = result - rem
            if add is not None:
                result = result + add
            if not result.is_empty():
                body.manifold = CadKernel.drop_slivers(result)
                body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name,
            "suppressed": self.suppressed, "source_ids": list(self.source_ids), "kind": self.kind,
            "axis1": self.axis1, "count1": self.count1, "spacing1": self.spacing1,
            "axis2": self.axis2, "count2": self.count2, "spacing2": self.spacing2,
            "mirror_mode": self.mirror_mode, "about": self.about, "angle": self.angle,
            "rotation_axis": self.rotation_axis, "axis_origin": self.axis_origin,
            "axis_direction": self.axis_direction,
        }
