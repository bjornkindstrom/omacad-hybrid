"""Tests for selecting face boundary edges/loops in edge pick mode (Fusion 360 parity).
Clicking a planar face during fillet/chamfer edge pick selects all boundary loops / edges
of the face.
"""
import os
from pathlib import Path
import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import LoopEdge, PlanarFace
from omacad.model.features.fillet import FilletFeature
from omacad.ui.viewport.viewport import Viewport3D
from omacad.ui.math3d import orbit_view, perspective


def test_fillet_face_click_selects_all_boundary_loops():
    doc_path = str(Path(__file__).parent / "data" / "fillet_face_pick.omacad")
    doc = Exporter.load_project(doc_path)
    b = doc.bodies["body_extrude_2"]

    # The patterned face with the 13 loops. Move (ry -180 about the centre) turns it to the top, z=10, normal +z; the old
    # edge cache handed back the edges from before the move, so this test used to look at z=0 (#105).
    face44 = next(f for f in b.faces if np.allclose(f.normal, [0, 0, 1], atol=1e-3) and abs(f.origin[2] - 10.0) < 1e-4)

    class MockDoc:
        bodies = doc.bodies

    class MockViewport(Viewport3D):
        def __init__(self):
            self.doc = MockDoc()
            self.edge_pick_mode = True
            self.edge_xray = False
            self.hover_edge = None
            self.hover_face = self.hover_surface = None
            self.selected_edges = []
            self._w, self._h = 2036 - 360, 1114
            self.cam_az = 170.87696587004527
            self.cam_el = 17.911718750000006        # from above: the patterned face is in sight, not behind the fillets
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

        def update(self):
            pass

    vp = MockViewport()

    # _edges_of_face finds the 13 closed boundary/hole loops of face 44 and the straight sides of its hexagon holes
    face_edges = vp._edges_of_face(face44, b)
    assert sum(isinstance(e, LoopEdge) for e in face_edges) == 13
    assert sum(e.kind == "line" for e in face_edges) == 338

    # Pick point inside the face interior (away from edge boundary)
    interior_pt = np.array([-7.68197464, -26.07341804, 10.0])  # the face's most inner point, 2.9 mm from its edges
    vp.cam_target, vp.cam_dist = interior_pt, 40.0             # close enough that 2.9 mm is well past the pick radius
    scr = vp.world_to_screen(interior_pt)
    assert scr is not None
    sx, sy = scr

    # At this interior screen point, _pick_edge should be None
    # but _pick_face should hit face 44
    assert vp._pick_edge(sx, sy) is None
    hit = vp._pick_face(sx, sy)
    assert hit is not None
    hit_body, hit_face = hit
    assert hit_face.index == face44.index

    # Test hover update sets hover_face
    vp._update_edge_hover(sx, sy)
    assert vp.hover_edge is None
    assert vp.hover_face is not None
    assert vp.hover_face.index == face44.index

    # Simulate click logic on face
    edges = vp._edges_of_face(hit_face, hit_body)
    for fe in edges:
        if not any(vp._same_edge(k, fe) for k in vp.selected_edges):
            vp.selected_edges.append(fe)

    assert len(vp.selected_edges) == len(face_edges)

    # Applying chamfer with all these edges succeeds without error or skipped items
    feat = FilletFeature("test_chamfer", "Chamfer", [e.ref() for e in vp.selected_edges], 1.0, kind="chamfer")
    doc.timeline.features.append(feat)
    doc.timeline.recompute(doc)
    assert feat.skipped == 0
