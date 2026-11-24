"""
Omacad - Cut Thread Feature
Takes a placed cylinder ("Thread Pin"), turns it into a helical thread, cuts it
into a target body, and applies 3D-printer clearance + lead-in chamfers.
"""

from typing import Dict, Any, List, Optional, Sequence, Tuple, Union
import math
import numpy as np
import manifold3d as m3d

from omacad.model import quality
from omacad.model.faces import compute_planar_faces
from omacad.model.features.base import Feature
from omacad.model.features.offset_face import OVERSHOOT
from omacad.model.features.thread import ThreadFeature


def extract_pin_cylinder(manifold: m3d.Manifold) -> Tuple[list, list, list, list, float, float]:
    """Return (origin, normal, u, v, diameter, length) from a cylinder manifold."""
    faces = compute_planar_faces(manifold)
    best = None
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            f1, f2 = faces[i], faces[j]
            if float(np.dot(f1.normal, f2.normal)) > -0.99:
                continue
            if abs(f1.area - f2.area) > 0.05 * max(f1.area, f2.area, 1e-9):
                continue
            score = f1.area
            if best is None or score > best[0]:
                best = (score, f1, f2)
    if best is None:
        raise ValueError("Selected pin body is not a cylinder with two flat end caps.")
    _, f1, f2 = best
    n = np.array(f2.normal, dtype=float)
    n /= max(float(np.linalg.norm(n)), 1e-12)
    c1 = np.asarray(f1.origin, dtype=float)
    c2 = np.asarray(f2.origin, dtype=float)
    if float(np.dot(c2 - c1, n)) < 0.0:
        n = -n
    hint = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = hint - float(np.dot(hint, n)) * n
    u /= max(float(np.linalg.norm(u)), 1e-12)
    v = np.cross(n, u)
    verts = np.asarray(manifold.to_mesh().vert_properties, dtype=float)[:, :3]
    px, py, pz = verts @ u, verts @ v, verts @ n
    z_min, z_max = float(pz.min()), float(pz.max())
    origin = (0.5 * float(px.min() + px.max())) * u + (0.5 * float(py.min() + py.max())) * v + z_min * n
    length = z_max - z_min
    diameter = 0.5 * (float(px.max() - px.min()) + float(py.max() - py.min()))
    return origin.tolist(), n.tolist(), u.tolist(), v.tolist(), float(diameter), float(length)


def _cone_z(z0: float, z1: float, r0: float, r1: float, mat: Optional[np.ndarray], seg: int) -> m3d.Manifold:
    h = abs(z1 - z0)
    cone = m3d.Manifold.cylinder(h, max(0.01, r0), max(0.01, r1), circular_segments=seg).translate([0.0, 0.0, min(z0, z1)])
    return cone if mat is None else cone.transform(mat)


class CutThreadFeature(Feature):
    """Threads a placed cylinder pin, cuts it into one or more target bodies, and adds clearance + lead-in chamfers."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: Union[str, Sequence[str]],
        pin_body_id: str,
        pitch: float = 2.0,
        profile: str = "trapezoidal_45",
        clearance: float = 0.2,
        chamfer: float = 1.0,
        keep_screw: bool = True,
        taper_lead_in: bool = True,
        target_body_ids: Optional[Sequence[str]] = None,
    ):
        super().__init__(feature_id, "cut_thread", name)
        raw_ids = (
            list(target_body_ids)
            if target_body_ids is not None
            else (list(target_body_id) if isinstance(target_body_id, (list, tuple, set)) else [target_body_id])
        )
        self.target_body_ids: List[str] = list(dict.fromkeys(str(b) for b in raw_ids if b))
        self.target_body_id: str = self.target_body_ids[0] if self.target_body_ids else ""
        self.pin_body_id = str(pin_body_id)
        self.pitch = float(pitch)
        self.profile = str(profile)
        self.clearance = max(0.0, float(clearance))
        self.chamfer = max(0.0, float(chamfer))
        self.keep_screw = bool(keep_screw)
        self.taper_lead_in = bool(taper_lead_in)

    @staticmethod
    def _prepare_tools(
        pin_manifold: m3d.Manifold,
        pitch: float = 2.0,
        profile: str = "trapezoidal_45",
        clearance: float = 0.2,
        chamfer: float = 1.0,
        keep_screw: bool = True,
        taper_lead_in: bool = True,
    ):
        origin, normal, u, v, diameter, length = extract_pin_cylinder(pin_manifold)
        tf = ThreadFeature(
            "tmp_thread",
            "tmp_thread",
            diameter=diameter,
            pitch=pitch,
            length=length,
            is_female=False,
            clearance=0.0,
            profile=profile,
            taper_lead_in=taper_lead_in,
            plane_origin=origin,
            plane_normal=normal,
            plane_u=u,
            plane_v=v,
        )
        nominal_bolt = tf.build_solid()
        clr = max(0.0, float(clearance))
        ch = max(0.0, float(chamfer))
        seg = quality.circle_segments()
        mat = tf.placement()

        if keep_screw:
            cut_tool = nominal_bolt
            screw_tf = ThreadFeature(
                "tmp_screw",
                "tmp_screw",
                diameter=diameter,
                pitch=pitch,
                length=length,
                is_female=False,
                clearance=0.0,
                profile=profile,
                taper_lead_in=taper_lead_in,
                grow=-clr,
            )
            r_core = max(0.05, screw_tf.root_radius() - clr)
            local_screw = screw_tf.build_solid(core_radius=r_core)
            if ch > 1e-6:
                r_out = max(0.2, 0.5 * diameter - clr)
                c_bolt = min(ch, 0.35 * length, 0.4 * r_out)
                if c_bolt > 1e-6:
                    c_bot = _cone_z(0.0, c_bolt + 0.02, r_out - c_bolt, r_out + 0.02, None, seg)
                    c_top = _cone_z(length - c_bolt - 0.02, length, r_out + 0.02, r_out - c_bolt, None, seg)
                    mid = _cone_z(c_bolt, length - c_bolt, r_out + 1.0, r_out + 1.0, None, seg)
                    local_screw = local_screw ^ (c_bot + mid + c_top)
            new_screw = local_screw if mat is None else local_screw.transform(mat)
        else:
            cut_tool = (nominal_bolt + tf.zone(clr, channel=True)) if clr > 1e-6 else nominal_bolt
            new_screw = None

        return cut_tool, new_screw, tf, origin, normal, diameter, length, clr, ch, seg, mat

    @staticmethod
    def _cut_one(
        target_manifold: m3d.Manifold,
        pin_manifold: m3d.Manifold,
        cut_tool: m3d.Manifold,
        tf: ThreadFeature,
        origin: list,
        normal: list,
        diameter: float,
        length: float,
        clr: float,
        ch: float,
        keep_screw: bool,
        seg: int,
        mat: Optional[np.ndarray],
    ) -> m3d.Manifold:
        new_target = target_manifold - cut_tool
        if ch > 1e-6:
            orig_v = np.asarray(origin, dtype=float)
            norm_v = np.asarray(normal, dtype=float)
            r_hole = 0.5 * diameter + (0.0 if keep_screw else clr)
            c_hole = min(ch, 0.4 * diameter)
            r_outer = r_hole + c_hole
            r_inner = max(0.2, tf.root_radius() - 0.05)
            dz = min(r_outer - r_inner, 0.45 * length)
            r_tip = r_outer - dz
            seen = []
            for pf in compute_planar_faces(new_target):
                dot = float(np.dot(pf.normal, norm_v))
                if abs(dot) < 0.99:
                    continue
                pts = pf.tris.reshape(-1, 3) - orig_v
                radial = np.linalg.norm(pts - np.outer(pts @ norm_v, norm_v), axis=1)
                if float(radial.min()) > r_outer + 0.5:
                    continue
                along = float(np.dot(np.asarray(pf.origin, dtype=float) - orig_v, pf.normal)) / dot
                if not (-0.01 <= along <= length + 0.01):
                    continue
                if any(abs(along - a) < 0.05 and (dot > 0.0) == s for a, s in seen):
                    continue
                # Only chamfer faces that the pin actually intersects around the axis
                probe = _cone_z(along - 0.05, along + 0.05, r_hole * 0.5, r_hole * 0.5, mat, 16)
                if (pin_manifold ^ probe).volume() < 1e-6:
                    continue
                seen.append((along, dot > 0.0))
                if dot > 0.0:
                    cone = _cone_z(along - dz, along + 0.02, r_tip, r_outer + 0.02, mat, seg)
                else:
                    cone = _cone_z(along - 0.02, along + dz, r_outer + 0.02, r_tip, mat, seg)
                new_target = new_target - cone
        return new_target

    @classmethod
    def compute_many(
        cls,
        target_manifolds: Sequence[m3d.Manifold],
        pin_manifold: m3d.Manifold,
        pitch: float = 2.0,
        profile: str = "trapezoidal_45",
        clearance: float = 0.2,
        chamfer: float = 1.0,
        keep_screw: bool = True,
        taper_lead_in: bool = True,
    ) -> Tuple[List[m3d.Manifold], Optional[m3d.Manifold]]:
        cut_tool, new_screw, tf, origin, normal, diameter, length, clr, ch, seg, mat = cls._prepare_tools(
            pin_manifold,
            pitch=pitch,
            profile=profile,
            clearance=clearance,
            chamfer=chamfer,
            keep_screw=keep_screw,
            taper_lead_in=taper_lead_in,
        )
        results = [
            cls._cut_one(m, pin_manifold, cut_tool, tf, origin, normal, diameter, length, clr, ch, keep_screw, seg, mat)
            for m in target_manifolds
        ]
        return results, new_screw

    @classmethod
    def compute(
        cls,
        target_manifold: m3d.Manifold,
        pin_manifold: m3d.Manifold,
        pitch: float = 2.0,
        profile: str = "trapezoidal_45",
        clearance: float = 0.2,
        chamfer: float = 1.0,
        keep_screw: bool = True,
        taper_lead_in: bool = True,
    ) -> Tuple[m3d.Manifold, Optional[m3d.Manifold]]:
        results, new_screw = cls.compute_many(
            [target_manifold],
            pin_manifold,
            pitch=pitch,
            profile=profile,
            clearance=clearance,
            chamfer=chamfer,
            keep_screw=keep_screw,
            taper_lead_in=taper_lead_in,
        )
        return results[0], new_screw

    def execute(self, doc: Any) -> None:
        pin = doc.bodies.get(self.pin_body_id)
        if not pin:
            return
        targets = [doc.bodies[bid] for bid in self.target_body_ids if bid in doc.bodies and bid != self.pin_body_id]
        if not targets:
            return
        new_targets, new_screw = self.compute_many(
            [t.manifold for t in targets],
            pin.manifold,
            pitch=self.pitch,
            profile=self.profile,
            clearance=self.clearance,
            chamfer=self.chamfer,
            keep_screw=self.keep_screw,
            taper_lead_in=self.taper_lead_in,
        )
        for target, new_m in zip(targets, new_targets):
            target.manifold = new_m
            target.update_render_mesh()
        if self.keep_screw and new_screw is not None:
            pin.manifold = new_screw
            pin.update_render_mesh()
        else:
            doc.bodies.pop(self.pin_body_id, None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "target_body_ids": list(self.target_body_ids),
            "pin_body_id": self.pin_body_id,
            "pitch": self.pitch,
            "profile": self.profile,
            "clearance": self.clearance,
            "chamfer": self.chamfer,
            "keep_screw": self.keep_screw,
            "taper_lead_in": self.taper_lead_in,
            "exprs": dict(self.exprs),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CutThreadFeature":
        feat = cls(
            feature_id=data["feature_id"],
            name=data.get("name", "Cut Thread"),
            target_body_id=data["target_body_id"],
            pin_body_id=data["pin_body_id"],
            pitch=data.get("pitch", 2.0),
            profile=data.get("profile", "trapezoidal_45"),
            clearance=data.get("clearance", 0.2),
            chamfer=data.get("chamfer", 1.0),
            keep_screw=data.get("keep_screw", True),
            taper_lead_in=data.get("taper_lead_in", True),
            target_body_ids=data.get("target_body_ids"),
        )
        feat.suppressed = data.get("suppressed", False)
        feat.exprs = dict(data.get("exprs", {}))
        return feat
