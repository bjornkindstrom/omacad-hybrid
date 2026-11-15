"""Surface Texture's cells end to end: ribbon button, pick flat face/cylinder, preview, OK undo, and dialog controls."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.features.offset_face import plane_face_ref
from omacad.model.features.honeycomb import SHAPES
from omacad.ui.dialogs import SurfaceTextureDialog
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(40, 30, 20, wall_thickness=2)
    yield w
    w.close()
    w.deleteLater()


def test_honeycomb_tool_adds_one_undoable_step(win):
    doc = win.doc
    body = next(iter(doc.bodies.values()))
    v0 = body.manifold.volume()
    win.ribbon.surface_texture_clicked.emit()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and dlg.windowTitle() == "Surface Texture" and dlg.kind() == "honeycomb"
    front = min(body.faces, key=lambda f: f.normal[1])
    win.viewport.offset_face_picked.emit(plane_face_ref(front), body.body_id)
    dlg.page.cmb_shape.setCurrentIndex(2)                        # square
    dlg.accept()
    feats = [f for f in doc.timeline.features if f.feature_type == "honeycomb"]
    assert len(feats) == 1 and feats[0].shape == "square" and feats[0].cells > 0
    after = next(iter(doc.bodies.values()))
    assert after.visible
    assert v0 - after.manifold.volume() == pytest.approx(feats[0].cells * 36.0 * 2.0, rel=1e-6)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(v0, rel=1e-9)


def test_cancel_leaves_the_model_alone(win):
    win.prompt_surface_texture()
    win.inspector.current_tool_dlg.reject()
    assert not [f for f in win.doc.timeline.features if f.feature_type == "honeycomb"]
    assert next(iter(win.doc.bodies.values())).visible


def test_panel_shows_randomness_and_seed_only_for_voronoi(win):
    dlg = SurfaceTextureDialog(win.doc)
    dlg.show()
    page = dlg.pages["honeycomb"]
    assert not page.spins["randomness"].isVisible() and not page.spins["seed"].isVisible()
    page.cmb_shape.setCurrentIndex(SHAPES.index("voronoi"))
    assert page.spins["randomness"].isVisible() and page.spins["seed"].isVisible()
    page.spins["seed"].setValue(5)
    params = dlg.params()
    assert (params["shape"], params["seed"], params["randomness"]) == ("voronoi", 5.0, 100.0)
    dlg.close()
    dlg.deleteLater()
