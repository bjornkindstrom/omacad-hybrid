"""Offset Plane from an origin plane is placed at the visible model's centre, not at world origin."""
import numpy as np

from omacad.model.document import Document
from omacad.model.sketch import SketchPlane


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
