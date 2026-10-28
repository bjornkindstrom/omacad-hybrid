"""Regression test: picking an edge that is part of a LoopEdge outline (such as a plate with rounded corners).
When an arc or line segment is shared between a composite LoopEdge and a CircularEdge arc,
picking must prefer the full LoopEdge so the user can select and chamfer/fillet the contour."""
import os
from pathlib import Path
import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import LoopEdge, CircularEdge
from omacad.ui.viewport.viewport import Viewport3D
from omacad.ui.math3d import orbit_view, perspective


def test_pick_edge_prefers_loop_over_overlapping_arc():
    doc_path = str(Path(__file__).parent / "data" / "fillet_face_pick.omacad")
    doc = Exporter.load_project(doc_path)
    b = doc.bodies["body_extrude_2"]
    outer_loop = next(e for e in b.edges if getattr(e, "kind", "") == "loop" and np.allclose(np.asarray(e.polyline())[:, 2], 10.0, atol=1e-3) and len(e.polyline()) > 50)

    class MockDoc:
        bodies = doc.bodies

    class MockViewport(Viewport3D):
        def __init__(self):
            self.doc = MockDoc()
            self.edge_pick_mode = True
            self.edge_xray = False
            self._w, self._h = 2036 - 360, 1114
            self.cam_az = 170.87696587004527
            self.cam_el = 17.911718750000006
            self.cam_dist = 99.63236863613498
            self.cam_target = np.array([-4.469699859619141, 11.18025016784668, 5.0])

        def width(self):
            return self._w

        def height(self):
            return self._h

        def get_matrices(self):
            view = orbit_view(self.cam_target, self.cam_dist, self.cam_az, self.cam_el)
            proj = perspective(45.0, self._w / self._h, max(0.5, self.cam_dist * 0.01), self.cam_dist + 5000.0)
            return proj, view, np.eye(4)

        def world_to_screen(self, p):
            proj, view, _ = self.get_matrices()
            mvp = proj @ view
            v = mvp @ np.array([p[0], p[1], p[2], 1.0], dtype=np.float32)
            if v[3] <= 0:
                return None
            ndc = v[:3] / v[3]
            return ((ndc[0] * 0.5 + 0.5) * self._w, (1.0 - (ndc[1] * 0.5 + 0.5)) * self._h)

    vp = MockViewport()

    # Test an unblocked segment on the corner arc where both LoopEdge and CircularEdge overlap
    # In outer_loop.pts, segment 24 is on a rounded corner arc (z=10: the Move turns the outline to the top)
    s0 = vp.world_to_screen(outer_loop.pts[24])
    s1 = vp.world_to_screen(outer_loop.pts[25])
    assert s0 is not None and s1 is not None
    sx = (s0[0] + s1[0]) / 2.0
    sy = (s0[1] + s1[1]) / 2.0

    picked = vp._pick_edge(sx, sy)
    assert isinstance(picked, LoopEdge)
    assert picked.same_as(outer_loop)
