"""Pivot centres use actual enclosed area; rotated constraints keep the figure editable."""
import math
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchPlane, SketchLine, SketchCircle, rotate_entity
from omacad.model.sketch_rotate import selection_pivots, face_centroid, rotate_axis_constraints, sketch_face_pivot
from omacad.model.sketch_solver import solve_sketch
from omacad.io.exporter import Exporter


def _loop(points, prefix="edge"):
    return [SketchLine(f"{prefix}{i}", a, b) for i, (a, b) in enumerate(zip(points, points[1:] + points[:1]))]


def test_asymmetric_figure_uses_area_centroid_not_bounds_or_vertex_average():
    pivots = selection_pivots(_loop([(0, 0), (6, 0), (0, 3)]))
    assert pivots["area"] == pytest.approx((2, 1))
    assert pivots["bounds"] == pytest.approx((3, 1.5))
    assert "area" not in selection_pivots([SketchLine("a", (0, 0), (6, 3))])


def test_area_centroid_excludes_holes_and_ignores_open_curves():
    entities = _loop([(0, 0), (10, 0), (10, 10), (0, 10)])
    entities += _loop([(1, 1), (3, 1), (3, 3), (1, 3)], "hole")
    entities += [SketchLine("open", (50, 50), (80, 80))]
    assert selection_pivots(entities)["area"] == pytest.approx((5.125, 5.125))
    assert selection_pivots([SketchCircle("c", (8, 7), 3)])["area"] == pytest.approx((8, 7))


def test_supporting_face_centroid_survives_project_round_trip():
    doc = Document()
    doc.add_box(20, 10, 5)
    face = max(next(iter(doc.bodies.values())).faces, key=lambda f: f.normal[2])
    plane = SketchPlane.from_face(face.normal, face.origin)  # deliberately not centred
    plane.face = face
    sk = doc.start_sketch_on_plane(plane)
    expected = face_centroid(plane, face.tris)
    assert sk.face_center == pytest.approx(expected)
    doc.finish_sketch()
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert sketch_face_pivot(loaded, loaded.sketches[sk.sketch_id]) == pytest.approx(expected)
    # An asymmetric face: tessellation or bounds must not decide the pivot.
    assert face_centroid(SketchPlane(), [[[0, 0, 0], [6, 0, 0], [0, 3, 0]]]) == pytest.approx((2, 1))


@pytest.mark.parametrize("angle", [45, 90, -30])
def test_rotated_rectangle_keeps_area_and_can_still_be_dimensioned(angle):
    sk = Sketch("s", "s", SketchPlane())
    lines = sk.add_rect((1, 2), (7, 5))
    ids = {e.entity_id for e in lines}
    for e in lines:
        rotate_entity(e, angle, (2, 1))
    rotate_axis_constraints(sk, ids, angle)
    assert solve_sketch(sk).ok
    assert sk.profiles[0].area == pytest.approx(18, abs=1e-3)
    first = sk.get_entity(lines[0].entity_id)
    assert math.degrees(math.atan2(first.p2[1] - first.p1[1], first.p2[0] - first.p1[0])) == pytest.approx(angle)
    sk.set_dimension_value(sk.dimensions[0].dim_id, 8)
    assert solve_sketch(sk).ok
    assert sk.profiles[0].area == pytest.approx(24, abs=1e-3)
    a, b = (np.subtract(e.p2, e.p1) for e in sk.entities[:2])
    assert np.dot(a, b) == pytest.approx(0, abs=1e-3)
