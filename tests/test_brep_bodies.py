"""Experimental B-rep bodies (step 1): plain Box/Cylinder as exact OpenCascade shapes behind the "brep_bodies"
setting; off = unchanged mesh bodies; any mesh write drops the shape."""
import math

import numpy as np
import pytest

from omacad.model import brep
from omacad.model.document import Document

pytestmark = pytest.mark.skipif(not brep.available(), reason="cadquery-ocp not installed")


@pytest.fixture
def brep_on():
    brep.set_enabled(True)
    yield
    brep.set_enabled(False)


def only_body(doc):
    (body,) = doc.bodies.values()
    return body


def bbox(body):
    b = body.manifold.bounding_box()
    return np.array(b[:3]), np.array(b[3:])


def test_setting_off_keeps_plain_mesh_bodies():
    doc = Document()
    doc.add_box(30, 20, 10)
    assert only_body(doc).brep is None


@pytest.mark.parametrize("center, lo", [(False, (0, 0, 0)), (True, (-15, -10, -5)), ("bottom_center", (-15, -10, 0))])
def test_box_is_exact_brep_placed_like_the_mesh(brep_on, center, lo):
    doc = Document()
    doc.add_box(30, 20, 10, center=center, translation=[1.0, 2.0, 3.0])
    body = only_body(doc)
    assert body.is_brep and brep.is_valid(body.brep)
    assert brep.volume(body.brep) == pytest.approx(6000, abs=1e-9)
    assert body.manifold.volume() == pytest.approx(6000, abs=1e-6)
    b0, b1 = bbox(body)
    np.testing.assert_allclose(b0, np.add(lo, (1, 2, 3)), atol=1e-9)
    np.testing.assert_allclose(b1 - b0, (30, 20, 10), atol=1e-9)
    assert len(body.faces) == 6 and len(body.edges) == 12      # face/edge analysis works on the tessellation


def test_cylinder_brep_volume_is_exact_and_mesh_has_the_curve_smoothness(brep_on):
    doc = Document()
    doc.add_cylinder(5, 12, translation=[10.0, 0.0, 0.0])
    body = only_body(doc)
    assert body.is_brep
    assert brep.volume(body.brep) == pytest.approx(math.pi * 25 * 12, rel=1e-12)
    n = 96
    polygon = 0.5 * n * 25 * math.sin(2 * math.pi / n) * 12          # what a 96-piece mesh cylinder holds
    assert body.manifold.volume() == pytest.approx(polygon, rel=2e-3)
    b0, b1 = bbox(body)
    np.testing.assert_allclose(b0[[2]], [0.0], atol=1e-9)
    np.testing.assert_allclose((b0 + b1)[:2] / 2, (10, 0), atol=1e-6)


def test_box_on_a_picked_plane_matches_the_mesh_placement(brep_on):
    doc_mesh, doc_brep = Document(), Document()
    kw = dict(plane_origin=[5, 5, 5], plane_normal=[1, 0, 0], plane_u=[0, 1, 0], plane_v=[0, 0, 1])
    brep.set_enabled(False)
    doc_mesh.add_box(8, 6, 4, **kw)
    brep.set_enabled(True)
    doc_brep.add_box(8, 6, 4, **kw)
    a, b = bbox(only_body(doc_mesh)), bbox(only_body(doc_brep))
    np.testing.assert_allclose(a[0], b[0], atol=1e-9)
    np.testing.assert_allclose(a[1], b[1], atol=1e-9)
    assert only_body(doc_brep).is_brep


def test_smart_box_options_stay_mesh_bodies(brep_on):
    doc = Document()
    doc.add_box(30, 20, 10, outer_round=2.0)
    assert only_body(doc).brep is None


def test_writing_a_mesh_drops_the_shape(brep_on):
    doc = Document()
    doc.add_box(10, 10, 10)
    body = only_body(doc)
    assert body.is_brep
    body.manifold = body.manifold.translate((1, 0, 0))
    assert body.brep is None


def test_mesh_features_after_a_brep_body_still_work(brep_on):
    """Fillet is still the mesh tool in step 1: the result is a mesh body with the exact rounded-box volume."""
    doc = Document()
    doc.add_box(30, 20, 10)
    edges = [e.ref() for e in only_body(doc).edges]
    doc.add_fillet(edges, 2.0, "fillet")
    body = only_body(doc)
    x, y, z, r = 26, 16, 6, 2.0
    exact = x * y * z + 2 * r * (x * y + y * z + x * z) + math.pi * r * r * (x + y + z) + 4 / 3 * math.pi * r ** 3
    assert body.manifold.volume() == pytest.approx(exact, rel=2e-3)
    assert body.brep is None


def test_switching_off_and_rebuilding_goes_back_to_mesh(brep_on):
    doc = Document()
    doc.add_box(10, 10, 10)
    assert only_body(doc).is_brep
    brep.set_enabled(False)
    doc.timeline.recompute(doc)
    assert only_body(doc).brep is None
    brep.set_enabled(True)
    doc.timeline.recompute(doc)
    assert only_body(doc).is_brep


def test_undo_and_save_roundtrip_with_brep_bodies(brep_on, tmp_path):
    from omacad.io.exporter import Exporter
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(3, 5, translation=[20.0, 0.0, 0.0])
    path = tmp_path / "b.omacad"
    assert Exporter.save_project(doc, str(path))
    doc.undo()
    assert len(doc.bodies) == 1 and only_body(doc).is_brep
    loaded = Exporter.load_project(str(path))
    assert len(loaded.bodies) == 2 and all(b.is_brep for b in loaded.bodies.values())


def test_unavailable_opencascade_means_inactive(monkeypatch):
    monkeypatch.setattr(brep, "_available", False)
    brep.set_enabled(True)
    try:
        assert not brep.active()
    finally:
        brep.set_enabled(False)
