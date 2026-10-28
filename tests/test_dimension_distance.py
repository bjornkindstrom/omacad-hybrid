"""Dimensions can be dragged out of the way, parallel lines get a distance, and bodies can be set apart."""
import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from omacad.model.dim_layout import line_distance, lines_are_parallel, offset_for_point  # noqa: E402
from omacad.model.document import Document  # noqa: E402
from omacad.model.sketch import SketchLine  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402


@pytest.fixture
def view(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    v = Viewport3D(Document())
    v.resize(800, 600)
    return v


def test_parallel_detection_and_gap():
    a, b = SketchLine("a", (0, 0), (10, 0)), SketchLine("b", (2, 7), (30, 7))
    assert lines_are_parallel(a, b) and lines_are_parallel(a, SketchLine("c", (5, 3), (-4, 3.01)))
    assert not lines_are_parallel(a, SketchLine("d", (0, 0), (10, 2)))
    assert line_distance(a, b) == pytest.approx(7.0)


def test_offset_for_point_inverts_the_layout():
    doc = Document()
    sk = doc.start_sketch("XY")
    ln = sk.add_line((0, 0), (10, 0))
    sk.add_dimension("LENGTH", ln.entity_id, 10.0, offset_distance=12.0)
    assert offset_for_point(sk, sk.dimensions[-1], (4, 7)) == pytest.approx(7.0)     # normal of +x is +y
    assert offset_for_point(sk, sk.dimensions[-1], (4, -3)) == pytest.approx(-3.0)
    a, b = sk.add_line((0, 0), (0, 5)), sk.add_line((20, 8), (20, 20))
    sk.add_dimension("HORIZ_DIST", a.entity_id, 20.0, refs=[b.entity_id], pts=["p1", "p1"])
    sk.add_dimension("VERT_DIST", a.entity_id, 8.0, refs=[b.entity_id], pts=["p2", "p1"])
    assert offset_for_point(sk, sk.dimensions[-2], (3, 30)) == pytest.approx(30 - 8)   # above the higher point (y=8)
    assert offset_for_point(sk, sk.dimensions[-1], (35, 3)) == pytest.approx(35 - 20)  # right of the further point (x=20)
    circ = sk.add_circle((50, 50), 5.0)
    sk.add_dimension("DIAMETER", circ.entity_id, 10.0, offset_distance=12.0)
    assert offset_for_point(sk, sk.dimensions[-1], (50, 70)) == pytest.approx(15.0)


def test_parallel_lines_distance_is_driven_and_kept_parallel():
    doc = Document()
    sk = doc.start_sketch("XY")
    a, b = sk.add_line((0, 0), (30, 0)), sk.add_line((0, 10), (30, 10.2))
    assert lines_are_parallel(a, b)
    assert doc.add_constraints(sk.sketch_id, [("PARALLEL", [a.entity_id, b.entity_id], [])])
    assert doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", a.entity_id, 25.0, refs=[b.entity_id], pts=["p1"])
    a, b = sk.get_entity(a.entity_id), sk.get_entity(b.entity_id)
    assert line_distance(a, b) == pytest.approx(25.0, abs=1e-4)
    assert lines_are_parallel(a, b, 0.01)


def _mouse(kind, pos, button=Qt.MouseButton.LeftButton):
    return QMouseEvent(kind, QPointF(*pos), QPointF(*pos), button, button, Qt.KeyboardModifier.NoModifier)


def test_dragging_a_badge_moves_the_dimension_and_is_one_undo_step(view):
    doc = view.doc
    sk = doc.start_sketch("XY")
    view.azimuth, view.elevation = 0.0, 89.9
    ln = sk.add_line((0, 0), (40, 0))
    doc.add_dimension_constraint(sk.sketch_id, "LENGTH", ln.entity_id, 40.0)
    dim = sk.dimensions[-1]
    before = dim.offset_distance
    view.align_to_plane(sk.plane)
    sk_now = doc.active_sketch
    rect_pos = lambda uv: view.world_to_screen(sk_now.plane.uv_to_world(*uv))
    start = rect_pos((20, before))
    from PySide6.QtCore import QRectF
    view.dim_badges[dim.dim_id] = (QRectF(start[0] - 30, start[1] - 10, 60, 20), sk.sketch_id, dim.dim_id, 40.0)
    view.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, start))
    target = rect_pos((20, 25))
    view.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, target, Qt.MouseButton.NoButton))
    view.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, target))
    assert dim.offset_distance == pytest.approx(25.0, abs=0.5)
    n = len(doc.undo_stack)
    assert doc.undo_stack[-1][0] == "sketch"
    doc.undo()
    assert sk.dimensions[-1].offset_distance == pytest.approx(before)
    assert len(doc.undo_stack) == n - 1


def test_set_distance_between_two_bodies(view, monkeypatch):
    from omacad.model.measure import measure_3d
    doc = view.doc
    doc.add_box(10, 10, 10)
    doc.add_box(10, 10, 10)
    b1, b2 = list(doc.bodies.values())[:2]
    doc.move_body(b2.body_id, 30.0, 0.0, 0.0)          # gap of 20 along x
    b1, b2 = list(doc.bodies.values())[:2]
    e1 = next(e for e in b1.edges if e.kind == "line" and abs(e.p0[0] - e.p1[0]) < 1e-6 and e.p0[0] > 9 and abs(e.p0[1]) < 1e-3)
    e2 = next(e for e in b2.edges if e.kind == "line" and abs(e.p0[0] - e.p1[0]) < 1e-6 and e.p0[0] < min(b2.render_mesh.bounds_min[0] + 1, 100)
              and abs(e.p0[1] - e1.p0[1]) < 1e-3)
    text, segs = measure_3d([e1, e2])
    view.measure = {"mode": "model", "picks": [e1, e2], "text": text, "segs": segs}
    plan = view._measure_set_distance_plan()
    assert plan is not None and plan[0] is b2 and plan[2] == pytest.approx(20.0, abs=1e-3)
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda self, *a, **k: (35.0, None))
    view._measure_set_distance()
    b2_after = doc.bodies[b2.body_id]
    gap = float(b2_after.render_mesh.bounds_min[0] - doc.bodies[b1.body_id].render_mesh.bounds_max[0])
    assert gap == pytest.approx(35.0, abs=1e-3)


def test_dimension_tool_on_two_parallel_lines_gives_a_distance(view, monkeypatch):
    doc = view.doc
    sk = doc.start_sketch("XY")
    a, b = sk.add_line((0, 0), (40, 0)), sk.add_line((0, 12), (40, 12))
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda self, *a_, **k: (20.0, None))
    assert view.handle_dimension_tool_click(20.0, 0.0)
    assert view.handle_dimension_tool_click(20.0, 12.0)
    kinds = [d.dim_type for d in sk.dimensions]
    assert kinds.count("PT_LINE_DIST") == 1 and "ANGLE" not in kinds, kinds    # (drawn lines come with LENGTH dims)
    assert any(c.ctype == "PARALLEL" for c in sk.constraints)
    la, lb = sk.get_entity(a.entity_id), sk.get_entity(b.entity_id)
    assert line_distance(la, lb) == pytest.approx(20.0, abs=1e-4)
    # clicking the same pair again edits the existing dimension instead of adding a second one
    edited = []
    monkeypatch.setattr(type(view), "prompt_edit_dimension", lambda self, *a_: edited.append(a_))
    for ln in (la, lb):
        view.handle_dimension_tool_click((ln.p1[0] + ln.p2[0]) / 2, (ln.p1[1] + ln.p2[1]) / 2)
    assert [d.dim_type for d in sk.dimensions].count("PT_LINE_DIST") == 1 and edited
