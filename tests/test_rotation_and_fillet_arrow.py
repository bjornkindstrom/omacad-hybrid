import pytest
import numpy as np
from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchLine, SketchCircle, SketchRect, rotate_entity, rotate_point


def test_rotate_point():
    p = (10.0, 0.0)
    # Rotate 90 deg around origin
    p_rot = rotate_point(p, 90.0, (0.0, 0.0))
    assert abs(p_rot[0] - 0.0) < 1e-6
    assert abs(p_rot[1] - 10.0) < 1e-6

    # Rotate 180 deg around (5.0, 0.0)
    p_rot180 = rotate_point(p, 180.0, (5.0, 0.0))
    assert abs(p_rot180[0] - 0.0) < 1e-6
    assert abs(p_rot180[1] - 0.0) < 1e-6


def test_rotate_sketch_entities():
    line = SketchLine("l1", (0.0, 0.0), (10.0, 0.0))
    rotate_entity(line, 90.0, (0.0, 0.0))
    assert abs(line.p1[0]) < 1e-6 and abs(line.p1[1]) < 1e-6
    assert abs(line.p2[0]) < 1e-6 and abs(line.p2[1] - 10.0) < 1e-6

    circle = SketchCircle("c1", (10.0, 0.0), 5.0)
    rotate_entity(circle, 90.0, (0.0, 0.0))
    assert abs(circle.center[0]) < 1e-6
    assert abs(circle.center[1] - 10.0) < 1e-6
    assert circle.radius == 5.0


def test_fillet_chamfer_arrow_direction():
    doc = Document()
    body = doc.add_box(10.0, 10.0, 10.0)
    
    # Convex edges should have an inward-pointing bisector (d1 + d2)
    convex_edges = [e for e in body.edges if hasattr(e, "p0") and getattr(e, "convex", True)]
    assert len(convex_edges) > 0
    for e in convex_edges:
        axis = e.d1 + e.d2
        assert np.linalg.norm(axis) > 1e-6
        # Pointing into material: dot product with outward face normals should be <= 0
        assert (axis @ e.n1) <= 1e-6
        assert (axis @ e.n2) <= 1e-6
