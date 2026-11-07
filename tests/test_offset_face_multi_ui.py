"""Request #192: edit the face set and see every selection while Offset Face previews."""
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.features.offset_face import plane_face_ref
from omacad.ui import feature_edit
from omacad.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def win():
    window = MainWindow()
    window.doc.add_box(20., 10., 5.)
    yield window
    window.close()
    window.deleteLater()


@pytest.mark.parametrize("accept", [True, False])
def test_edit_can_add_faces_with_persistent_highlights_and_undo(win, accept, tmp_path):
    doc, vp = win.doc, win.viewport
    body = next(iter(doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    doc.add_offset_face(body.body_id, [plane_face_ref(top)], 0.5)
    before = doc.bodies[body.body_id].manifold.volume()
    seen = {}

    def finish():
        dlg = win.inspector.current_tool_dlg
        seen["highlighted"] = len(vp.highlighted_faces)
        seen["listed"] = dlg.lst_faces.count()
        dlg.accept() if accept else dlg.reject()

    def pick():
        dlg = win.inspector.current_tool_dlg
        seen["initial"] = (len(dlg.faces), dlg.lst_faces.count(), vp.plane_pick_mode, vp.shell_target_body_id)
        side = max(doc.bodies[body.body_id].faces, key=lambda f: f.normal[0])
        vp.offset_face_picked.emit(plane_face_ref(side), body.body_id)
        QTimer.singleShot(120, finish)

    QTimer.singleShot(120, pick)
    assert bool(feature_edit.edit_feature(win, doc, 1)) == accept
    assert seen["initial"] == (1, 1, True, body.body_id)
    assert seen["listed"] == seen["highlighted"] == 2
    assert not vp.plane_pick_mode and not vp.shell_target_body_id and not vp.highlighted_faces
    assert doc.bodies[body.body_id].visible
    if accept:
        assert len(doc.timeline.features[1].faces) == 2
        assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(20.5 * 10. * 5.5)
        path = tmp_path / "multi.omacad"
        Exporter.save_project(doc, str(path))
        loaded = Exporter.load_project(str(path))
        assert len(loaded.timeline.features[1].faces) == 2
        doc.undo()
        assert len(doc.timeline.features[1].faces) == 1
        assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(before)
        doc.redo()
        assert len(doc.timeline.features[1].faces) == 2
    else:
        assert len(doc.timeline.features[1].faces) == 1
        assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(before)


def test_new_selection_lists_highlights_removes_and_clears(win):
    doc, vp = win.doc, win.viewport
    body = next(iter(doc.bodies.values()))
    win.prompt_offset_face(max(body.faces, key=lambda f: f.normal[2]))
    dlg = win.inspector.current_tool_dlg
    side = max(body.faces, key=lambda f: f.normal[0])
    vp.offset_face_picked.emit(plane_face_ref(side), body.body_id)
    assert dlg.lst_faces.count() == 2
    assert len(dlg.highlights(body)) == 2
    dlg.lst_faces.setCurrentRow(0)
    dlg.btn_remove.click()
    assert len(dlg.faces) == dlg.lst_faces.count() == 1
    dlg.clear()
    assert not dlg.faces and not dlg.body_id and not dlg.btn_ok.isEnabled()
    dlg.reject()
    assert body.visible and not vp.highlighted_faces


def test_cylindrical_selections_distinguish_concentric_faces_and_highlight():
    import numpy as np
    from omacad.model.document import Document
    from omacad.ui.dialogs.offset_face_dlg import OffsetFaceDialog
    doc = Document()
    body = doc.add_cylinder(10., 15., wall_thickness=2.)
    dlg = OffsetFaceDialog()
    outer = dict(kind="cylinder", origin=[0., 0., 0.], axis=[0., 0., 1.], radius=10., length=15., internal=False)
    inner = {**outer, "radius": 8., "internal": True}
    dlg.toggle(outer, body.body_id)
    dlg.toggle(inner, body.body_id)
    assert len(dlg.faces) == 2
    highlights = dlg.highlights(body)
    assert len(highlights) == 2
    for h, radius in zip(highlights, (10., 8.)):
        assert len(h["tris"]) > 0
        assert np.linalg.norm(h["tris"][:, :, :2], axis=2) == pytest.approx(radius, abs=0.02)
    dlg.reject()
    dlg.deleteLater()


def test_curved_selection_highlights_the_whole_smooth_patch():
    import numpy as np
    from omacad.model.document import Document
    from omacad.ui.dialogs.offset_face_dlg import OffsetFaceDialog
    doc = Document()
    body = doc.add_cylinder(10., 15.)
    dlg = OffsetFaceDialog()
    dlg.toggle({"kind": "surface", "point": [10., 0., 7.], "normal": [1., 0., 0.]}, body.body_id)
    triangles = dlg.highlights(body)[0]["tris"]
    assert len(triangles) > 10
    assert np.ptp(triangles[:, :, 0]) > 19.9
    assert np.ptp(triangles[:, :, 2]) == pytest.approx(15.)
    dlg.reject()
    dlg.deleteLater()
