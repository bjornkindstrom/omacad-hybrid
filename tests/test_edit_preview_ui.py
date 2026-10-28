"""Edit on the timeline: the preview of a primitive that was dragged before placing sits where the body is, and
editing a step right after making it has a preview (its before/after states are built first)."""
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from omacad.ui import feature_edit
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def _open_edit_and_look(win, index):
    seen = {}

    def look():
        seen["mesh"] = win.viewport.preview_mesh
        win.inspector.current_tool_dlg.reject()
    QTimer.singleShot(150, look)
    feature_edit.edit_feature(win, win.doc, index)
    return seen.get("mesh")


def test_moved_box_previews_where_it_is(win):
    win.doc.add_box(10, 10, 10, translation=[30.0, 0.0, 0.0])
    mesh = _open_edit_and_look(win, 0)
    assert mesh is not None and mesh.bounds_min[0] == pytest.approx(30.0, abs=1e-4)


def test_offset_face_edit_right_after_adding_has_a_preview(win):
    from omacad.model.features.offset_face import plane_face_ref
    win.doc.add_box(20, 20, 20)
    body = next(iter(win.doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    win.doc.add_offset_face(body.body_id, [plane_face_ref(top)], 2.0)
    win.doc.step_states.clear()                                       # as after an add without a rebuild
    mesh = _open_edit_and_look(win, 1)
    assert mesh is not None and mesh.bounds_max[2] == pytest.approx(22.0, abs=1e-4)
