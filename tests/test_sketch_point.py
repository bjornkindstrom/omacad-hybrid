"""Sketch points (sketch plan step 5): placed with one click, kept on what they were snapped to, dimensionable and
solved, saved and loaded, and never part of a profile."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchPoint, point_names
from omacad.model.sketch_solver import point_auto_relations, solve_sketch


def test_a_point_is_dimensioned_and_solved_and_makes_no_profile():
    doc = Document()
    sk = doc.start_sketch()
    wall = sk.add_line((-20.0, 0.0), (20.0, 0.0))
    doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [wall.entity_id], [])])
    point = doc.active_sketch.add_point((3.0, 7.0))
    assert point_names(point) == ("p",)
    assert doc.add_dimension_constraint(doc.active_sketch.sketch_id, "PT_LINE_DIST", point.entity_id, 12.0,
                                        refs=[wall.entity_id], pts=["p"])
    sk = doc.active_sketch
    point, wall = sk.get_entity(point.entity_id), sk.get_entity(wall.entity_id)
    assert abs(point.p[1] - wall.p1[1]) == pytest.approx(12.0, abs=1e-6)
    sk.solve_profiles()
    assert sk.profiles == [] or all(point.entity_id not in getattr(pr, "entity_ids", ()) for pr in sk.profiles)
    again = Sketch.from_dict(sk.to_dict())
    p2 = again.get_entity(point.entity_id)
    assert isinstance(p2, SketchPoint) and p2.p == pytest.approx(point.p) and solve_sketch(again).ok


def test_a_point_placed_on_an_end_or_a_line_stays_there():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (20.0, 0.0))
    on_end = sk.add_point((20.0, 0.0))
    assert point_auto_relations(sk, on_end) == [("COINCIDENT", [on_end.entity_id, line.entity_id], ["p", "p2"])]
    on_line = sk.add_point((8.0, 0.0))
    specs = point_auto_relations(sk, on_line)
    assert specs == [("POINT_ON_LINE", [on_line.entity_id, line.entity_id], ["p"])]
    assert doc.auto_constrain(sk, specs) == 1
    line.p2 = (20.0, 10.0)                                  # the line turns: the point goes along
    assert solve_sketch(sk, fixed_ids=[line.entity_id]).ok
    p = sk.get_entity(on_line.entity_id).p
    assert abs(p[1] - p[0] * 0.5) < 1e-6


def test_point_tool_in_the_view():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    sk.add_line((0.0, 0.0), (20.0, 0.0))
    vp.set_sketch_tool("POINT")
    vp._place_sketch_point((20.0, 0.0))
    sk = doc.active_sketch
    point = next(e for e in sk.entities if isinstance(e, SketchPoint))
    assert any(c.ctype == "COINCIDENT" and point.entity_id in c.refs for c in sk.constraints)
    assert sk.hit_test(20.05, 0.0, 0.2) is not None
    doc.undo()
    assert not any(isinstance(e, SketchPoint) for e in doc.active_sketch.entities)
    vp.deleteLater()
