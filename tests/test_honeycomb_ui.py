"""The Honeycomb tool end to end: ribbon button, pick a flat face and a cylinder, preview, OK -> one undoable step."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.features.offset_face import plane_face_ref
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(40, 30, 20, wall_thickness=2)
    return w


def test_honeycomb_tool_adds_one_undoable_step(win):
    doc = win.doc
    body = next(iter(doc.bodies.values()))
    v0 = body.manifold.volume()
    win.ribbon.honeycomb_clicked.emit()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and dlg.windowTitle() == "Honeycomb"
    front = min(body.faces, key=lambda f: f.normal[1])
    win.viewport.offset_face_picked.emit({"kind": "surface", "point": [0, 0, 0], "normal": [1, 0, 0]}, body.body_id)
    assert dlg.faces == []                                  # a free-form surface takes no honeycomb
    win.viewport.offset_face_picked.emit(plane_face_ref(front), body.body_id)
    dlg.cmb_shape.setCurrentIndex(2)                        # square
    dlg.accept()
    feats = [f for f in doc.timeline.features if f.feature_type == "honeycomb"]
    assert len(feats) == 1 and feats[0].shape == "square" and feats[0].cells > 0
    after = next(iter(doc.bodies.values()))
    assert after.visible
    assert v0 - after.manifold.volume() == pytest.approx(feats[0].cells * 36.0 * 2.0, rel=1e-6)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(v0, rel=1e-9)


def test_cancel_leaves_the_model_alone(win):
    win.prompt_honeycomb()
    win.inspector.current_tool_dlg.reject()
    assert not [f for f in win.doc.timeline.features if f.feature_type == "honeycomb"]
    assert next(iter(win.doc.bodies.values())).visible
