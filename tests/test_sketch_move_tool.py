"""Sketch Move: pick several things, Enter, click the base point, click the target. It only translates."""
import pytest
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication
from omacad.model.document import Document
from omacad.ui.dyn_input import DynInput
from omacad.ui.viewport import Viewport3D


@pytest.fixture
def scene():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0, 0), (10, 0))
    circle = sk.add_circle((20, 5), 2)
    other = sk.add_circle((40, 40), 1)
    vp = Viewport3D(doc)
    yield doc, sk, vp, line.entity_id, circle.entity_id, other.entity_id
    vp.set_sketch_tool("NONE")
    vp.close()
    vp.deleteLater()
    app.processEvents()


def _press(vp, button=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    p = QPointF(10, 10)
    vp.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, p, p, button, button, mods))


def _key(vp, key):
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))


def test_pick_several_enter_base_point_then_target_translates_without_rotating(scene, monkeypatch):
    doc, sk, vp, line, circle, other = scene
    before = sk.to_dict()
    undo_count = len(doc.undo_stack)
    vp.set_sketch_tool("MOVE")
    assert vp.sketch_tool == "MOVE" and vp._move_phase == "pick"

    for eid in (line, circle):
        monkeypatch.setattr(vp, "_pick_entity", lambda x, y, e=sk.get_entity(eid): e)
        _press(vp)
    assert vp.selected_entities == {line, circle}
    _key(vp, Qt.Key.Key_Return)
    assert vp._move_phase == "base"

    vp.sketch_current_uv = (10.0, 0.0)          # base point: the line's end
    _press(vp)
    vp.sketch_current_uv = (13.0, 5.0)          # target: up and to the right, diagonal
    _press(vp)

    assert sk.get_entity(line).p1 == pytest.approx((3, 5))
    assert sk.get_entity(line).p2 == pytest.approx((13, 5))   # still horizontal: no angle from the mouse
    assert sk.get_entity(circle).center == pytest.approx((23, 10))
    assert sk.get_entity(other).to_dict() == before["entities"][2]
    assert len(doc.undo_stack) == undo_count + 1
    assert vp.sketch_tool == "NONE"
    doc.undo()
    assert sk.to_dict() == before


def test_preselected_goes_straight_to_base_point_and_has_no_angle_field(scene):
    doc, sk, vp, line, *_ = scene
    vp.selected_entities = {line}
    vp.set_sketch_tool("MOVE")
    assert vp._move_phase == "base"
    dyn = DynInput()
    dyn.start("MOVE")
    assert dyn.names == ["X", "Y"]
    end, live = dyn.resolve((0, 0), (3, 4))
    assert end == pytest.approx((3, 4)) and set(live) == {"X", "Y"}


def test_enter_without_pick_stays_and_escape_cancels(scene):
    doc, sk, vp, *_ = scene
    before = sk.to_dict()
    vp.set_sketch_tool("MOVE")
    _key(vp, Qt.Key.Key_Return)
    assert vp.sketch_tool == "MOVE" and vp._move_phase == "pick"
    _key(vp, Qt.Key.Key_Escape)
    assert vp.sketch_tool == "NONE"
    assert sk.to_dict() == before
