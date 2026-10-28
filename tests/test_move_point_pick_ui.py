"""Move / Rotate panel: pick a point on the body (here the hidden corner of a rounding) and a point on another
body; the preview follows, OK makes a point-to-point Move step, Esc after the first point keeps it as the pivot."""
import time

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication


def _move(vp, point):
    p = QPointF(*point)
    vp.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, p, p, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                  Qt.KeyboardModifier.NoModifier))


def _click(vp, point):
    _move(vp, point)
    p = QPointF(*point)
    for kind, buttons, handler in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton, vp.mousePressEvent),
                                   (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton, vp.mouseReleaseEvent)):
        handler(QMouseEvent(kind, p, p, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier))


@pytest.fixture
def scene():
    from omacad.ui.main_window import MainWindow
    from omacad.ui.dialogs.transform_dlg import MoveBodyDialog
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
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


def _screen(vp, xyz):
    return tuple(vp.world_to_screen(np.array(xyz, dtype=float)))


def test_pick_hidden_corner_then_box_corner_and_ok(scene):
    app, win, doc, vp, dlg, block, box = scene
    dlg.btn_points.setChecked(True)
    assert vp.point_pick
    assert vp.move_gizmo is None
    _move(vp, _screen(vp, (30, 20, 10)))
    assert vp.hover_point is not None and vp.hover_point[1] == "corner"     # shown though no edge is there
    _click(vp, _screen(vp, (30, 20, 10)))
    frm, to = dlg.get_points()
    assert frm["kind"] == "corner" and frm["body"] == block and frm["xyz"] == pytest.approx([30, 20, 10], abs=1e-3)
    assert dlg.cmb_pivot.currentData() == "point"
    _click(vp, _screen(vp, (50, 40, 0)))
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


def test_escape_after_first_point_keeps_it_as_pivot(scene):
    app, win, doc, vp, dlg, block, box = scene
    dlg.btn_points.setChecked(True)
    _click(vp, _screen(vp, (30, 20, 10)))
    vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not vp.point_pick and not dlg.btn_points.isChecked()
    frm, to = dlg.get_points()
    assert frm is not None and to is None and dlg.cmb_pivot.currentData() == "point"
    dlg.spn_rz.setValue(90)
    dlg.accept()
    for _ in range(5):
        app.processEvents()
    bb = doc.bodies[block].manifold.bounding_box()
    # a quarter turn counter-clockwise about the corner (30, 20), which stays put: x 30..50, y -10..20
    assert bb[:2] == pytest.approx((30, -10), abs=1e-3) and bb[3:5] == pytest.approx((50, 20), abs=1e-3)


def test_right_click_selects_body_in_move_tool(scene):
    app, win, doc, vp, dlg, block, box = scene
    vp.pick_body = lambda *_: box
    p = QPointF(500, 400)
    vp.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, p, p, Qt.MouseButton.RightButton,
                                   Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier))
    vp.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, p, p, Qt.MouseButton.RightButton,
                                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert dlg.get_values()[0] == box
    assert doc.selected_body_ids == [box]


@pytest.mark.parametrize("projection", ["perspective", "orthographic"])
def test_face_centres_show_and_points_behind_the_body_do_not(scene, projection):
    from omacad.ui.settings import get_settings
    app, win, doc, vp, dlg, block, box = scene
    get_settings().set("view_projection", projection)
    dlg.btn_points.setChecked(True)
    _move(vp, _screen(vp, (55, 45, 10)))
    assert vp.hover_point is not None and vp.hover_point[1] == "top_center"
    shown = [tuple(np.round(c[2], 3)) for c in vp._near_points]
    assert (55.0, 45.0, 10.0) in shown
    assert (55.0, 45.0, 0.0) not in shown            # the bottom centre is behind the box seen from above
    _move(vp, _screen(vp, (15, 0, 5)))
    assert vp.hover_point is not None and vp.hover_point[1] == "face_center"
    assert vp.hover_point[2] == pytest.approx((15, 0, 5), abs=1e-3)
    _move(vp, _screen(vp, (15, 10, 10)))             # the moved body hides behind its preview, yet still hides its back
    shown = [tuple(np.round(c[2], 3)) for c in vp._near_points]
    assert (15.0, 10.0, 10.0) in shown and (15.0, 10.0, 0.0) not in shown
