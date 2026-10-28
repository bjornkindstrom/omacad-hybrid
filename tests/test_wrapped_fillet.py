"""Request #63: select and round the nonplanar rim/floor of a wrapped deboss."""
from pathlib import Path
import math

import manifold3d as m3d
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import edge_from_ref
from omacad.model.features.fillet import FilletFeature
from omacad.model.kernel import CadKernel
from omacad.model.wrapped_edges import WrappedLoopEdge, wrapped_round_tool
from omacad.ui.viewport.viewport import Viewport3D

DATA = Path(__file__).parent / "data" / "wrapped_deboss_fillet.omacad"


def load():
    return Exporter.load_project(str(DATA))


def test_report_has_both_pickable_wrapped_rims():
    doc = load()
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "wrapped"]
    assert len(edges) == 2
    assert {e.convex for e in edges} == {True, False}
    assert sorted(e.radius for e in edges) == pytest.approx([19, 20], abs=.01)
    for e in edges:
        assert edge_from_ref(e.ref(), body.edges) is e
        size = FilletFeature._safe_edge_size(body, e, 2)
        assert .48 < size < .50


@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
@pytest.mark.parametrize("convex", [True, False])
def test_report_rounding_survives_save_rebuild_and_undo(kind, convex):
    doc = load()
    body = next(iter(doc.bodies.values()))
    before = body.manifold.volume()
    edge = next(e for e in body.edges if e.kind == "wrapped" and e.convex == convex)
    feature = doc.add_fillet([edge.ref()], .25, kind=kind)
    assert feature.skipped == 0
    after = next(iter(doc.bodies.values())).manifold.volume()
    assert .1 < abs(after-before) < 4
    assert (after < before) == convex
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert restored.timeline.features[-1].skipped == 0
    assert next(iter(restored.bodies.values())).manifold.volume() == pytest.approx(after, abs=1e-6)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(before, abs=1e-6)
    doc.redo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(after, abs=1e-6)


def test_cylindrical_face_can_select_its_nonplanar_boundary():
    app = QApplication.instance() or QApplication([])
    doc = load()
    vp = Viewport3D(doc)
    vp.resize(1000, 800)
    vp.azimuth, vp.elevation, vp.distance = 0., 0., 80.
    vp.target = np.array([0., 0., 10.], dtype=np.float32)
    vp.edge_pick_mode = True
    point = vp.world_to_screen(np.array([0., -19., 10.]))
    body, face = vp._pick_face(*point)
    edges = vp._edges_of_face(face, body)
    assert len(edges) == 1 and edges[0].kind == "wrapped" and not edges[0].convex
    mouse = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(*point), QPointF(*point),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    vp.mousePressEvent(mouse)
    release = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(*point), QPointF(*point),
                          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    vp.mouseReleaseEvent(release)
    assert len(vp.selected_edges) == 1
    assert vp.selected_edges[0].same_as(edges[0])
    vp.edge_pick_mode = False
    hit = vp._pick_face(*point)
    assert hit is None or hit[1].index >= 0  # curved faces never become sketch planes
    vp.close()


def test_wrapped_chamfer_volume_matches_cylindrical_integral():
    # Rounding a raised rectangular patch. At radial depth z in [-r,0],
    # the removed band has UV area 2*(w+h)*(r+z)-4*(r+z)^2.
    # Wrapping multiplies its volume element by (1+z/R).
    r, radius, w, h = .25, 20., 10., 15.
    corners = np.array([[-w/2, 0], [w/2, 0], [w/2, h], [-w/2, h]])
    uv = []
    for a, b in zip(corners, np.roll(corners, -1, axis=0)):
        for t in np.linspace(0, 1, math.ceil(np.linalg.norm(b-a)/.2), endpoint=False):
            uv.append(a+(b-a)*t)
    uv = np.asarray(uv)
    def wrap(p):
        theta = p[:, 0]/radius
        return np.column_stack(((radius+p[:, 2])*np.sin(theta),
                                -(radius+p[:, 2])*np.cos(theta), p[:, 1]))
    pts = wrap(np.column_stack((uv, np.zeros(len(uv)))))
    edge = WrappedLoopEdge(pts, np.array([0.,0.,1.]), np.zeros(3), radius,
                           np.array([0.,-1.,0.]), np.array([1.,0.,0.]), True, ())
    base = m3d.Manifold.cube((w,h,2)).translate((-w/2,0,-2)).refine_to_length(.2).warp_batch(wrap)
    tool = wrapped_round_tool(edge, r, "chamfer")
    removed = (base ^ tool).volume()
    expected = (w+h)*r*r - 4*r**3/3 - (w+h)*r**3/(3*radius) + r**4/(3*radius)
    assert removed == pytest.approx(expected, rel=.02)


def test_report_at_original_high_curve_quality():
    from omacad.model import quality
    quality.set_circle_segments(360)
    doc = load()
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "wrapped"]
    assert len(edges) == 2
    assert sorted(e.radius for e in edges) == pytest.approx([19, 20], abs=.01)
    feature = doc.add_fillet([e.ref() for e in edges], .25)
    assert feature.skipped == 0
    assert next(iter(doc.bodies.values())).manifold.status() == m3d.Error.NoError


def test_wrapped_rounding_is_invariant_under_body_rotation():
    body = next(iter(load().bodies.values()))
    edge = next(e for e in body.edges if e.kind == "wrapped" and e.convex)
    delta = body.manifold.volume()-(body.manifold-CadKernel.round_tool(edge, .25, "fillet")).volume()
    body.manifold = body.manifold.rotate([20, 35, 10])
    body.update_render_mesh()
    edge = next(e for e in body.edges if e.kind == "wrapped" and e.convex)
    rotated_delta = body.manifold.volume()-(body.manifold-CadKernel.round_tool(edge, .25, "fillet")).volume()
    assert rotated_delta == pytest.approx(delta, rel=.02)


def test_raised_wrapped_emboss_has_both_roundable_rims():
    doc = load()
    assert doc.edit_feature(3, depth=1.)
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "wrapped"]
    assert len(edges) == 2
    assert sorted(e.radius for e in edges) == pytest.approx([20, 21], abs=.01)
    feature = doc.add_fillet([e.ref() for e in edges], .25)
    assert feature.skipped == 0
    assert next(iter(doc.bodies.values())).manifold.status() == m3d.Error.NoError
