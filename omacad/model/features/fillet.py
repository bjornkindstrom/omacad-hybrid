"""
Omacad - Fillet and Chamfer Features
Rounds (fillet) or bevels (chamfer) straight and circular edges on solid bodies.
"""

from typing import Dict, Any, List
import math
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.faces import edge_from_ref, fuzzy_edge_from_ref, compute_planar_edges
from omacad.model.faces_edges import loop_contains
from omacad.model.features.base import Feature, feature_bodies


class FilletFeature(Feature):
    """Rounds (fillet) or bevels (chamfer) straight edges. Works on outside and inside corners.

    Edges are remembered by their end points and found again on rebuild, so the step survives
    changes elsewhere as long as the edge is still there."""

    CHAMFER_TYPES = ("equal", "two", "angle")    # Fusion: Equal distance, Two distances, Distance and angle

    def __init__(self, feature_id: str, name: str, edges, size: float, kind: str = "fillet",
                 chamfer_type: str = "equal", size2: float = 0.0, angle: float = 45.0, flip: bool = False):
        super().__init__(feature_id, "fillet", name)
        # each entry: ((x,y,z),(x,y,z)) for a straight edge, or ("circle", centre, axis, radius)
        self.edges = [self._norm_ref(e) for e in edges]
        self.size = float(size)
        self.kind = kind  # "fillet" or "chamfer"
        self.chamfer_type = chamfer_type if chamfer_type in self.CHAMFER_TYPES else "equal"
        self.size2 = float(size2)     # "two": distance on the second face
        self.angle = float(angle)     # "angle": degrees between the first face and the bevel
        self.flip = bool(flip)        # swap which face gets the first distance
        self.skipped = 0  # edges that could not be found/applied in the last rebuild

    def second_distance(self) -> float:
        """The chamfer's distance on the second face (= size for an equal chamfer or a fillet)."""
        if self.kind != "chamfer" or self.chamfer_type == "equal":
            return abs(self.size)
        if self.chamfer_type == "two":
            return abs(self.size2) if self.size2 > 1e-9 else abs(self.size)
        return abs(self.size) * math.tan(math.radians(min(max(self.angle, 1.0), 89.0)))

    def tool_sizes(self, edge, size: float):
        """(distance along the tool's face 1, distance along face 2) for `edge`, `size` being the (possibly clearance
        limited) first distance. The first distance lies on the flat face of a circle or outline, and for a straight
        edge on the face that is most horizontal (top/bottom), so a mix of edges bevels the same way; Flip swaps."""
        second = self.second_distance() * size / max(abs(self.size), 1e-12)
        if abs(second - size) < 1e-9:
            return size, None
        first_is_face1 = True
        if getattr(edge, "kind", "") == "line":
            z1, z2 = abs(float(edge.n1[2])), abs(float(edge.n2[2]))
            if abs(z1 - z2) < 1e-6:
                z1, z2 = abs(float(edge.n1[0])), abs(float(edge.n2[0]))
            first_is_face1 = z1 >= z2 - 1e-9
        if self.flip:
            first_is_face1 = not first_is_face1
        return (size, second) if first_is_face1 else (second, size)

    def _limited_sizes(self, body, edge, size: float):
        """tool_sizes after the clearance limit, judged on the larger of the two distances."""
        big = max(size, self.second_distance() * size / max(abs(self.size), 1e-12))
        scale = self._safe_edge_size(body, edge, big) / max(big, 1e-12)
        return self.tool_sizes(edge, size * scale)

    @staticmethod
    def _norm_ref(e):
        if e and e[0] == "wrapped":
            return ("wrapped", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]), bool(e[4]))
        if e and e[0] == "curve":
            return ("curve", tuple(map(float, e[1])), float(e[2]))
        if e and e[0] == "circle":
            return ("circle", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]))
        if e and e[0] == "arc":
            return ("arc", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]), float(e[4]), float(e[5]))
        if e and e[0] == "loop":
            return ("loop", tuple(map(float, e[1])), tuple(map(float, e[2])), float(e[3]))
        return (tuple(map(float, e[0])), tuple(map(float, e[1])))

    @staticmethod
    def _free_ends(body, edge, eps: float = 1e-3):
        """How far the tool may reach past each end of a convex edge: a hair (so it cuts cleanly through the end
        face) where the edge ends in open space, nothing where more material continues past the end (the foot of
        a rounded corner standing on a lower step): reaching there would cut a notch into that material."""
        t = (edge.p1 - edge.p0) / max(float(np.linalg.norm(edge.p1 - edge.p0)), 1e-12)
        inward = edge.d1 + edge.d2
        inward = inward / max(float(np.linalg.norm(inward)), 1e-12)
        probe = m3d.Manifold.cube((eps, eps, eps), True)
        out = []
        for end, direction in ((edge.p0, -t), (edge.p1, t)):
            q = end + direction * 3 * eps + inward * 3 * eps
            solid = not (probe.translate(tuple(q)) ^ body.manifold).is_empty()
            out.append(0.0 if solid else eps)
        return tuple(out)

    def _arc_reach(self, body, edge):
        """How far the tool of an open arc runs past each end (radians): a little where the arc ends in open air
        (the next face meets it at a slant, so a square end would leave a sliver), none where material continues."""
        if not edge.convex:
            return (0.0, 0.0)
        eps = 1e-3
        probe = m3d.Manifold.cube((eps, eps, eps), True)
        u, v = edge._basis()
        out = []
        for ang, sgn in ((edge.a0, -1.0), (edge.a0 + edge.sweep, 1.0)):
            radial = math.cos(ang) * u + math.sin(ang) * v
            tangent = sgn * (-math.sin(ang) * u + math.cos(ang) * v)
            end = edge.center + edge.radius * radial
            q = end + tangent * 3 * eps + (edge.s1 * radial + edge.s2 * edge.axis) * 3 * eps
            solid = not (probe.translate(tuple(q)) ^ body.manifold).is_empty()
            out.append(0.0 if solid else min(4.0 * self.size / max(edge.radius, 1e-6), math.radians(80.0)))
        return tuple(out)

    @staticmethod
    def _safe_edge_size(body, edge, requested_size: float) -> float:
        """Limits the rounding/bevel size on a convex straight edge so that it does not cut past
        adjacent face boundaries, holes, or opposite walls on either adjacent face. At the foot of a wall (concave)
        the fillet touches each face `size / tan(half the angle)` from the edge, so that reach is what must fit."""
        if getattr(edge, "kind", "") == "wrapped":
            limit = min(requested_size, edge.radius*.1)
            patch_ids = {p.index for p in edge.patches}
            for other in body.edges:
                if (other.kind == "wrapped" and other is not edge
                        and patch_ids.intersection(p.index for p in other.patches)):
                    gap = abs(edge.radius-other.radius)
                    if gap > 1e-3:
                        limit = min(limit, .49*gap)
            return limit
        if getattr(edge, "kind", "") != "line" or requested_size <= 1e-6:
            return requested_size
        t = (edge.p1 - edge.p0) / max(float(np.linalg.norm(edge.p1 - edge.p0)), 1e-12)
        L = float(np.linalg.norm(edge.p1 - edge.p0))
        limit = requested_size
        half = math.acos(float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0))) / 2.0
        reach_per_size = 1.0 if edge.convex else 1.0 / max(math.tan(half), 1e-6)
        for d, n in [(edge.d1, edge.n1), (edge.d2, edge.n2)]:
            for other in body.edges:
                if other is edge:
                    continue
                k = getattr(other, "kind", "line")
                if k == "line":
                    if abs(float((other.p0 - edge.p0) @ n)) < 1e-3 and abs(float((other.p1 - edge.p0) @ n)) < 1e-3:
                        t0 = float((other.p0 - edge.p0) @ t)
                        t1 = float((other.p1 - edge.p0) @ t)
                        if max(min(t0, t1), 0.0) < min(max(t0, t1), L) - 1e-3:
                            d0 = float((other.p0 - edge.p0) @ d)
                            d1 = float((other.p1 - edge.p0) @ d)
                            dist = min(d0, d1)
                            if dist > 1e-4:
                                limit = min(limit, dist * 0.99 / reach_per_size)
                elif k in ("circle", "loop"):
                    pts = other.pts if k == "loop" else [other.center]
                    if all(abs(float((p - edge.p0) @ n)) < 1e-3 for p in pts):
                        t_vals = [float((p - edge.p0) @ t) for p in pts]
                        if max(min(t_vals), 0.0) < min(max(t_vals), L) - 1e-3:
                            d_vals = [float((p - edge.p0) @ d) for p in pts]
                            r_sub = other.radius if k == "circle" else 0.0
                            dist = min(d_vals) - r_sub
                            if dist > 1e-4:
                                limit = min(limit, dist * 0.99 / reach_per_size)
        return max(limit, 0.01)

    @staticmethod
    def _circular_neighbor_tool(body, edge, size: float):
        """Build the concave blend between a straight face and an axial circular face.

        The ordinary edge tool treats both neighbours as tangent planes. For a cylinder
        that substitutes a tangent line for the curved wall and can leave a lip. This
        section uses the true circle as the second boundary and is extruded along the edge.
        """
        if size <= 1e-6 or getattr(edge, "kind", "") != "line" or edge.convex:
            return None
        t = np.asarray(edge.p1 - edge.p0, dtype=float)
        length = float(np.linalg.norm(t))
        if length <= 1e-8:
            return None
        t /= length
        midpoint = (edge.p0 + edge.p1) * 0.5
        matches = []
        for circle in body.edges:
            if getattr(circle, "kind", "") != "circle" or abs(float(circle.axis @ t)) < 0.999:
                continue
            center_mid = circle.center + t * float((midpoint - circle.center) @ t)
            radial = midpoint - center_mid
            radial -= t * float(radial @ t)
            radial_len = float(np.linalg.norm(radial))
            if radial_len <= 1e-8 or abs(radial_len - circle.radius) > max(0.15, 0.01 * circle.radius):
                continue
            radial /= radial_len
            alignments = (abs(float(radial @ edge.n1)), abs(float(radial @ edge.n2)))
            if max(alignments) < 0.98:
                continue
            # The other adjacent face is the straight profile wall.
            plane_normal = np.asarray(edge.n2 if alignments[0] > alignments[1] else edge.n1, dtype=float)
            matches.append((max(alignments), circle, plane_normal))
        if not matches:
            return None

        _alignment, circle, plane_normal = max(matches, key=lambda item: item[0])
        u = np.cross(t, plane_normal)
        u_len = float(np.linalg.norm(u))
        if u_len <= 1e-8:
            return None
        u /= u_len
        # Orient the section consistently with the adjacent planar face.
        if abs(float(u @ edge.d1)) < abs(float(u @ edge.d2)):
            u = -u
        v = np.cross(t, u)
        v /= max(float(np.linalg.norm(v)), 1e-12)

        origin = np.asarray(edge.p0, dtype=float)
        center = np.array(circle.center, dtype=float, copy=True)
        center -= t * float((center - origin) @ t)
        circle_center = np.array([float((center - origin) @ u), float((center - origin) @ v)])
        radius = float(circle.radius)
        half_chord_sq = radius * radius - circle_center[1] * circle_center[1]
        if half_chord_sq <= 1e-8:
            return None
        half_chord = math.sqrt(half_chord_sq)
        qx = min((circle_center[0] - half_chord, circle_center[0] + half_chord), key=abs)
        corner = np.array([qx, 0.0])

        face_angle = math.acos(float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0)))
        half_angle = face_angle / 2.0
        bisector = edge.d1 + edge.d2
        bisector /= max(float(np.linalg.norm(bisector)), 1e-12)
        expected = corner + np.array([bisector @ u, bisector @ v]) * size / max(math.sin(half_angle), 1e-8)

        centers = []
        for side in (-1.0, 1.0):
            cy = side * size
            for offset in (-1.0, 1.0):
                center_distance = radius + offset * size
                if center_distance <= 1e-8:
                    continue
                dx_sq = center_distance**2 - (cy - circle_center[1])**2
                if dx_sq < -1e-8:
                    continue
                dx = math.sqrt(max(0.0, dx_sq))
                centers.extend((np.array([circle_center[0] - dx, cy]),
                                np.array([circle_center[0] + dx, cy])))
        if not centers:
            return None
        blend_center = min(centers, key=lambda p: float(np.linalg.norm(p - expected)))
        center_distance = float(np.linalg.norm(blend_center - circle_center))
        if center_distance <= 1e-8:
            return None
        line_touch = np.array([blend_center[0], 0.0])
        circle_touch = circle_center + (blend_center - circle_center) * (radius / center_distance)

        def arc_points(c, r, a, b, segments):
            a0 = math.atan2(float(a[1] - c[1]), float(a[0] - c[0]))
            a1 = math.atan2(float(b[1] - c[1]), float(b[0] - c[0]))
            sweep = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
            return [c + r * np.array([math.cos(a0 + sweep * i / segments),
                                      math.sin(a0 + sweep * i / segments)])
                    for i in range(1, segments)]

        section = ([corner, line_touch]
                   + arc_points(blend_center, size, line_touch, circle_touch, 32)
                   + [circle_touch]
                   + arc_points(circle_center, radius, circle_touch, corner, 48))
        area = sum(section[i][0] * section[(i + 1) % len(section)][1]
                   - section[(i + 1) % len(section)][0] * section[i][1]
                   for i in range(len(section)))
        if abs(area) <= 1e-8:
            return None
        if area < 0:
            section.reverse()
        cross_section = m3d.CrossSection([[list(map(float, p)) for p in section]])
        if cross_section.is_empty():
            return None
        solid = m3d.Manifold.extrude(cross_section, length)
        transform = np.column_stack((u, v, t, origin)).astype(float)
        return solid.transform(transform)

    def _mitred_tool(self, body, edge, edges, size):
        """Fill tool for a straight edge at the foot of a wall. Where the next selected foot edge meets it on the
        same floor, both bands run past the corner and are cut off along the bisector (mitred), so the roundings
        flow into each other with no notch."""
        ext = [0.0, 0.0]
        trims = []
        reach = 20.0 * self.size + 10.0
        for k, v in enumerate((edge.p0, edge.p1)):
            far = edge.p1 if k == 0 else edge.p0
            ta = (far - v) / max(float(np.linalg.norm(far - v)), 1e-12)
            for other in edges:
                if other is edge or other.convex != edge.convex or getattr(other, "kind", "") != "line":
                    continue
                q = None
                if np.linalg.norm(other.p0 - v) < 1e-4:
                    q = other.p1
                elif np.linalg.norm(other.p1 - v) < 1e-4:
                    q = other.p0
                if q is None:
                    continue
                tb = (q - v) / max(float(np.linalg.norm(q - v)), 1e-12)
                same_face = any(float(na @ nb) > 0.999 for na in (edge.n1, edge.n2) for nb in (other.n1, other.n2))
                if not same_face or abs(float(ta @ tb)) > 0.999:
                    continue
                corner = self._wall_corner(body, edge, other, v)
                if corner is not None:
                    # outside corner of the wall: the band stops where the ball starts to swing round the corner
                    nf, cd, wall, wall_b, r = corner
                    ext[k] = reach
                    if self.kind == "chamfer":
                        m = np.cross(cd, wall)
                        m = m / np.linalg.norm(m)
                        if float(m @ ta) < 0.0:
                            m = -m
                        trims.append((m, float(m @ v)))
                        trims.extend(self._lowered_top(body, edge, other, v, ta, nf, cd, wall, wall_b))
                    else:
                        # square across the band through the ball's first touch on the corner edge: where that edge
                        # leans, a plane along it would let the band run on past the ball near the floor
                        t = v + r * (1.0 - float(nf @ wall)) / float(nf @ cd) * cd
                        trims.append((ta, float(ta @ t)))
                    break
                m = ta - tb
                m = m / np.linalg.norm(m)
                ext[k] = reach
                trims.append((m, float(m @ v)))
                break
            else:
                trims.extend(self._face_end_trims(body, edge, v, ta))
        a, b = self.tool_sizes(edge, size)
        tool = CadKernel.round_tool(edge, a, self.kind, extend=tuple(ext), size2=b)
        for m, off in trims:
            tool = tool.trim_by_plane([float(x) for x in m], off)
        return tool

    @staticmethod
    def _face_end_trims(body, edge, v, ta):
        """Where a face next to a foot edge narrows at the end `v` (the side of a triangular rib leans in), the
        band must stop at that side, carried straight out of the face, like Fusion; a square end would fill air
        beside the narrowing face. Returns (normal, offset) planes that keep the band's own side."""
        trims = []
        for d, n in ((edge.d1, edge.n1), (edge.d2, edge.n2)):
            for other in body.edges:
                if other is edge or getattr(other, "kind", "") != "line":
                    continue
                if np.linalg.norm(other.p0 - v) < 1e-4:
                    q = other.p1
                elif np.linalg.norm(other.p1 - v) < 1e-4:
                    q = other.p0
                else:
                    continue
                tb = (q - v) / max(float(np.linalg.norm(q - v)), 1e-12)
                if abs(float(tb @ n)) > 1e-3 or float(tb @ d) < 1e-3 or float(ta @ tb) < 1e-3:
                    continue  # not a side of this face leaning in over the edge
                m = np.cross(tb, n)
                m = m / max(float(np.linalg.norm(m)), 1e-12)
                if float(m @ ta) < 0.0:
                    m = -m
                trims.append((m, float(m @ v)))
        return trims

    @staticmethod
    def _past_the_other_wall(ea, eb, tool_a, tool_b) -> m3d.Manifold:
        """At an inside corner of a face outline that is not square (a 60 or 120 degree corner of a honeycomb cell),
        each band run on past the corner also leaves the other wall's material and comes out over the open cell side,
        where nothing holds that rim up: the outline is the union of the two walls' half planes, each rounded on its
        own. The overlap of the bands alone leaves a sharp ridge there; this is the missing piece of each band:
        behind the corner and on the open side of the other wall (empty at a square corner)."""
        v = next(p for p in (ea.p0, ea.p1) if min(np.linalg.norm(p - eb.p0), np.linalg.norm(p - eb.p1)) < 1e-4)

        def frame(e):
            far = e.p1 if np.linalg.norm(e.p0 - v) < 1e-4 else e.p0
            t = (far - v) / max(float(np.linalg.norm(far - v)), 1e-12)
            other = eb if e is ea else ea
            shared = max((e.n1, e.n2), key=lambda n: max(float(n @ other.n1), float(n @ other.n2)))
            wall = e.n2 if shared is e.n1 else e.n1
            return t, np.asarray(wall, dtype=float)

        (t_a, wall_a), (t_b, wall_b) = frame(ea), frame(eb)
        pieces = []
        for t, tool, wall_other, t_other, wall in ((t_a, tool_a, wall_b, t_b, wall_a), (t_b, tool_b, wall_a, t_a, wall_b)):
            if float(wall @ t_other) < 1e-3 or float(t @ wall_other) < 1e-3:
                continue          # not an inside corner of the outline: behind it the band runs on into air
            piece = (tool.trim_by_plane([float(x) for x in -t], float(-t @ v))
                     .trim_by_plane([float(x) for x in wall_other], float(wall_other @ v)))
            if piece.volume() > 1e-9:
                pieces.append(piece)
        return m3d.Manifold.batch_boolean(pieces, m3d.OpType.Add) if pieces else m3d.Manifold()

    def _wall_corner(self, body, ea, eb, v):
        """Two fillet/chamfer foot edges on the same floor that meet at `v` round the outside corner of a wall (the
        side of a rib meets its end). Fusion's rolling ball swings round the wall's corner edge there, so the
        roundings flow into each other; a mitre would leave a crease. A chamfer's bevel swings round the same way.
        Returns (floor normal, corner edge direction going up, wall normal of `ea`, wall normal of `eb`, radius),
        or None for an inside corner or unequal fillet sizes."""
        if self.size <= 0:
            return None
        faces_a = [(ea.n1, ea.d1), (ea.n2, ea.d2)]
        faces_b = [(eb.n1, eb.d1), (eb.n2, eb.d2)]
        for ia, (na, da) in enumerate(faces_a):
            for ib, (nb, _db) in enumerate(faces_b):
                if float(na @ nb) < 0.999:
                    continue
                far = eb.p1 if np.linalg.norm(eb.p0 - v) < 1e-4 else eb.p0
                tb = (far - v) / max(float(np.linalg.norm(far - v)), 1e-12)
                if float(tb @ da) > -1e-3:
                    return None       # the other edge runs into this floor: an inside corner
                wall_a, wall_b = faces_a[1 - ia][0], faces_b[1 - ib][0]
                cd = np.cross(wall_a, wall_b)
                if np.linalg.norm(cd) < 1e-6:
                    return None
                cd = cd / np.linalg.norm(cd)
                if float(cd @ na) < 0.0:
                    cd = -cd
                if float(cd @ na) < 0.05:
                    return None
                ra = self._safe_edge_size(body, ea, abs(self.size))
                rb = self._safe_edge_size(body, eb, abs(self.size))
                if self.kind == "fillet" and abs(ra - rb) > 1e-6:
                    return None
                return na, cd, wall_a, wall_b, ra
        return None

    def _wall_corner_tools(self, seen):
        """(body id, fill, balls) for each outside wall corner between two selected foot edges (`_wall_corner`);
        a chamfer has no balls (None)."""
        feet = [(b, e) for b, e in seen if not e.convex and getattr(e, "kind", "") == "line"]
        out = []
        for i in range(len(feet)):
            for j in range(i + 1, len(feet)):
                (ba, ea), (bb, eb) = feet[i], feet[j]
                if ba is not bb:
                    continue
                v = next((p for p in (ea.p0, ea.p1) if min(np.linalg.norm(p - eb.p0), np.linalg.norm(p - eb.p1)) < 1e-4), None)
                if v is None:
                    continue
                corner = self._wall_corner(ba, ea, eb, v)
                if corner is None:
                    continue
                if self.kind == "chamfer":
                    nf, cd, wall_a, wall_b, _r = corner
                    bevels = [self._bevel_plane(ba, e, v) for e in (ea, eb)]
                    out.append((ba.body_id, self.wall_chamfer_tool(v, nf, cd, wall_a, wall_b, *bevels), None))
                else:
                    out.append((ba.body_id, *self.wall_corner_tool(v, *corner)))
        return out

    def _bevel_plane(self, body, edge, v):
        """(normal, point) of the bevel face the chamfer band of the foot edge `edge` gets (as in `_mitred_tool`)."""
        a, b = self.tool_sizes(edge, self._safe_edge_size(body, edge, abs(self.size)))
        t = edge.p1 - edge.p0
        pa, pb = v + a * edge.d1, v + (a if b is None else b) * edge.d2
        n = np.cross(t, pb - pa)
        return n / np.linalg.norm(n), pa

    @staticmethod
    def _bevel_reach(v, nf, cd, wall, bevel):
        """(height up the corner edge `cd`, reach out over the floor `nf`) where the bevel plane `bevel` of the band
        next to `wall` meets the corner edge and the floor in the plane where the band stops at the corner `v`."""
        g = wall - float(wall @ nf) / float(cd @ nf) * cd      # the floor's line in the plane of cd and the wall normal
        g = g / np.linalg.norm(g)
        n, p = bevel
        along = lambda direction: float(n @ (p - v)) / float(n @ direction)
        return along(cd), along(g), g

    def _lowered_top(self, body, edge, other, v, ta, nf, cd, wall, wall_b):
        """Where two walls lean differently, the same chamfer distance meets their common corner edge at two
        heights. The bands are made to meet at one point there, the lower one: the higher band's top comes down to it
        over the last chamfer distance before the corner (a flat facet through its floor point at the corner).
        Returns the trim plane for `edge`'s band, or nothing when it is the lower one."""
        h, reach, g = self._bevel_reach(v, nf, cd, wall, self._bevel_plane(body, edge, v))
        h_other = self._bevel_reach(v, nf, cd, wall_b, self._bevel_plane(body, other, v))[0]
        if h <= h_other + 1e-6:
            return []
        low, foot = v + h_other * cd, v + reach * g
        back = v + h * cd + reach * ta               # on the band's top line, one chamfer distance from the corner
        m = np.cross(back - foot, low - foot)
        m = m / np.linalg.norm(m)
        inside = v + 0.25 * (low - v) + 0.25 * (foot - v)
        if float(m @ inside) < float(m @ foot):
            m = -m
        return [(m, float(m @ foot))]

    @staticmethod
    def wall_chamfer_tool(v, nf, cd, wall_a, wall_b, bevel_a, bevel_b, step_deg: float = 3.0):
        """The chamfer round an outside wall corner at `v` (see `wall_corner_tool`): each band's bevel meets the
        floor in the plane where the band stops, and both meet the corner edge (going up along `cd`) at the lower of
        their two heights (`_lowered_top`); in between the bevel swings round the corner edge, its floor point on an
        arc round `v`. Returns the fill."""
        meets = [FilletFeature._bevel_reach(v, nf, cd, wall, bevel) for wall, bevel in ((wall_a, bevel_a), (wall_b, bevel_b))]
        height = min(h for h, _r, _g in meets)
        heights = [height, height]
        reaches = [r for _h, r, _g in meets]

        def floor_dir(u):
            g = u - float(u @ nf) / float(cd @ nf) * cd      # the floor's line in the plane of cd and u
            return g / np.linalg.norm(g)
        w = wall_b - (wall_a @ wall_b) * wall_a
        w = w / np.linalg.norm(w)
        sweep = math.acos(float(np.clip(wall_a @ wall_b, -1.0, 1.0)))
        n = max(4, int(math.ceil(math.degrees(sweep) / step_deg)))
        e = 1e-3 * max(1.0, max(heights + reaches))
        slices = []
        for k in range(n + 1):
            s = k / n
            u = math.cos(sweep * s) * wall_a + math.sin(sweep * s) * w
            top = v + ((1 - s) * heights[0] + s * heights[1]) * cd
            foot = v + ((1 - s) * reaches[0] + s * reaches[1]) * floor_dir(u)
            # a hair into the wall and the floor, so the fill overlaps the body instead of touching it along the edge
            slices.append([v - e * u - e * nf, top - e * u, top, foot, foot - e * nf])
        hulls = [m3d.Manifold.hull_points([tuple(map(float, p)) for p in slices[k] + slices[k + 1]]) for k in range(n)]
        return m3d.Manifold.batch_boolean(hulls, m3d.OpType.Add)

    @staticmethod
    def wall_corner_tool(v, nf, cd, wall_a, wall_b, r, step_deg: float = 3.0):
        """The rounding round an outside wall corner at `v` on the floor `nf`, the wall's corner edge going up along
        `cd`. The ball (radius r) rests on the floor and leans on the corner edge while it turns from wall_a to
        wall_b. Each slice holds the floor point under the corner, the touch points on the edge and the floor and the
        ball centre; the hull of neighbouring slices minus the swept ball is the fill. Returns (fill, swept balls):
        the balls also come off the two bands, which run straight on where the ball already turns."""
        w = wall_b - (wall_a @ wall_b) * wall_a
        w = w / np.linalg.norm(w)
        sweep = math.acos(float(np.clip(wall_a @ wall_b, -1.0, 1.0)))
        n = max(4, int(math.ceil(math.degrees(sweep) / step_deg)))
        e = 1e-3 * max(1.0, r)
        slices, centres = [], []
        for k in range(n + 1):
            phi = sweep * k / n
            u = math.cos(phi) * wall_a + math.sin(phi) * w
            t = v + r * (1.0 - float(nf @ u)) / float(nf @ cd) * cd       # where the ball touches the corner edge
            c = t + r * u
            k_floor = t - float(nf @ (t - v)) * nf
            # a hair into the wall and the floor, so the fill overlaps the body instead of touching it along the edge
            slices.append([v - e * u - e * nf, k_floor - e * u - e * nf, t - e * u, t, c, c - r * nf, c - r * nf - e * nf])
            centres.append(c)
        hulls = [m3d.Manifold.hull_points([tuple(map(float, p)) for p in slices[k] + slices[k + 1]]) for k in range(n)]
        fill = m3d.Manifold.batch_boolean(hulls, m3d.OpType.Add)
        ball = m3d.Manifold.sphere(r, circular_segments=96)   # as fine as the bands (24 pieces a quarter turn)
        balls = m3d.Manifold.batch_boolean(
            [m3d.Manifold.hull(ball.translate(tuple(map(float, centres[k]))) + ball.translate(tuple(map(float, centres[k + 1]))))
             for k in range(n)], m3d.OpType.Add)
        return fill - balls, balls

    def _corner_tools(self, seen):
        """Where three selected outside edges meet square at a vertex (a box corner), the edge tools alone leave a
        pointed bump (three cylinders crossing). Fusion's rolling ball rounds that corner into a sphere, and a chamfer
        gets a small flat triangle; this is the extra cut for each such corner: the corner cube minus the ball (fillet)
        or the cube below the triangle (equal chamfer). Corners with unequal sizes keep the plain result."""
        if self.kind == "chamfer" and self.chamfer_type != "equal":
            return []
        lines = [(b, e) for b, e in seen if e.convex and getattr(e, "kind", "") == "line"]
        out, done = [], []
        for body, edge in lines:
            for v in (edge.p0, edge.p1):
                if any(body is b and np.linalg.norm(v - q) < 1e-4 for b, q in done):
                    continue
                meet = []
                for b2, e2 in lines:
                    if b2 is not body:
                        continue
                    if np.linalg.norm(e2.p0 - v) < 1e-4:
                        meet.append((e2, e2.p1))
                    elif np.linalg.norm(e2.p1 - v) < 1e-4:
                        meet.append((e2, e2.p0))
                if len(meet) != 3:
                    continue
                done.append((body, v))
                ts = [(far - v) / max(float(np.linalg.norm(far - v)), 1e-12) for _e, far in meet]
                if any(abs(float(ts[i] @ ts[j])) > 1e-3 for i in range(3) for j in range(i + 1, 3)):
                    continue        # not a square corner
                # each edge's faces must run along the other two edges (a real outside corner of the solid)
                ok = True
                for k, (e3, _far) in enumerate(meet):
                    others = [ts[j] for j in range(3) if j != k]
                    if not all(max(float(d @ o) for o in others) > 0.999 for d in (e3.d1, e3.d2)):
                        ok = False
                if not ok:
                    continue
                sizes = [self._safe_edge_size(body, e3, abs(self.size)) for e3, _ in meet]
                if max(sizes) - min(sizes) > 1e-6:
                    continue
                r = sizes[0]
                tool = self.corner_tool(r, self.kind)
                t1, t2, t3 = ts
                if float(np.cross(t1, t2) @ t3) < 0:
                    t2, t3 = t3, t2
                mat = np.column_stack([t1, t2, t3, v]).astype(float)
                out.append((body.body_id, tool.transform(mat)))
        return out

    @staticmethod
    def corner_tool(r: float, kind: str) -> m3d.Manifold:
        """The extra cut at a square outside corner in local coordinates (corner at the origin, edges along +x/+y/+z):
        fillet = cube [0, r]^3 minus the ball of radius r centred at (r, r, r), chamfer = the part of the cube below
        the plane x + y + z = 2r. The cube reaches a hair outside the corner so the cut is clean."""
        m = 1e-3 * max(1.0, r)
        cube = m3d.Manifold.cube((r + m, r + m, r + m)).translate((-m, -m, -m))
        if kind == "chamfer":
            k = 1.0 / math.sqrt(3.0)
            return cube.trim_by_plane((-k, -k, -k), -2.0 * r * k)
        ball = m3d.Manifold.sphere(r, circular_segments=96).translate((r, r, r))
        return cube - ball

    def edges_in(self, manifolds: dict) -> list:
        """The edges this step rounds, found in the bodies as they were before it (`manifolds`: body id -> solid),
        so the view can show which edges a step in the timeline is about."""
        cands = []
        for m in manifolds.values():
            try:
                bb = np.array(m.bounding_box())
                cands.append((compute_planar_edges(m), 0.75 * float(np.linalg.norm(bb[3:] - bb[:3]))))
            except Exception:
                pass
        out = []
        for ref in self.edges:
            hit = next((e for edges, _ in cands if (e := edge_from_ref(ref, edges)) is not None), None)
            if hit is None:
                hit = next((e for edges, reach in cands
                            if (e := fuzzy_edge_from_ref(ref, edges, used=out, reach=reach)) is not None), None)
            if hit is not None:
                out.append(hit)
        return out

    def execute(self, doc: Any) -> None:
        """All edges are matched against the body as it is *before* this step and the tools are applied
        together; rounding them one after another would hide the neighbouring edges (the first
        rounding turns the faces next to it into curved ones)."""
        self.skipped = 0
        if abs(self.size) <= 1e-6:
            return
        cut, add = {}, {}
        seen = []

        def take(body, edge):
            if edge.kind == "curve":    # free-form creases can be picked (measure, paths) but not rounded yet
                self.skipped += 1
                return
            if any(body is b and edge.same_as(e) for b, e in seen):
                return  # the same edge selected twice
            seen.append((body, edge))

        missing = []
        for ref in self.edges:
            hit = None
            for body in feature_bodies(doc, self):
                edge = edge_from_ref(ref, body.edges)
                if edge is not None:
                    hit = (body, edge)
                    break
            if hit is None:
                missing.append(ref)
                continue
            take(*hit)
        # Edges that moved or changed size because something earlier in the history was edited: take the
        # nearest edge of the same kind instead of leaving the sharp corner behind.
        for ref in missing:
            best = None
            for body in feature_bodies(doc, self):
                bb = np.array(body.manifold.bounding_box())
                reach = 0.75 * float(np.linalg.norm(bb[3:] - bb[:3]))
                edge = fuzzy_edge_from_ref(ref, body.edges, used=[e for b, e in seen if b is body], reach=reach)
                if edge is not None:
                    best = (body, edge)
                    break
            if best is None:
                self.skipped += 1
            else:
                take(*best)

        # A whole outline includes its straight and circular pieces. Cutting those again with independently fitted
        # tools makes nearly coincident bevels, splitting one surface into many narrow strips.
        loops = [(body, edge) for body, edge in seen if edge.kind == "loop"]
        seen = [(body, edge) for body, edge in seen
                if not any(body is owner and loop_contains(loop, edge) for owner, loop in loops)]

        for body, edge in seen:
            ext = self._free_ends(body, edge) if edge.convex and getattr(edge, "kind", "") == "line" else 1e-3 if edge.convex else 0.0
            size = abs(self.size)
            if self.size < 0 and self.kind == "fillet":
                # Negative fillet cuts a concave cove, limited to convex box edges and full circular
                # rims; chamfer remains unsigned.
                tool = CadKernel.round_cove_tool(edge, self._safe_edge_size(body, edge, size), extend=ext)
                if tool.is_empty():
                    self.skipped += 1
                else:
                    cut.setdefault(body.body_id, []).append(tool)
                continue
            eff_size = self._safe_edge_size(body, edge, size)
            a, b = self._limited_sizes(body, edge, size)
            curved_fill = (self._circular_neighbor_tool(body, edge, self.size)
                           if self.kind == "fillet" and not edge.convex else None)
            if curved_fill is not None:
                tool = curved_fill
            elif getattr(edge, "kind", "") == "loop" and not edge.convex:
                tool = CadKernel.foot_fill_tool(body.manifold, edge, self.size, self.kind)
            elif not edge.convex and getattr(edge, "kind", "") == "line":
                tool = self._mitred_tool(body, edge, [e for b, e in seen if b is body], eff_size)
            elif getattr(edge, "kind", "") == "circle" and edge.is_arc:
                a, b = self.tool_sizes(edge, size)
                tool = CadKernel.circle_round_tool(edge, a, self.kind, reach=self._arc_reach(body, edge), size2=b)
            else:
                tool = CadKernel.round_tool(edge, a, self.kind, extend=ext, size2=b)
            (cut if edge.convex else add).setdefault(body.body_id, []).append(tool)

        # Inside corners of a face outline: the two bevel bands end square at the corner and leave a notch there.
        # Material survives only where one wall still allows it, so what must go is the overlap of both bands.
        convex = ([(b, e) for b, e in seen if e.convex and getattr(e, "kind", "") == "line"]
                  if self.size >= 0 or self.kind != "fillet" else [])
        for i in range(len(convex)):
            for j in range(i + 1, len(convex)):
                (ba, ea), (bb, eb) = convex[i], convex[j]
                if ba is not bb:
                    continue
                shared = any(np.linalg.norm(p - q) < 1e-4 for p in (ea.p0, ea.p1) for q in (eb.p0, eb.p1))
                da = (ea.p1 - ea.p0) / max(np.linalg.norm(ea.p1 - ea.p0), 1e-12)
                db = (eb.p1 - eb.p0) / max(np.linalg.norm(eb.p1 - eb.p0), 1e-12)
                same_face = any(float(na @ nb) > 0.999 for na in (ea.n1, ea.n2) for nb in (eb.n1, eb.n2))
                if not shared or not same_face or abs(float(da @ db)) > 0.999:
                    continue
                sa = self._limited_sizes(ba, ea, self.size)
                sb = self._limited_sizes(bb, eb, self.size)
                ext = 40.0 * max(min(sa[0], sb[0]), min(sa[1] or sa[0], sb[1] or sb[0])) + 10.0
                try:
                    ta_tool = CadKernel.edge_round_tool(ea, sa[0], self.kind, extend=ext, size2=sa[1])
                    tb_tool = CadKernel.edge_round_tool(eb, sb[0], self.kind, extend=ext, size2=sb[1])
                    corner = (ta_tool ^ tb_tool) + self._past_the_other_wall(ea, eb, ta_tool, tb_tool)
                except Exception:
                    continue
                if not corner.is_empty():
                    cut.setdefault(ba.body_id, []).append(corner)

        for body_id, fill, balls in self._wall_corner_tools(seen):
            if balls is not None:
                add[body_id] = [t - balls for t in add.get(body_id, [])]
            add.setdefault(body_id, []).append(fill)

        if self.size > 0:
            for body_id, tool in self._corner_tools(seen):
                cut.setdefault(body_id, []).append(tool)

        for body_id in set(cut) | set(add):
            body = doc.bodies.get(body_id)
            if body is None:
                continue
            try:
                result = body.manifold
                cut_tools = cut.get(body_id)
                if cut_tools:
                    if len(cut_tools) == 1:
                        combined = cut_tools[0]
                    else:
                        combined = m3d.Manifold.batch_boolean(cut_tools, m3d.OpType.Add)
                    result = result - combined
                add_tools = add.get(body_id)
                if add_tools:
                    if len(add_tools) == 1:
                        combined_add = add_tools[0]
                    else:
                        combined_add = m3d.Manifold.batch_boolean(add_tools, m3d.OpType.Add)
                    result = result + combined_add
            except Exception:
                self.skipped += len(cut.get(body_id, [])) + len(add.get(body_id, []))
                continue
            if not result.is_empty():
                body.manifold = CadKernel.drop_slivers(result)
                body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "edges": [list(e) if isinstance(e[0], str) else [list(e[0]), list(e[1])] for e in self.edges],
            "size": self.size,
            "kind": self.kind,
            "chamfer_type": self.chamfer_type,
            "size2": self.size2,
            "angle": self.angle,
            "flip": self.flip,
        }
