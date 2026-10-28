"""
Omacad - Boolean, Split and Delete Body Features
"""

from typing import Dict, Any, Optional, List
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.features.base import Feature, Body


class DeleteBodyFeature(Feature):
    """Removes a body from the model (a step in the history, so a rebuild keeps it removed)."""

    def __init__(self, feature_id: str, name: str, target_body_id: str):
        super().__init__(feature_id, "delete_body", name)
        self.target_body_id = target_body_id

    def execute(self, doc: Any) -> None:
        doc.bodies.pop(self.target_body_id, None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
        }


class CombineFeature(Feature):
    def __init__(self, feature_id: str, name: str, target_body_id: str, tool_body_id: str, operation: str = "join", keep_tool: bool = False):
        super().__init__(feature_id, "combine", name)
        self.target_body_id = target_body_id
        self.tool_body_id = tool_body_id
        self.operation = operation  # join, cut, intersect
        self.keep_tool = keep_tool

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        tool = doc.bodies.get(self.tool_body_id)
        if not target or not tool:
            return

        target.manifold = CadKernel.boolean_op(target.manifold, tool.manifold, self.operation)
        target.update_render_mesh()
        # Remove tool body after combine unless keep_tool is True
        if not self.keep_tool:
            doc.bodies.pop(self.tool_body_id, None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "tool_body_id": self.tool_body_id,
            "operation": self.operation,
            "keep_tool": self.keep_tool,
        }


class SplitBodyFeature(Feature):
    """Splits an existing solid body using a plane (construction plane or origin plane) into two separate bodies."""

    def __init__(
        self,
        feature_id: str,
        name: str,
        target_body_id: str,
        plane_id: str,
        plane_origin: Optional[List[float]] = None,
        plane_normal: Optional[List[float]] = None,
        new_body_name: Optional[str] = None,
        frozen_source: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(feature_id, "split_body", name)
        self.target_body_id = target_body_id
        self.plane_id = plane_id
        self.plane_origin = [float(x) for x in plane_origin] if plane_origin is not None else None
        self.plane_normal = [float(x) for x in plane_normal] if plane_normal is not None else None
        self.new_body_name = new_body_name
        self.frozen_source = frozen_source

    def execute(self, doc: Any) -> None:
        target = doc.bodies.get(self.target_body_id)
        if not target:
            return

        origin, normal = None, None
        if hasattr(doc, "construction_planes") and self.plane_id in doc.construction_planes:
            cp = doc.construction_planes[self.plane_id]
            origin = np.array(cp["origin"], dtype=float)
            normal = np.array(cp["normal"], dtype=float)
        elif hasattr(doc, "origin_planes") and self.plane_id in doc.origin_planes:
            op = doc.origin_planes[self.plane_id]
            origin = np.array(op.origin, dtype=float)
            normal = np.array(op.normal, dtype=float)
        elif self.plane_origin is not None and self.plane_normal is not None:
            origin = np.array(self.plane_origin, dtype=float)
            normal = np.array(self.plane_normal, dtype=float)

        if origin is None or normal is None:
            return

        norm = float(np.linalg.norm(normal))
        if norm < 1e-9:
            return
        normal = normal / norm
        d = float(np.dot(normal, origin))

        # New split steps cut a saved copy of the source solid, so edits to sketches and
        # features before this step cannot reshape either resulting body. Older files
        # without a snapshot retain their original parametric behavior.
        source = target.manifold
        if self.frozen_source is not None:
            verts = np.asarray(self.frozen_source["vertices"], dtype=np.float32)
            tris = np.asarray(self.frozen_source["triangles"], dtype=np.int32)
            source = m3d.Manifold(m3d.Mesh(vert_properties=verts, tri_verts=tris))

        # Split manifold into two watertight solid bodies
        part1 = source.trim_by_plane(normal, d)
        part2 = source.trim_by_plane(-normal, -d)

        if part1.is_empty() or part2.is_empty() or part1.volume() < 1e-6 or part2.volume() < 1e-6:
            return

        target.manifold = part1
        target.update_render_mesh()

        new_body_id = f"body_{self.feature_id}"
        name = self.new_body_name or f"{target.name} (Split)"
        new_body = Body(
            body_id=new_body_id,
            name=name,
            manifold=part2,
            color=list(target.color),
        )
        new_body.update_render_mesh()
        doc.bodies[new_body_id] = new_body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "name": self.name,
            "suppressed": self.suppressed,
            "target_body_id": self.target_body_id,
            "plane_id": self.plane_id,
            "plane_origin": self.plane_origin,
            "plane_normal": self.plane_normal,
            "new_body_name": self.new_body_name,
            "frozen_source": self.frozen_source,
        }
