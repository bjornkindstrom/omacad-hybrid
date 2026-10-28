"""A boolean annular cut must preserve both circular edges for Fillet picking."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import CircularEdge
from omacad.ui.math3d import camera_matrices
from omacad.ui.viewport.viewport import Viewport3D

DOC = Path(__file__).parent / "data" / "cylinder_annular_cut_edge_pick.omacad"


def test_annular_cut_keeps_and_picks_its_outer_circular_edge():
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    outer = [e for e in body.edges if isinstance(e, CircularEdge)
             and abs(e.center[2] - 30.0) < .01 and abs(e.radius - 20.0) < .01]
    inner = [e for e in body.edges if isinstance(e, CircularEdge)
             and abs(e.center[2] - 30.0) < .01 and abs(e.radius - 10.0) < .01]
    assert len(outer) == 1
    assert len(inner) == 1

    class MockViewport(Viewport3D):
        def __init__(self):
            self.doc = doc
            self.edge_pick_mode = True
            self.plane_pick_mode = False
            self.edge_xray = False
            self._w, self._h = 742, 1000
            self.cam_az, self.cam_el, self.cam_dist = 18.953125, 20.665625, 76.262237973452
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
    # The visible inner edge of the annular face lands within sub-pixel boolean
    # tolerance of its triangulated boundary. It must still pick the face.
    point = np.array([10 * np.cos(np.radians(330)), 10 * np.sin(np.radians(330)), 30.0])
    sx, sy = vp.world_to_screen(point)
    hit = vp._pick_plane_target(sx, sy)
    assert hit is not None and hit[0] == "face" and hit[1].index == 0
    sketch, profile_index = doc.face_to_sketch(hit[1])
    assert profile_index is not None
    assert abs(sketch.profiles[profile_index].area - hit[1].area) < 1.0

    for edge, radius in ((outer[0], 20.0), (inner[0], 10.0)):
        point = np.array([radius * np.cos(np.radians(330)), radius * np.sin(np.radians(330)), 30.0])
        sx, sy = vp.world_to_screen(point)
        picked = vp._pick_edge(sx, sy)
        assert picked is not None and picked.same_as(edge)
