"""After an annular extrude (hole cut in a cylinder), both rim edges must be selectable from any angle."""
import numpy as np
from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.faces import CircularEdge
from omacad.ui.math3d import camera_matrices
from omacad.ui.viewport.viewport import Viewport3D

DOC = Path(__file__).parent / "data" / "extrude_ring_edge_pick.omacad"


def test_extrude_ring_edge_picking_from_shallow_angle():
    """Edge picking on shallow-view rims must test visibility at the closest point on the edge, not the segment midpoint."""
    doc = Exporter.load_project(str(DOC))
    doc.timeline.recompute(doc)

    body = next(iter(doc.bodies.values()))

    # Find the inner circular edges created by the extrude
    inner_edges = [e for e in body.edges if isinstance(e, CircularEdge)
                   and abs(e.radius - 10.0) < 0.5]

    assert len(inner_edges) == 2, f"Expected 2 inner edges, got {len(inner_edges)}"

    # Test from a shallow viewing angle (similar to the user's report)
    class MockViewport(Viewport3D):
        def __init__(self):
            self.doc = doc
            self.edge_pick_mode = True
            self.plane_pick_mode = False
            self.edge_xray = False
            self._w, self._h = 2048, 1122
            # Shallow angle (low elevation)
            self.cam_az, self.cam_el, self.cam_dist = 144.296875, 28.946875, 124.7076644897461
            self.cam_target = np.array([0.0, 0.0, 20.0])

        def width(self):
            return self._w

        def height(self):
            return self._h

        def get_matrices(self):
            proj, view = camera_matrices(self.cam_target, self.cam_dist, self.cam_az,
                                        self.cam_el, self._w / self._h)
            return proj, view, np.eye(4)

    vp = MockViewport()

    # Test picking the inner circular edge at z=30 from multiple angles
    inner_at_top = [e for e in inner_edges if abs(e.center[2] - 30.0) < 1.0][0]

    for angle in [0, 90, 180, 270]:
        point = np.array([10.0 * np.cos(np.radians(angle)),
                         10.0 * np.sin(np.radians(angle)),
                         30.0])
        sx, sy = vp.world_to_screen(point)

        picked = vp._pick_edge(sx, sy)
        assert picked is not None, f"Failed to pick inner top edge at angle {angle}, screen pos ({sx:.0f}, {sy:.0f})"
        assert picked.same_as(inner_at_top), f"Wrong edge picked at angle {angle}"
