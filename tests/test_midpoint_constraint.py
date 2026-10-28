"""Björn #73: a Midpoint constraint puts an end point or a circle's centre on the middle of a line."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch_solver import midpoint_spec


def test_line_end_goes_to_the_middle_of_the_other_line_and_stays_there():
    doc = Document()
    sk = doc.start_sketch()
    base = sk.add_line((0.0, 0.0), (40.0, 0.0))
    post = sk.add_line((15.0, 3.0), (15.0, 20.0))          # its lower end is near the base's middle
    spec = midpoint_spec([post, base], [])
    assert spec == ("MIDPOINT", [post.entity_id, base.entity_id], ["p1"])
    doc.add_constraints(sk.sketch_id, [spec])
    post, base = sk.get_entity(post.entity_id), sk.get_entity(base.entity_id)
    mid = ((base.p1[0] + base.p2[0]) / 2, (base.p1[1] + base.p2[1]) / 2)
    assert post.p1 == pytest.approx(mid, abs=1e-6)


def test_circle_centre_goes_to_the_middle_of_a_line():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 10.0), (30.0, 10.0))
    circle = sk.add_circle((5.0, 2.0), 3.0)
    spec = midpoint_spec([line], [circle])
    assert spec == ("MIDPOINT", [circle.entity_id, line.entity_id], ["center"])
    doc.add_constraints(sk.sketch_id, [spec])
    line, circle = sk.get_entity(line.entity_id), sk.get_entity(circle.entity_id)
    assert circle.center == pytest.approx(((line.p1[0] + line.p2[0]) / 2, (line.p1[1] + line.p2[1]) / 2), abs=1e-6)
    assert circle.radius == pytest.approx(3.0)


def test_midpoint_button_exists():
    from omacad.ui.ribbon import Ribbon
    assert any(c[0] == "MIDPOINT" for c in Ribbon.CONSTRAINTS)
