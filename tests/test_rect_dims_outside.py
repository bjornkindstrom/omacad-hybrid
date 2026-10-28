"""Björn #71/#72: rectangle dimensions sit outside the rectangle, and hovering a dimension says what it is."""
import numpy as np
import pytest

from omacad.model.dim_layout import PT_LINE_DEFAULT_OFFSET, describe_dimension, pt_line_base_shift
from omacad.model.sketch import Sketch, SketchPlane


def _dim_line_point(sk, dim):
    """A point on the drawn dimension line (same maths as the overlay)."""
    ent = sk.get_entity(dim.target_entity_id)
    if dim.dim_type == "LENGTH":
        d = np.subtract(ent.p2, ent.p1)
        n = np.array([-d[1], d[0]]) / np.linalg.norm(d)
        return (np.add(ent.p1, ent.p2) / 2) + n * dim.offset_distance
    ref = sk.get_entity(dim.refs[0])
    d = np.subtract(ref.p2, ref.p1)
    d = d / np.linalg.norm(d)
    return np.asarray(getattr(ent, dim.pts[0])) + d * (pt_line_base_shift(ref) + dim.offset_distance - PT_LINE_DEFAULT_OFFSET)


@pytest.mark.parametrize("p1, p2", [((0, 0), (40, 30)), ((40, 30), (0, 0)), ((0, 30), (40, 0))])
@pytest.mark.parametrize("rounded", [False, True])
def test_width_and_height_are_drawn_outside(p1, p2, rounded):
    sk = Sketch("s", "S", SketchPlane())
    sk.add_rounded_rect(p1, p2, 5.0) if rounded else sk.add_rect(p1, p2)
    dims = {d.name: d for d in sk.dimensions if d.name in ("Width", "Height")}
    assert set(dims) == {"Width", "Height"}
    for d in dims.values():
        x, y = _dim_line_point(sk, d)
        assert not (0.0 < x < 40.0 and 0.0 < y < 30.0), (d.name, x, y)
        assert max(-x, x - 40.0, -y, y - 30.0) == pytest.approx(10.0, abs=1e-6)   # 10 mm outside


def test_hover_text_says_what_the_dimension_is():
    sk = Sketch("s", "S", SketchPlane())
    sk.add_rect((0, 0), (40, 30))
    width = next(d for d in sk.dimensions if d.name == "Width")
    width.expr = "w*2"
    text = describe_dimension(width)
    assert "Width" in text and "Length of a line: 40 mm" in text and "Formula: w*2" in text
