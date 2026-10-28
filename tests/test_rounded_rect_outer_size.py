"""A rounded rectangle is dimensioned by its overall width and height; radii stay, holes measured from a wall follow."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchCircle, SketchLine, SketchArc


def _make():
    d = Document()
    sk = d.start_sketch("XY")
    lines = sk.add_rounded_rect((0, 0), (60, 40), 10)
    return d, sk, lines


def _extent(sk):
    xs, ys = [], []
    for e in sk.entities:
        if isinstance(e, SketchLine):
            xs += [e.p1[0], e.p2[0]]
            ys += [e.p1[1], e.p2[1]]
    return min(xs), max(xs), min(ys), max(ys)


def test_dimensions_are_the_overall_size():
    _, sk, _ = _make()
    by = {x.name: x for x in sk.dimensions}
    assert by["Width"].dim_type == "PT_LINE_DIST" and by["Width"].value == pytest.approx(60)    # wall to wall,
    assert by["Height"].dim_type == "PT_LINE_DIST" and by["Height"].value == pytest.approx(40)  # also when turned
    assert not [x for x in sk.dimensions if x.dim_type == "LENGTH"]


def test_changing_the_width_keeps_radii_and_moves_the_hole_with_its_wall():
    d, sk, lines = _make()
    left = lines[3]
    c = sk.add_circle((15, 30), 5)
    d.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 15, refs=[left.entity_id], pts=["center"])
    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 90)
    xs = [e.p1[0] for e in sk.entities if isinstance(e, SketchLine)] + [e.p2[0] for e in sk.entities if isinstance(e, SketchLine)]
    assert max(xs) - min(xs) == pytest.approx(90, abs=1e-3)           # the walls, i.e. the overall width
    arcs = [e for e in sk.entities if isinstance(e, SketchArc)]
    assert len(arcs) == 4
    for a in arcs:
        assert a.get_circle_params()[1] == pytest.approx(10.0, abs=1e-3)
    assert abs(c.center[0] - left.p1[0]) == pytest.approx(15.0, abs=1e-3)


def test_a_hole_measured_from_the_far_wall_and_the_top_follows_height_and_width():
    d, sk, lines = _make()
    bottom, right, top, left = lines
    c = sk.add_circle((50, 30), 4)
    d.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 10, refs=[right.entity_id], pts=["center"])
    d.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 10, refs=[top.entity_id], pts=["center"])
    for name, val in (("Width", 100), ("Height", 70)):
        dim = next(x for x in sk.dimensions if x.name == name)
        assert d.update_dimension(sk.sketch_id, dim.dim_id, val)
    assert abs(right.p1[0] - c.center[0]) == pytest.approx(10, abs=1e-3)
    assert abs(top.p1[1] - c.center[1]) == pytest.approx(10, abs=1e-3)
    assert abs(right.p1[0] - left.p1[0]) == pytest.approx(100, abs=1e-3)
    assert abs(top.p1[1] - bottom.p1[1]) == pytest.approx(70, abs=1e-3)


def test_widening_keeps_the_arcs_joined_to_the_walls():
    """Report 200609: changing the width moved one wall and left the corner arcs behind."""
    d, sk, _ = _make()
    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 90)
    ends = [p for e in sk.entities if isinstance(e, SketchLine) for p in (e.p1, e.p2)]
    for arc in (e for e in sk.entities if isinstance(e, SketchArc)):
        assert arc.get_circle_params()[1] == pytest.approx(10)
        for p in (arc.p_start, arc.p_end):
            assert min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in ends) < 1e-6
    assert len(sk.profiles) == 1
    assert sk.profiles[0].area == pytest.approx(90 * 40 - (4 - math.pi) * 100, rel=2e-3)
