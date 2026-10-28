"""Björn #76 / #75: every sketch tool shows what to do and its numbers as fields with sliders in the sketch palette;
a value set there locks the shape; Move has X / Y with sliders from the selection's centre, and Copy."""
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.sketch import SketchLine
from omacad.ui.numeric_slider import NumericSlider
from omacad.ui.viewport import Viewport3D


@pytest.fixture
def vp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.start_sketch()
    v = Viewport3D(doc)
    v.sketch_palette.chk_snap_grid.setChecked(False)
    v.sketch_palette.chk_snap_points.setChecked(False)
    monkeypatch.setattr(v, "get_sketch_plane_uv", lambda x, y: (float(x), float(y)))   # screen x/y = sketch u/v
    yield v
    v.set_sketch_tool("NONE")
    v.close()
    v.deleteLater()
    app.processEvents()


def _mouse(v, kind, pos):
    p = QPointF(*pos)
    t = QEvent.Type.MouseButtonPress if kind == "press" else QEvent.Type.MouseMove
    b = Qt.MouseButton.LeftButton if kind == "press" else Qt.MouseButton.NoButton
    (v.mousePressEvent if kind == "press" else v.mouseMoveEvent)(QMouseEvent(t, p, p, b, b, Qt.KeyboardModifier.NoModifier))


@pytest.mark.parametrize("tool, fields", [("LINE", ["Length", "Angle"]), ("RECT", ["Width", "Height"]),
                                          ("POLYGON", ["Side", "Sides"]), ("CIRCLE", ["Diameter"]), ("ARC", []),
                                          ("TRIM", [])])
def test_each_tool_shows_its_fields_with_sliders(vp, tool, fields):
    vp.set_sketch_tool(tool)
    panel = vp.tool_panel
    assert not panel.isHidden() and panel.hint.text()
    assert list(panel.spins) == fields
    assert all(isinstance(s.parentWidget(), NumericSlider) for s in panel.spins.values())


def test_rotate_keeps_its_own_panel(vp):
    vp.doc.active_sketch.add_line((0, 0), (10, 0))
    vp.selected_entities = {vp.doc.active_sketch.entities[0].entity_id}
    vp.set_sketch_tool("ROTATE")
    assert vp.tool_panel.isHidden()


def test_width_set_in_the_panel_locks_every_rectangle(vp):
    vp.set_sketch_tool("RECT")
    vp.tool_panel.spins["Width"].setValue(25.0)
    for start in ((0.0, 0.0), (100.0, 0.0)):
        _mouse(vp, "move", start)
        _mouse(vp, "press", start)
        end = (start[0] + 7.0, start[1] + 12.0)
        _mouse(vp, "move", end)
        assert vp.tool_panel.spins["Height"].value() == pytest.approx(12.0)     # follows the mouse
        _mouse(vp, "press", end)
    lines = [e for e in vp.doc.active_sketch.entities if isinstance(e, SketchLine)]
    widths = sorted(abs(l.p2[0] - l.p1[0]) for l in lines if abs(l.p2[1] - l.p1[1]) < 1e-9)
    assert widths == pytest.approx([25.0] * 4)


def test_polygon_sides_in_the_panel_set_the_default(vp):
    vp.set_sketch_tool("POLYGON")
    vp.tool_panel.spins["Sides"].setValue(8)
    assert vp.sketch_palette.spn_sides.value() == 8


def test_move_x_slider_moves_at_once_and_copy_keeps_the_original(vp):
    sk = vp.doc.active_sketch
    line = sk.add_line((0.0, 0.0), (10.0, 0.0))
    vp.selected_entities = {line.entity_id}
    vp.set_sketch_tool("MOVE")
    vp.tool_panel.chk_copy.setChecked(True)
    vp.tool_panel.spins["X"].setValue(30.0)
    vp.tool_panel.spins["Y"].setValue(5.0)
    assert sk.get_entity(line.entity_id).p1 == pytest.approx((30.0, 5.0))       # live, before any click
    vp._commit_sketch_point(vp.sketch_current_uv)
    lines = sorted((e.p1, e.p2) for e in sk.entities if isinstance(e, SketchLine))
    assert lines == [((0.0, 0.0), (10.0, 0.0)), ((30.0, 5.0), (40.0, 5.0))]
    assert len(vp.doc.undo_stack) >= 1


def test_pattern_rows_columns_and_around_a_centre_ok_and_cancel(vp):
    sk = vp.doc.active_sketch
    circle = sk.add_circle((0.0, 0.0), 2.0)
    vp.selected_entities = {circle.entity_id}
    vp.set_sketch_tool("PATTERN")
    panel = vp.pattern_panel
    assert not panel.isHidden()
    panel.count_x.setValue(3)
    panel.spacing_x.setValue(10.0)
    panel.count_y.setValue(2)
    panel.spacing_y.setValue(7.0)
    centres = sorted(tuple(e.center) for e in sk.entities)
    assert centres == sorted((10.0 * i, 7.0 * j) for i in range(3) for j in range(2))
    panel.kind.setCurrentIndex(1)                       # circular, about the sketch origin
    panel.centre.setCurrentIndex(panel.centre.findData("origin"))
    panel.count.setValue(4)
    assert len(sk.entities) == 4                        # the circle sits on the origin: four on top of each other
    panel.cancel.click()
    assert [e.entity_id for e in sk.entities] == [circle.entity_id]
    vp.selected_entities = {circle.entity_id}
    vp.set_sketch_tool("PATTERN")
    panel.kind.setCurrentIndex(0)                       # the type is remembered: back to rows
    panel.count_x.setValue(4)
    panel.ok.click()
    assert len(sk.entities) == 4 and vp.sketch_tool == "NONE"
    vp.doc.undo()
    assert len(vp.doc.active_sketch.entities) == 1
