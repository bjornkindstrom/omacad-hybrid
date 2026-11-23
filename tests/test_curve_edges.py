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
from test_loft import _square_loft            # noqa: E402

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


def test_cut_hollow_sphere_rims_are_closed_smooth_and_filletable():
    """Report 20261123-211745: a hollow sphere cut by another sphere must shade smoothly (no flat-patched
    rim facets), expose both rims as single closed CurveEdges, and allow Fillet/Chamfer on them."""
    from pathlib import Path
    from omacad.io.exporter import Exporter
    from omacad.model.kernel import CadKernel

    fixture = Path(__file__).parent / "data" / "cut_hollow_sphere_fillet.omacad"
    doc = Exporter.load_project(str(fixture))
    doc.timeline.features[-1].suppressed = True
    doc.timeline.recompute(doc)
    body = doc.bodies["body_sphere_1"]

    m = body.manifold.to_mesh64()
    v = np.asarray(m.vert_properties, dtype=np.float64)[:, :3]
    f = np.asarray(m.tri_verts, dtype=np.int32)
    assert int(CadKernel._flat_triangles(v, f).sum()) == 0

    curves = [e for e in body.edges if getattr(e, "kind", "") == "curve"]
    assert len(curves) == 2
    assert all(e.closed and e.is_roundable() for e in curves)

    vol_before = body.manifold.volume()
    fillet = doc.add_fillet([e.ref() for e in curves], 1.5)
    assert fillet.skipped == 0
    assert body.manifold.genus() == 0
    assert body.manifold.volume() < vol_before


def test_cylinder_on_sphere_seam_is_pickable_and_filletable():
    """Report 20261123-213454: a cylinder joined onto a hollow sphere must not emit a WrappedLoopEdge
    that encircles the cylinder (which shadows the roundable CurveEdge and fails in wrapped_round_tool)."""
    from pathlib import Path

    fixture = Path(__file__).parent / "data" / "cylinder_on_hollow_sphere_fillet.omacad"
    doc = Exporter.load_project(str(fixture))
    body = doc.bodies["body_sphere_1"]

    assert not [e for e in body.edges if e.kind == "wrapped"]
    seam = [e for e in body.edges if e.kind == "curve" and e.is_roundable()]
    assert len(seam) == 1
    assert seam[0].closed and not seam[0].convex

    vol_before = body.manifold.volume()
    fillet = doc.add_fillet([seam[0].ref()], 2.0)
    assert fillet.skipped == 0
    assert body.manifold.genus() == 0
    assert body.manifold.volume() > vol_before
