"""
Omacad - Hole Feature (Simple, Counterbore, Countersink)
"""

from typing import Dict, Any, List
import math
import numpy as np
import manifold3d as m3d
from omacad.model.kernel import CadKernel
from omacad.model.features.base import Feature, _bbox_overlap


def hole_tool(kind: str, diameter: float, depth: float, cb_diameter: float = 0.0, cb_depth: float = 0.0,
              cs_diameter: float = 0.0, cs_angle: float = 90.0, tip: str = "flat", tip_angle: float = 118.0,
              margin: float = 0.5, segments: int = 64, chamfer: float = 0.0,
              chamfer_angle: float = 45.0, chamfer_depth: float = 0.0) -> m3d.Manifold:
    """The drill: top face at z = 0, going down to z = -depth. kind: simple, counterbore, countersink."""
    r = diameter / 2.0
    top = margin
    pts = [(0.0, top)]
    chamfer = max(0.0, float(chamfer))
    chamfer_angle = min(89.0, max(1.0, float(chamfer_angle)))
    chamfer_r = r + chamfer
    chamfer_h = chamfer / math.tan(math.radians(chamfer_angle)) if chamfer else 0.0
    chamfer_depth = max(0.0, float(chamfer_depth))
    if kind == "counterbore" and cb_diameter > diameter and cb_depth > 0:
        rc = cb_diameter / 2.0
        cbd = min(cb_depth, depth)
        if chamfer_depth:
            natural_h = chamfer / math.tan(math.radians(chamfer_angle)) if chamfer else chamfer_depth
            h = min(chamfer_depth, natural_h, cbd)
            dr = h * math.tan(math.radians(chamfer_angle))
            pts += [(rc + dr, top), (rc + dr, 0.0), (rc, -h)]
        elif chamfer:
            h = min(chamfer_h, cbd)
            pts += [(rc + chamfer, top), (rc, top - h)]
        else:
            pts += [(rc, top)]
        pts += [(rc, -cbd), (r, -cbd)]
    elif kind == "countersink" and cs_diameter > diameter:
        rs = cs_diameter / 2.0
        t = math.tan(math.radians(max(10.0, min(cs_angle, 170.0))) / 2.0)
        h = (rs - r) / t
        pts += [(rs + top * t, top), (r, -min(h, depth))]
    else:
        if chamfer_depth:
            natural_h = chamfer / math.tan(math.radians(chamfer_angle)) if chamfer else chamfer_depth
            h = min(chamfer_depth, natural_h, depth)
            dr = h * math.tan(math.radians(chamfer_angle))
            pts += [(r + dr, top), (r + dr, 0.0), (r, -h)]
        else:
            pts += [(chamfer_r, top), (r, top - chamfer_h)] if chamfer else [(r, top)]
    pts.append((r, -depth))
    if tip == "angle":
        pts.append((0.0, -depth - r / math.tan(math.radians(tip_angle) / 2.0)))
    else:
        pts.append((0.0, -depth))
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area < 0:   # a cross-section must run counter-clockwise
        pts.reverse()
    return m3d.Manifold.revolve(m3d.CrossSection([[list(map(float, q)) for q in pts]]), segments)


class HoleFeature(Feature):
    """Drilled holes (Fusion 360 Hole): simple, counterbore or countersink, placed at points on faces.
    points: [{"origin": [x, y, z], "normal": [nx, ny, nz]}], the normal points out of the material."""

    def __init__(self, feature_id: str, name: str, points, hole_type: str = "simple", diameter: float = 6.0,
                 depth: float = 10.0, through: bool = False, cb_diameter: float = 12.0, cb_depth: float = 4.0,
                 cs_diameter: float = 12.0, cs_angle: float = 90.0, tip: str = "flat", tip_angle: float = 118.0,
                 chamfer: float = 0.0, chamfer_angle: float = 45.0, chamfer_depth: float = 0.0):
        super().__init__(feature_id, "hole", name)
        self.points = [{"origin": [float(x) for x in p["origin"]], "normal": [float(x) for x in p["normal"]]} for p in points]
        self.hole_type = hole_type
        self.diameter, self.depth, self.through = float(diameter), float(depth), bool(through)
        self.cb_diameter, self.cb_depth = float(cb_diameter), float(cb_depth)
        self.cs_diameter, self.cs_angle = float(cs_diameter), float(cs_angle)
        self.tip, self.tip_angle = tip, float(tip_angle)
        self.chamfer, self.chamfer_angle = max(0.0, float(chamfer)), float(chamfer_angle)
        self.chamfer_depth = max(0.0, float(chamfer_depth))

    def tools(self, doc: Any):
        """One drill per placed point, in world space."""
        out = []
        reach = 1.0
        for b in doc.bodies.values():
            bb = np.array(b.manifold.bounding_box())
            reach = max(reach, float(np.linalg.norm(bb[3:] - bb[:3])))
        depth = reach + 1.0 if self.through else max(self.depth, 0.01)
        tool = hole_tool(self.hole_type, self.diameter, depth, self.cb_diameter, self.cb_depth, self.cs_diameter,
                         self.cs_angle, "flat" if self.through else self.tip, self.tip_angle,
                         chamfer=self.chamfer, chamfer_angle=self.chamfer_angle,
                         chamfer_depth=self.chamfer_depth)
        for pt in self.points:
            n = np.array(pt["normal"], dtype=float)
            n = n / max(float(np.linalg.norm(n)), 1e-12)
            u = np.cross(n, [1.0, 0.0, 0.0])
            if np.linalg.norm(u) < 1e-6:
                u = np.cross(n, [0.0, 1.0, 0.0])
            u = u / np.linalg.norm(u)
            v = np.cross(n, u)
            out.append(tool.transform(np.column_stack([u, v, n, np.array(pt["origin"], dtype=float)]).astype(float)))
        return out

    def execute(self, doc: Any) -> None:
        tools = self.tools(doc)
        if not tools:
            return
        cutter = m3d.Manifold.batch_boolean(tools, m3d.OpType.Add) if len(tools) > 1 else tools[0]
        from omacad.model.features.base import feature_bodies
        for body in feature_bodies(doc, self):
            if not _bbox_overlap(body.manifold, cutter):
                continue
            result = body.manifold - cutter
            if result.is_empty():
                continue
            body.manifold = CadKernel.drop_slivers(result)
            body.update_render_mesh()

    def to_dict(self) -> Dict[str, Any]:
        return {"feature_id": self.feature_id, "feature_type": self.feature_type, "name": self.name, "suppressed": self.suppressed,
                "points": self.points, "hole_type": self.hole_type, "diameter": self.diameter, "depth": self.depth,
                "through": self.through, "cb_diameter": self.cb_diameter, "cb_depth": self.cb_depth,
                "cs_diameter": self.cs_diameter, "cs_angle": self.cs_angle, "tip": self.tip, "tip_angle": self.tip_angle,
                "chamfer": self.chamfer, "chamfer_angle": self.chamfer_angle,
                "chamfer_depth": self.chamfer_depth}
