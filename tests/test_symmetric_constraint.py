"""Symmetric: two lines (or circles) mirrored across a third selected line, as in Fusion 360."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch_solver import symmetric_spec


def _signed(axis, p):
    ax, ay = axis.p2[0] - axis.p1[0], axis.p2[1] - axis.p1[1]
    return (ax * (p[1] - axis.p1[1]) - ay * (p[0] - axis.p1[0])) / math.hypot(ax, ay)


def test_two_sides_of_a_rectangle_mirror_across_the_axis_and_stay_square_to_it():
    doc = Document()
    sk = doc.start_sketch()
    left = sk.add_line((-30.0, 0.0), (-30.0, 10.0))
    right = sk.add_line((22.0, 1.0), (22.0, 12.0))      # off-centre on purpose
    axis = sk.add_line((0.0, -5.0), (0.0, 15.0))
    spec = symmetric_spec([left, right, axis], [])
    assert spec[0] == "SYMMETRIC" and spec[1][2] == axis.entity_id
    doc.add_constraints(sk.sketch_id, [spec])
    left, right, axis = (sk.get_entity(e.entity_id) for e in (left, right, axis))
    pa, pb = spec[2]
    a, b = getattr(left, pa), getattr(right, pb)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    assert _signed(axis, mid) == pytest.approx(0, abs=1e-6)          # the midpoint sits on the mirror line
    assert _signed(axis, a) == pytest.approx(-_signed(axis, b), abs=1e-6)  # opposite sides, same distance
    ax, ay = axis.p2[0] - axis.p1[0], axis.p2[1] - axis.p1[1]
    assert ax * (b[0] - a[0]) + ay * (b[1] - a[1]) == pytest.approx(0, abs=1e-6)   # connector square to the axis


def test_the_mirror_line_is_the_one_that_fits_not_the_one_clicked_first():
    doc = Document()
    sk = doc.start_sketch()
    left = sk.add_line((-30.0, 0.0), (-30.0, 10.0))
    right = sk.add_line((30.0, 0.0), (30.0, 10.0))
    axis = sk.add_line((0.0, -5.0), (0.0, 15.0))
    for lines in ([left, right, axis], [axis, right, left], [right, axis, left]):
        assert symmetric_spec(lines, [])[1][2] == axis.entity_id


def test_an_explicitly_picked_mirror_line_is_honored():
    doc = Document()
    sk = doc.start_sketch()
    left = sk.add_line((-30.0, 0.0), (-30.0, 10.0))
    right = sk.add_line((22.0, 1.0), (22.0, 12.0))
    axis = sk.add_line((0.0, -5.0), (0.0, 15.0))
    lines = [left, right, axis]

    assert symmetric_spec(lines, [], axis_id=axis.entity_id)[1][2] == axis.entity_id
    # A line that does not mirror the other two must not be substituted for the clicked axis.
    assert symmetric_spec(lines, [], axis_id=left.entity_id) is None




def test_two_circles_mirror_across_a_line():
    doc = Document()
    sk = doc.start_sketch()
    c1 = sk.add_circle((-20.0, 3.0), 4.0)
    c2 = sk.add_circle((14.0, 6.0), 4.0)
    axis = sk.add_line((0.0, -10.0), (0.0, 10.0))
    spec = symmetric_spec([axis], [c1, c2])
    assert spec == ("SYMMETRIC", [c1.entity_id, c2.entity_id, axis.entity_id], ["center", "center"])
    doc.add_constraints(sk.sketch_id, [spec])
    c1, c2 = sk.get_entity(c1.entity_id), sk.get_entity(c2.entity_id)
    axis = sk.get_entity(axis.entity_id)                 # the solver may move the mirror line too
    assert _signed(axis, c1.center) == pytest.approx(-_signed(axis, c2.center), abs=1e-6)
    mid = ((c1.center[0] + c2.center[0]) / 2, (c1.center[1] + c2.center[1]) / 2)
    assert _signed(axis, mid) == pytest.approx(0, abs=1e-6)
    assert c1.radius == pytest.approx(4.0) and c2.radius == pytest.approx(4.0)


def test_two_lines_without_a_mirror_line_or_two_circles_without_one_give_nothing():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((5.0, 0.0), (5.0, 10.0))
    b = sk.add_line((9.0, 0.0), (9.0, 10.0))
    c = sk.add_circle((0.0, 0.0), 2.0)
    assert symmetric_spec([a, b], []) is None
    assert symmetric_spec([a], []) is None
    assert symmetric_spec([a], [c]) is None
