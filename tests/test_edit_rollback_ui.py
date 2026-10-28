"""Edit on the timeline rolls the history back to the step while its panel is open (as in Fusion 360): picks see the
model as it was. Shell's open faces and a primitive's 'On face' can be picked again; Cancel or OK rolls forward."""
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane
from omacad.ui import feature_edit
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(20, 20, 20)
    bid = next(iter(w.doc.bodies))
    w.doc.add_shell(bid, 2.0, open_faces=[{"normal": [0.0, 0.0, 1.0], "origin": [0.0, 0.0, 20.0], "body_id": bid}])
    w.doc.add_cylinder(3, 5, plane_origin=[40.0, 0.0, 0.0], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0])
    return w, bid


def _face_plane(face):
    plane = SketchPlane.from_face(face.normal, face.origin)
    plane.face = face
    return plane


def test_shell_edit_picks_another_open_face(win):
    w, bid = win
    seen = {}

    def during():
        seen["marker"] = w.doc.timeline.marker_index
        seen["bodies"] = len(w.doc.bodies)
        seen["volume"] = w.doc.bodies[bid].manifold.volume()            # the box before Shell
        side = max(w.doc.bodies[bid].faces, key=lambda f: f.normal[0])
        w.viewport.shell_face_picked.emit(_face_plane(side))
        seen["open"] = len(w.inspector.current_tool_dlg.open_faces)
        w.inspector.current_tool_dlg.accept()
    QTimer.singleShot(150, during)
    assert feature_edit.edit_feature(w, w.doc, 1)
    assert seen == {"marker": 3, "bodies": 2, "volume": pytest.approx(8000.0), "open": 2}
    assert len(w.doc.timeline.features[1].open_faces) == 2
    assert w.doc.timeline.marker_index == 3 and len(w.doc.bodies) == 2
    w.doc.undo()
    assert len(w.doc.timeline.features[1].open_faces) == 1 and w.doc.timeline.marker_index == 3


def test_cancel_rolls_forward_unchanged(win):
    w, bid = win
    vol = w.doc.bodies[bid].manifold.volume()
    QTimer.singleShot(150, lambda: w.inspector.current_tool_dlg.reject())
    assert not feature_edit.edit_feature(w, w.doc, 1)
    assert w.doc.timeline.marker_index == 3 and len(w.doc.bodies) == 2
    assert w.doc.bodies[bid].manifold.volume() == pytest.approx(vol)
    assert not w.viewport.plane_pick_mode


def test_cylinder_edit_on_face_button_picks_a_face(win):
    w, bid = win

    def during():
        dlg = w.inspector.current_tool_dlg
        dlg.pick_face_requested.emit()
        assert w.viewport.plane_pick_mode
        top = max(w.doc.bodies[bid].faces, key=lambda f: f.normal[2])
        w.viewport.primitive_face_picked.emit(_face_plane(top))
        dlg.accept()
    QTimer.singleShot(150, during)
    feature_edit.edit_feature(w, w.doc, 2)
    assert w.doc.timeline.features[2].plane_origin[2] == pytest.approx(20.0)
