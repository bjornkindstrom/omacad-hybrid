"""Request #143: Coincident works on slanted lines, as in Fusion: an end point goes onto the other line anywhere along
it (POINT_ON_LINE), and two end points next to each other are still joined."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch
from omacad.model.sketch_solver import coincident_spec, solve_sketch
from omacad.ui.viewport.sketch_move_mixin import SketchMoveMixin


def _distance_to_line(p, line):
    (x1, y1), (x2, y2) = line.p1, line.p2
    return abs((p[0] - x1) * (y2 - y1) - (p[1] - y1) * (x2 - x1)) / math.dist(line.p1, line.p2)


def test_end_point_goes_onto_a_slanted_line_and_stays_there():
    doc = Document()
    sk = doc.start_sketch()
    slant = sk.add_line((0.0, 0.0), (40.0, 30.0))            # 36.87 degrees
    post = sk.add_line((22.0, 13.0), (10.0, 40.0))            # lower end close to the middle of the slant
    spec = coincident_spec(post, slant)
    assert spec == ("POINT_ON_LINE", [post.entity_id, slant.entity_id], ["p1"])
    doc.add_constraints(sk.sketch_id, [spec])
    post, slant = sk.get_entity(post.entity_id), sk.get_entity(slant.entity_id)
    assert _distance_to_line(post.p1, slant) == pytest.approx(0.0, abs=1e-6)

    # tilting the slanted line keeps the point on it
    slant.p2 = (40.0, 10.0)
    assert solve_sketch(sk, fixed_ids=[slant.entity_id]).ok
    assert _distance_to_line(post.p1, slant) == pytest.approx(0.0, abs=1e-6)


def test_selection_order_does_not_matter():
    doc = Document()
    sk = doc.start_sketch()
    slant = sk.add_line((0.0, 0.0), (40.0, 30.0))
    post = sk.add_line((22.0, 13.0), (10.0, 40.0))
    assert coincident_spec(slant, post) == coincident_spec(post, slant)


def test_nearby_ends_of_slanted_lines_are_still_joined():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (10.0, 6.0))
    b = sk.add_line((12.0, 7.0), (20.0, -3.0))
    spec = coincident_spec(a, b)
    assert spec == ("COINCIDENT", [a.entity_id, b.entity_id], ["p2", "p1"])
    doc.add_constraints(sk.sketch_id, [spec])
    a, b = sk.get_entity(a.entity_id), sk.get_entity(b.entity_id)
    assert a.p2 == pytest.approx(b.p1, abs=1e-6)


def test_point_on_line_survives_save_load_and_undo():
    doc = Document()
    sk = doc.start_sketch()
    slant = sk.add_line((0.0, 0.0), (40.0, 30.0))
    post = sk.add_line((22.0, 13.0), (10.0, 40.0))
    doc.add_constraints(sk.sketch_id, [coincident_spec(post, slant)])
    again = Sketch.from_dict(sk.to_dict())
    assert [(c.ctype, c.refs, c.pts) for c in again.constraints] == [
        ("POINT_ON_LINE", [post.entity_id, slant.entity_id], ["p1"])]
    doc.undo()
    assert not doc.active_sketch.constraints
    assert doc.active_sketch.get_entity(post.entity_id).p1 == pytest.approx((22.0, 13.0))


def test_end_released_on_a_slanted_line_lands_on_it():
    doc = Document()
    sk = doc.start_sketch()
    slant = sk.add_line((0.0, 0.0), (40.0, 30.0))
    post = sk.add_line((20.2, 15.3), (10.0, 40.0))            # 0.2 mm beside the line
    assert SketchMoveMixin._drop_end_on_line(sk, post, "p1", 0.5)
    assert _distance_to_line(post.p1, slant) == pytest.approx(0.0, abs=1e-9)
    c = sk.constraints[-1]
    assert (c.ctype, c.refs, c.pts) == ("POINT_ON_LINE", [post.entity_id, slant.entity_id], ["p1"])
    assert solve_sketch(sk).ok


def test_line_drawn_ending_on_a_slanted_line_is_held_there():
    from types import SimpleNamespace
    from omacad.ui.viewport.sketch_tools_mixin import SketchToolsMixin
    doc = Document()
    sk = doc.start_sketch()
    sk.add_line((0.0, 0.0), (40.0, 30.0))
    post = sk.add_line((20.0, 15.0), (10.0, 40.0))            # drawn from a point snapped onto the slant
    host = SimpleNamespace(doc=doc)
    SketchToolsMixin._auto_constrain_line(host, sk, post)
    assert [c.ctype for c in sk.constraints] == ["POINT_ON_LINE"]
