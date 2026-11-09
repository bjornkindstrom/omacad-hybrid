"""
Omacad - Smart Joint Feature
Connects bodies with a kinematic joint (revolute/hinge or slider) and configurable min/max limits.
"""

from typing import Dict, Any, Optional, List, Tuple
import math
import numpy as np
import manifold3d as m3d
from omacad.model.features.base import Feature, Body


def axis_angle_matrix(axis, angle_deg: float, pivot=None) -> np.ndarray:
    """Returns a 4x4 homogenous matrix for rotation by angle_deg around axis passing through pivot."""
    axis = np.asarray(axis, dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        axis = np.array([0.0, 0.0, 1.0])
    else:
        axis = axis / norm
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    ux, uy, uz = axis
    K = np.array([
        [0.0, -uz, uy],
        [uz, 0.0, -ux],
        [-uy, ux, 0.0]
    ], dtype=float)
    R = np.eye(3) * cos_a + (1.0 - cos_a) * np.outer(axis, axis) + sin_a * K
    M = np.eye(4, dtype=float)
    M[:3, :3] = R
    if pivot is not None:
        p = np.asarray(pivot, dtype=float)
        M[:3, 3] = p - R @ p
    return M


def slider_matrix(axis, distance: float) -> np.ndarray:
    """Returns a 4x4 homogenous matrix for translation along axis by distance."""
    axis = np.asarray(axis, dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-9:
        axis = np.array([0.0, 0.0, 1.0])
    else:
        axis = axis / norm
    M = np.eye(4, dtype=float)
    M[:3, 3] = axis * float(distance)
    return M


def infer_joint_from_edge(edge: Any, body: Optional[Body] = None) -> Tuple[str, np.ndarray, np.ndarray]:
    """Infers (joint_type, origin, axis) from a picked body edge."""
    kind = getattr(edge, "kind", "")
    if kind == "circle":
        center = np.asarray(edge.center, dtype=float)
        axis = np.asarray(edge.axis, dtype=float)
        norm = np.linalg.norm(axis)
        if norm > 1e-9:
            axis = axis / norm
        else:
            axis = np.array([0.0, 0.0, 1.0])
        return "revolute", center, axis
    elif kind == "line":
        p0 = np.asarray(edge.p0, dtype=float)
        p1 = np.asarray(edge.p1, dtype=float)
        vec = p1 - p0
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            axis = vec / norm
        else:
            axis = np.array([0.0, 1.0, 0.0])
        return "revolute", p0, axis
    if body is not None and getattr(body, "manifold", None):
        bb = body.manifold.bounding_box()
        center = (np.array(bb[:3]) + np.array(bb[3:])) * 0.5
    else:
        center = np.array([0.0, 0.0, 0.0])
    return "revolute", center, np.array([0.0, 0.0, 1.0])


class JointFeature(Feature):
    """Kinematic joint (Revolute / Hinge or Slider) between bodies with min/max limits.

    Revolute: rotates around an axis line (origin, axis) by `value` degrees.
    Slider: translates along `axis` by `value` mm.
    Limits: if `limits_enabled`, `value` is clamped to `[min_limit, max_limit]`.
    """

    JOINT_TYPES = ("revolute", "slider")

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        ref_body_id: Optional[str] = None,
        joint_type: str = "revolute",
        origin: Any = (0.0, 0.0, 0.0),
        axis: Any = (0.0, 0.0, 1.0),
        value: float = 0.0,
        limits_enabled: bool = True,
        min_limit: float = 0.0,
        max_limit: float = 90.0,
        smart_ref: Optional[dict] = None,
    ):
        super().__init__(feature_id, "joint", name)
        self.target_body_id = target_body_id
        self.ref_body_id = ref_body_id
        self.joint_type = joint_type if joint_type in self.JOINT_TYPES else "revolute"
        self.origin = np.asarray(origin, dtype=float).tolist()
        norm = np.linalg.norm(axis)
        self.axis = (np.asarray(axis, dtype=float) / (norm if norm > 1e-9 else 1.0)).tolist()
        self.limits_enabled = bool(limits_enabled)
        self.min_limit = float(min(min_limit, max_limit) if limits_enabled else min_limit)
        self.max_limit = float(max(min_limit, max_limit) if limits_enabled else max_limit)
        self.value = float(self.clamp(value))
        self.smart_ref = smart_ref
        self.applied: Optional[np.ndarray] = None

    def clamp(self, val: float) -> float:
        if not self.limits_enabled:
            return float(val)
        return float(np.clip(val, self.min_limit, self.max_limit))

    def set_value(self, val: float):
        self.value = self.clamp(val)

    def matrix(self, val: Optional[float] = None) -> np.ndarray:
        v = self.clamp(self.value if val is None else val)
        if self.joint_type == "revolute":
            return axis_angle_matrix(self.axis, v, pivot=self.origin)
        elif self.joint_type == "slider":
            return slider_matrix(self.axis, v)
        return np.eye(4, dtype=float)

    def execute(self, doc: Any) -> None:
        self.applied = None
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return
        mat = self.matrix()
        self.applied = mat
        target.manifold = target.manifold.transform(mat[:3, :])
        target.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "ref_body_id": self.ref_body_id,
            "joint_type": self.joint_type,
            "origin": list(self.origin),
            "axis": list(self.axis),
            "value": float(self.value),
            "limits_enabled": bool(self.limits_enabled),
            "min_limit": float(self.min_limit),
            "max_limit": float(self.max_limit),
            "smart_ref": self.smart_ref,
        }
