"""A removable slip-over lid from the projected envelope of a body's end."""
import math
import numpy as np
import manifold3d as m3d
from shapely.geometry import Polygon
from omacad.model.features.base import Feature, Body


class LidFeature(Feature):
    PARAMS = ("clearance", "thickness", "overlap", "direction", "edge_kind", "edge_size")
    DIRECTIONS = {"+Z": (0, 0, 1), "-Z": (0, 0, -1), "+X": (1, 0, 0),
                  "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0)}

    def __init__(self, feature_id, name, target_body_id, clearance=0.25,
                 thickness=2.0, overlap=5.0, direction="+Z", edge_kind="none", edge_size=0.5):
        super().__init__(feature_id, "lid", name)
        self.target_body_id = target_body_id
        self.clearance, self.thickness, self.overlap = map(float, (clearance, thickness, overlap))
        self.direction = direction
        self.edge_kind = edge_kind
        self.edge_size = float(edge_size)

    def build(self, source):
        if (not all(math.isfinite(v) for v in (self.clearance, self.thickness, self.overlap))
                or self.clearance < 0 or self.thickness <= 0 or self.overlap <= 0):
            raise ValueError("Clearance must be nonnegative; thickness and overlap must be positive.")
        if self.direction not in self.DIRECTIONS:
            raise ValueError("Choose a valid lid direction.")
        if self.edge_kind not in ("none", "chamfer", "fillet"):
            raise ValueError("Choose None, Chamfer or Fillet for the top edge.")
        if not math.isfinite(self.edge_size) or self.edge_size < 0:
            raise ValueError("Edge size must be finite and nonnegative.")
        if self.edge_kind != "none" and not 0 < self.edge_size < self.thickness:
            raise ValueError("Edge size must be positive and smaller than the lid thickness.")
        n = np.array(self.DIRECTIONS[self.direction], dtype=float)
        u = np.cross((0, 1, 0) if abs(n[1]) < .9 else (1, 0, 0), n)
        v = np.cross(n, u)
        rotation = np.array([u, v, n])
        local = source.transform(np.column_stack((rotation, np.zeros(3))))
        bounds = local.bounding_box()
        if self.overlap >= bounds[5] - bounds[2]:
            raise ValueError("Overlap must be smaller than the body height in the lid direction.")
        bottom = bounds[5] - self.overlap
        band = local.trim_by_plane((0, 0, 1), bottom)
        # Project the entire overlap, not just one slice: tapered/curved walls must clear too.
        rings = band.project().to_polygons()
        profile = m3d.CrossSection()
        for ring in rings:
            poly = Polygon(ring)
            if poly.exterior.is_ccw:
                profile = profile + m3d.CrossSection([ring])
        if profile.is_empty() or len(profile.decompose()) != 1:
            raise ValueError("The selected end must have one connected outline. Choose another direction or overlap.")
        inside = profile.offset(self.clearance, m3d.JoinType.Miter)
        outside = profile.offset(self.clearance + self.thickness, m3d.JoinType.Miter)
        skirt = (outside - inside).extrude(self.overlap + self.clearance)
        roof = outside.extrude(self.thickness).translate((0, 0, self.overlap + self.clearance))
        lid = (skirt + roof).translate((0, 0, bottom))
        if self.edge_kind != "none":
            from omacad.model.faces import compute_planar_edges
            from omacad.model.kernel import CadKernel
            top = bounds[5] + self.clearance + self.thickness
            tools = []
            for edge in compute_planar_edges(lid):
                kind = getattr(edge, "kind", "line")
                if kind == "line":
                    points = np.array([edge.p0, edge.p1])
                elif kind == "circle":
                    if abs(edge.axis[2]) < .999:
                        continue
                    points = np.array([edge.center])
                elif kind == "loop":
                    points = np.asarray(edge.pts)
                else:
                    continue
                if edge.convex and np.allclose(points[:, 2], top, atol=1e-6, rtol=0):
                    tools.append(CadKernel.round_tool(edge, self.edge_size, self.edge_kind))
            if not tools:
                raise ValueError("Cannot finish this lid's top edge.")
            for tool in tools:
                if tool.is_empty():
                    raise ValueError("Cannot finish this lid's top edge at the requested size.")
                lid = lid - tool
        if lid.is_empty() or lid.status() != m3d.Error.NoError or len(lid.decompose()) != 1:
            raise ValueError("Cannot create a connected lid with these dimensions.")
        return lid.transform(np.column_stack((rotation.T, np.zeros(3))))

    def execute(self, doc):
        if self.target_body_id not in doc.bodies:
            raise ValueError("The source body for this lid is missing.")
        body = Body("body_" + self.feature_id, self.name, self.build(doc.bodies[self.target_body_id].manifold))
        body.is_lid = True
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self):
        return dict(feature_id=self.feature_id, feature_type=self.feature_type, name=self.name,
                    suppressed=self.suppressed, target_body_id=self.target_body_id,
                    **{key: getattr(self, key) for key in self.PARAMS})
