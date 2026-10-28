"""Rotation transaction: preview, pivot changes, pick, cancellation, undo and persistence."""
import pytest
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication
from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchConstraint
from omacad.ui.viewport import Viewport3D


@pytest.fixture
def scene():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch()
    selected = sk.add_slot((2, 2), (8, 2), 1)
    untouched = sk.add_circle((20, 20), 2)
    viewport = Viewport3D(doc)
    viewport.selected_entities = {selected.entity_id}
    yield doc, sk, viewport, selected.entity_id, untouched.entity_id
    viewport.set_sketch_tool("NONE")
    viewport.close()
    viewport.deleteLater()
    app.processEvents()


def test_preview_pivot_changes_cancel_commit_undo_redo_and_save(scene):
    doc, sk, vp, eid, other = scene
    before = sk.to_dict()
    undo_count = len(doc.undo_stack)
    vp.set_sketch_tool("ROTATE")
    panel = vp.rotation_panel
    assert panel.pivot.currentData() == "area"
    assert vp._move["pivot"] == pytest.approx((5, 2))
    panel.angle.setValue(90)
    assert sk.get_entity(eid).center1 == pytest.approx((5, -1))
    panel.pivot.setCurrentIndex(panel.pivot.findData("origin"))
    assert sk.get_entity(eid).center1 == pytest.approx((-2, 2))
    assert sk.get_entity(other).to_dict() == before["entities"][1]
    assert len(doc.undo_stack) == undo_count
    panel.cancel.click()
    assert sk.to_dict() == before
    vp.set_sketch_tool("ROTATE")
    panel.angle.setValue(90)
    panel.ok.click()
    after = sk.to_dict()
    assert len(doc.undo_stack) == undo_count + 1
    assert vp.sketch_tool == "NONE"
    doc.undo()
    assert sk.to_dict() == before
    doc.redo()
    assert sk.to_dict() == after
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert loaded.sketches[sk.sketch_id].get_entity(eid).to_dict() == sk.get_entity(eid).to_dict()


def _mouse(vp, kind, pos, mods=Qt.KeyboardModifier.NoModifier):
    p = QPointF(*pos)
    types = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove, "release": QEvent.Type.MouseButtonRelease}
    buttons = Qt.MouseButton.NoButton if kind == "release" else Qt.MouseButton.LeftButton
    event = QMouseEvent(types[kind], p, p, Qt.MouseButton.LeftButton, buttons, mods)
    {"press": vp.mousePressEvent, "move": vp.mouseMoveEvent, "release": vp.mouseReleaseEvent}[kind](event)


def test_click_sets_custom_pivot_and_escape_restores_everything(scene, monkeypatch):
    doc, sk, vp, eid, _ = scene
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(90)
    vp.sketch_palette.chk_snap_grid.setChecked(False)
    vp.sketch_palette.chk_snap_points.setChecked(False)
    monkeypatch.setattr(vp, "get_sketch_plane_uv", lambda x, y: (1.0, 1.0))
    _mouse(vp, "press", (10, 10))
    _mouse(vp, "release", (10, 10))
    assert vp.rotation_panel.pivot.currentData() == "custom"
    assert vp._move["pivot"] == pytest.approx((1, 1))
    assert sk.get_entity(eid).center1 == pytest.approx((0, 2))
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert sk.to_dict() == before
    assert vp.sketch_tool == "NONE"


def test_drag_around_pivot_rotates_shift_snaps_and_enter_is_one_undo_step(scene, monkeypatch):
    doc, sk, vp, eid, _ = scene
    before = sk.to_dict()
    undo_count = len(doc.undo_stack)
    vp.set_sketch_tool("ROTATE")
    assert vp._move["pivot"] == pytest.approx((5, 2))       # figure area centre
    # screen x/y stand for sketch u/v here: the pivot is at (5, 2)
    monkeypatch.setattr(vp, "get_sketch_plane_uv", lambda x, y: (float(x), float(y)))
    _mouse(vp, "press", (10, 2))
    _mouse(vp, "move", (5, 7))                                # a quarter turn counter-clockwise
    assert vp.rotation_panel.angle.value() == pytest.approx(90)
    assert sk.get_entity(eid).center1 == pytest.approx((5, -1))
    _mouse(vp, "move", (5 + 10 * 0.643, 2 + 10 * 0.766), Qt.KeyboardModifier.ShiftModifier)   # 50° -> 45° step
    assert vp.rotation_panel.angle.value() == pytest.approx(45)
    for x, y in ((0, 2), (5, -3), (10, 2), (5 + 10 * 0.643, 2 + 10 * 0.766)):   # once more around: 360 + 50°
        _mouse(vp, "move", (x, y))
    assert vp.rotation_panel.angle.value() == pytest.approx(410)
    _mouse(vp, "move", (5 + 10 * 0.643, 2 + 10 * 0.766), Qt.KeyboardModifier.ShiftModifier)
    assert vp.rotation_panel.angle.value() == pytest.approx(405)
    _mouse(vp, "release", (5 + 10 * 0.643, 2 + 10 * 0.766))
    assert vp._move["pivot"] == pytest.approx((5, 2))       # a drag does not move the pivot
    assert len(doc.undo_stack) == undo_count                # still only a preview
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert vp.sketch_tool == "NONE"
    assert len(doc.undo_stack) == undo_count + 1
    doc.undo()
    assert sk.to_dict() == before


def test_drag_angle_wraps_to_half_turn():
    from omacad.ui.viewport.sketch_rotate_mixin import drag_angle
    assert drag_angle((0, 0), (1, 0), (0, 1)) == pytest.approx(90)
    assert drag_angle((0, 0), (0, 1), (1, 0)) == pytest.approx(-90)
    assert drag_angle((0, 0), (-1, 0.01), (-1, -0.01)) == pytest.approx(1.146, abs=1e-3)


def test_fixed_and_projected_geometry_are_protected(scene):
    _, sk, vp, eid, _ = scene
    sk.constraints.append(SketchConstraint("fixed", "FIX", [eid]))
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(30)
    assert not vp.rotation_panel.ok.isEnabled()
    vp.rotation_panel.cancel.click()
    assert sk.to_dict() == before
    sk.get_entity(eid).projected = True
    vp.set_sketch_tool("ROTATE")
    assert vp.sketch_tool == "NONE"
    assert vp._move is None


def test_rectangle_rotation_restores_constraints_on_cancel_and_is_one_undo_step(scene):
    doc, sk, vp, _, _ = scene
    lines = sk.add_rect((0, 0), (6, 3))
    vp.selected_entities = {e.entity_id for e in lines}
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(45)
    assert any(c.ctype == "PERPENDICULAR" for c in sk.constraints)
    vp.set_sketch_tool("LINE")
    assert sk.to_dict() == before
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(45)
    vp.rotation_panel.ok.click()
    doc.undo()
    assert sk.to_dict() == before
    vp.set_sketch_tool("ROTATE")
    undo_count = len(doc.undo_stack)
    vp.rotation_panel.ok.click()  # zero degrees makes no history entry
    assert len(doc.undo_stack) == undo_count


def test_rotation_rejects_incompatible_axis_distance(scene):
    _, sk, vp, _, other = scene
    line = sk.add_line((2, 2), (8, 2))
    vp.selected_entities = {line.entity_id}
    sk.add_dimension("HORIZ_DIST", line.entity_id, 18, refs=[other], pts=["p1", "center"])
    before = sk.to_dict()
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(90)
    assert not vp.rotation_panel.ok.isEnabled()
    vp.rotation_panel.cancel.click()
    assert sk.to_dict() == before


def test_text_rotates_about_picked_coordinates_and_path_text_is_protected(scene):
    from shapely import affinity
    _, sk, vp, _, _ = scene
    text = sk.add_text("L", (4, 3), height=5)
    expected = affinity.rotate(text.geometry(), 30, origin=(0, 0))
    vp.selected_entities = {text.entity_id}
    vp.set_sketch_tool("ROTATE")
    panel = vp.rotation_panel
    panel.pivot.setCurrentIndex(panel.pivot.findData("origin"))
    panel.angle.setValue(30)
    moved = sk.get_entity(text.entity_id)
    assert moved.geometry().symmetric_difference(expected).area < 1e-6
    assert moved.sketch is sk
    panel.ok.click()
    path = sk.add_circle((0, 0), 10, is_construction=True)
    text = sk.add_text("PATH", height=3, path_id=path.entity_id)
    before = sk.to_dict()
    vp.selected_entities = {text.entity_id}
    vp.set_sketch_tool("ROTATE")
    panel.angle.setValue(30)
    assert not panel.ok.isEnabled()
    panel.cancel.click()
    assert sk.to_dict() == before


def test_rounded_rectangle_rotates_and_keeps_its_size_dimensions(scene):
    import math
    from omacad.model.sketch import SketchLine
    doc, sk, vp, _, _ = scene
    lines = sk.add_rounded_rect((0, 0), (30, 20), 4)
    vp.selected_entities = set(sk.connected_entities(lines[0].entity_id))
    vp.set_sketch_tool("ROTATE")
    vp.rotation_panel.angle.setValue(30)
    assert vp.rotation_panel.ok.isEnabled()          # used to be blocked by horizontal/vertical size dimensions
    vp.rotation_panel.ok.click()
    bottom = sk.get_entity(lines[0].entity_id)
    assert math.degrees(math.atan2(bottom.p2[1] - bottom.p1[1], bottom.p2[0] - bottom.p1[0])) == pytest.approx(30, abs=1e-3)
    width = next(d for d in sk.dimensions if d.name == "Width" and d.dim_type == "PT_LINE_DIST")   # not the slot's
    assert doc.update_dimension(sk.sketch_id, width.dim_id, 40)
    bottom, left, right = (sk.get_entity(lines[i].entity_id) for i in (0, 3, 1))
    assert math.degrees(math.atan2(bottom.p2[1] - bottom.p1[1], bottom.p2[0] - bottom.p1[0])) == pytest.approx(30, abs=1e-3)
    ux, uy = math.cos(math.radians(30)), math.sin(math.radians(30))   # along the bottom wall
    assert abs((right.p1[0] - left.p1[0]) * ux + (right.p1[1] - left.p1[1]) * uy) == pytest.approx(40, abs=1e-3)
    guides = [e for e in sk.entities if isinstance(e, SketchLine) and e.is_construction]
    assert len({(round(g.p2[0], 4), round(g.p2[1], 4)) for g in guides}) == 4   # still meeting at four corners
