"""Sketch Fillet where a line meets an arc (report 20261025-110832): the corners between the big arc and its two
lines could not be picked or rounded, only corners between two lines."""
import json
import math
import os

import pytest

from omacad.model.sketch import Sketch

DATA = os.path.join(os.path.dirname(__file__), "data", "fillet_line_arc_sketch.json")


def _sketch():
    with open(DATA) as f:
        return Sketch.from_dict(json.load(f))


def _line_dist(line, p):
    (x1, y1), (x2, y2) = line.p1, line.p2
    return abs((x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1)) / math.hypot(x2 - x1, y2 - y1)


def _assert_tangent(sk, fillet, big, r):
    centre, radius = fillet.get_circle_params()[:2]
    assert radius == pytest.approx(r, abs=1e-9)
    line = sk.get_entity(fillet.fillet_info["line_b"])
    assert _line_dist(line, centre) == pytest.approx(r, abs=1e-9)
    big_c, big_r = big.get_circle_params()[:2]
    assert math.dist(centre, big_c) == pytest.approx(big_r - r, abs=1e-9)    # inside the big arc, touching it
    ends = {fillet.p_start, fillet.p_end}
    assert any(math.dist(p, q) < 1e-9 for p in ends for q in (big.p_start, big.p_end))
    assert any(math.dist(p, q) < 1e-9 for p in ends for q in (line.p1, line.p2))


def test_line_arc_corners_are_found_and_rounded():
    sk = _sketch()
    big = sk.get_entity("arc_1")
    big_circle = big.get_circle_params()[:2]
    area = sk.profiles[0].area
    corners = sk.find_corners()
    assert sorted((a.entity_id, b.entity_id) for _p, a, b, _ea, _eb in corners) == [("arc_1", "line_2"), ("arc_1", "line_6")]
    for pt, a, b, _ea, _eb in corners:
        arc, msg = sk.fillet_corner(a, b, 5.0, pt)
        assert msg == "OK"
        _assert_tangent(sk, arc, big, 5.0)
    c, r = big.get_circle_params()[:2]
    assert math.dist(c, big_circle[0]) < 1e-9 and r == pytest.approx(big_circle[1])     # the big arc keeps its circle
    assert len(sk.profiles) == 1 and sk.profiles[0].area < area
    assert sk.find_corners() == []                      # everything meets tangentially now


def test_line_arc_fillet_radius_can_be_changed_both_ways():
    sk = _sketch()
    pt, a, b, _ea, _eb = next(c for c in sk.find_corners() if c[2].entity_id == "line_2")
    arc, _msg = sk.fillet_corner(a, b, 5.0, pt)
    dim = next(d for d in sk.dimensions if d.target_entity_id == arc.entity_id)
    for r in (8.0, 2.0):
        sk.set_dimension_value(dim.dim_id, r)
        _assert_tangent(sk, arc, sk.get_entity("arc_1"), r)
        line = sk.get_entity("line_2")
        length = next(d for d in sk.dimensions if d.target_entity_id == "line_2" and d.dim_type == "LENGTH")
        assert length.value == pytest.approx(math.dist(line.p1, line.p2))


def test_too_large_radius_is_refused_and_changes_nothing():
    sk = _sketch()
    before = sk.to_dict()
    pt, a, b, _ea, _eb = next(c for c in sk.find_corners() if c[2].entity_id == "line_6")
    arc, msg = sk.fillet_corner(a, b, 500.0, pt)
    assert arc is None and "too large" in msg
    assert sk.to_dict() == before


def test_two_arcs_meeting_at_a_corner():
    """Two humps meeting in a notch: the fillet sits in the notch, outside both circles and touching each."""
    with open(DATA) as f:
        sk = Sketch.from_dict({**json.load(f), "entities": [], "dimensions": [], "constraints": []})
    a = sk.add_arc((-20.0, 0.0), (-10.0, 10.0), (0.0, 0.0))                       # centre (-10, 0), r 10
    b = sk.add_arc((0.0, 0.0), (10.0, -10.0 + math.sqrt(200.0)), (20.0, 0.0))     # centre (10, -10), r 14.1
    [(pt, ea, eb, _x, _y)] = sk.find_corners()
    arc, msg = sk.fillet_corner(ea, eb, 2.0, pt)
    assert msg == "OK"
    centre = arc.get_circle_params()[0]
    for big in (a, b):
        c, r = big.get_circle_params()[:2]
        assert math.dist(centre, c) == pytest.approx(r + 2.0, abs=1e-9)
        assert any(math.dist(p, q) < 1e-9 for p in (arc.p_start, arc.p_end) for q in (big.p_start, big.p_end))
