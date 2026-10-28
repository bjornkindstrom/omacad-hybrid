"""The corner lines of a twisted extrude or a loft are curves, not straight edges or circles, and could not be
selected. They are free-form creases (`CurveEdge`): hover/pick, find again from a ref, path for a Pipe; a Fillet
skips them instead of failing."""
import os
import sys

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import edge_from_ref
from omacad.model.measure import measure_3d
from omacad.ui.math3d import camera_matrices
from omacad.ui.viewport.viewport import Viewport3D

sys.path.insert(0, os.path.dirname(__file__))
from test_loft_twist import _square_loft            # noqa: E402

TWISTED = os.path.join(os.path.dirname(__file__), "data", "twisted_extrude_on_box.omacad")


def _curves(doc):
    return [e for b in doc.bodies.values() for e in b.edges if e.kind == "curve"]


def test_twisted_extrude_and_loft_have_four_corner_curves():
    for doc in (Exporter.load_project(TWISTED), _square_loft(45.0)):
        curves = _curves(doc)
        assert len(curves) == 4
        assert all(e.length > 25 and not e.closed for e in curves)
        top = max(e.pts[:, 2].max() for e in curves)
        bottom = min(c.pts[:, 2].min() for c in curves)
        assert all(abs(e.pts[:, 2].min() - bottom) < 1e-6 for e in curves)
        assert all(abs(e.pts[:, 2].max() - top) < 1e-6 for e in curves)
    assert not _curves(_square_loft(0.0))                       # untwisted: straight lines only


def test_a_corner_curve_is_picked_found_again_and_measured():
    doc = _square_loft(45.0)
    body = next(iter(doc.bodies.values()))
    edge = _curves(doc)[0]

    class View(Viewport3D):
        def __init__(self):
            self.doc, self.edge_pick_mode, self.plane_pick_mode, self.edge_xray = doc, True, False, False
            self.cam_az, self.cam_el, self.cam_dist, self.cam_target = 30.0, 35.0, 120.0, np.array([0.0, 0.0, 15.0])

        def width(self):
            return 1400

        def height(self):
            return 900

        def get_matrices(self):
            proj, view = camera_matrices(self.cam_target, self.cam_dist, self.cam_az, self.cam_el, 1400 / 900)
            return proj, view, np.eye(4)

    vp = View()
    for i in (len(edge.pts) // 3, len(edge.pts) // 2):
        s = vp.world_to_screen(edge.pts[i])
        picked = vp._pick_edge(*s) if s else None
        if picked is not None and picked.kind == "curve":
            assert any(picked.same_as(c) for c in _curves(doc))
            break
    else:
        raise AssertionError("no corner curve could be picked")
    assert edge_from_ref(edge.ref(), body.edges).same_as(edge)
    assert measure_3d([edge])[0][0].startswith("Curve length")


def test_pipe_runs_along_a_corner_curve_and_fillet_skips_it():
    doc = _square_loft(45.0)
    edge = _curves(doc)[0]
    doc.add_fillet([edge.ref()], 1.0)
    fillet = next(f for f in doc.timeline.features if f.feature_type == "fillet")
    assert fillet.skipped == 1
    doc.add_pipe(("@edges", [edge.ref()]), 2.0)
    pipe = [b for b in doc.bodies.values() if b.name.startswith("Pipe")][0]
    assert pipe.manifold.volume() > 0.8 * np.pi * 1.0 ** 2 * edge.length
