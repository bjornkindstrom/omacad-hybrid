"""Move feature UI, gizmo interaction, face-to-face and point-to-point picking tests."""
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.geometry import face_centroid
from omacad.ui.dialogs.transform_dlg import MoveBodyDialog
from omacad.ui.main_window import MainWindow

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Gizmo drag & immediate apply UI tests
# ==============================================================================

@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    w.doc.add_box(10, 10, 10)
    yield w
    w.close()


def _min_x(win):
    return next(iter(win.doc.bodies.values())).manifold.bounding_box()[0]


def _moves(win):
    return [f for f in win.doc.timeline.features if f.feature_type == "move"]


def _drag(win, axis, delta):
    win.viewport.move_gizmo_dragged.emit(axis, delta)
    win.viewport.move_gizmo_finished.emit()
    QApplication.processEvents()


def test_two_drags_without_ok_are_two_applied_moves(win):
    win.prompt_move_body()
    dlg = win.inspector.current_tool_dlg
    _drag(win, "X", 10.0)
    assert len(_moves(win)) == 1 and _min_x(win) == pytest.approx(10.0)
    assert dlg.spn_dx.value() == 0.0 and win.inspector.current_tool_dlg is dlg
    _drag(win, "X", 5.0)
    assert len(_moves(win)) == 2 and _min_x(win) == pytest.approx(15.0)
    dlg.accept()
    assert len(_moves(win)) == 2
    win.doc.undo()
    assert _min_x(win) == pytest.approx(10.0)


def test_escape_keeps_applied_moves_and_drops_the_pending_one(win):
    win.prompt_move_body()
    dlg = win.inspector.current_tool_dlg
    _drag(win, "X", 10.0)
    dlg.spn_dy.setValue(7.0)
    dlg.reject()
    assert len(_moves(win)) == 1 and _min_x(win) == pytest.approx(10.0)
    assert next(iter(win.doc.bodies.values())).manifold.bounding_box()[1] == pytest.approx(0.0)


def test_starting_a_pick_applies_the_typed_move_first(win):
    win.prompt_move_body()
    dlg = win.inspector.current_tool_dlg
    dlg.spn_dx.setValue(20.0)
    dlg.btn_points.setChecked(True)
    assert len(_moves(win)) == 1 and _min_x(win) == pytest.approx(20.0)
    dlg.btn_points.setChecked(False)
    dlg.reject()


# ==============================================================================
# Face to face dialog flow tests
# ==============================================================================

def test_dialog_flow_two_clicks_fills_the_numbers_and_the_option_recomputes():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    doc = w.doc
    doc.add_box(20, 20, 10)
    a = next(iter(doc.bodies))
    doc.add_box(6, 6, 4)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=40)
    w.prompt_move_body(b)
    dlg = w.inspector.current_tool_dlg
    vp = w.viewport
    src = max(doc.bodies[b].faces, key=lambda f: -f.normal[2])
    dst = max(doc.bodies[a].faces, key=lambda f: f.normal[2])
    dlg.btn_f2f.setChecked(True)
    assert vp.move_gizmo is None
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", src)))
    assert dlg.btn_f2f.isChecked()
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", dst)))
    assert not dlg.btn_f2f.isChecked()
    assert vp.move_gizmo is not None
    assert not doc.bodies[b].visible
    want = face_centroid(dst) - face_centroid(src)
    assert np.allclose([dlg.spn_dx.value(), dlg.spn_dy.value(), dlg.spn_dz.value()], want, atol=1e-3)
    assert abs(want[2] - 10.0) < 1e-6 and np.linalg.norm(want[:2]) > 1.0
    assert np.allclose([dlg.spn_rx.value(), dlg.spn_ry.value(), dlg.spn_rz.value()], 0, atol=1e-3)
    dlg.chk_f2f_centre.setChecked(False)
    assert np.allclose([dlg.spn_dx.value(), dlg.spn_dy.value(), dlg.spn_dz.value()], [0, 0, 10], atol=1e-3)
    dlg.reject()
    w.close()


def test_dialog_flow_accepts_target_face_before_moving_face():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    doc = w.doc
    doc.add_box(20, 20, 10)
    a = next(iter(doc.bodies))
    doc.add_box(6, 6, 4)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=40)
    w.prompt_move_body(b)
    dlg, vp = w.inspector.current_tool_dlg, w.viewport
    src = max(doc.bodies[b].faces, key=lambda f: -f.normal[2])
    dst = max(doc.bodies[a].faces, key=lambda f: f.normal[2])
    dlg.btn_f2f.setChecked(True)
    assert vp.move_gizmo is None
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", dst)))
    assert dlg.btn_f2f.isChecked()
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", src)))
    assert not dlg.btn_f2f.isChecked()
    assert vp.move_gizmo is not None
    assert not doc.bodies[b].visible
    want = face_centroid(dst) - face_centroid(src)
    assert np.allclose([dlg.spn_dx.value(), dlg.spn_dy.value(), dlg.spn_dz.value()], want, atol=1e-3)
    dlg.reject()
    w.close()


def test_lay_on_ground_hides_gizmo_and_accepts_a_body_face():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    doc = w.doc
    doc.add_box(6, 6, 4)
    bid = next(iter(doc.bodies))
    doc.move_body(bid, dx=40, dz=12)
    w.prompt_move_body(bid)
    dlg, vp = w.inspector.current_tool_dlg, w.viewport

    assert vp.move_gizmo is not None
    dlg.btn_lay.setChecked(True)
    assert vp.move_gizmo is None
    assert doc.bodies[bid].visible
    face = max(doc.bodies[bid].faces, key=lambda f: f.normal[0])
    vp.move_body_picked.emit(vp.plane_from_target(("face", face)))
    assert not dlg.btn_lay.isChecked()
    assert vp.move_gizmo is not None
    assert dlg.spn_rx.value() != 0 or dlg.spn_ry.value() != 0
    dlg.reject()
    w.close()


# ==============================================================================
# Point to point picking in Viewport
# ==============================================================================

def _move_mouse(vp, point):
    p = QPointF(*point)
    vp.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, p, p, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                  Qt.KeyboardModifier.NoModifier))


def _click_mouse(vp, point):
    _move_mouse(vp, point)
    p = QPointF(*point)
    for kind, buttons, handler in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton, vp.mousePressEvent),
                                   (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton, vp.mouseReleaseEvent)):
        handler(QMouseEvent(kind, p, p, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))


@pytest.fixture
def p2p_scene():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.viewport.paintGL = lambda: None
    win.viewport.initializeGL = lambda: None
    doc = win.doc
    sk = doc.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (30, 20), 4)
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 10)
    block = next(iter(doc.bodies))
    doc.add_box(10, 10, 10)
    box = next(b for b in doc.bodies if b != block)
    doc.move_body(box, 50, 40, 0, pivot="origin")
    vp = win.viewport
    vp.resize(1000, 800)
    vp.azimuth, vp.elevation, vp.distance = 30., 25., 160.
    vp.target = np.array([30., 20., 5.], dtype=np.float32)
    doc.selected_body_ids = {block}
    win.prompt_move_body(block)
    dlg = next(w for w in app.allWidgets() if isinstance(w, MoveBodyDialog) and not w.isHidden())
    yield app, win, doc, vp, dlg, block, box
    if not dlg.isHidden() and dlg.result() == 0:
        dlg.reject()
    win.close()


def _screen_coords(vp, xyz):
    return tuple(vp.world_to_screen(np.array(xyz, dtype=float)))


def test_pick_hidden_corner_then_box_corner_and_ok(p2p_scene):
    app, win, doc, vp, dlg, block, box = p2p_scene
    dlg.btn_points.setChecked(True)
    assert vp.point_pick
    assert vp.move_gizmo is None
    _move_mouse(vp, _screen_coords(vp, (30, 20, 10)))
    assert vp.hover_point is not None and vp.hover_point[1] == "corner"
    _click_mouse(vp, _screen_coords(vp, (30, 20, 10)))
    frm, to = dlg.get_points()
    assert frm["kind"] == "corner" and frm["body"] == block and frm["xyz"] == pytest.approx([30, 20, 10], abs=1e-3)
    assert dlg.cmb_pivot.currentData() == "point"
    _click_mouse(vp, _screen_coords(vp, (50, 40, 0)))
    frm, to = dlg.get_points()
    assert to["body"] == box and to["xyz"] == pytest.approx([50, 40, 0], abs=1e-3)
    assert not vp.point_pick and not dlg.btn_points.isChecked()
    dlg.accept()
    for _ in range(5):
        app.processEvents()
    bb = doc.bodies[block].manifold.bounding_box()
    assert bb[3:] == pytest.approx((50, 40, 0), abs=1e-3)
    move = [f for f in doc.timeline.features if f.feature_type == "move"][-1]
    assert move.from_point["kind"] == "corner" and move.to_point["body"] == box


def test_escape_after_first_point_keeps_it_as_pivot(p2p_scene):
    app, win, doc, vp, dlg, block, box = p2p_scene
    dlg.btn_points.setChecked(True)
    _click_mouse(vp, _screen_coords(vp, (30, 20, 10)))
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not vp.point_pick and not dlg.btn_points.isChecked()
    frm, to = dlg.get_points()
    assert frm is not None and to is None and dlg.cmb_pivot.currentData() == "point"
    dlg.spn_rz.setValue(90)
    dlg.accept()
    for _ in range(5):
        app.processEvents()
    bb = doc.bodies[block].manifold.bounding_box()
    assert bb[:2] == pytest.approx((30, -10), abs=1e-3) and bb[3:5] == pytest.approx((50, 20), abs=1e-3)


def test_right_click_selects_body_in_move_tool(p2p_scene):
    app, win, doc, vp, dlg, block, box = p2p_scene
    vp.pick_body = lambda *_: box
    p = QPointF(500, 400)
    vp.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, p, p, Qt.MouseButton.RightButton,
                                   Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier))
    vp.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, p, p, Qt.MouseButton.RightButton,
                                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert dlg.get_values()[0] == box
    assert doc.selected_body_ids == [box]


@pytest.mark.parametrize("projection", ["perspective", "orthographic"])
def test_face_centres_show_and_points_behind_the_body_do_not(p2p_scene, projection):
    from omacad.ui.settings import get_settings
    app, win, doc, vp, dlg, block, box = p2p_scene
    get_settings().set("view_projection", projection)
    dlg.btn_points.setChecked(True)
    _move_mouse(vp, _screen_coords(vp, (55, 45, 10)))
    assert vp.hover_point is not None and vp.hover_point[1] == "top_center"
    shown = [tuple(np.round(c[2], 3)) for c in vp._near_points]
    assert (55.0, 45.0, 10.0) in shown
    assert (55.0, 45.0, 0.0) not in shown
    _move_mouse(vp, _screen_coords(vp, (15, 0, 5)))
    assert vp.hover_point is not None and vp.hover_point[1] == "face_center"
    assert vp.hover_point[2] == pytest.approx((15, 0, 5), abs=1e-3)
    _move_mouse(vp, _screen_coords(vp, (15, 10, 10)))
    shown = [tuple(np.round(c[2], 3)) for c in vp._near_points]
    assert (15.0, 10.0, 10.0) in shown and (15.0, 10.0, 0.0) not in shown
