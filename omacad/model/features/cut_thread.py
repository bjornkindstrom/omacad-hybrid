"""
Omacad - Cut Thread Feature
Takes a placed cylinder ("Thread Pin"), turns it into a helical thread, cuts it
into a target body, and applies 3D-printer clearance + lead-in chamfers.
"""

from typing import Dict, Any, Optional, Tuple
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
    """Threads a placed cylinder pin, cuts it into a target body, and adds clearance + lead-in chamfers."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        pin_body_id: str,
        pitch: float = 2.0,
        profile: str = "trapezoidal_45",
        clearance: float = 0.2,
        chamfer: float = 1.0,
        keep_screw: bool = True,
        taper_lead_in: bool = True,
    ):
        super().__init__(feature_id, "cut_thread", name)
        self.target_body_id = str(target_body_id)
        self.pin_body_id = str(pin_body_id)
        self.pitch = float(pitch)
        self.profile = str(profile)
        self.clearance = max(0.0, float(clearance))
        self.chamfer = max(0.0, float(chamfer))
        self.keep_screw = bool(keep_screw)
        self.taper_lead_in = bool(taper_lead_in)

    @staticmethod
    def compute(
        target_manifold: m3d.Manifold,
        pin_manifold: m3d.Manifold,
        pitch: float = 2.0,
        profile: str = "trapezoidal_45",
        clearance: float = 0.2,
        chamfer: float = 1.0,
        keep_screw: bool = True,
        taper_lead_in: bool = True,
    ) -> Tuple[m3d.Manifold, Optional[m3d.Manifold]]:
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
            new_target = target_manifold - nominal_bolt
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
            new_target = target_manifold - cut_tool
            new_screw = None

        if ch > 1e-6:
            orig_v = np.asarray(origin, dtype=float)
            norm_v = np.asarray(normal, dtype=float)
            r_hole = 0.5 * diameter + (0.0 if keep_screw else clr)
            c_hole = min(ch, 0.4 * diameter)
            for pf in compute_planar_faces(new_target):
                dot = float(np.dot(pf.normal, norm_v))
                if abs(dot) < 0.99:
                    continue
                along = float(np.dot(np.asarray(pf.origin, dtype=float) - orig_v, norm_v))
                if not (-0.01 <= along <= length + 0.01):
                    continue
                # Only chamfer faces that the pin actually intersects around the axis
                probe = _cone_z(along - 0.05, along + 0.05, r_hole * 0.5, r_hole * 0.5, mat, 16)
                if (pin_manifold ^ probe).volume() < 1e-6:
                    continue
                if dot > 0.0:
                    cone = _cone_z(along - c_hole, along + 0.02, r_hole, r_hole + c_hole + 0.02, mat, seg)
                else:
                    cone = _cone_z(along - 0.02, along + c_hole, r_hole + c_hole + 0.02, r_hole, mat, seg)
                new_target = new_target - cone

        return new_target, new_screw

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        pin = doc.bodies.get(self.pin_body_id)
        if not target or not pin:
            return
        new_target, new_screw = self.compute(
            target.manifold,
            pin.manifold,
            pitch=self.pitch,
            profile=self.profile,
            clearance=self.clearance,
            chamfer=self.chamfer,
            keep_screw=self.keep_screw,
            taper_lead_in=self.taper_lead_in,
        )
        target.manifold = new_target
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
        )
        feat.suppressed = data.get("suppressed", False)
        feat.exprs = dict(data.get("exprs", {}))
        return feat
