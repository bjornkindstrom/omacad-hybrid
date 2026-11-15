"""Construction and reference plane model tests: offsets, angles, axes, and face centering."""
import math
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.model.sketch_snap import SketchSnapper


# =========================================================================
# 1. Offset Planes
# =========================================================================

def test_offset_plane_keeps_in_plane_origin_and_exact_offset():
    doc = Document()
    base = SketchPlane.from_face(np.array([0.0, 0.0, 1.0]), np.zeros(3), name="XY")
    pid = doc.add_construction_plane(base, 7.5, origin=[10.0, 5.0, 0.0])
    assert np.allclose(doc.construction_planes[pid]["origin"], [10.0, 5.0, 7.5])
    plane = doc.construction_plane(pid)
    assert np.allclose(plane.origin, [10.0, 5.0, 7.5])
    assert np.allclose(plane.normal, [0.0, 0.0, 1.0])
    doc.undo()
    assert pid not in doc.construction_planes


def test_offset_plane_without_origin_uses_base_origin():
    doc = Document()
    base = SketchPlane.from_face(np.array([0.0, 0.0, 1.0]), np.zeros(3), name="XY")
    pid = doc.add_construction_plane(base, -3.0)
    assert np.allclose(doc.construction_plane(pid).origin, [0.0, 0.0, -3.0])


# =========================================================================
# 2. Angled Planes
# =========================================================================

def test_plane_turned_about_x_then_offset():
    doc = Document()
    pid = doc.add_construction_plane(doc.origin_planes["XY"], 5.0, origin=(0, 0, 0), angle=30.0, axis_dir=(1, 0, 0))
    c = doc.construction_planes[pid]
    want_n = np.array([0.0, -math.sin(math.radians(30)), math.cos(math.radians(30))])
    assert np.allclose(c["normal"], want_n, atol=1e-9)
    assert np.allclose(c["origin"], want_n * 5.0, atol=1e-9)
    sk = doc.start_sketch_on_plane(doc.construction_plane(pid))
    assert np.allclose(sk.plane.normal, want_n, atol=1e-6)


def test_plane_turned_about_a_box_edge_contains_the_edge(tmp_path):
    doc = Document()
    box = doc.add_box(20, 10, 6)
    top = box.manifold.bounding_box()[5]
    edge = next(e for e in box.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - top) < 1e-9 and abs(e.p1[2] - top) < 1e-9 and abs(e.p0[1] - e.p1[1]) < 1e-9)
    mid, d = (edge.p0 + edge.p1) / 2, edge.p1 - edge.p0
    top_plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], top, origin=(0, 0, 0)))
    pid = doc.add_construction_plane(top_plane, 0.0, origin=mid, angle=45.0, axis_point=mid, axis_dir=d)
    c = doc.construction_planes[pid]
    n = np.asarray(c["normal"])
    for p in (edge.p0, edge.p1):
        assert abs(float((p - np.asarray(c["origin"])) @ n)) < 1e-9
    assert abs(abs(float(n[2])) - math.cos(math.radians(45))) < 1e-9
    path = tmp_path / "p.omacad"
    Exporter.save_project(doc, str(path))
    assert np.allclose(Exporter.load_project(str(path)).construction_planes[pid]["normal"], n)


def test_angle_zero_is_a_plain_offset():
    o, n = Document.angled_plane((0, 0, 1), (1, 2, 3), 4.0, 0.0, None, (1, 0, 0))
    assert np.allclose(o, (1, 2, 7)) and np.allclose(n, (0, 0, 1))


# =========================================================================
# 3. Face Centering & Snapping
# =========================================================================

TRIS = np.array([[[10, 0, 5], [40, 0, 5], [40, 20, 5]], [[10, 0, 5], [40, 20, 5], [10, 20, 5]]], dtype=float)


def _face_plane():
    return SketchPlane.from_face(np.array([0, 0, 1.0]), np.array([10, 0, 5.0])).centered_on(TRIS)


def test_origin_is_face_centre():
    plane = _face_plane()
    assert plane.origin == pytest.approx([25.0, 10.0, 5.0])
    assert plane.world_to_uv(np.array([40.0, 20.0, 5.0])) == pytest.approx((15.0, 10.0))


def test_origin_snap_locks_to_the_face_centre():
    r = SketchSnapper.snap(raw_uv=(0.4, -0.3), sketch=None, snap_distance=1.0)
    assert r.snap_type == "ORIGIN" and r.uv == (0.0, 0.0)


def test_sketch_on_centred_plane_survives_save_and_load():
    d = Document()
    d.start_sketch_on_plane(_face_plane())
    d2 = Document()
    Exporter.apply_dict(d2, Exporter.document_to_dict(d))
    sk = next(iter(d2.sketches.values()))
    assert sk.plane.origin == pytest.approx([25.0, 10.0, 5.0])
