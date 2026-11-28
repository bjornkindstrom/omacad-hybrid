"""The ellipse takes part in the constraint solver: axis dimensions, line relations on its axis, its centre."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch


def _doc_with_ellipse():
    doc = Document()
    sk = doc.start_sketch()
    e = sk.add_ellipse((3.0, 2.0), (15.0, 5.0), 4.0)
    return doc, sk, e


def _dimension(doc, e, kind, value):
    """As the Dimension tool does: placed at the present size, then the typed value."""
    sk = doc.active_sketch
    e = sk.get_entity(e.entity_id)
    assert doc.add_dimension_constraint(sk.sketch_id, kind, e.entity_id, 2.0 * (e.major if kind == "LENGTH" else e.minor))
    assert doc.update_dimension(sk.sketch_id, doc.active_sketch.dimensions[-1].dim_id, value), doc.last_message


def test_length_and_width_dimensions_drive_the_axes_and_survive_save():
    doc, sk, e = _doc_with_ellipse()
    _dimension(doc, e, "LENGTH", 40.0)
    _dimension(doc, e, "DIAMETER", 16.0)
    e = doc.active_sketch.get_entity(e.entity_id)
    assert (e.major, e.minor) == (pytest.approx(20.0, abs=1e-6), pytest.approx(8.0, abs=1e-6))
    dim = next(d for d in doc.active_sketch.dimensions if d.dim_type == "DIAMETER")
    assert doc.update_dimension(sk.sketch_id, dim.dim_id, 10.0)
    e = doc.active_sketch.get_entity(e.entity_id)
    assert e.minor == pytest.approx(5.0, abs=1e-6) and e.major == pytest.approx(20.0, abs=1e-6)
    assert doc.active_sketch.profiles[0].area == pytest.approx(math.pi * 20 * 5, rel=2e-3)
    back = Sketch.from_dict(doc.active_sketch.to_dict())
    assert back.get_entity(e.entity_id).minor == pytest.approx(5.0)


def test_horizontal_axis_centre_on_origin_and_full_definition():
    doc, sk, e = _doc_with_ellipse()
    origin = sk.add_point((0.0, 0.0))
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [e.entity_id], [])])
    assert doc.add_constraints(sk.sketch_id, [("FIX", [origin.entity_id], [])])
    assert doc.add_constraints(sk.sketch_id, [("COINCIDENT", [e.entity_id, origin.entity_id], ["center", "p"])])
    e = doc.active_sketch.get_entity(e.entity_id)
    assert e.center == pytest.approx((0.0, 0.0), abs=1e-6) and e.angle == pytest.approx(0.0, abs=1e-6) or \
        abs(e.angle) == pytest.approx(math.pi, abs=1e-6)
    assert doc.active_sketch.dof == 2                                       # its two axis lengths are still free
    _dimension(doc, e, "LENGTH", 30.0)
    _dimension(doc, e, "DIAMETER", 12.0)
    assert doc.active_sketch.dof == 0
    from omacad.model.sketch_solver import entity_defined
    assert entity_defined(doc.active_sketch, doc.active_sketch.get_entity(e.entity_id))


def test_concentric_with_a_circle_and_a_distance_from_its_centre():
    doc, sk, e = _doc_with_ellipse()
    c = sk.add_circle((20.0, 20.0), 3.0)
    assert doc.add_constraints(sk.sketch_id, [("CONCENTRIC", [e.entity_id, c.entity_id], [])])
    s = doc.active_sketch
    assert s.get_entity(e.entity_id).center == pytest.approx(s.get_entity(c.entity_id).center, abs=1e-6)
    assert s.get_entity(e.entity_id).minor == pytest.approx(4.0, abs=1e-6)          # the shape is kept


def test_a_free_ellipse_stays_put_when_something_else_is_solved():
    doc, sk, e = _doc_with_ellipse()
    line = sk.add_line((40.0, 0.0), (60.0, 3.0))
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [line.entity_id], [])])
    e2 = doc.active_sketch.get_entity(e.entity_id)
    assert (e2.center, e2.major_end, e2.minor) == (pytest.approx((3.0, 2.0)), pytest.approx((15.0, 5.0)), pytest.approx(4.0))


def test_the_dimension_tool_picks_the_axis_under_the_cursor_and_draws_it(monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QImage, QPainter
    from omacad.model.dim_layout import offset_for_point
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    vp.resize(400, 300)
    sk = doc.start_sketch()
    e = sk.add_ellipse((0.0, 0.0), (20.0, 0.0), 6.0)
    asked = []
    monkeypatch.setattr(vp, "prompt_dimension_value", lambda _t, label, value, *a, **k: asked.append((label, value)) or (value, None))
    vp._dim_ellipse_axis(e, True)
    vp._dim_ellipse_axis(e, False)
    assert [round(v, 6) for _l, v in asked] == [40.0, 12.0]
    kinds = sorted(d.dim_type for d in doc.active_sketch.dimensions)
    assert kinds == ["DIAMETER", "LENGTH"]
    length = next(d for d in doc.active_sketch.dimensions if d.dim_type == "LENGTH")
    assert offset_for_point(doc.active_sketch, length, (0.0, 6.0 + 9.0)) == pytest.approx(9.0)
    img = QImage(400, 300, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    vp.draw_dimensions(p)
    p.end()
    assert len(vp.dim_badges) == 2
    vp.deleteLater()
