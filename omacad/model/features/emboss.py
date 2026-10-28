"""
Omacad - Emboss Feature
Fusion's Emboss: raise a sketch profile (typically text) from a face by a depth (Emboss, adds material) or press it
into the face (Deboss, removes material). The sign of the depth decides, like in Fusion; Flip reverses the side;
Horizontal / Vertical distance and Rotation move the shape on the face.
"""

import math
from typing import Any, Dict, List, Optional

import numpy as np
import manifold3d as m3d
from shapely import affinity

from omacad.model import quality
from omacad.model.features.base import combine_with_bodies, region_cross_section
from omacad.model.features.extrude import ExtrudeFeature

EPS = 0.02      # the tool starts a hair behind the face, so a join never leaves a coplanar skin


class EmbossFeature(ExtrudeFeature):
    """An extrusion with Emboss's vocabulary: depth (+ emboss, - deboss), flip, shift and turn on the face."""

    def __init__(self, feature_id: str, name: str, sketch_id: str, profile_idx: int, depth: float = 1.0,
                 flip: bool = False, dx: float = 0.0, dy: float = 0.0, rotation: float = 0.0,
                 wrap: bool = True, extra_profiles=None, extra_refs=None):
        super().__init__(feature_id, name, sketch_id, profile_idx, depth, "join" if depth > 0 else "cut",
                         extra_profiles=extra_profiles, extra_refs=extra_refs)
        self.feature_type = "emboss"
        self.depth = float(depth)
        self.flip = bool(flip)
        self.dx, self.dy, self.rotation = float(dx), float(dy), float(rotation)
        self.wrap = bool(wrap)

    @property
    def effect(self) -> str:
        return "emboss" if self.depth > 0 else "deboss"

    def build_solid(self, doc: Any) -> Optional[m3d.Manifold]:
        sketch = doc.sketches.get(self.sketch_id)
        if sketch:
            self.resolve_profile_refs(sketch)
        if not sketch or self.profile_idx >= len(sketch.profiles) or abs(self.depth) < 1e-6:
            return None
        idxs = [self.profile_idx] + [i for i in self.extra_profiles if i != self.profile_idx and i < len(sketch.profiles)]
        region = self.region(doc, sketch, idxs)
        if region.is_empty:
            return None
        if abs(self.rotation) > 1e-9:
            region = affinity.rotate(region, self.rotation, origin=region.centroid)
        if abs(self.dx) > 1e-9 or abs(self.dy) > 1e-9:
            region = affinity.translate(region, self.dx, self.dy)
        cs = region_cross_section(region)
        M = sketch.plane.get_transform_matrix_3x4()
        surface = None if self.flip else self._surface_behind(doc, M, region)
        field = None if self.flip or surface is not None else self._height_field(doc, M, region)
        if field is not None:
            # the letters sit over faces of different kinds (a flat wall running into a rounded corner): no single
            # plane or cylinder carries them, so they are projected onto the surface as it is (Björn #57)
            solid = self._projected(M, region, field)
        elif surface and surface["kind"] == "cylinder":
            solid = self._wrapped(cs, M, surface, region)
        else:
            z0 = surface["z"] if surface else 0.0      # a flat face behind the sketch plane: the letters start on it
            lo, hi = (-EPS, self.depth) if self.depth > 0 else (self.depth, EPS)      # along the sketch normal
            if self.flip:
                lo, hi = -hi, -lo
                if self.depth > 0:
                    hi = min(hi, 0.0)       # flipped, the letters go into the body: no hair-thin skin standing on the face
            solid = m3d.Manifold.extrude(cs, height=float(hi - lo)).translate((0.0, 0.0, float(lo + z0)))
            solid = solid.transform(M)
        return solid if solid is not None and not solid.is_empty() else None

    @staticmethod
    def _height_field(doc: Any, M, region, cells: int = 160) -> Optional[Dict[str, Any]]:
        """Where the bodies' surface lies under the letters, seen along the sketch normal: a grid over the region's
        bounds with the sketch-z of the nearest surface facing the sketch in each cell (NaN where there is none),
        made by rasterising the facing triangles (a z-buffer), plus the footprint those triangles cover."""
        from shapely.geometry import Polygon as _Poly
        from shapely.ops import unary_union
        A = np.vstack([np.asarray(M, dtype=float).reshape(3, 4), [0.0, 0.0, 0.0, 1.0]])
        inv = np.linalg.inv(A)
        minx, miny, maxx, maxy = region.bounds
        size = max(maxx - minx, maxy - miny, 1e-6)
        step = max(size / cells, 0.05)
        pad = 2 * step
        xs = np.arange(minx - pad, maxx + pad + step, step)
        ys = np.arange(miny - pad, maxy + pad + step, step)
        H = np.full((len(ys), len(xs)), np.nan)
        polys = []
        for body in doc.bodies.values():
            mesh = body.render_mesh
            if mesh is None or len(mesh.vertices) == 0 or not body.visible:
                continue
            tri = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3)
            tri = (tri @ inv[:3, :3].T + inv[:3, 3]).reshape(-1, 3, 3)
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            keep = ((n[:, 2] > 1e-12) & (tri[:, :, 0].max(1) >= xs[0]) & (tri[:, :, 0].min(1) <= xs[-1])
                    & (tri[:, :, 1].max(1) >= ys[0]) & (tri[:, :, 1].min(1) <= ys[-1]) & (tri[:, :, 2].max(1) < 0.0))
            for t in tri[keep]:
                (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = t
                det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
                if abs(det) < 1e-14:
                    continue
                polys.append(_Poly(t[:, :2]))
                i0 = max(0, int(np.floor((min(x0, x1, x2) - xs[0]) / step)))
                i1 = min(len(xs) - 1, int(np.ceil((max(x0, x1, x2) - xs[0]) / step)))
                j0 = max(0, int(np.floor((min(y0, y1, y2) - ys[0]) / step)))
                j1 = min(len(ys) - 1, int(np.ceil((max(y0, y1, y2) - ys[0]) / step)))
                if i1 < i0 or j1 < j0:
                    continue
                gx, gy = np.meshgrid(xs[i0:i1 + 1], ys[j0:j1 + 1])
                a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / det
                b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / det
                c = 1.0 - a - b
                inside = (a >= -1e-9) & (b >= -1e-9) & (c >= -1e-9)
                z = a * z0 + b * z1 + c * z2
                sub = H[j0:j1 + 1, i0:i1 + 1]
                upd = inside & (np.isnan(sub) | (z > sub))     # nearest to the sketch (largest z) wins
                sub[upd] = z[upd]
        if not polys or np.all(np.isnan(H)):
            return None
        return {"xs": xs, "ys": ys, "H": H, "step": step, "footprint": unary_union(polys).buffer(1e-6)}

    @staticmethod
    def _surface_z(field, x, y):
        """Bilinear surface height at points (x, y); cells without surface take their nearest neighbours."""
        H = field["H"].copy()
        for _ in range(8):           # grow known heights into empty cells next to them (letters reaching an edge)
            if not np.isnan(H).any():
                break
            nb = np.stack([np.roll(H, k, axis=a) for a in (0, 1) for k in (1, -1)])
            fill = np.isnan(H) & ~np.all(np.isnan(nb), axis=0)
            H[fill] = np.where(np.isnan(nb), -np.inf, nb).max(axis=0)[fill]
        H = np.where(np.isnan(H), np.nanmin(H), H)
        xs, ys, step = field["xs"], field["ys"], field["step"]
        fx = np.clip((x - xs[0]) / step, 0, len(xs) - 1.000001)
        fy = np.clip((y - ys[0]) / step, 0, len(ys) - 1.000001)
        i, j = fx.astype(int), fy.astype(int)
        tx, ty = fx - i, fy - j
        return ((H[j, i] * (1 - tx) + H[j, i + 1] * tx) * (1 - ty)
                + (H[j + 1, i] * (1 - tx) + H[j + 1, i + 1] * tx) * ty)

    def _projected(self, M, region, field) -> Optional[m3d.Manifold]:
        """The letters projected along the sketch normal onto the surface under them: each point of the shape keeps
        its place in the sketch and stands `depth` above (or below) the surface there. Parts beyond the body's
        outline are left out."""
        from shapely import segmentize
        region = region.intersection(field["footprint"])
        if region.is_empty or region.area < 1e-9:
            return None
        step = field["step"]
        cs = region_cross_section(segmentize(region, max_segment_length=2 * step))
        d = float(self.depth)
        lo, hi = (-max(EPS, 2 * step), d) if d > 0 else (d, max(EPS, 2 * step))
        prism = m3d.Manifold.extrude(cs, height=1.0).refine_to_length(2 * step)

        def warp(pts):
            z0 = self._surface_z(field, pts[:, 0], pts[:, 1])
            return np.column_stack([pts[:, 0], pts[:, 1], z0 + lo + pts[:, 2] * (hi - lo)])

        return prism.warp_batch(warp).transform(M)

    def _surface_behind(self, doc: Any, M, region) -> Optional[Dict[str, Any]]:
        """The first outer cylinder or flat face (parallel to the sketch plane) a ray from the letters hits going
        against the sketch normal, in sketch coordinates: {"kind", "z"} (+ axis data for a cylinder)."""
        from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit
        A = np.vstack([np.asarray(M, dtype=float).reshape(3, 4), [0.0, 0.0, 0.0, 1.0]])
        inv = np.linalg.inv(A)
        reach = 1e4
        direction = -A[:3, 2] / np.linalg.norm(A[:3, 2])
        # Long text can have its centroid beside the body while the letters still sit over it: try the centroid
        # first, then points spread across the shape, and keep the first ray that hits something.
        c = region.centroid
        minx, miny, maxx, maxy = region.bounds
        cands = [(c.x, c.y)]
        rp = region.representative_point()
        cands.append((rp.x, rp.y))
        cands += [(minx + (maxx - minx) * f, (miny + maxy) / 2) for f in (0.5, 0.25, 0.75, 0.1, 0.9)]
        best = None
        origin = None
        for cx, cy in cands:
            o = (A @ np.array([cx, cy, reach, 1.0]))[:3]
            for body in doc.bodies.values():
                mesh = body.render_mesh
                if mesh is None or len(mesh.vertices) == 0:
                    continue
                hit = ray_mesh_hit(mesh, o, direction)
                if hit is not None and (best is None or hit[0] < best[0]):
                    best = (hit[0], mesh, hit[1])
                    origin = o
            if best is not None:
                break
        if best is None:
            return None
        t, mesh, tri = best
        z = reach - t
        cyl = detect_cylinder_surface(mesh, tri)
        if cyl is not None and not cyl["is_internal"]:
            axis = inv[:3, :3] @ np.asarray(cyl["axis"], dtype=float)
            pt = np.asarray(cyl["origin"], dtype=float)
            hit_pt = origin + direction * t
            centre = pt + ((hit_pt - pt) @ cyl["axis"]) * np.asarray(cyl["axis"], dtype=float)   # on the axis, level with the hit
            return {"kind": "cylinder", "z": z, "radius": float(cyl["radius"]), "centre": centre,
                    "axis": np.asarray(cyl["axis"], dtype=float), "zc": float((inv @ np.append(centre, 1.0))[2])}
        v = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3, 3)[tri]
        face_n = np.cross(v[1] - v[0], v[2] - v[0])
        face_n = face_n / max(float(np.linalg.norm(face_n)), 1e-12)
        if float(face_n @ -direction) > 0.9999:
            return {"kind": "plane", "z": z}
        return None

    def _wrapped(self, cs, M, surface, region=None) -> m3d.Manifold:
        """Letters that hug a cylinder: when `self.wrap` is True, the 2D profile is bent around the cylinder's
        circumference (theta = s_perp / r) so text wider than the diameter wraps all the way around; when False,
        it projects straight along the sketch normal and is clipped to the coaxial cylinder."""
        from omacad.model.features.offset_face import _frame
        r, d = float(surface["radius"]), float(self.depth)
        if self.wrap and r > 1e-4:
            A = np.vstack([np.asarray(M, dtype=float).reshape(3, 4), [0.0, 0.0, 0.0, 1.0]])
            inv = np.linalg.inv(A)
            centre_sk = (inv @ np.append(surface["centre"], 1.0))[:3]
            axis_sk = inv[:3, :3] @ np.asarray(surface["axis"], dtype=float)
            axis_uv = np.array([axis_sk[0], axis_sk[1]], dtype=float)
            norm_uv = float(np.linalg.norm(axis_uv))
            if norm_uv > 1e-4:
                e_par = axis_uv / norm_uv
                e_perp = np.array([-e_par[1], e_par[0]], dtype=float)
                u0, v0 = float(centre_sk[0]), float(centre_sk[1])
                if region is not None and not region.is_empty:
                    from shapely import segmentize
                    step = max(0.25, r * math.radians(3.0))
                    cs_fine = region_cross_section(segmentize(region, max_segment_length=step))
                else:
                    cs_fine = cs
                margin = 0.05 * r + 0.02
                r_in, r_out = (max(0.01, r - EPS), r + d) if d > 0 else (max(0.01, r + d), r + margin)
                prism = m3d.Manifold.extrude(cs_fine, height=1.0, n_divisions=2)
                # Boundary segmentation alone leaves long diagonals across the caps.
                # After wrapping, those chords can dip inside the cylinder and leave
                # a detached skin over a deboss. Refine the cap interiors as well.
                prism = prism.refine_to_length(max(0.25, r * math.radians(3.0)))

                def _warp_batch(pts):
                    du = pts[:, 0] - u0
                    dv = pts[:, 1] - v0
                    s_par = du * e_par[0] + dv * e_par[1]
                    s_perp = du * e_perp[0] + dv * e_perp[1]
                    theta = s_perp / r
                    rad = r_in + pts[:, 2] * (r_out - r_in)
                    sin_t = np.sin(theta)
                    cos_t = np.cos(theta)
                    u_new = u0 + s_par * e_par[0] + rad * sin_t * e_perp[0]
                    v_new = v0 + s_par * e_par[1] + rad * sin_t * e_perp[1]
                    z_new = float(surface["zc"]) + rad * cos_t
                    return np.column_stack([u_new, v_new, z_new])

                return prism.warp_batch(_warp_batch).transform(M)

        zc = surface["zc"]
        prism = m3d.Manifold.extrude(cs, height=float(r + abs(d) + 1.0)).translate((0.0, 0.0, float(zc)))
        prism = prism.transform(M)
        length = 2.0 * (r + abs(d)) + 2.0 * 1e4
        frame = _frame(surface["centre"], surface["axis"])
        def cylinder(radius):
            cyl = m3d.Manifold.extrude(m3d.CrossSection.circle(radius, quality.circle_segments()), length)
            return cyl.translate((0.0, 0.0, -length / 2.0)).transform(frame[:3, :])
        if d > 0:
            return prism ^ cylinder(r + d)
        margin = 0.05 * r + 0.01
        return prism ^ (cylinder(r + margin) - cylinder(max(r + d, 0.01)))

    def execute(self, doc: Any) -> None:
        tool = self.build_solid(doc)
        if tool is None:
            return
        self.operation = "join" if self.depth > 0 else "cut"
        combine_with_bodies(doc, self.feature_id, self.name, self.operation, tool)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "sketch_id": self.sketch_id,
            "profile_idx": self.profile_idx,
            "extra_profiles": list(self.extra_profiles),
            "extra_refs": [[sid, i, list(sig)] for sid, i, sig in self.extra_refs],
            "depth": self.depth,
            "flip": self.flip,
            "dx": self.dx,
            "dy": self.dy,
            "rotation": self.rotation,
            "wrap": self.wrap,
            **self.profile_refs_dict(),
        }
