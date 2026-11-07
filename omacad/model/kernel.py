"""
Omacad - Solid Geometry Kernel
Wraps Manifold3D and Trimesh for watertight CAD operations and mesh extraction.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np
import manifold3d as m3d
import trimesh
from omacad.model import quality


STRAY_OPEN_SHARE = 0.015      # an open run of edge lines shorter than this share of the body diagonal is stray
STRAY_LOOP_SHARE = 0.003      # a closed one only below this (small holes and round ends are real)


def stray_line_mask(segments: np.ndarray, diag: float) -> np.ndarray:
    """Mask over line segments (k, 2, 3) of the stray bits: connected runs of lines that are short compared with the
    body and lead nowhere. A boolean seam or the tessellation of a bent rib leaves such dashes and ticks along
    smooth surfaces; real edges join into long runs or close around a hole."""
    k = len(segments)
    if k == 0 or diag <= 0:
        return np.zeros(k, dtype=bool)
    q = np.round(np.asarray(segments, dtype=np.float64).reshape(-1, 3) / (diag * 1e-6)).astype(np.int64)
    _, vid = np.unique(q, axis=0, return_inverse=True)
    vid = vid.ravel().reshape(-1, 2)
    parent = np.arange(vid.max() + 1)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in vid:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    comp = np.array([find(a) for a in vid[:, 0]])
    length = np.linalg.norm(segments[:, 1] - segments[:, 0], axis=1)
    total = np.bincount(comp, weights=length, minlength=len(parent))
    degree = np.bincount(vid.ravel(), minlength=len(parent))
    open_end = np.zeros(len(parent), dtype=bool)
    ends = np.flatnonzero(degree == 1)
    if len(ends):
        open_end[[find(e) for e in ends]] = True
    limit = np.where(open_end, STRAY_OPEN_SHARE, STRAY_LOOP_SHARE) * diag
    return total[comp] < limit[comp]


@dataclass
class RenderMesh:
    """Holds tessellated data ready for OpenGL rendering."""
    vertices: np.ndarray      # Shape (N, 3), float32 (triangles unrolled)
    normals: np.ndarray       # Shape (N, 3), float32
    sharp_lines: np.ndarray   # Shape (M, 3), float32 (pairs of vertices for lines)
    bounds_min: np.ndarray    # [min_x, min_y, min_z]
    bounds_max: np.ndarray    # [max_x, max_y, max_z]
    center: np.ndarray        # [cx, cy, cz]
    source: Optional[tuple] = field(default=None, repr=False)   # (vertices, triangles, kept mask) for tangent_lines
    _tangent: Optional[np.ndarray] = field(default=None, repr=False)
    _surface_ids: Optional[np.ndarray] = field(default=None, repr=False)
    _display: Optional[dict] = field(default=None, repr=False)
    _patch_display: dict = field(default_factory=dict, repr=False)

    def drawn_edges(self, tangent: bool) -> np.ndarray:
        """Edge lines to draw: the sharp lines (+ tangent lines when shown) without the stray bits a boolean or a
        tessellation leaves (`stray_line_mask`), so only edges the user made show (Björn #214/#215). Picking,
        snapping and measuring keep using every sharp line."""
        cache = self.__dict__.setdefault("_drawn_edges", {})
        if tangent not in cache:
            lines = np.vstack([self.sharp_lines, self.tangent_lines()]) if tangent else self.sharp_lines
            lines = np.asarray(lines, dtype=np.float32).reshape(-1, 3)
            diag = float(np.linalg.norm(np.asarray(self.bounds_max) - np.asarray(self.bounds_min)))
            keep = ~stray_line_mask(lines.reshape(-1, 2, 3), diag)
            cache[tangent] = np.ascontiguousarray(lines.reshape(-1, 2, 3)[keep].reshape(-1, 3))
        return cache[tangent]

    def display_arrays(self, edge_lines: np.ndarray):
        """(vertices, normals, edge lines) to draw: smoothed (display_smooth) while "Fast view, exact export" is
        on, otherwise the mesh as it is. Cached per set of edge lines (tangent edges on/off)."""
        if not quality.fast_view_enabled():
            return self.vertices, self.normals, edge_lines
        if self._display is None:
            self._display = {}
        key = len(edge_lines)
        if key not in self._display:
            from omacad.model.display_smooth import smooth_arrays
            self._display = {key: smooth_arrays(self.vertices, self.normals, edge_lines)}
        return self._display[key]

    def display_patch_arrays(self, triangles, lines):
        """Draw a selected patch and its outline with the same smoothing as the solid."""
        vertices = np.asarray(triangles, dtype=np.float32).reshape(-1, 3)
        if not quality.fast_view_enabled() or not len(vertices):
            return vertices, None, lines
        key = (id(triangles), len(lines))
        cached = self._patch_display.get(key)
        if cached is not None and cached[0] is triangles:
            return cached[1]
        tri = vertices.reshape(-1, 3, 3)
        full = np.ascontiguousarray(self.vertices.reshape(-1, 9), dtype=np.float32)
        subset = np.ascontiguousarray(vertices.reshape(-1, 9))
        dtype = np.dtype((np.void, 9 * full.dtype.itemsize))
        keys, wanted = full.view(dtype).ravel(), subset.view(dtype).ravel()
        order = np.argsort(keys)
        at = np.searchsorted(keys[order], wanted)
        at = np.minimum(at, len(order) - 1)
        matched = keys[order[at]] == wanted
        normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-12)
        normals = np.repeat(normal[:, None, :], 3, axis=1)
        normals[matched] = self.normals.reshape(-1, 3, 3)[order[at[matched]]]
        from omacad.model.display_smooth import smooth_arrays
        result = smooth_arrays(vertices, normals.reshape(-1, 3), lines)
        if len(self._patch_display) >= 4:
            self._patch_display.clear()
        self._patch_display[key] = (triangles, result)
        return result

    def tangent_lines(self) -> np.ndarray:
        """Line pairs (like `sharp_lines`) where a flat face runs smoothly into a curved one (Settings > Show tangent
        edges). Worked out the first time they are drawn: most bodies never need them."""
        if self._tangent is None:
            self._tangent = np.zeros((0, 3), dtype=np.float32)
            if self.source is not None:
                from omacad.model.faces_surfaces import tangent_edge_mask
                v, f, keep = self.source
                tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
                mask = tangent_edge_mask(v, f, tm, CadKernel.SHARP_EDGE_DEG)
                if keep is not None:
                    mask &= keep[tm.face_adjacency[:, 0]] & keep[tm.face_adjacency[:, 1]]
                self._tangent = v[tm.face_adjacency_edges[mask]].reshape(-1, 3).astype(np.float32)
        return self._tangent

    def curved_surface(self, tri: int) -> Optional[np.ndarray]:
        """The triangles (k, 3, 3) of the curved surface that drawn triangle `tri` lies on (a fillet, a cylinder
        wall), for the hover highlight; None on a flat face. Worked out the first time a curve is hovered."""
        res = self.curved_surface_with_normals(tri)
        return res[0] if res is not None else None

    def curved_surface_with_normals(self, tri: int) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """The triangles (k, 3, 3) and vertex normals (k, 3, 3) of the curved surface that drawn triangle `tri`
        lies on; None on a flat face."""
        if self.source is None:
            return None
        v, f, keep = self.source
        if self._surface_ids is None:
            from omacad.model.faces_surfaces import curved_surface_ids
            ids = curved_surface_ids(v, f, trimesh.Trimesh(vertices=v, faces=f, process=False), CadKernel.SHARP_EDGE_DEG)
            self._surface_ids = ids if keep is None else ids[keep]
        sid = int(self._surface_ids[tri])
        if sid < 0:
            return None
        mask = (self._surface_ids == sid)
        verts = np.asarray(self.vertices, dtype=np.float32).reshape(-1, 3, 3)[mask]
        norms = np.asarray(self.normals, dtype=np.float32).reshape(-1, 3, 3)[mask]
        return verts, norms


class CadKernel:
    """Provides high-level solid modeling operations."""
    SHARP_EDGE_DEG = 20.0     # faces meeting at more than this show an edge line

    @staticmethod
    def create_box(length: float, width: float, height: float, center: bool = False) -> m3d.Manifold:
        """Create a 3D rectangular box/prism."""
        return m3d.Manifold.cube([float(length), float(width), float(height)], center=center)

    @staticmethod
    def create_cylinder(radius: float, height: float, segments: Optional[int] = None, center: bool = False) -> m3d.Manifold:
        """Create a cylinder with specified radius and height."""
        cyl = m3d.Manifold.cylinder(float(height), float(radius), float(radius), circular_segments=segments or quality.circle_segments())
        if center:
            mat = np.array([
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, -height / 2.0]
            ], dtype=float)
            cyl = cyl.transform(mat)
        return cyl

    @staticmethod
    def create_sphere(radius: float, segments: Optional[int] = None) -> m3d.Manifold:
        """Create a UV sphere."""
        return m3d.Manifold.sphere(float(radius), circular_segments=segments or quality.sphere_segments())

    @staticmethod
    def extrude_cross_section(
        polygon_pts: List[Tuple[float, float]], 
        height: float, 
        transform_mat: Optional[np.ndarray] = None
    ) -> m3d.Manifold:
        """
        Extrude a 2D planar polygon along its normal vector.
        polygon_pts: list of (u, v) points forming a closed loop
        height: extrusion distance
        transform_mat: optional 3x4 transform matrix to place the solid in 3D space
        """
        if len(polygon_pts) < 3:
            raise ValueError("Polygon must have at least 3 points")
        
        # Ensure polygon vertices are clean float tuples
        coords = [[float(p[0]), float(p[1])] for p in polygon_pts]
        cs = m3d.CrossSection([coords])
        manifold = m3d.Manifold.extrude(cs, height=float(height))
        
        if transform_mat is not None:
            if transform_mat.shape != (3, 4):
                raise ValueError("Transform matrix must have shape (3, 4)")
            manifold = manifold.transform(transform_mat.astype(float))
            
        return manifold

    @staticmethod
    def revolve_cross_section(
        polygon_pts: List[Tuple[float, float]],
        segments: int = 48,
        transform_mat: Optional[np.ndarray] = None
    ) -> m3d.Manifold:
        """Revolve a 2D planar polygon around the V axis."""
        coords = [[float(p[0]), float(p[1])] for p in polygon_pts]
        cs = m3d.CrossSection([coords])
        manifold = m3d.Manifold.revolve(cs, circular_segments=segments)
        
        if transform_mat is not None:
            manifold = manifold.transform(transform_mat.astype(float))
            
        return manifold

    @staticmethod
    def edge_round_tool(edge, size: float, kind: str, extend=0.0, arc_segments: int = 24, size2=None) -> m3d.Manifold:
        """The sliver along an edge that a chamfer/fillet removes (convex edge) or fills in (concave).

        Cross-section in the plane across the edge, with the corner at the origin and e1 along face 1:
        chamfer = triangle (corner, A, B); fillet = corner, A, arc towards the corner, B, where A and B
        are the tangent points a distance size/tan(theta/2) along the faces. `size2`: a chamfer's distance
        along face 2 (d2) when it differs from `size` (two distances / distance and angle)."""
        t = (edge.p1 - edge.p0) / np.linalg.norm(edge.p1 - edge.p0)
        origin = edge.p0.copy()
        ext_start, ext_end = (extend if isinstance(extend, (tuple, list)) else (extend, extend))   # at p0, at p1
        cos_faces = float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0))
        if not 1e-6 < math.acos(cos_faces) < math.pi - 1e-6:
            return m3d.Manifold()         # flat (no corner) or folded flat on itself: nothing to round, no 1/tan(0)
        e1 = edge.d1
        e2 = edge.d2 - (edge.d2 @ e1) * e1
        e2 = e2 / np.linalg.norm(e2)
        if np.cross(e1, e2) @ t < 0:      # keep the frame right-handed so the solid isn't inside-out
            t, origin = -t, edge.p1.copy()
            ext_start, ext_end = ext_end, ext_start
        cos_th = float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0))
        theta = math.acos(cos_th)         # angle between the faces, as seen from the edge
        half = theta / 2.0
        convex = getattr(edge, "convex", True)
        # a fill reaches a hair into the material too: one that only touches the faces stays a loose piece
        m = 1e-3 * max(1.0, float(size)) if convex else 1e-4 * max(1.0, float(size))
        # A convex tool reaches a hair out of the body, past each face along its outward normal (face 1 lies
        # along +x, face 2 at angle theta); a point square to the axes would sit inside the material when the
        # faces are not at 90 degrees (a hexagon's 120 degree corner got a notch in face 2).
        n1, n2 = np.array([0.0, -1.0]), np.array([-math.sin(theta), math.cos(theta)])
        out1, out2, out0 = tuple(m * n1), tuple(m * n2), tuple(m * (n1 + n2))
        if kind == "chamfer":
            s = float(size)
            s2 = s if size2 is None else float(size2)
            A = np.array([s, 0.0])
            B = s2 * np.array([math.cos(theta), math.sin(theta)])
            if m > 0:
                poly = [out0, tuple(A + out1), tuple(A), tuple(B), tuple(B + out2)]
            else:
                poly = [(0.0, 0.0), tuple(A), tuple(B)]
        else:
            r = float(size)
            s = r / math.tan(half)
            A = np.array([s, 0.0])
            B = s * np.array([math.cos(theta), math.sin(theta)])
            rc = r / math.sin(half)
            c = rc * np.array([math.cos(half), math.sin(half)])
            pa, pb = math.atan2(A[1] - c[1], A[0] - c[0]), math.atan2(B[1] - c[1], B[0] - c[0])
            sweep = (pb - pa + math.pi) % (2 * math.pi) - math.pi   # the short way round: faces the corner
            arc = [(c[0] + r * math.cos(pa + sweep * k / arc_segments), c[1] + r * math.sin(pa + sweep * k / arc_segments))
                   for k in range(1, arc_segments)]
            if m > 0:
                poly = [out0, tuple(A + out1), tuple(A)] + arc + [tuple(B), tuple(B + out2)]
            else:
                poly = [(0.0, 0.0), tuple(A)] + arc + [tuple(B)]
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))
        if area < 0:
            poly.reverse()
        length = float(np.linalg.norm(edge.p1 - edge.p0)) + ext_start + ext_end
        solid = m3d.Manifold.extrude(m3d.CrossSection([[list(map(float, q)) for q in poly]]), height=length)
        mat = np.column_stack([e1, e2, t, origin - t * ext_start]).astype(float)
        return solid.transform(mat)

    @staticmethod
    def grown(solid: m3d.Manifold, dist: float) -> m3d.Manifold:
        """`solid` grown `dist` outward (a hair-thin offset): each vertex moves so that every face around it moves
        `dist` along its normal, in the least-squares sense (a box corner moves (1, 1, 1) * dist)."""
        mesh = solid.to_mesh64()
        verts = np.asarray(mesh.vert_properties[:, :3], dtype=float)
        tris = np.asarray(mesh.tri_verts, dtype=np.int64)
        if len(tris) == 0:
            return solid
        keys, inv = np.unique(verts, axis=0, return_inverse=True)   # split copies of a vertex move together
        inv = inv.reshape(-1)
        p = verts[tris]
        face_n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        area = np.linalg.norm(face_n, axis=1)
        face_n /= np.maximum(area, 1e-30)[:, None]
        longest = np.max([np.einsum("ij,ij->i", e, e) for e in (p[:, 1] - p[:, 0], p[:, 2] - p[:, 1], p[:, 0] - p[:, 2])], axis=0)
        ok = area > 1e-3 * longest              # needle triangles a boolean leaves have no trustworthy normal
        nn = np.einsum("ij,ik->ijk", face_n, face_n)
        A = np.zeros((len(keys), 3, 3))
        rhs = np.zeros((len(keys), 3))
        for k in range(3):
            a, b = p[:, (k + 1) % 3] - p[:, k], p[:, (k + 2) % 3] - p[:, k]
            cos = np.einsum("ij,ij->i", a, b) / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-30)
            w = np.where(ok, np.arccos(np.clip(cos, -1.0, 1.0)), 0.0)
            np.add.at(A, inv[tris[:, k]], w[:, None, None] * nn)
            np.add.at(rhs, inv[tris[:, k]], w[:, None] * face_n)
        # Damped: nearly parallel faces (a flat face split into slivers) must not send a vertex far off.
        A += 0.01 * np.trace(A, axis1=1, axis2=2)[:, None, None] * np.eye(3) + 1e-30 * np.eye(3)
        move = np.linalg.solve(A, rhs[:, :, None])[:, :, 0]
        move *= dist / np.maximum(1.0, np.linalg.norm(move, axis=1) / 3.0)[:, None]
        real = area > 1e-6 * longest
        for k in range(3):   # a vertex that would pull one of its faces inward (a fin in `solid`) stays put
            inward = real & (np.einsum("ij,ij->i", move[inv[tris[:, k]]], face_n) < 0.0)
            move[inv[tris[inward, k]]] = 0.0

        def push(pts):
            if pts.shape == verts.shape and np.array_equal(pts, verts):   # warp sees the mesh's own vertex order
                return pts + move[inv]
            index = {tuple(k): i for i, k in enumerate(keys)}
            return pts + move[[index[tuple(q)] for q in pts]]
        return solid.warp_batch(push)

    @staticmethod
    def has_needles(solid: m3d.Manifold, thin: float = 1e-3) -> bool:
        """True when a triangle is thinner than `thin` mm (its height over the longest edge): a strip a boolean
        left where two almost-equal walls meet, e.g. a skin of a wall standing above a cut's floor."""
        mesh = solid.to_mesh64()
        tris = np.asarray(mesh.tri_verts, dtype=np.int64)
        if len(tris) == 0:
            return False
        p = np.asarray(mesh.vert_properties[:, :3], dtype=float)[tris]
        sides = [p[:, 1] - p[:, 0], p[:, 2] - p[:, 1], p[:, 0] - p[:, 2]]
        area2 = np.linalg.norm(np.cross(sides[0], -sides[2]), axis=1)     # twice the triangle area
        longest = np.max([np.linalg.norm(e, axis=1) for e in sides], axis=0)
        return bool(np.any(area2 < thin * np.maximum(longest, 1e-30)))

    @staticmethod
    def has_sheets(solid: m3d.Manifold) -> bool:
        """True when two real (non-needle) triangles meet back to back along an edge: a zero-thickness sheet."""
        mesh = solid.to_mesh64()
        tris = np.asarray(mesh.tri_verts, dtype=np.int64)
        if len(tris) == 0:
            return False
        p = np.asarray(mesh.vert_properties[:, :3], dtype=float)[tris]
        n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        area = np.linalg.norm(n, axis=1)
        n /= np.maximum(area, 1e-30)[:, None]
        edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
        owner = np.tile(np.arange(len(tris)), 3)
        order = np.lexsort((edges[:, 1], edges[:, 0]))
        edges, owner = edges[order], owner[order]
        same = np.all(edges[1:] == edges[:-1], axis=1)
        t0, t1 = owner[:-1][same], owner[1:][same]
        real = (area[t0] > 1e-3) & (area[t1] > 1e-3)
        return bool(np.any(real & (np.einsum("ij,ij->i", n[t0], n[t1]) < -0.9)))

    @staticmethod
    def clean_difference(a: m3d.Manifold, b: m3d.Manifold, eps: float = 1e-6) -> m3d.Manifold:
        """a - b without zero-thickness sheets. Where a's surface lies on b's but is tessellated differently
        (a body before and after a join), a plain difference keeps both copies of that surface as volume-less
        sheets fused to the real change; copied by a pattern they become hundreds of hair-thin strips. The
        cut is taken against b grown by `eps`, then the result is grown back 2 eps and clipped to a, so it still
        reaches (a hair into) b and nothing thinner than eps survives."""
        plain = a - b
        if a.is_empty() or b.is_empty() or not CadKernel.has_sheets(plain):
            return plain     # growing moves every face a hair off its plane, which splits edge picking
        cut = a - CadKernel.grown(b, eps)
        if cut.is_empty():
            return cut
        return CadKernel.grown(cut, 2.0 * eps) ^ a

    @staticmethod
    def drop_slivers(solid: m3d.Manifold) -> m3d.Manifold:
        """Removes loose, practically volume-less shells that a boolean can leave where two almost-equal
        surfaces (a mirrored copy of a tessellated curve) fail to coincide."""
        # Forget the mesh relation: after a pattern it can hold ~10^5 runs and decompose() then eats GBs (CI killed).
        solid = solid.as_original()
        try:
            parts = solid.decompose()
        except Exception:
            return solid
        if len(parts) <= 1:
            return solid
        limit = max(1e-5 * max(abs(p.volume()) for p in parts), 1e-3)
        keep = [p for p in parts if p.volume() > limit]
        voids = [p for p in parts if p.volume() < -limit]
        if not keep or len(keep) + len(voids) == len(parts):
            return solid
        # Rebuild from the solid parts and cut the closed inner voids (negative parts) back out, turned right side
        # out. Subtracting the flakes instead leaves them where they lie on the surface: test_mirror_no_fins.
        result = m3d.Manifold.compose(keep) if len(keep) > 1 else keep[0]
        for void in voids:
            mesh = void.to_mesh64()
            tris = np.array(np.asarray(mesh.tri_verts)[:, ::-1], dtype=np.uint64, order="C")   # own copies: a
            verts = np.array(mesh.vert_properties, dtype=np.float64, order="C")              # view is refused
            result -= m3d.Manifold(m3d.Mesh64(vert_properties=verts, tri_verts=tris))
        return result

    @staticmethod
    def round_tool(edge, size: float, kind: str, extend=0.0, size2=None) -> m3d.Manifold:
        """Tool body for a straight or circular edge. `size2`: second chamfer distance (see edge_round_tool);
        wrapped edges only take equal distances."""
        if getattr(edge, "kind", "") == "wrapped":
            from omacad.model.wrapped_edges import wrapped_round_tool
            return wrapped_round_tool(edge, size, kind)
        if getattr(edge, "kind", "line") == "circle":
            return CadKernel.circle_round_tool(edge, size, kind, size2=size2)
        if getattr(edge, "kind", "line") == "loop":
            return CadKernel.loop_round_tool(edge, size, kind, size2=size2)
        return CadKernel.edge_round_tool(edge, size, kind, extend, size2=size2)

    @staticmethod
    def round_cove_tool(edge, radius: float, extend=0.0) -> m3d.Manifold:
        """Cut for a negative fillet: a concave cove, the quarter circle centred on the sharp edge itself, so the
        surface leaves one face a radius from the edge and meets the other a radius away (Lennart #79).

        Supports straight, square edges and full circular rims, the box and cylinder cases. Other edge types
        return an empty tool so the caller can report them as skipped.
        """
        r = abs(float(radius))
        if r <= 1e-6 or not getattr(edge, "convex", False):
            return m3d.Manifold()
        # Local x runs into the solid along the first face, y along the second; the margin lies outside.
        m = 0.05 * r + 1e-3
        arc = [(r * math.cos(ph), r * math.sin(ph)) for ph in np.linspace(0.0, math.pi / 2.0, 33)]
        profile = [(-m, -m), (r, -m), *arc, (-m, r)]
        if getattr(edge, "kind", "") == "line":
            theta = math.acos(float(np.clip(edge.d1 @ edge.d2, -1.0, 1.0)))
            if abs(theta - math.pi / 2.0) > math.radians(2.0):
                return m3d.Manifold()
            t = (edge.p1 - edge.p0) / max(float(np.linalg.norm(edge.p1 - edge.p0)), 1e-12)
            origin = edge.p0.copy()
            ext_start, ext_end = (extend if isinstance(extend, (tuple, list)) else (extend, extend))
            e1 = np.asarray(edge.d1, dtype=float)
            e2 = np.asarray(edge.d2, dtype=float) - float(edge.d2 @ e1) * e1
            e2 /= max(float(np.linalg.norm(e2)), 1e-12)
            if np.cross(e1, e2) @ t < 0:
                t, origin = -t, edge.p1.copy()
                ext_start, ext_end = ext_end, ext_start
            poly = profile
            area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                       for i in range(len(poly)))
            if area < 0:
                poly.reverse()
            length = float(np.linalg.norm(edge.p1 - edge.p0)) + ext_start + ext_end
            solid = m3d.Manifold.extrude(m3d.CrossSection([[list(map(float, q)) for q in poly]]), height=length)
            frame = np.column_stack([e1, e2, t, origin - t * ext_start]).astype(float)
            return solid.transform(frame)
        if getattr(edge, "kind", "") == "circle" and not edge.is_arc:
            R = float(edge.radius)
            # For convex rims, positive local x/y point into the solid.
            poly = [(R + edge.s1 * x, edge.s2 * y) for x, y in profile]
            area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                       for i in range(len(poly)))
            if area < 0:
                poly.reverse()
            if min(p[0] for p in poly) <= 0.0:
                return m3d.Manifold()
            cs = m3d.CrossSection([[list(map(float, p)) for p in poly]])
            if cs.is_empty():
                return m3d.Manifold()
            solid = m3d.Manifold.revolve(cs, circular_segments=max(int(getattr(edge, "nseg", 48)), 24))
            u, v = edge._basis()
            return solid.transform(np.column_stack([u, v, edge.axis, edge.center]).astype(float))
        return m3d.Manifold()

    @staticmethod
    def loop_round_tool(edge, size: float, kind: str, arc_segments: int = 16, size2=None) -> m3d.Manifold:
        """Fillet/chamfer all the way round an outline of straight pieces and arcs: the usual corner
        cross-section swept along the outline (mitred where the direction changes)."""
        P = np.asarray(edge.pts, dtype=float)
        n = np.asarray(edge.n, dtype=float)
        N = len(P)
        r = float(size)
        r2 = r if size2 is None else float(size2)       # chamfer distance up/down the wall
        t = np.roll(P, -1, axis=0) - P                      # segment i goes from point i to point i+1
        t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]
        inw = np.cross(n, t)                                # into the face (it lies on the left)
        prev = np.roll(inw, 1, axis=0)                      # inward normal of the segment ending at point i
        miter = (prev + inw) / (1.0 + np.einsum("ij,ij->i", prev, inw))[:, None]   # length 1/cos(half turn)
        # when the inner outline folds over itself (radius larger than the corner arcs) the tube would
        # intersect itself; then the section is swept piece by piece and the pieces are merged
        inner = P + r * miter
        d_in = np.roll(inner, -1, axis=0) - inner
        folded = bool((np.einsum("ij,ij->i", d_in, t) <= 1e-9).any())
        m = 0.05 * r + 1e-3
        convex = bool(getattr(edge, "convex", True))
        walls = getattr(edge, "walls", None)

        def section(wall, a):   # the wall's normal seen in the section plane (a = into the face, h = along n)
            w2 = None if wall is None else (float(wall @ a), float(wall @ n))
            return CadKernel._loop_section(kind, convex, r, r2, m, arc_segments, w2)

        if walls is not None:   # at each point the mean of the walls of the pieces on either side
            walls = np.asarray(walls, dtype=float)
            at_pts = walls + np.roll(walls, 1, axis=0)
            at_pts /= np.maximum(np.linalg.norm(at_pts, axis=1), 1e-12)[:, None]
        if folded:
            return CadKernel._loop_tool_pieces(P, n, t, inw, walls, section)
        if walls is None:
            secs = [section(None, None)] * N
        else:
            mh = miter / np.linalg.norm(miter, axis=1)[:, None]
            secs = [section(w, a) for w, a in zip(at_pts, mh)]
        M = len(secs[0])
        verts = np.array([P[i] + a * miter[i] + h * n for i in range(N) for a, h in secs[i]], dtype=np.float64)
        tris = []
        for i in range(N):
            j = (i + 1) % N
            for k in range(M):
                k2 = (k + 1) % M
                a, b, c, d = i * M + k, j * M + k, j * M + k2, i * M + k2
                tris += [[a, b, c], [a, c, d]]
        # end caps are not needed: the tube is closed around the loop. Fix orientation by the signed volume.
        tr = np.array(tris, dtype=np.uint32)
        vol = np.einsum("ij,ij->i", verts[tr[:, 0]], np.cross(verts[tr[:, 1]], verts[tr[:, 2]])).sum() / 6.0
        if vol < 0:
            tr = tr[:, ::-1]
        # Keep the original outline coordinates through the cut, especially where the tool meets the wall.
        mesh = m3d.Mesh64(vert_properties=verts, tri_verts=np.ascontiguousarray(tr, dtype=np.uint64))
        solid = m3d.Manifold(mesh)
        if solid.is_empty():
            raise ValueError("Could not build the rounding for this outline.")
        return solid

    @staticmethod
    def _loop_section(kind, convex, r, r2, m, arc_segments, wall=None) -> list:
        """The corner cross-section of a loop: a = into the face, h = along the face's outward normal, the corner
        at the origin. `wall` = the wall's outward normal in that plane ((-1, 0) under a rim, (1, 0) for a square
        wall rising from the face). A convex rim cuts away the corner, a foot (not convex) adds material in it;
        both reach a margin m past the faces into the empty side (or into the material, for a foot)."""
        wa, wh = wall or ((-1.0, 0.0) if convex else (1.0, 0.0))
        k = math.hypot(wa, wh)
        wa, wh = wa / k, wh / k
        d = np.array([-wh, wa])                 # along the wall away from the corner
        s = 1.0 if convex else -1.0             # the margin's side: outside the material, or into the wall
        O = np.array([(s * m - wh * s * m) / wa, s * m])   # corner of the margins along face and wall
        wn = np.array([wa, wh]) * s
        if kind == "chamfer":
            pts = [O, (r, s * m), (r, 0.0), d * r2, d * r2 + wn * m]
        else:
            half = 0.5 * math.acos(float(np.clip(d[0], -1.0, 1.0)))   # half the angle between face and wall
            reach = r / math.tan(half)
            c = np.array([reach, -s * r]) if convex else np.array([reach, r])
            t1, t2 = np.array([reach, 0.0]), d * reach
            a0 = math.atan2(*(t1 - c)[::-1])
            a1 = a0 + math.remainder(math.atan2(*(t2 - c)[::-1]) - a0, 2.0 * math.pi)
            arc = [c + r * np.array([math.cos(ph), math.sin(ph)]) for ph in np.linspace(a0, a1, arc_segments + 1)]
            pts = [O, (reach, s * m)] + arc + [t2 + wn * m]
        return [(float(a), float(h)) for a, h in pts]

    @staticmethod
    def foot_fill_tool(body: m3d.Manifold, edge, size: float, kind: str) -> m3d.Manifold:
        """Filling tool for the foot of a wall (a LoopEdge with convex=False). The fillet lies on the face next to
        the wall, so it needs flat face under it. Where an earlier rounding has already cut that face away (a
        shelf narrower than the radius) the tool would hang over the cut like a lip; the radius is then reduced
        to the widest one that still rests on the face, so the fillet runs out smoothly into the other rounding."""
        n = np.asarray(edge.n, dtype=float)
        u = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
        u /= np.linalg.norm(u)
        basis = np.column_stack([u, np.cross(n, u), n])
        below = m3d.Manifold.cube((1e5, 1e5, 1e5), True).transform(
            np.column_stack([basis, np.asarray(edge.pts[0], dtype=float) - n * 5e4]))   # everything under the face plane

        def hangs(tool) -> bool:
            return ((tool ^ below) - body).volume() > 1e-6 * max(float(size), 1.0) ** 3

        tool = CadKernel.loop_round_tool(edge, size, kind)
        if not hangs(tool):
            return tool
        lo, hi = 0.0, float(size)
        for _ in range(12):
            mid = (lo + hi) / 2.0
            if hangs(CadKernel.loop_round_tool(edge, mid, kind)):
                hi = mid
            else:
                lo = mid
        return CadKernel.loop_round_tool(edge, lo, kind) if lo > 1e-3 else m3d.Manifold()

    @staticmethod
    def _loop_tool_pieces(P, n, t, inw, walls, section) -> m3d.Manifold:
        """The corner cross-section extruded along every straight piece of the outline (arcs are many short
        pieces), merged. Where the radius is larger than a corner arc the pieces overlap and cut a dome.
        Along leaning walls (`walls` per piece, see LoopEdge) the section follows the wall point by point."""
        from omacad.model.sweep_geometry import ring_solid
        N = len(P)
        # join consecutive pieces that run in the same direction
        starts = [i for i in range(N) if float(t[i] @ t[i - 1]) < 1.0 - 1e-9]
        if not starts:
            starts = [0]
        def ccw(sec):
            poly = [list(map(float, q)) for q in sec]
            area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
            return poly[::-1] if area < 0 else poly

        def wall_at(j, i0, i1):   # a piece's end takes its own wall, not the mean with the next piece round the corner
            if walls is None:
                return None
            if j == i0 or j == i1:
                return walls[i0 if j == i0 else (i1 - 1) % N]
            w = walls[j - 1] + walls[j]
            return w / np.linalg.norm(w)

        bisector = lambda i: (inw[i - 1] + inw[i]) / max(float(np.linalg.norm(inw[i - 1] + inw[i])), 1e-12)
        cs = {i: m3d.CrossSection([ccw(section(None if walls is None else (walls[i - 1] + walls[i]) / 2.0, bisector(i)))])
              for i in starts}
        pieces = []
        for k, i0 in enumerate(starts):
            i1 = starts[(k + 1) % len(starts)]
            idx = i0
            length = 0.0
            while True:
                length += float(np.linalg.norm(P[(idx + 1) % N] - P[idx]))
                idx = (idx + 1) % N
                if idx == i1:
                    break
            if length < 1e-9:
                continue
            # a hair past both ends, so neighbouring pieces overlap instead of touching face to face (that left
            # zero-thickness flaps in the result)
            eps = 1e-3 + 1e-4 * length
            if walls is None:
                solid = m3d.Manifold.extrude(cs[i0], height=length + 2.0 * eps).translate((0.0, 0.0, -eps))
                pieces.append(solid.transform(np.column_stack([inw[i0], n, t[i0], P[i0]]).astype(float)))
                continue
            js = [i0]
            while js[-1] != i1:
                js.append((js[-1] + 1) % N)
            secs = [np.array(ccw(section(wall_at(j, i0, i1), inw[i0]))) for j in js]
            rings = [P[j] + q[:, :1] * inw[i0] + q[:, 1:] * n + (-eps if k == 0 else eps if k == len(js) - 1 else 0.0) * t[i0]
                     for k, (j, q) in enumerate(zip(js, secs))]
            pieces.append(ring_solid(rings, secs[0], secs[-1]))
        pieces += CadKernel._loop_joints(P, n, t, inw, starts, cs)
        result = m3d.Manifold.batch_boolean(pieces, m3d.OpType.Add)
        if result.is_empty():
            raise ValueError("Could not build the rounding for this outline.")
        return result

    @staticmethod
    def _loop_joints(P, n, t, inw, starts, cs) -> list:
        """Where the outline turns away from the face (a right turn: the inside of a concave arc), two straight
        pieces leave a wedge between them on the face side that nothing cuts: a row of teeth along the arc
        (Björn #78). Fill each with the face-side half of the section turned about the corner, which is exactly
        what a smooth sweep would have covered there."""
        joints = []
        for i in starts:
            size = 4.0 * max(abs(x) for poly in cs[i].to_polygons() for p in poly for x in p) + 1.0
            half = cs[i] ^ m3d.CrossSection.square((size, 2.0 * size)).translate((0.0, -size))   # a >= 0: the face side
            if half.is_empty():
                continue
            turn = float(np.cross(t[i - 1], t[i]) @ n)
            cos = float(np.clip(t[i - 1] @ t[i], -1.0, 1.0))
            if turn >= -1e-9:
                continue                     # a left turn: the pieces overlap on the face side already
            angle = math.degrees(math.acos(cos))
            if angle < 1e-6:
                continue
            e1 = inw[i - 1]
            e2 = inw[i] - (inw[i] @ e1) * e1
            if float(np.linalg.norm(e2)) < 1e-12:
                continue
            e2 = e2 / np.linalg.norm(e2)
            up = np.cross(e1, e2)            # right-handed frame; the section's height runs along n
            sec = half if float(up @ n) > 0 else half.mirror((0.0, 1.0))
            # a little past both pieces' end faces: faces that coincide exactly leave paper-thin flaps
            over = min(0.5, 0.25 * angle + 0.05)
            sweep = angle + 2.0 * over
            # circular_segments counts a whole turn: enough that this small angle still gets a step per 5°
            wedge = m3d.Manifold.revolve(sec, int(math.ceil(360.0 / min(sweep, 5.0))) + 1, sweep)
            wedge = wedge.rotate((0.0, 0.0, -over))
            joints.append(wedge.transform(np.column_stack([e1, e2, up, P[i]]).astype(float)))
        return joints

    @staticmethod
    def circle_round_tool(edge, size: float, kind: str, arc_segments: int = 24, reach=(0.0, 0.0), size2=None) -> m3d.Manifold:
        """Same cross-section as a straight edge (a right angle between the flat face and the cylinder
        wall) revolved around the circle's axis. `size2`: chamfer distance along the wall."""
        R = float(edge.radius)
        # The wall of the original solid is a polygon whose chords sag inside the radius; a tool that
        # only reached R would leave a hair-thin lip along the old edge (visible as a leftover line).
        # So the tool also covers a margin on the empty side of the corner (harmless for a union too:
        # there it overlaps existing material).
        sag = R * (1.0 - math.cos(math.pi / max(int(getattr(edge, "nseg", 48)), 6)))
        m = 2.0 * sag + 1e-3 * max(1.0, R)
        if kind == "chamfer":
            s = float(size)
            s2 = s if size2 is None else float(size2)
            local = [(-m, -m), (s, -m), (s, 0.0), (0.0, s2), (-m, s2)]
        else:
            r = float(size)
            # tangent points A=(r,0) on the face and B=(0,r) on the wall; the arc is centred at (r,r)
            # and bulges towards the corner. Walk it from A to B (interior points only).
            arc = []
            for k in range(1, arc_segments):
                beta = (math.pi / 2) * (1.0 - k / arc_segments)
                arc.append((r - r * math.cos(beta), r - r * math.sin(beta)))
            local = [(-m, -m), (r, -m), (r, 0.0)] + arc + [(0.0, r), (-m, r)]
        # local x runs along the face (away from the edge), local y along the wall (away from the face)
        poly = [(R + edge.s1 * x, edge.s2 * y) for x, y in local]
        area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))
        if area < 0:
            poly.reverse()
        cs = m3d.CrossSection([[list(map(float, q)) for q in poly]])
        if min(q[0] for q in poly) < 0:   # a round bigger than the radius: keep the part beside the axis
            half = m3d.CrossSection([[(0.0, -1e6), (1e6, -1e6), (1e6, 1e6), (0.0, 1e6)]])
            cs = cs ^ half
        if cs.is_empty():
            return m3d.Manifold()
        nseg = max(int(getattr(edge, "nseg", 48)), 12)   # same segment count as the wall so vertices line up
        if edge.is_arc:
            # `reach`: how far (radians) the tool runs past each end, where the arc ends in open space
            a0, sweep = edge.a0 - reach[0], edge.sweep + reach[0] + reach[1]
            solid = m3d.Manifold.revolve(cs, circular_segments=nseg, revolve_degrees=math.degrees(sweep))
            solid = solid.rotate((0.0, 0.0, math.degrees(a0)))
        else:
            solid = m3d.Manifold.revolve(cs, circular_segments=nseg)
        u, v = edge._basis()
        mat = np.column_stack([u, v, edge.axis, edge.center]).astype(float)
        return solid.transform(mat)

    @staticmethod
    def boolean_union(a: m3d.Manifold, b: m3d.Manifold) -> m3d.Manifold:
        """Boolean Join (A ∪ B)"""
        return a + b

    @staticmethod
    def boolean_difference(target: m3d.Manifold, tool: m3d.Manifold) -> m3d.Manifold:
        r"""Boolean Cut (Target \ Tool)"""
        return target - tool

    @staticmethod
    def boolean_intersection(a: m3d.Manifold, b: m3d.Manifold) -> m3d.Manifold:
        """Boolean Intersect (A ∩ B)"""
        return a ^ b

    @staticmethod
    def boolean_op(target: m3d.Manifold, tool: m3d.Manifold, operation: str) -> m3d.Manifold:
        """Combine: "join", "cut" or "intersect" the tool into the target."""
        ops = {"join": CadKernel.boolean_union, "cut": CadKernel.boolean_difference,
               "intersect": CadKernel.boolean_intersection}
        return ops[operation](target, tool)

    @staticmethod
    def _face_normals(v, f):
        cross_prod = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        lengths = np.linalg.norm(cross_prod, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        return cross_prod / lengths

    @staticmethod
    def thin_triangles(manifold: m3d.Manifold, v, f, thickness: float):
        """Mask of triangles with less than `thickness` of material behind them: a ray cast inward from the
        triangle leaves the solid that soon, or never was inside it (its twin lies on top of it, so the first
        thing met is an entry). The difference of two states of a body is full of such zero-volume skins wherever
        the two meshes share a surface but split it into other triangles (a thread's twisted quads), and they show
        as stripes over the model. The ray is tilted a little so that it does not run exactly through the
        vertices and edges of a symmetric mesh, where hits are missed."""
        normals, centres = CadKernel._face_normals(v, f), v[f].mean(axis=1)
        reach = float(np.linalg.norm(np.ptp(v, axis=0))) + 1.0
        tilt = np.array([0.0123, 0.0071, 0.0037])
        thin = np.zeros(len(f), dtype=bool)
        for i, (c, n) in enumerate(zip(centres, normals)):
            if not n.any():                          # no area: nothing to draw either
                thin[i] = True
                continue
            d = tilt - n
            d /= np.linalg.norm(d)
            start = c + d * 1e-4                    # past the triangle itself (float precision)
            exit_at = CadKernel._first_exit(manifold.ray_cast(tuple(start), tuple(start + d * reach)), d, reach)
            thin[i] = exit_at is None or exit_at < thickness
        return thin

    @staticmethod
    def _first_exit(hits, direction, reach: float):
        """Distance to where a ray leaves the solid, None if it first enters it (it started outside) or meets
        nothing. Hits at the same distance are taken together, so that a skin of zero thickness on the way (an
        entry and an exit at once) is passed through."""
        k = 0
        while k < len(hits):
            at = hits[k].distance
            net = 0
            while k < len(hits) and (hits[k].distance - at) * reach < 1e-6:
                net += 1 if float(np.dot(hits[k].normal, direction)) > 0 else -1
                k += 1
            if net:
                return at * reach if net > 0 else None
        return None

    @staticmethod
    def _flat_triangles(v, f, smooth_below_deg: float = 30.0, coplanar_deg: float = 0.5):
        """Mask of triangles in a flat patch (triangles joined edge to edge at under `coplanar_deg`) that is
        walled in by sharp edges in two different directions, like a box side. Smooth vertex normals must not
        tilt them: a wall that touches a curved surface at a shallow angle (a twisted extrude on a box) showed
        dark fans on the flat wall. A strip of a cylinder wall has sharp edges in one direction only (its rim)."""
        tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
        angles, adj = tm.face_adjacency_angles, tm.face_adjacency
        # a needle triangle (boolean/Shell leftover) has a meaningless normal: its "sharp" edges must not wall in
        # the strips of a fillet beside it, or they are shaded flat (#213)
        diag = float(np.linalg.norm(np.ptp(v, axis=0))) if len(v) else 1.0
        areas = tm.area_faces
        solid = (areas[adj[:, 0]] > 1e-7 * diag * diag) & (areas[adj[:, 1]] > 1e-7 * diag * diag)
        from omacad import viewport_accel
        if viewport_accel.backend_name() == "rust":
            sharp = (angles >= np.radians(smooth_below_deg)) & solid
            edges = tm.face_adjacency_edges[sharp]
            diffs = v[edges[:, 1]] - v[edges[:, 0]]
            norms = np.linalg.norm(diffs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return viewport_accel.flat_patch_mask(len(f), adj[angles < np.radians(coplanar_deg)], adj[sharp], diffs / norms)
        parent = np.arange(len(f))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for a, b in adj[angles < np.radians(coplanar_deg)]:
            parent[root(a)] = root(b)
        sharp = (angles >= np.radians(smooth_below_deg)) & solid
        directions = {}          # patch -> first sharp edge direction
        flat_roots = set()
        edges = tm.face_adjacency_edges[sharp]
        diffs = v[edges[:, 1]] - v[edges[:, 0]]
        norms = np.linalg.norm(diffs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        d_vec = diffs / norms
        for (a, b), d in zip(adj[sharp], d_vec):
            for patch in (root(a), root(b)):
                first = directions.get(patch)
                if first is None:
                    directions[patch] = d
                else:
                    # Inline cross-product norm squared: avoids expensive numpy dispatch per edge
                    cx = first[1] * d[2] - first[2] * d[1]
                    cy = first[2] * d[0] - first[0] * d[2]
                    cz = first[0] * d[1] - first[1] * d[0]
                    if (cx * cx + cy * cy + cz * cz) > 0.01:
                        flat_roots.add(patch)
        return np.array([root(i) in flat_roots for i in range(len(f))], dtype=bool)

    WIDE_FLAT_RATIO = 4.0       # a flat patch this many times wider than every smooth neighbour patch is a face

    @staticmethod
    def _patches(v, f, smooth_below_deg: float = 30.0, coplanar_deg: float = 0.5):
        """Coplanar patches of a mesh (triangles joined edge to edge at under `coplanar_deg`): per triangle its patch
        `inv`; per patch `planar` (every triangle within `coplanar_deg` of the patch normal) and `width` (2 * std of
        its corners along the minor in-plane axis); `pa`/`pb` the pairs of patches meeting smoothly
        (under `smooth_below_deg`) where neither is a needle leftover of a boolean/Shell (narrower than
        SLIVER_MIN_WIDTH): a fillet strip whose only smooth neighbours were such slivers counted as a wide flat
        face and was shaded flat, a band per facet (#213)."""
        from omacad.model.faces_topology import SLIVER_MIN_WIDTH
        tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
        angles, adj = tm.face_adjacency_angles, tm.face_adjacency
        n_f = len(f)
        # coplanar patches by label propagation (vectorised union-find)
        join = adj[angles < np.radians(coplanar_deg)]
        label = np.arange(n_f)
        if len(join):
            while True:
                low = np.minimum(label[join[:, 0]], label[join[:, 1]])
                new = label.copy()
                np.minimum.at(new, join[:, 0], low)
                np.minimum.at(new, join[:, 1], low)
                new = new[new]
                if np.array_equal(new, label):
                    break
                label = new
        roots, inv = np.unique(label, return_inverse=True)
        k = len(roots)
        normals = tm.face_normals
        area = tm.area_faces
        mean_n = np.zeros((k, 3))
        np.add.at(mean_n, inv, normals * area[:, None])
        mean_n /= np.maximum(np.linalg.norm(mean_n, axis=1, keepdims=True), 1e-12)
        planar = np.ones(k, dtype=bool)
        np.logical_and.at(planar, inv, (normals * mean_n[inv]).sum(1) > np.cos(np.radians(coplanar_deg)))
        w = np.repeat(area[:, None] / 3.0, 3, axis=1).ravel()
        pts = v[f].reshape(-1, 3)
        pin = np.repeat(inv, 3)
        tot = np.maximum(np.bincount(pin, weights=w, minlength=k), 1e-18)
        mu = np.stack([np.bincount(pin, weights=w * pts[:, i], minlength=k) for i in range(3)], 1) / tot[:, None]
        d = pts - mu[pin]
        cov = np.zeros((k, 3, 3))
        for i in range(3):
            for j in range(i, 3):
                cov[:, i, j] = cov[:, j, i] = np.bincount(pin, weights=w * d[:, i] * d[:, j], minlength=k) / tot
        eig = np.linalg.eigvalsh(cov)                          # ascending: [~0 normal, minor, major]
        width = 2.0 * np.sqrt(np.maximum(eig[:, 1], 0.0))
        smooth = (angles < np.radians(smooth_below_deg)) & (inv[adj[:, 0]] != inv[adj[:, 1]])
        pa, pb = inv[adj[smooth, 0]], inv[adj[smooth, 1]]
        thin = width < SLIVER_MIN_WIDTH
        real = ~thin[pa] & ~thin[pb]
        # patches that meet only across a needle still meet: bridge each sliver to the real patches around it, at any
        # angle (a needle's own normal means nothing; whoever uses the pairs compares the real patches' normals)
        bridge_a, bridge_b = [], []
        qa, qb = inv[adj[:, 0]], inv[adj[:, 1]]
        touch = np.r_[np.c_[qa, qb], np.c_[qb, qa]]
        touch = touch[thin[touch[:, 0]] & ~thin[touch[:, 1]]]
        if len(touch):
            touch = np.unique(touch[:, 0] * np.int64(k) + touch[:, 1])               # sorted (sliver, patch) pairs
            touch = np.c_[touch // k, touch % k]
            cuts = np.flatnonzero(np.diff(touch[:, 0])) + 1
            sizes = np.diff(np.r_[0, cuts, len(touch)])
            for size in np.unique(sizes):
                if not 1 < size <= 32:
                    continue
                starts = np.r_[0, cuts][sizes == size]
                ia, ib = np.triu_indices(size, 1)
                bridge_a.append(touch[(starts[:, None] + ia).ravel(), 1])
                bridge_b.append(touch[(starts[:, None] + ib).ravel(), 1])
        if bridge_a:
            ba, bb = np.concatenate(bridge_a), np.concatenate(bridge_b)
            keep = (mean_n[ba] * mean_n[bb]).sum(1) > np.cos(np.radians(smooth_below_deg))
            bridge_a, bridge_b = [ba[keep]], [bb[keep]]
        pa = np.concatenate([pa[real], *bridge_a]).astype(np.int64)
        pb = np.concatenate([pb[real], *bridge_b]).astype(np.int64)
        return dict(tm=tm, inv=inv, k=k, planar=planar, width=width, pa=pa, pb=pb, normal=mean_n)

    @staticmethod
    def _wide_flat_triangles(v, f, smooth_below_deg: float = 30.0, coplanar_deg: float = 0.5, patches=None):
        """Mask of triangles in a truly flat patch that is much wider than each patch it meets smoothly: a box side
        or bottom between rounded edges. Smooth vertex normals tilted such a face by several degrees where it meets
        the fillets, and the view's Phong smoothing then bulged the whole face up to 0.6 mm, in front of the hover
        and selection highlights (#204). A cylinder strip meets strips of the same width and keeps smooth normals;
        a fine curved mesh chained into one "coplanar" patch fails the planarity test."""
        if len(f) == 0:
            return np.zeros(0, dtype=bool)
        p = patches or CadKernel._patches(v, f, smooth_below_deg, coplanar_deg)
        k, width, pa, pb = p["k"], p["width"], p["pa"], p["pb"]
        neighbour = np.zeros(k)
        np.maximum.at(neighbour, pa, width[pb])
        np.maximum.at(neighbour, pb, width[pa])
        has_neighbour = np.zeros(k, dtype=bool)
        has_neighbour[pa] = True
        has_neighbour[pb] = True
        wide = p["planar"] & has_neighbour & (width > CadKernel.WIDE_FLAT_RATIO * neighbour)
        return wide[p["inv"]]

    STRIP_WIDTH_RATIO = 2.0     # the facets of one curved surface are about equally wide
    WELD_MM = 1e-2              # corners within half of this (per axis) are one vertex for smooth normals

    @staticmethod
    def _weld(v, grid: float):
        """Vertex labels where corners closer than grid/2 on every axis share a label (eight shifted grids, so no pair
        is split by a cell boundary; nothing further apart than grid * sqrt(3) is joined)."""
        n = len(v)
        label = np.arange(n)
        q = np.asarray(v, dtype=np.float64) / grid
        pairs = []
        lo = np.floor(q.min(0)) - 1
        span = (np.floor(q.max(0)) - lo + 2).astype(np.int64)
        for shift in np.array(np.meshgrid([0, 0.5], [0, 0.5], [0, 0.5])).T.reshape(-1, 3):
            ijk = (np.floor(q + shift) - lo).astype(np.int64)
            key = (ijk[:, 0] * span[1] + ijk[:, 1]) * span[2] + ijk[:, 2]
            _u, cell = np.unique(key, return_inverse=True)
            cell = cell.ravel()
            first = np.full(cell.max() + 1, -1)
            first[cell[::-1]] = np.arange(n)[::-1]
            pairs.append(np.c_[np.arange(n), first[cell]])
        pairs = np.concatenate(pairs)
        pairs = pairs[pairs[:, 0] != pairs[:, 1]]
        while len(pairs):
            low = np.minimum(label[pairs[:, 0]], label[pairs[:, 1]])
            new = label.copy()
            np.minimum.at(new, pairs[:, 0], low)
            np.minimum.at(new, pairs[:, 1], low)
            new = new[new]
            if np.array_equal(new, label):
                break
            label = new
        return np.unique(label, return_inverse=True)[1].ravel()

    @staticmethod
    def _strip_normals(v, f, normals, smooth_below_deg: float = 30.0):
        """Smooth corner normals for the facets of a curved surface (#213). Manifold's calculate_normals keeps
        "flat faces of three or more triangles" flat, and a Shell leaves the strips of a round wall split, joined
        through needle triangles, with T-junctions and corners a few micrometres apart: the wall showed a band per
        facet. On the welded mesh (needles gone) a strip is a planar patch with smooth neighbour patches of about
        its width on both sides (a flat face beside a fillet is much wider, a narrow flat rim has one at most). Each strip corner gets the mean of its own
        strip's normal and those of the strips beside it, weighted by where the corner lies across the strip
        (a T-junction has no shared vertex); needles along a strip take the strips' normal at their corners."""
        if len(f) == 0:
            return normals
        from omacad.model.faces_topology import SLIVER_MIN_WIDTH
        v = np.asarray(v, dtype=np.float64)
        weld = CadKernel._weld(v, CadKernel.WELD_MM)
        fw = weld[f]
        p0, p1, p2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cross = np.cross(p1 - p0, p2 - p0)
        live = (fw[:, 0] != fw[:, 1]) & (fw[:, 1] != fw[:, 2]) & (fw[:, 0] != fw[:, 2]) \
            & (np.linalg.norm(cross, axis=1) > 1e-9)
        if not live.any():
            return normals
        rep = np.zeros((weld.max() + 1, 3))
        rep[weld] = v
        lf = np.flatnonzero(live)
        try:
            p = CadKernel._patches(rep, fw[lf], smooth_below_deg)
        except Exception:
            return normals
        width, pa, pb, inv, pn, k = p["width"], p["pa"], p["pb"], p["inv"], p["normal"], p["k"]
        ratio = np.maximum(width[pa], width[pb]) / np.maximum(np.minimum(width[pa], width[pb]), 1e-12)
        similar = (ratio < CadKernel.STRIP_WIDTH_RATIO) & p["planar"][pa] & p["planar"][pb]
        links = np.r_[np.c_[pa[similar], pb[similar]], np.c_[pb[similar], pa[similar]]]
        if not len(links):
            return normals
        links = np.unique(links[:, 0] * np.int64(k) + links[:, 1])
        links = np.c_[links // k, links % k]                                     # (patch, neighbour), sorted
        # across each patch: minor in-plane axis of its distinct corners, unweighted (area weights count the corners
        # on a strip's diagonal twice and tilt the axis toward its length)
        nv = np.int64(weld.max() + 1)
        pv = np.unique(np.repeat(inv, 3).astype(np.int64) * nv + fw[lf].ravel())
        pv = np.c_[pv // nv, pv % nv]
        cnt = np.maximum(np.bincount(pv[:, 0], minlength=k), 1)
        pts = rep[pv[:, 1]]
        centre = np.stack([np.bincount(pv[:, 0], weights=pts[:, i], minlength=k) for i in range(3)], 1) / cnt[:, None]
        dd = pts - centre[pv[:, 0]]
        cov = np.zeros((k, 3, 3))
        for i in range(3):
            for j in range(i, 3):
                cov[:, i, j] = cov[:, j, i] = np.bincount(pv[:, 0], weights=dd[:, i] * dd[:, j], minlength=k) / cnt
        axis = np.linalg.eigh(cov)[1][:, :, 1]
        proj = ((v[f[lf]] - centre[inv][:, None, :]) * axis[inv][:, None, :]).sum(2)     # (live tris, 3)
        lo = np.full(k, np.inf)
        hi = np.full(k, -np.inf)
        np.minimum.at(lo, inv, proj.min(1))
        np.maximum.at(hi, inv, proj.max(1))
        span = np.maximum(hi - lo, 1e-12)
        side = ((centre[links[:, 1]] - centre[links[:, 0]]) * axis[links[:, 0]]).sum(1)
        beside = np.abs(side) > 0.25 * span[links[:, 0]]                           # not a patch above or below
        links, side = links[beside], side[beside]
        # a strip has strips of its width on both sides; a narrow flat rim beside a fillet has one at most
        plus = np.zeros(k, dtype=bool)
        minus = np.zeros(k, dtype=bool)
        plus[links[side > 0, 0]] = True
        minus[links[side < 0, 0]] = True
        strip = plus & minus
        patch_of = np.full(len(f), -1)
        patch_of[lf] = inv
        tri = np.zeros(len(f), dtype=bool)
        tri[lf] = strip[inv]
        if not tri.any():
            return normals
        out = normals.reshape(-1, 3, 3).copy()
        # strip corners: own patch normal + each neighbour beside it, weighted by where the corner lies across the
        # strip: one at the edge toward that neighbour, none at the far edge (a T-junction in the middle of a
        # strip, which shares no vertex with anyone, gets half of each side)
        c_f, c_k = np.nonzero(np.repeat(tri[:, None], 3, axis=1))
        x = v[f[c_f, c_k]]
        own = patch_of[c_f]
        acc = pn[own].copy()
        t = np.clip((((x - centre[own]) * axis[own]).sum(1) - lo[own]) / span[own], 0.0, 1.0)   # 0 at lo, 1 at hi
        start = np.searchsorted(links[:, 0], own, side="left")
        count = np.searchsorted(links[:, 0], own, side="right") - start
        ci = np.repeat(np.arange(len(own)), count)
        li = np.repeat(start - np.cumsum(np.r_[0, count[:-1]]), count) + np.arange(int(count.sum()))
        weight = np.where(side[li] > 0, t[ci], 1.0 - t[ci])
        np.add.at(acc, ci, pn[links[li, 1]] * weight[:, None])
        out[c_f, c_k] = acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)
        # needles along a strip: the strip normal at the same welded vertex
        e = np.stack([np.linalg.norm(p1 - p0, axis=1), np.linalg.norm(p2 - p1, axis=1),
                      np.linalg.norm(p0 - p2, axis=1)], 1)
        needle = ~tri & (np.linalg.norm(cross, axis=1) / np.maximum(e.max(1), 1e-18) < SLIVER_MIN_WIDTH)
        needle &= (patch_of < 0) | (width[np.maximum(patch_of, 0)] < SLIVER_MIN_WIDTH)   # not part of a real face
        if needle.any():
            sums = np.zeros((weld.max() + 1, 3))
            np.add.at(sums, fw[c_f, c_k], out[c_f, c_k])
            n_f, n_k = np.nonzero(np.repeat(needle[:, None], 3, axis=1))
            got = sums[fw[n_f, n_k]]
            length = np.linalg.norm(got, axis=1)
            got = got / np.maximum(length, 1e-12)[:, None]
            # only where the strip continues the surface the needle lies in (not a strip around a sharp corner)
            ok = (length > 1e-12) & ((got * out[n_f, n_k]).sum(1) > np.cos(np.radians(smooth_below_deg)))
            out[n_f[ok], n_k[ok]] = got[ok]
        return out.reshape(-1, 3)

    @staticmethod
    def _shaded_triangles(manifold: m3d.Manifold, v, f, smooth_below_deg: float = 30.0, smooth: bool = True):
        """Unrolled triangle corners and their normals. Curved surfaces are shaded smooth (vertex normals shared
        across edges flatter than `smooth_below_deg`, sharp CAD edges stay crisp): with one flat normal per triangle
        the irregular triangles of a wrapped emboss floor showed as blotches and fan streaks (Björn #61).
        `smooth=False` gives every triangle its own normal, for a preview of a mesh too big to smooth while dragging."""
        if not smooth:
            return CadKernel._flat_shaded(v, f)
        try:
            mesh = manifold.calculate_normals(0, smooth_below_deg).to_mesh()
            props = np.asarray(mesh.vert_properties)
            tris = np.asarray(mesh.tri_verts)
            if props.shape[1] >= 6 and len(tris) == len(f):
                normals = props[tris].reshape(-1, props.shape[1])[:, 3:6]
                length = np.linalg.norm(normals, axis=1, keepdims=True)
                # a few corners of degenerate (needle) triangles get no normal from Manifold, e.g. after a Shell:
                # they take their triangle's own normal instead of the whole body falling back to flat shading,
                # which showed every facet of a fillet as a band (#213)
                bad = ~(np.all(np.isfinite(normals), axis=1) & (length[:, 0] > 0.5))
                if bad.any() and bad.mean() < 0.05:
                    face = np.repeat(CadKernel._face_normals(v, f), 3, axis=0)
                    face_len = np.linalg.norm(face, axis=1)
                    face[face_len < 0.5] = (0.0, 0.0, 1.0)
                    normals = np.where(bad[:, None], face, normals)
                    length = np.where(bad[:, None], 1.0, length)
                if np.all(np.isfinite(normals)) and np.all(length > 0.5):
                    normals = normals / length
                    normals = CadKernel._strip_normals(v, f, normals, smooth_below_deg)
                    flat = CadKernel._flat_triangles(v, f) | CadKernel._wide_flat_triangles(v, f, smooth_below_deg)
                    if flat.any():
                        normals = normals.reshape(-1, 3, 3)
                        normals[flat] = CadKernel._face_normals(v, f)[flat][:, None, :]
                        normals = normals.reshape(-1, 3)
                    return (props[tris].reshape(-1, props.shape[1])[:, :3].astype(np.float32),
                            normals.astype(np.float32))
        except Exception as e:      # fall back to flat shading, which is always right, and say why
            from omacad import applog
            applog.log("ERROR", f"smooth normals: {e!r}")
        return CadKernel._flat_shaded(v, f)

    @staticmethod
    def _flat_shaded(v, f):
        """Unrolled triangle corners, each triangle with its own normal."""
        v0, v1, v2 = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cross_prod = np.cross(v1 - v0, v2 - v0)
        lengths = np.linalg.norm(cross_prod, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        return v[f].reshape(-1, 3).astype(np.float32), np.repeat(cross_prod / lengths, 3, axis=0).astype(np.float32)

    @staticmethod
    def extract_render_mesh(manifold: m3d.Manifold, edge_angle_threshold_deg: float = SHARP_EDGE_DEG,
                            min_thickness: float = 0.0, smooth: bool = True) -> RenderMesh:
        """
        Extract triangle buffers and sharp CAD feature edges for OpenGL rendering. With `min_thickness`,
        material thinner than that is left out (see `thin_triangles`).
        """
        mesh = manifold.to_mesh()
        v = mesh.vert_properties[:, :3]
        f = mesh.tri_verts
        keep = ~CadKernel.thin_triangles(manifold, v, f, min_thickness) if min_thickness > 0 and len(f) else None

        if len(f) == 0:
            empty = np.zeros((0, 3), dtype=np.float32)
            return RenderMesh(
                vertices=empty,
                normals=empty,
                sharp_lines=empty,
                bounds_min=np.zeros(3, dtype=np.float32),
                bounds_max=np.zeros(3, dtype=np.float32),
                center=np.zeros(3, dtype=np.float32)
            )

        tri_verts, tri_normals = CadKernel._shaded_triangles(manifold, v, f, smooth=smooth)
        if keep is not None:
            tri_verts = tri_verts.reshape(-1, 3, 3)[keep].reshape(-1, 3)
            tri_normals = tri_normals.reshape(-1, 3, 3)[keep].reshape(-1, 3)

        # Extract sharp CAD edges using trimesh
        try:
            tm = trimesh.Trimesh(vertices=v, faces=f, process=False)
            rad_thresh = np.radians(edge_angle_threshold_deg)
            sharp_mask = tm.face_adjacency_angles > rad_thresh
            # booleans on tessellated curves leave zero-area triangles whose normals are meaningless:
            # they would show up as stray "sharp" lines across smooth surfaces
            diag = float(np.linalg.norm(np.ptp(v, axis=0))) or 1.0
            areas = tm.area_faces
            fa = tm.face_adjacency
            sharp_mask &= (areas[fa[:, 0]] > 1e-7 * diag * diag) & (areas[fa[:, 1]] > 1e-7 * diag * diag)
            if keep is not None:
                sharp_mask &= keep[fa[:, 0]] & keep[fa[:, 1]]
            sharp_edges = tm.face_adjacency_edges[sharp_mask]
            
            # Also include single-face boundary edges (if open mesh)
            if len(tm.faces) > 0 and len(tm.face_adjacency) < len(tm.edges_unique):
                boundary_edges = tm.edges_unique[tm.edges_unique_inverse != 2] if hasattr(tm, 'edges_unique_inverse') else []
                if len(boundary_edges) > 0:
                    sharp_edges = np.vstack([sharp_edges, boundary_edges])

            if len(sharp_edges) > 0:
                sharp_lines = v[sharp_edges].reshape(-1, 3).astype(np.float32)
            else:
                sharp_lines = np.zeros((0, 3), dtype=np.float32)
        except Exception:
            sharp_lines = np.zeros((0, 3), dtype=np.float32)

        b_min = np.min(v, axis=0).astype(np.float32)
        b_max = np.max(v, axis=0).astype(np.float32)
        center = ((b_min + b_max) * 0.5).astype(np.float32)

        return RenderMesh(
            vertices=tri_verts,
            normals=tri_normals,
            sharp_lines=sharp_lines,
            bounds_min=b_min,
            bounds_max=b_max,
            center=center,
            source=(np.asarray(v, dtype=np.float64), np.asarray(f, dtype=np.int64), keep),
        )

    @staticmethod
    def create_thread(
        diameter: float,
        pitch: float,
        length: float,
        is_female: bool = False,
        clearance: float = 0.0,
        profile: str = "trapezoidal_45",
        taper_lead_in: bool = True,
        taper_turns: float = 0.75,
        segments_per_turn: Optional[int] = None,
        include_core: bool = True,
        attached_to_cylinder: bool = False,
        grow: float = 0.0,
    ) -> m3d.Manifold:
        """Create a 3D-print optimized helical thread (male bolt or female cutter/nut core).

        Parameters:
        - diameter: nominal thread diameter (mm)
        - pitch: thread pitch (distance per turn, mm)
        - length: total threaded length along Z axis (mm)
        - is_female: True for female thread (internal nut/hole), False for male (bolt)
        - clearance: diametral/radial clearance compensation for FDM 3D printing
        - profile: 'trapezoidal_45' (45° overhang safe), 'iso_60', or 'round' (circular coil/thread)
        - taper_lead_in: whether to smoothly fade the tooth in/out for easy screwing
        - taper_turns: how many helical turns over which to fade (e.g. 0.75 turn)
        - include_core: whether to include the inner core cylinder (for male thread)
        - attached_to_cylinder: whether thread is wrapped directly on an existing cylinder of diameter D
        - grow: the tooth profile is offset outwards by this much on every side (negative: thinner); Offset Face on a
          thread surface edits this instead of deforming the finished mesh
        """
        dia = float(diameter)
        p = max(0.2, float(pitch))
        l = max(p, float(length))
        clr = max(0.0, float(clearance))
        seg = int(segments_per_turn or quality.circle_segments())

        turns = l / p
        n_pts = max(16, int(round(turns * seg)))

        # Tooth profile geometry
        if profile == "round" or profile == "circular":
            # Round bottle / container thread (DIN 168 / glass & jar standard round thread):
            # The bead has a smooth semi-circular/elliptical ridge with proportions:
            # - Radial bead height dr_full ~ 0.22 * pitch (~0.77 mm for pitch 3.5 mm)
            # - Axial half-width a_z ~ 0.28 * pitch (leaving adequate space between turns for mating thread)
            dr_full = 0.22 * p
            a_z = 0.28 * p
            overlap = 0.06  # slight overlap into cylinder wall to prevent coplanar facets and gaps

            if not is_female:
                if attached_to_cylinder:
                    # Thread wrapped directly around existing cylinder of diameter D:
                    # Crest stands out by dr_eff = dr_full - (clearance * 0.5)
                    dr_eff = dr_full - (clr * 0.5)
                    r_center = (dia * 0.5) - overlap
                    a_r = dr_eff + overlap
                    r_root = dia * 0.5
                else:
                    # Standalone bolt: outer crest diameter is D - clearance
                    r_outer = (dia * 0.5) - (clr * 0.5)
                    r_root = r_outer - dr_full
                    r_center = r_root
                    a_r = dr_full
            else:
                # Female cutter cutting internal groove into hole of diameter D:
                # Sinks into the hole wall to depth dr_eff = dr_full + (clearance * 0.5)
                dr_eff = dr_full + (clr * 0.5)
                r_center = (dia * 0.5) - overlap
                a_r = dr_eff + overlap
                r_root = dia * 0.5
            
            # `grow` is added after the lead-in taper, so the offset is the same all along the coil
            a_z_max = 0.49 * p                               # 0.49: the turns never touch
            n_circ = 16
            circ_angles = np.linspace(0.0, 2.0 * math.pi, n_circ, endpoint=False)

            theta = np.linspace(0, turns * 2.0 * math.pi, n_pts + 1)
            z_base = (theta / (2.0 * math.pi)) * p

            if taper_lead_in:
                taper_n = max(1, int(round(taper_turns * seg)))
                f_taper = np.ones(n_pts + 1, dtype=np.float32)
                for i in range(min(taper_n, (n_pts + 1) // 2)):
                    frac = i / float(taper_n)
                    smooth_val = float(math.sin(0.5 * math.pi * frac) ** 2)
                    f_taper[i] = smooth_val
                    f_taper[-(i + 1)] = smooth_val
            else:
                f_taper = np.ones(n_pts + 1, dtype=np.float32)

            verts = []
            for i in range(n_pts + 1):
                th = float(theta[i])
                c, s = float(math.cos(th)), float(math.sin(th))
                zb = float(z_base[i])
                fw = max(0.02, float(f_taper[i]))
                for phi in circ_angles:
                    rr = max(0.005, a_r * fw + grow)
                    rz = min(max(0.005, a_z * fw + grow), a_z_max)
                    r = r_center + rr * float(math.cos(phi))
                    z = zb + rz * float(math.sin(phi))
                    verts.append([r * c, r * s, z])

            verts = np.array(verts, dtype=np.float32)
            tris = []
            for i in range(n_pts):
                b0 = i * n_circ
                b1 = (i + 1) * n_circ
                for j in range(n_circ):
                    j_next = (j + 1) % n_circ
                    tris.append([b0 + j, b1 + j, b1 + j_next])
                    tris.append([b0 + j, b1 + j_next, b0 + j_next])

            # Watertight end caps with consistent normal orientation:
            for j in range(1, n_circ - 1):
                tris.append([0, j, j + 1])
            end_b = n_pts * n_circ
            for j in range(1, n_circ - 1):
                tris.append([end_b + 0, end_b + j + 1, end_b + j])

            tris = np.array(tris, dtype=np.int32)
            coil_mesh = m3d.Mesh(vert_properties=verts, tri_verts=tris)
            coil = m3d.Manifold(coil_mesh)

            # Trim coils to the exact thread length [0, length] along Z to prevent
            # thread profile overhangs/burrs ("fnas") past the cylinder ends.
            coil = coil.trim_by_plane((0.0, 0.0, 1.0), 0.0).trim_by_plane((0.0, 0.0, -1.0), -l)

            if include_core and not is_female:
                cyl_core = m3d.Manifold.cylinder(l, r_root, r_root, circular_segments=seg)
                return cyl_core + coil
            return coil

        elif profile == "iso_60":
            # 60 degree metric thread profile:
            # flank angle 30 deg to normal, tooth height ~ 0.54 * pitch
            flank_dz = 0.35 * p
            crest_flat_z = 0.125 * p
            dr_full = flank_dz / math.tan(math.radians(30)) * 0.5  # ~ 0.54 * p
        else:
            # 45 degree overhang-safe trapezoidal profile:
            # 45 deg flanks (safe to 3D print without supports at any layer height)
            crest_flat_z = 0.18 * p
            flank_dz = 0.28 * p
            dr_full = flank_dz  # tan(45°) = 1.0

        half_crest = crest_flat_z * 0.5
        half_slot = half_crest + flank_dz
        if grow:   # offset every flank by `grow` along its normal (see `grow` above)
            k = math.sqrt(1.0 + (dr_full / flank_dz) ** 2)
            half_slot = min(half_slot + grow * k, 0.49 * p)
            half_crest = min(max(half_crest + grow * (k - flank_dz / dr_full), 0.01), half_slot - 0.01)

        if not is_female:
            if attached_to_cylinder:
                # Wrapped directly on existing cylinder body of diameter D:
                # Root is at cylinder boundary (with slight penetration into cylinder for watertight union),
                # crest extends outward from cylinder surface.
                r_root = dia * 0.5
                r_in = r_root - 0.1
                dr_eff = dr_full - (clr * 0.5)
            else:
                # Standalone male bolt: outer crest is at (dia * 0.5) - (clr * 0.5)
                r_outer = (dia * 0.5) - (clr * 0.5)
                r_root = r_outer - dr_full
                r_in = r_root - (0.2 * dr_full)  # slight overlap inside core for watertight boolean
                dr_eff = dr_full
        else:
            # Female cutter thread:
            # Cuts outward into hole wall of diameter D from r_root to r_root + dr_eff
            r_root = dia * 0.5
            r_in = r_root - (0.2 * dr_full)
            dr_eff = dr_full + (clr * 0.5)

        theta = np.linspace(0, turns * 2.0 * math.pi, n_pts + 1)
        z_base = (theta / (2.0 * math.pi)) * p

        # Lead-in / runout taper envelope
        if taper_lead_in:
            taper_n = max(1, int(round(taper_turns * seg)))
            f_taper = np.ones(n_pts + 1, dtype=np.float32)
            for i in range(min(taper_n, (n_pts + 1) // 2)):
                frac = i / float(taper_n)
                smooth_val = float(math.sin(0.5 * math.pi * frac) ** 2)
                f_taper[i] = smooth_val
                f_taper[-(i + 1)] = smooth_val
        else:
            f_taper = np.ones(n_pts + 1, dtype=np.float32)

        verts = []
        for i in range(n_pts + 1):
            th = theta[i]
            c, s = float(math.cos(th)), float(math.sin(th))
            zb = float(z_base[i])
            eff_dr = max(0.005, dr_eff * float(f_taper[i]) + grow)    # grow after the taper: the same all along
            r_out = r_root + eff_dr

            # 4 profile cross-section vertices:
            # 0: inner root lower (inside core / hole)
            v0 = [r_in * c, r_in * s, zb - half_slot]
            # 1: outer lower crest edge
            v1 = [r_out * c, r_out * s, zb - half_crest]
            # 2: outer upper crest edge
            v2 = [r_out * c, r_out * s, zb + half_crest]
            # 3: inner root upper (inside core / hole)
            v3 = [r_in * c, r_in * s, zb + half_slot]
            verts.extend([v0, v1, v2, v3])

        verts = np.array(verts, dtype=np.float32)
        tris = []

        # Connect consecutive slices with watertight quads (positive outward normals):
        for i in range(n_pts):
            b0 = i * 4
            b1 = (i + 1) * 4
            # Lower flank (downward):
            tris.append([b0 + 0, b1 + 1, b0 + 1])
            tris.append([b0 + 0, b1 + 0, b1 + 1])
            # Crest flat (radially outward):
            tris.append([b0 + 1, b1 + 2, b0 + 2])
            tris.append([b0 + 1, b1 + 1, b1 + 2])
            # Upper flank (upward):
            tris.append([b0 + 2, b1 + 3, b0 + 3])
            tris.append([b0 + 2, b1 + 2, b1 + 3])
            # Inner root wall (radially inward):
            tris.append([b0 + 3, b1 + 0, b0 + 0])
            tris.append([b0 + 3, b1 + 3, b1 + 0])

        # Start cap at i=0:
        tris.append([0, 1, 2])
        tris.append([0, 2, 3])

        # End cap at i=n_pts:
        end_b = n_pts * 4
        tris.append([end_b + 0, end_b + 2, end_b + 1])
        tris.append([end_b + 0, end_b + 3, end_b + 2])

        tris = np.array(tris, dtype=np.int32)
        coil_mesh = m3d.Mesh(vert_properties=verts, tri_verts=tris)
        coil = m3d.Manifold(coil_mesh)

        # Trim coils to the exact thread length [0, length] along Z to prevent
        # thread profile overhangs/burrs ("fnas") past the cylinder ends.
        coil = coil.trim_by_plane((0.0, 0.0, 1.0), 0.0).trim_by_plane((0.0, 0.0, -1.0), -l)

        if include_core and not is_female:
            cyl_core = m3d.Manifold.cylinder(l, r_root, r_root, circular_segments=seg)
            return cyl_core + coil
        return coil

