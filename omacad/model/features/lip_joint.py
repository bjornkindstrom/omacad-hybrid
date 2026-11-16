"""Lip joint feature (#241): adds a mating lip on one half of a split body and a matching pocket on the other."""
from typing import Any, Dict, List, Optional, Tuple

import manifold3d as m3d
import numpy as np

from omacad.model.features.base import Feature, clean_cut


def _signed_area(poly) -> float:
    p = np.asarray(poly, dtype=float)
    if len(p) < 3:
        return 0.0
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def plane_frame(origin: np.ndarray, normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (R, mat_w2l_3x4, mat_l2w_3x4) where R @ normal = +Z and plane is z = 0."""
    n = np.asarray(normal, dtype=float)
    n = n / np.linalg.norm(n)
    o = np.asarray(origin, dtype=float)
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(ref, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    R = np.vstack([u, v, n])
    mat_w2l = np.hstack([R, (-R @ o).reshape(3, 1)])
    mat_l2w = np.hstack([R.T, o.reshape(3, 1)])
    return R, mat_w2l, mat_l2w


def _resolve_plane(doc: Any, plane_id: str, plane_origin: Optional[List[float]],
                   plane_normal: Optional[List[float]]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    origin, normal = None, None
    if hasattr(doc, "construction_planes") and plane_id in doc.construction_planes:
        cp = doc.construction_planes[plane_id]
        origin = np.array(cp["origin"], dtype=float)
        normal = np.array(cp["normal"], dtype=float)
    elif hasattr(doc, "origin_planes") and plane_id in doc.origin_planes:
        op = doc.origin_planes[plane_id]
        origin = np.array(op.origin, dtype=float)
        normal = np.array(op.normal, dtype=float)
    elif plane_origin is not None and plane_normal is not None:
        origin = np.array(plane_origin, dtype=float)
        normal = np.array(plane_normal, dtype=float)
    if origin is None or normal is None:
        return None, None
    norm = float(np.linalg.norm(normal))
    if norm < 1e-9:
        return None, None
    return origin, normal / norm


def lip_geometry(local_manifold: m3d.Manifold, side: float, width: float = 0.0,
                 style: str = "inner") -> Tuple[m3d.CrossSection, float]:
    """Compute the 2D lip CrossSection in the plane's local frame (z=0) at slice z = side * 1e-3.

    Supports style = 'inner' (step on inside of wall), 'outer' (step on outside of wall),
    or 'groove' (centered tongue & groove in the middle of the wall).
    When width <= 0, auto-detects from the wall thickness.
    """
    ring = local_manifold.slice(float(side) * 1e-3)
    if ring.is_empty() or ring.area() <= 1e-6:
        return m3d.CrossSection(), 0.0
    ccw = [p for p in ring.to_polygons() if _signed_area(p) > 0.0]
    if not ccw:
        return m3d.CrossSection(), 0.0
    outer = m3d.CrossSection(ccw)
    inner = outer - ring

    b = ring.bounds()
    hi = max(b[2] - b[0], b[3] - b[1]) * 0.5
    lo = 0.0
    for _ in range(28):
        mid = 0.5 * (lo + hi)
        if ring.offset(-mid, m3d.JoinType.Miter).is_empty():
            hi = mid
        else:
            lo = mid
    t_max = lo
    if width <= 0.0:
        w = (2.0 * t_max) / 3.0 if style == "groove" else t_max
    else:
        w = float(width)
    if w <= 1e-6:
        return m3d.CrossSection(), 0.0

    is_solid = inner.is_empty() or inner.area() <= 1e-6
    if style == "outer":
        lip = ring - ring.offset(-w, m3d.JoinType.Miter) if is_solid else ring ^ (outer - outer.offset(-w, m3d.JoinType.Miter))
    elif style == "groove":
        inset = max(0.0, t_max - 0.5 * w)
        lip = ring.offset(-inset, m3d.JoinType.Miter) if inset > 1e-6 else ring
    else:
        lip = ring.offset(-w, m3d.JoinType.Miter) if is_solid else ring ^ inner.offset(w, m3d.JoinType.Miter)
    return lip, w


def _snap_tab_sites(lip_cs: m3d.CrossSection, style: str) -> List[Tuple[np.ndarray, np.ndarray, float]]:
    """Find (midpoint_2d, outward_normal_2d, tab_length) for snap-fit tabs on the mating wall of `lip_cs`."""
    polys = lip_cs.to_polygons()
    want_ccw = style != "outer"
    loops = [np.asarray(p, dtype=float) for p in polys if (_signed_area(p) > 0.0) == want_ccw]
    if not loops and polys:
        loops = [np.asarray(p, dtype=float) for p in polys if _signed_area(p) > 0.0]
    sites: List[Tuple[np.ndarray, np.ndarray, float]] = []
    for poly in loops:
        if len(poly) < 3:
            continue
        p_next = np.roll(poly, -1, axis=0)
        edges = p_next - poly
        lengths = np.linalg.norm(edges, axis=1)
        long_idx = [i for i, L in enumerate(lengths) if L >= 10.0]
        if long_idx:
            for i in long_idx:
                L = float(lengths[i])
                e = edges[i] / L
                n_out = np.array([e[1], -e[0]], dtype=float)
                mid = 0.5 * (poly[i] + p_next[i])
                sites.append((mid, n_out, min(10.0, L * 0.3)))
        else:
            # Curved/segmented rim (e.g. cylinder): place 2 opposite tabs along the perimeter
            total = float(lengths.sum())
            if total >= 20.0:
                cum = np.concatenate(([0.0], np.cumsum(lengths)))
                for target_s in (0.0, 0.5 * total):
                    idx = int(np.searchsorted(cum[1:], target_s, side="right")) % len(poly)
                    L = float(lengths[idx])
                    if L > 1e-6:
                        e = edges[idx] / L
                        n_out = np.array([e[1], -e[0]], dtype=float)
                        mid = 0.5 * (poly[idx] + p_next[idx])
                        sites.append((mid, n_out, min(8.0, total * 0.1)))
    return sites


def build_snap_tabs(lip_cs: m3d.CrossSection, height: float, extrude_dir: float,
                    style: str = "inner", clearance: float = 0.0, snap_depth: float = 0.6) -> Optional[m3d.Manifold]:
    """Build trapezoidal snap-fit detent bumps (or clearance pockets when clearance > 0) in local frame."""
    sites = _snap_tab_sites(lip_cs, style)
    if not sites or height < 1.5:
        return None
    c = max(0.0, float(clearance))
    d = float(snap_depth) + c
    h_snap = min(float(height) * 0.7, 2.0 * d + 1.0 + 2.0 * c)
    h_flat = max(0.2, h_snap - 2.0 * d)
    z_mid = (0.5 * float(height)) * (1.0 if extrude_dir > 0 else -1.0)
    z0, z1, z2, z3 = z_mid - 0.5 * h_snap, z_mid - 0.5 * h_flat, z_mid + 0.5 * h_flat, z_mid + 0.5 * h_snap
    prof = m3d.CrossSection([[(-0.05, z0), (0.0, z0), (d, z1), (d, z2), (0.0, z3), (-0.05, z3)]])
    tabs = []
    for mid, n_out, tab_len in sites:
        tl = tab_len + 2.0 * c
        tab = m3d.Manifold.extrude(prof, tl).translate((0.0, 0.0, -0.5 * tl))
        col0 = np.array([n_out[0], n_out[1], 0.0])
        col1 = np.array([0.0, 0.0, 1.0])
        col2 = np.cross(col0, col1)
        mat = np.column_stack([col0, col1, col2, np.array([mid[0], mid[1], 0.0])])
        tabs.append(tab.transform(mat))
    return m3d.Manifold.compose(tabs) if len(tabs) > 1 else tabs[0]


def build_lip_solid(local_manifold: m3d.Manifold, slice_side: float, extrude_dir: float,
                    height: float, width: float = 0.0, style: str = "inner",
                    snap_fit: bool = False) -> Tuple[Optional[m3d.Manifold], float]:
    """Build the lip solid in local frame, extruding along `extrude_dir` (+1 or -1)."""
    lip, used_w = lip_geometry(local_manifold, slice_side, width, style=style)
    if lip.is_empty() or lip.area() <= 1e-6 or height <= 1e-6:
        return None, used_w
    h = float(height)
    solid = m3d.Manifold.extrude(lip, h + 0.01)
    tz = -0.01 if extrude_dir > 0 else -h
    solid = solid.translate((0.0, 0.0, tz))
    if snap_fit:
        tabs = build_snap_tabs(lip, h, extrude_dir, style=style, clearance=0.0)
        if tabs is not None:
            solid = solid + tabs
    return solid, used_w


def build_pocket_solid(local_manifold: m3d.Manifold, slice_side: float, extrude_dir: float,
                       height: float, width: float = 0.0, clearance: float = 0.2,
                       style: str = "inner", snap_fit: bool = False) -> Tuple[Optional[m3d.Manifold], float]:
    """Build the clearance pocket solid in local frame, extruding along `extrude_dir` (+1 or -1)."""
    lip, used_w = lip_geometry(local_manifold, slice_side, width, style=style)
    if lip.is_empty() or lip.area() <= 1e-6 or height <= 1e-6:
        return None, used_w
    c = max(0.0, float(clearance))
    pocket_cs = lip.offset(c, m3d.JoinType.Round) if c > 0.0 else lip
    if pocket_cs.is_empty() or pocket_cs.area() <= 1e-6:
        return None, used_w
    depth = float(height) + c
    solid = m3d.Manifold.extrude(pocket_cs, depth + 0.01)
    tz = -0.01 if extrude_dir > 0 else -depth
    solid = solid.translate((0.0, 0.0, tz))
    if snap_fit:
        tabs = build_snap_tabs(lip, float(height), extrude_dir, style=style, clearance=c)
        if tabs is not None:
            solid = solid + tabs
    return solid, used_w


class LipJointFeature(Feature):
    """Adds either the protruding lip ('lip') or the mating pocket ('pocket') after a Split Body."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        role: str,
        plane_id: str,
        plane_origin: Optional[List[float]] = None,
        plane_normal: Optional[List[float]] = None,
        height: float = 5.0,
        width: float = 0.0,
        clearance: float = 0.2,
        style: str = "inner",
        snap_fit: bool = False,
        exprs: Optional[Dict[str, str]] = None,
    ):
        super().__init__(feature_id, "lip_joint", name)
        self.target_body_id = target_body_id
        self.role = role  # "lip" or "pocket"
        self.plane_id = plane_id
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.height = float(height)
        self.width = float(width)
        self.clearance = float(clearance)
        self.style = style
        self.snap_fit = bool(snap_fit)
        if exprs:
            self.exprs = dict(exprs)

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target or target.manifold.is_empty():
            return
        origin, normal = _resolve_plane(doc, self.plane_id, self.plane_origin, self.plane_normal)
        if origin is None or normal is None:
            return

        lo_hi = np.asarray(target.manifold.bounding_box(), dtype=float).reshape(2, 3)
        centroid = lo_hi.mean(axis=0)
        into_other = 1.0 if float(np.dot(origin - centroid, normal)) >= 0.0 else -1.0
        slice_side = -into_other

        _, mat_w2l, mat_l2w = plane_frame(origin, normal)
        local = target.manifold.transform(mat_w2l)

        if self.role == "lip":
            solid_local, _ = build_lip_solid(local, slice_side, into_other, self.height, self.width,
                                             style=self.style, snap_fit=self.snap_fit)
            if solid_local is None:
                return
            target.manifold = target.manifold + solid_local.transform(mat_l2w)
        else:
            solid_local, _ = build_pocket_solid(local, slice_side, -into_other, self.height, self.width,
                                                self.clearance, style=self.style, snap_fit=self.snap_fit)
            if solid_local is None:
                return
            target.manifold = clean_cut(target.manifold, solid_local.transform(mat_l2w))
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "role": self.role,
            "plane_id": self.plane_id,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "height": self.height,
            "width": self.width,
            "clearance": self.clearance,
            "style": self.style,
            "snap_fit": self.snap_fit,
        }
