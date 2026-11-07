"""Request #221: Coincident works between a line and a circle or an arc."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchArc
from omacad.model.sketch_solver import coincident_curve_spec, solve_sketch
from omacad.ui.viewport.viewport import Viewport3D


def _arc(sk, start, mid, end):
    arc = SketchArc(sk._new_entity_id("arc"), start, mid, end)
    sk.entities.append(arc)
    return arc


def test_line_end_goes_onto_a_circle_and_follows_it():
    doc = Document()
    sk = doc.start_sketch()
    circle = sk.add_circle((0.0, 0.0), 10.0)
    line = sk.add_line((13.0, 2.0), (30.0, 20.0))
    spec = coincident_curve_spec(line, circle)
    assert spec == ("POINT_ON_CIRCLE", [circle.entity_id, line.entity_id], ["p1"])
    assert doc.add_constraints(sk.sketch_id, [spec])
    circle, line = sk.get_entity(circle.entity_id), sk.get_entity(line.entity_id)
    assert math.dist(line.p1, circle.center) == pytest.approx(circle.radius, abs=1e-6)

    circle.radius = 15.0
    assert solve_sketch(sk, fixed_ids=[circle.entity_id]).ok
    assert math.dist(line.p1, circle.center) == pytest.approx(15.0, abs=1e-6)


def test_line_end_near_the_centre_goes_to_the_centre():
    doc = Document()
    sk = doc.start_sketch()
    circle = sk.add_circle((0.0, 0.0), 10.0)
    line = sk.add_line((1.0, 1.0), (30.0, 20.0))
    spec = coincident_curve_spec(line, circle)
    assert spec == ("COINCIDENT", [line.entity_id, circle.entity_id], ["p1", "center"])
    doc.add_constraints(sk.sketch_id, [spec])
    circle, line = sk.get_entity(circle.entity_id), sk.get_entity(line.entity_id)
    assert line.p1 == pytest.approx(circle.center, abs=1e-6)


def test_line_end_goes_onto_an_arc_which_stays_put():
    doc = Document()
    sk = doc.start_sketch()
    arc = _arc(sk, (10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))      # upper half circle, r 10 about the origin
    line = sk.add_line((3.0, 12.0), (5.0, 30.0))
    spec = coincident_curve_spec(line, arc)
    assert spec == ("POINT_ON_CIRCLE", [arc.entity_id, line.entity_id], ["p1"])
    assert doc.add_constraints(sk.sketch_id, [spec])
    arc, line = sk.get_entity(arc.entity_id), sk.get_entity(line.entity_id)
    assert arc.p_start == (10.0, 0.0) and arc.p_mid == (0.0, 10.0) and arc.p_end == (-10.0, 0.0)
    assert math.hypot(*line.p1) == pytest.approx(10.0, abs=1e-6)

    # the arc grows: the line follows on the next solve
    arc.p_start, arc.p_mid, arc.p_end = (20.0, 0.0), (0.0, 20.0), (-20.0, 0.0)
    assert solve_sketch(sk).ok
    assert math.hypot(*line.p1) == pytest.approx(20.0, abs=1e-6)


def test_line_end_beside_the_arc_joins_its_nearest_end():
    doc = Document()
    sk = doc.start_sketch()
    arc = _arc(sk, (10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    line = sk.add_line((12.0, -2.0), (30.0, -20.0))               # below the arc's sweep, near its start
    spec = coincident_curve_spec(line, arc)
    assert spec == ("ARC_END", [line.entity_id, arc.entity_id], ["p1", "p_start"])
    doc.add_constraints(sk.sketch_id, [spec])
    line = sk.get_entity(line.entity_id)
    assert line.p1 == pytest.approx((10.0, 0.0), abs=1e-6)


def test_arc_coincidence_survives_save_load_and_undo():
    doc = Document()
    sk = doc.start_sketch()
    arc = _arc(sk, (10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    line = sk.add_line((3.0, 12.0), (5.0, 30.0))
    doc.add_constraints(sk.sketch_id, [coincident_curve_spec(line, arc)])
    again = Sketch.from_dict(sk.to_dict())
    assert [(c.ctype, c.refs, c.pts) for c in again.constraints] == [
        ("POINT_ON_CIRCLE", [arc.entity_id, line.entity_id], ["p1"])]
    assert solve_sketch(again).ok
    doc.undo()
    assert not doc.active_sketch.constraints
    assert doc.active_sketch.get_entity(line.entity_id).p1 == pytest.approx((3.0, 12.0))


def test_constraint_guide_takes_a_line_and_a_curve():
    doc = Document()
    sk = doc.start_sketch()
    line, circle = sk.add_line((0.0, 0.0), (1.0, 1.0)), sk.add_circle((5.0, 5.0), 2.0)
    arc = _arc(sk, (10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    accepts = Viewport3D._constraint_guide_accepts
    assert accepts("COINCIDENT", [], circle) and accepts("COINCIDENT", [], arc)
    assert accepts("COINCIDENT", [line], arc) and accepts("COINCIDENT", [line], circle)
    assert accepts("COINCIDENT", [arc], line)
    assert not accepts("COINCIDENT", [arc], circle)
