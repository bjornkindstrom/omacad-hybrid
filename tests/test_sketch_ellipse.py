"""Ellipse in a sketch: three clicks, a closed profile, edits and save/load."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch


def test_an_ellipse_is_a_closed_profile_of_the_right_area_and_survives_save():
    doc = Document()
    sk = doc.start_sketch()
    e = sk.add_ellipse((10.0, 5.0), (30.0, 5.0), 8.0)
    assert e.major == pytest.approx(20.0) and e.minor == 8.0
    assert len(sk.profiles) == 1 and sk.profiles[0].area == pytest.approx(math.pi * 20 * 8, rel=2e-3)
    back = Sketch.from_dict(sk.to_dict()).entities[0]
    assert (back.center, back.major_end, back.minor) == (e.center, e.major_end, e.minor)
    assert sk.hit_test(10.0, 13.0, 0.2) is e and sk.hit_test(10.0, 5.0, 0.2) is None


def test_move_turn_scale_and_mirror_keep_its_shape():
    from omacad.model.sketch_entities import move_entity, rotate_entity, scale_entity
    doc = Document()
    sk = doc.start_sketch()
    e = sk.add_ellipse((0.0, 0.0), (10.0, 0.0), 4.0)
    move_entity(e, 5.0, 1.0)
    rotate_entity(e, 90.0, e.center)
    assert e.major_end == pytest.approx((5.0, 11.0)) and e.angle == pytest.approx(math.pi / 2)
    scale_entity(e, 2.0, e.center)
    assert (e.major, e.minor) == (pytest.approx(20.0), pytest.approx(8.0))
    m = sk.mirror_entities([e.entity_id], (0.0, -100.0), (0.0, 100.0))[0]
    assert m.center == pytest.approx((-5.0, 1.0)) and (m.major, m.minor) == (pytest.approx(20.0), pytest.approx(8.0))


def test_the_tool_draws_it_with_three_clicks_and_a_constrained_sketch_still_solves():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui import commands
    from omacad.ui.sketch_tools import SKETCH_TOOLS
    from omacad.ui.viewport.viewport import Viewport3D
    assert "ELLIPSE" in {t[0] for t in SKETCH_TOOLS} and commands.get("ellipse").arg == "ELLIPSE"
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    line = sk.add_line((40.0, 0.0), (60.0, 3.0))
    vp.set_sketch_tool("ELLIPSE")
    vp.sketch_start_uv = (0.0, 0.0)
    vp._commit_sketch_point((12.0, 0.0))                 # the long axis
    vp._commit_sketch_point((3.0, 5.0))                  # how wide: 5 from the axis
    e = next(x for x in doc.active_sketch.entities if x.entity_type == "ellipse")
    assert (e.major, e.minor) == (pytest.approx(12.0), pytest.approx(5.0))
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [line.entity_id], [])])
    sk = doc.active_sketch
    assert sk.get_entity(line.entity_id).p1[1] == pytest.approx(sk.get_entity(line.entity_id).p2[1])
    assert sk.get_entity(e.entity_id).major_end == pytest.approx((12.0, 0.0))        # the ellipse stands still
    doc.undo()
    doc.undo()
    assert not [x for x in doc.active_sketch.entities if x.entity_type == "ellipse"]
    vp.deleteLater()
