"""A sketch on a face has its origin (and grid) in the middle of that face, not at the world origin."""
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.model.sketch_snap import SketchSnapper

# top face of a block spanning x 10..40, y 0..20 at z = 5
TRIS = np.array([[[10, 0, 5], [40, 0, 5], [40, 20, 5]], [[10, 0, 5], [40, 20, 5], [10, 20, 5]]], dtype=float)


def face_plane():
    return SketchPlane.from_face(np.array([0, 0, 1.0]), np.array([10, 0, 5.0])).centered_on(TRIS)


def test_origin_is_face_centre():
    plane = face_plane()
    assert plane.origin == pytest.approx([25.0, 10.0, 5.0])
    assert plane.world_to_uv(np.array([40.0, 20.0, 5.0])) == pytest.approx((15.0, 10.0))


def test_origin_snap_locks_to_the_face_centre():
    r = SketchSnapper.snap(raw_uv=(0.4, -0.3), sketch=None, snap_distance=1.0)
    assert r.snap_type == "ORIGIN" and r.uv == (0.0, 0.0)


def test_sketch_on_centred_plane_survives_save_and_load():
    from omacad.io.exporter import Exporter
    d = Document()
    d.start_sketch_on_plane(face_plane())
    d2 = Document()
    Exporter.apply_dict(d2, Exporter.document_to_dict(d))
    sk = next(iter(d2.sketches.values()))
    assert sk.plane.origin == pytest.approx([25.0, 10.0, 5.0])
