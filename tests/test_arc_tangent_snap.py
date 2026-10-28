"""Björn #53: the 3-point Arc sticks to exactly tangent when it meets a line or arc almost smoothly."""
import math

import pytest

from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchArc
from omacad.model.sketch_tangent import arc_out_direction, snap_tangent_arc


def _sketch_with_line(p1, p2):
    sk = Sketch("s", "S", SketchPlane())
    sk.add_line(p1, p2)
    return sk


def _angle(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))))


def test_arc_leaving_a_line_almost_smoothly_snaps_to_tangent():
    sk = _sketch_with_line((-10.0, 0.0), (0.0, 0.0))           # line arriving at the origin along +x
    start, end = (0.0, 0.0), (10.0, 10.0)                       # quarter circle about (0, 10) is the tangent one
    cursor = (7.2, 2.8)                                         # a few degrees off
    assert 0 < _angle(arc_out_direction(start, cursor, end), (1.0, 0.0)) < 8
    mid = snap_tangent_arc(start, end, cursor, sk.entities)
    assert mid == pytest.approx((10 * math.sin(math.pi / 4), 10 - 10 * math.cos(math.pi / 4)), abs=1e-9)
    assert _angle(arc_out_direction(start, mid, end), (1.0, 0.0)) == pytest.approx(0.0, abs=1e-6)
    params = SketchArc("a", start, mid, end).get_circle_params()
    assert params[0] == pytest.approx((0.0, 10.0)) and params[1] == pytest.approx(10.0)


def test_far_from_smooth_does_not_stick():
    sk = _sketch_with_line((-10.0, 0.0), (0.0, 0.0))
    assert snap_tangent_arc((0.0, 0.0), (10.0, 10.0), (2.0, 8.0), sk.entities) is None


def test_arc_arriving_at_a_line_end_snaps_too():
    sk = _sketch_with_line((10.0, 10.0), (10.0, 20.0))         # line leaving (10, 10) upwards
    start, end = (0.0, 0.0), (10.0, 10.0)
    mid = snap_tangent_arc(start, end, (7.2, 2.8), sk.entities)  # the same quarter circle, tangent at its end
    assert mid is not None
    d = arc_out_direction(start, mid, end, at_end=True)
    assert _angle(d, (0.0, 1.0)) == pytest.approx(0.0, abs=1e-6)


def test_arc_following_an_arc_snaps_to_its_tangent():
    sk = Sketch("s", "S", SketchPlane())
    sk.add_arc((-10.0, 10.0), (-10 * math.sin(math.pi / 4), 10 - 10 * math.cos(math.pi / 4)), (0.0, 0.0))  # about (0, 10)
    # the first arc arrives at the origin heading +x; continue with a reverse curve down to (10, -10)
    mid = snap_tangent_arc((0.0, 0.0), (10.0, -10.0), (7.2, -2.8), sk.entities)
    assert mid is not None
    assert _angle(arc_out_direction((0.0, 0.0), mid, (10.0, -10.0)), (1.0, 0.0)) == pytest.approx(0.0, abs=1e-6)


def test_face_edge_counts_as_a_neighbour():
    refs = [((-10.0, 0.0), (0.0, 0.0))]
    assert snap_tangent_arc((0.0, 0.0), (10.0, 10.0), (7.2, 2.8), [], refs) is not None


def test_arc_tool_sticks_to_tangent_and_draws_the_tangent_arc(monkeypatch):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from omacad.model.document import Document
    from omacad.ui.viewport import Viewport3D
    app = QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch()
    sk.add_line((-10.0, 0.0), (0.0, 0.0))
    vp = Viewport3D(doc)
    vp.sketch_palette.chk_snap_grid.setChecked(False)
    vp.set_sketch_tool("ARC")
    monkeypatch.setattr(vp, "get_sketch_plane_uv", lambda x, y: (float(x), float(y)))   # screen x/y = sketch u/v

    def event(kind, pos):
        p = QPointF(*pos)
        t = QEvent.Type.MouseButtonPress if kind == "press" else QEvent.Type.MouseMove
        b = Qt.MouseButton.LeftButton if kind == "press" else Qt.MouseButton.NoButton
        (vp.mousePressEvent if kind == "press" else vp.mouseMoveEvent)(QMouseEvent(t, p, p, b, b, Qt.KeyboardModifier.NoModifier))

    for pos in ((0.0, 0.0), (10.0, 10.0)):
        event("move", pos)
        event("press", pos)
    event("move", (7.2, 2.8))
    assert vp.active_snap.snap_type == "TANGENT"
    event("press", (7.2, 2.8))
    arc = next(e for e in sk.entities if isinstance(e, SketchArc))
    centre, r = arc.get_circle_params()[:2]
    assert centre == pytest.approx((0.0, 10.0), abs=1e-6) and r == pytest.approx(10.0, abs=1e-6)
    vp.set_sketch_tool("NONE")
    vp.close()
    vp.deleteLater()
    app.processEvents()
