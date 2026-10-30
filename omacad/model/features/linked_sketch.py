"""
Omacad - Linked / Parametric Copied Sketch Feature
"""

from typing import Dict, Any, Optional
import copy
import numpy as np
from omacad.model.features.base import Feature
from omacad.model.sketch import Sketch, SketchPlane, scale_entity


def plane_from_spec(spec: Any, doc: Any) -> SketchPlane:
    """Converts a plane identifier or dict spec into a SketchPlane."""
    if isinstance(spec, SketchPlane):
        return spec
    if isinstance(spec, str):
        if spec.upper() in doc.origin_planes:
            return doc.origin_planes[spec.upper()]
        if hasattr(doc, "construction_planes") and spec in doc.construction_planes:
            return doc.construction_plane(spec)
    if isinstance(spec, dict):
        if "normal" in spec and "origin" in spec:
            n = np.asarray(spec["normal"], dtype=np.float32)
            o = np.asarray(spec["origin"], dtype=np.float32)
            u = np.asarray(spec.get("u_axis", [1, 0, 0]), dtype=np.float32) if "u_axis" in spec else None
            v = np.asarray(spec.get("v_axis", [0, 1, 0]), dtype=np.float32) if "v_axis" in spec else None
            p = SketchPlane.from_face(n, o, spec.get("name", "PLANE"))
            p.origin = o
            if u is not None and v is not None:
                p.u_axis = u
                p.v_axis = v
            return p
    return doc.origin_planes.get("XY", SketchPlane())


class LinkedSketchFeature(Feature):
    """
    Parametric copy of a sketch onto another plane with optional scaling.
    Whenever the source sketch or target plane changes, recompute updates the copy.
    """

    def __init__(
        self,
        feature_id: str,
        name: str,
        source_sketch_id: str,
        target_sketch_id: str,
        target_plane_spec: Any,
        scale: float = 1.0,
    ):
        super().__init__(feature_id, "linked_sketch", name)
        self.source_sketch_id = source_sketch_id
        self.target_sketch_id = target_sketch_id
        self.target_plane_spec = target_plane_spec
        self.scale = float(scale) if float(scale) != 0.0 else 1.0

    def execute(self, doc: Any) -> None:
        src = doc.sketches.get(self.source_sketch_id)
        if src is None:
            raise ValueError(f"Source sketch '{self.source_sketch_id}' not found")

        target_plane = plane_from_spec(self.target_plane_spec, doc)
        
        # Build or update the target sketch
        target = doc.sketches.get(self.target_sketch_id)
        if target is None:
            target = Sketch(self.target_sketch_id, self.name, target_plane)
        else:
            target.plane = target_plane
            target.name = self.name
            target.entities.clear()
            target.dimensions.clear()
            target.constraints.clear()

        # Map local (u, v) from source sketch directly to target sketch local (u, v) and scale
        s = self.scale

        for ent in src.entities:
            copied = copy.deepcopy(ent)
            if abs(s - 1.0) > 1e-9:
                scale_entity(copied, s, (0.0, 0.0))
            target.entities.append(copied)

        target.visible = True
        doc.refresh_sketch_references(target)
        target.solve_profiles()
        doc.sketches[self.target_sketch_id] = target

    def _map_entity_planes(self, ent: Any, src_plane: SketchPlane, dst_plane: SketchPlane) -> None:
        def conv(pt):
            w = src_plane.uv_to_world(float(pt[0]), float(pt[1]))
            return dst_plane.world_to_uv(w)

        from omacad.model.sketch_entities import (
            SketchLine, SketchRect, SketchCenterRect, SketchCircle,
            SketchArc, SketchSlot, SketchText, SketchSpline
        )
        if isinstance(ent, (SketchLine, SketchRect)):
            ent.p1 = conv(ent.p1)
            ent.p2 = conv(ent.p2)
        elif isinstance(ent, SketchCenterRect):
            ent.center = conv(ent.center)
            ent.corner = conv(ent.corner)
        elif isinstance(ent, SketchCircle):
            ent.center = conv(ent.center)
        elif isinstance(ent, SketchArc):
            ent.p_start = conv(ent.p_start)
            ent.p_mid = conv(ent.p_mid)
            ent.p_end = conv(ent.p_end)
        elif isinstance(ent, SketchSlot):
            ent.center1 = conv(ent.center1)
            ent.center2 = conv(ent.center2)
        elif isinstance(ent, SketchText):
            ent.anchor = conv(ent.anchor)
        elif isinstance(ent, SketchSpline):
            ent.points = [conv(p) for p in ent.points]

    def to_dict(self) -> Dict[str, Any]:
        plane_spec = self.target_plane_spec
        if isinstance(plane_spec, SketchPlane):
            plane_spec = {
                "name": plane_spec.name,
                "origin": plane_spec.origin.tolist() if hasattr(plane_spec.origin, "tolist") else list(plane_spec.origin),
                "u_axis": plane_spec.u_axis.tolist() if hasattr(plane_spec.u_axis, "tolist") else list(plane_spec.u_axis),
                "v_axis": plane_spec.v_axis.tolist() if hasattr(plane_spec.v_axis, "tolist") else list(plane_spec.v_axis),
                "normal": plane_spec.normal.tolist() if hasattr(plane_spec.normal, "tolist") else list(plane_spec.normal),
            }
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "source_sketch_id": self.source_sketch_id,
            "target_sketch_id": self.target_sketch_id,
            "target_plane_spec": plane_spec,
            "scale": self.scale,
        }
