"""The Offset Face tool end to end: pick a face, type a distance, OK -> one undoable step with the exact volume."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.features.offset_face import plane_face_ref
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(20, 10, 5)
    return w


def test_offset_face_tool_adds_one_undoable_step(win):
    doc = win.doc
    body = next(iter(doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    win.prompt_offset_face(top)                       # as from the right-click menu
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and len(dlg.faces) == 1 and dlg.faces[0] == plane_face_ref(top)
    dlg.spn_dist.setValue(0.5)
    dlg.accept()
    feats = [f for f in doc.timeline.features if f.feature_type == "offset_face"]
    assert len(feats) == 1 and feats[0].distance == 0.5
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - 20 * 10 * 5.5) < 1e-6
    assert next(iter(doc.bodies.values())).visible
    doc.undo()
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - 1000.0) < 1e-6


def test_cancel_leaves_the_model_alone(win):
    doc = win.doc
    top = max(next(iter(doc.bodies.values())).faces, key=lambda f: f.normal[2])
    win.prompt_offset_face(top)
    win.inspector.current_tool_dlg.reject()
    assert not [f for f in doc.timeline.features if f.feature_type == "offset_face"]
    assert next(iter(doc.bodies.values())).visible
