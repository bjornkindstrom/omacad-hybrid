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


def test_star_shape_ui_toggles_and_params(win):
    from omacad.model.features.honeycomb import HoneycombFeature
    dlg = SurfaceTextureDialog(win.doc)
    dlg.show()
    page = dlg.pages["honeycomb"]
    page.cmb_shape.setCurrentIndex(SHAPES.index("star"))
    assert page.spins["star_points"].isVisible()
    assert page.spins["star_inner"].isVisible()
    assert page.spins["randomness"].isVisible()
    assert page.spins["random_rotation"].isVisible()
    assert page.spins["seed"].isVisible()
    assert page.chk_random_size.isVisible()
    assert not page.spins["fine_size"].isVisible()

    page.chk_random_size.setChecked(True)
    assert page.spins["fine_size"].isVisible()
    page.spins["star_points"].setValue(6)
    page.spins["star_inner"].setValue(35)
    page.spins["fine_size"].setValue(2.5)
    page.spins["random_rotation"].setValue(180)
    params = dlg.params()
    assert params["shape"] == "star"
    assert params["random_size"] is True
    assert params["star_points"] == 6.0
    assert params["star_inner"] == 35.0
    assert params["fine_size"] == 2.5
    assert params["random_rotation"] == 180.0

    feat = HoneycombFeature("h1", "Cells 1", "b1", **params)
    dlg2 = SurfaceTextureDialog(win.doc, feature=feat)
    p2 = dlg2.params()
    assert p2["shape"] == "star" and p2["random_size"] is True
    assert p2["star_points"] == 6.0 and p2["star_inner"] == 35.0
    dlg.close()
    dlg.deleteLater()
    dlg2.close()
    dlg2.deleteLater()
