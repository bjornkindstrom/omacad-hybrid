"""Extend and Break for sketch lines (sketch plan step 5)."""
import math

import pytest

from omacad.model.document import Document


def _length_dim(sk, line):
    return next(d for d in sk.dimensions if d.target_entity_id == line.entity_id and d.dim_type == "LENGTH")


def test_extend_grows_the_nearest_end_to_the_line_it_points_at_and_stays_on_it():
    doc = Document()
    sk = doc.start_sketch()
    wall = sk.add_line((30.0, -20.0), (30.0, 20.0))
    line = sk.add_line((0.0, 5.0), (12.0, 5.0))
    assert doc.extend_line_at(sk.sketch_id, 11.0, 5.0, 1.0)            # near its right end
    sk = doc.active_sketch
    line = sk.get_entity(line.entity_id)
    assert line.p2 == pytest.approx((30.0, 5.0), abs=1e-6) and line.p1 == pytest.approx((0.0, 5.0))
    assert _length_dim(sk, line).value == pytest.approx(30.0)
    assert any(c.ctype == "POINT_ON_LINE" and c.refs == [line.entity_id, wall.entity_id] for c in sk.constraints)
    doc.undo()
    assert doc.active_sketch.get_entity(line.entity_id).p2 == pytest.approx((12.0, 5.0))


def test_extend_reaches_a_circle_and_does_nothing_when_nothing_is_ahead():
    doc = Document()
    sk = doc.start_sketch()
    circle = sk.add_circle((40.0, 0.0), 10.0)
    line = sk.add_line((0.0, 0.0), (10.0, 0.0))
    assert doc.extend_line_at(sk.sketch_id, 9.0, 0.0, 1.0)
    line = doc.active_sketch.get_entity(line.entity_id)
    assert line.p2 == pytest.approx((30.0, 0.0), abs=1e-6)                # the circle's near side
    assert not doc.extend_line_at(doc.active_sketch.sketch_id, 1.0, 0.0, 1.0)   # left end points at nothing
    assert "Extend" in doc.last_message


def test_break_cuts_a_line_in_two_joined_pieces_and_moves_what_was_on_its_end():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (30.0, 0.0))
    up = sk.add_line((30.0, 0.0), (30.0, 10.0))
    doc.add_constraints(sk.sketch_id, [("COINCIDENT", [line.entity_id, up.entity_id], ["p2", "p1"])])
    assert doc.break_line_at(sk.sketch_id, 12.0, 0.3, 1.0)
    sk = doc.active_sketch
    a = sk.get_entity(line.entity_id)
    b = next(e for e in sk.entities if e.entity_type == "line" and e.entity_id not in (line.entity_id, up.entity_id))
    assert a.p2 == pytest.approx((12.0, 0.0), abs=1e-6) and b.p1 == pytest.approx((12.0, 0.0), abs=1e-6)
    assert b.p2 == pytest.approx((30.0, 0.0), abs=1e-6)
    joined = [c for c in sk.constraints if c.ctype == "COINCIDENT" and up.entity_id in c.refs]
    assert joined and b.entity_id in joined[0].refs                      # the corner now belongs to the new piece
    assert _length_dim(sk, a).value == pytest.approx(12.0) and _length_dim(sk, b).value == pytest.approx(18.0)


def test_break_snaps_to_a_crossing_near_the_click():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (30.0, 0.0))
    sk.add_line((20.0, -10.0), (20.0, 10.0))
    assert doc.break_line_at(sk.sketch_id, 19.4, 0.0, 1.0)
    assert doc.active_sketch.get_entity(line.entity_id).p2 == pytest.approx((20.0, 0.0), abs=1e-6)
    assert not doc.break_line_at(doc.active_sketch.sketch_id, 0.1, 0.0, 1.0)      # at its end: nothing to cut


def test_extend_and_break_are_tools_in_the_view_and_the_ribbon():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui import commands
    from omacad.ui.sketch_tools import SKETCH_TOOLS
    from omacad.ui.viewport.viewport import Viewport3D
    assert {"EXTEND", "BREAK"} <= {t[0] for t in SKETCH_TOOLS}
    assert commands.get("extend_sketch").arg == "EXTEND" and commands.get("break_sketch").arg == "BREAK"
    doc = Document()
    vp = Viewport3D(doc)
    vp.resize(600, 400)
    sk = doc.start_sketch()
    sk.add_line((30.0, -20.0), (30.0, 20.0))
    line = sk.add_line((0.0, 5.0), (12.0, 5.0))
    vp.align_to_plane(sk.plane)
    vp.set_sketch_tool("EXTEND")
    tip = vp.world_to_screen(sk.plane.uv_to_world(11.5, 5.0))
    vp._extend_or_break_hover(*tip)
    assert vp.fillet_preview is not None                        # the piece it would grow by
    vp._extend_or_break_at(*tip)
    assert doc.active_sketch.get_entity(line.entity_id).p2 == pytest.approx((30.0, 5.0), abs=1e-6)
    vp.deleteLater()


def test_center_point_arc_follows_the_mouse_round_past_180_degrees():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.model.sketch_entities import center_arc_points, sweep_step
    from omacad.ui.viewport.viewport import Viewport3D
    s, m, e = center_arc_points((0.0, 0.0), (10.0, 0.0), math.radians(270))
    assert m == pytest.approx((-7.0710678, 7.0710678)) and e == pytest.approx((0.0, -10.0), abs=1e-9)
    assert sweep_step((0, 0), (10, 0), (0, 10)) == pytest.approx(math.pi / 2)
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    vp.set_sketch_tool("CENTER_ARC")
    vp.sketch_start_uv = (0.0, 0.0)                 # the centre
    vp._commit_sketch_point((10.0, 0.0))            # the start
    for p in ((0.0, 10.0), (-10.0, 0.0), (0.0, -10.0)):      # the mouse goes three quarters round
        vp._center_arc_sweep += sweep_step((0.0, 0.0), vp._center_arc_last, p)
        vp._center_arc_last = p
    vp._commit_sketch_point((0.0, -10.0))
    arc = next(e for e in doc.active_sketch.entities if e.entity_type == "arc")
    centre, r = arc.get_circle_params()[:2]
    assert centre == pytest.approx((0.0, 0.0), abs=1e-9) and r == pytest.approx(10.0)
    assert arc.p_mid == pytest.approx((-7.0710678, 7.0710678))         # the long way round, through the top-left
    vp.deleteLater()
