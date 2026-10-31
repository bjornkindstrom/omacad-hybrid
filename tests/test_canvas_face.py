"""Canvas placement on a translated, tilted body face survives editing and saving."""
import json
import numpy as np
import pytest
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.canvas import canvas_plane
from omacad.model.document import Document
from omacad.ui.canvas_dialog import CanvasEditorDialog


def test_canvas_face_placement_edit_save_and_undo(tmp_path):
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(40, 30, 20)
    bid = next(iter(doc.bodies))
    doc.move_body(bid, dx=17, dy=9, dz=25, rx=30)
    face = doc.bodies[bid].faces[0]
    path = str(tmp_path / "reference.png")
    img = QImage(12, 8, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    assert img.save(path)
    dlg = CanvasEditorDialog(doc, initial_image_path=path, preselected_face=face)
    data = dlg.get_canvas_data()
    assert data["plane_id"] == "FACE"
    cid = doc.add_canvas(**data)
    plane = canvas_plane(doc, doc.canvases[cid])
    assert np.dot(plane.normal, face.normal) == pytest.approx(1, abs=1e-6)
    for u, v in ((-6, -4), (6, 4), (0, 0)):
        assert np.dot(plane.uv_to_world(u, v) - face.origin, face.normal) == pytest.approx(0, abs=1e-5)
    copy = Document()
    Exporter.apply_dict(copy, json.loads(json.dumps(Exporter.document_to_dict(doc))))
    assert canvas_plane(copy, copy.canvases[cid]).origin == pytest.approx(plane.origin)
    edit = CanvasEditorDialog(copy, existing_canvas_id=cid)
    assert edit.get_canvas_data()["face_plane"] == data["face_plane"]
    edit.cmb_plane.setCurrentIndex(edit.cmb_plane.findData("XZ"))
    copy.update_canvas(cid, **edit.get_canvas_data())
    assert canvas_plane(copy, copy.canvases[cid]).name == "XZ"
    doc.undo()
    assert not doc.canvases
    doc.redo()
    assert canvas_plane(doc, doc.canvases[cid]).origin == pytest.approx(plane.origin)
    dlg.close()
    edit.close()


def test_canvas_dialog_offers_body_faces_without_creating_planes():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 20, 30)
    before = doc.snapshot()
    dlg = CanvasEditorDialog(doc)
    faces = [dlg.cmb_plane.itemData(i) for i in range(dlg.cmb_plane.count())
             if isinstance(dlg.cmb_plane.itemData(i), dict)]
    assert len(faces) == 6
    dlg.reject()
    assert doc.snapshot() == before


def test_face_context_menu_opens_canvas_editor_on_that_face(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QMenu
    from omacad.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.doc.add_box(10, 20, 30)
    face = next(iter(win.doc.bodies.values())).faces[0]
    path = str(tmp_path / "image.png")
    img = QImage(4, 4, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    img.save(path)
    monkeypatch.setattr(win.viewport, "_pick_plane_target", lambda *_: ("face", face))
    class FaceMenu(QMenu):
        def exec(self, *_):
            return next(a for a in self.actions() if "Insert Canvas on this Face" in a.text())

    monkeypatch.setattr("omacad.ui.viewport.context_menu_mixin.QMenu", FaceMenu)

    def accept_image(dialog):
        dialog.load_image_file(path)
        return 1

    monkeypatch.setattr(CanvasEditorDialog, "exec", accept_image)
    received = []
    win.viewport.canvas_face_requested.connect(received.append)
    event = SimpleNamespace(position=lambda: QPointF(10, 10), globalPosition=lambda: QPointF(10, 10))
    win.viewport._show_face_menu(event)
    app.processEvents()
    assert received == [face]
    assert len(win.doc.canvases) == 1
    c = next(iter(win.doc.canvases.values()))
    assert np.dot(canvas_plane(win.doc, c).normal, face.normal) == pytest.approx(1)
    win.close()


def test_fit_to_face_scales_the_image_inside_the_face_and_centres_it(tmp_path):
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(40, 30, 20)
    bid = next(iter(doc.bodies))
    doc.move_body(bid, dx=17, dy=9, dz=25, rx=30)
    face = doc.bodies[bid].faces[0]
    path = str(tmp_path / "wide.png")
    img = QImage(300, 100, QImage.Format.Format_RGB32)   # 3:1 image on a face that is not 3:1
    img.fill(QColor("red"))
    assert img.save(path)
    dlg = CanvasEditorDialog(doc, initial_image_path=path, preselected_face=face)
    assert dlg.btn_fit_face.isEnabled()
    dlg.fit_to_face()
    from omacad.model.canvas import face_size_uv
    cu, cv, fw, fh = face_size_uv(face)
    data = dlg.get_canvas_data()
    assert data["width_mm"] <= fw + 1e-6 and data["height_mm"] <= fh + 1e-6
    assert max(data["width_mm"] / fw, data["height_mm"] / fh) == pytest.approx(1, rel=1e-6)  # fills one side
    cid = doc.add_canvas(**data)
    plane = canvas_plane(doc, doc.canvases[cid])
    centre = plane.uv_to_world(cu, cv)
    origin_u, origin_v = data["origin_uv"]
    image_centre = plane.uv_to_world(origin_u + data["width_mm"] / 2, origin_v + data["height_mm"] / 2)
    assert image_centre == pytest.approx(centre, abs=1e-5)
    dlg.close()


def test_fit_to_face_is_only_enabled_for_a_face_with_an_image(tmp_path):
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(40, 30, 20)
    dlg = CanvasEditorDialog(doc)
    dlg.cmb_plane.setCurrentIndex(dlg.cmb_plane.findData("XY"))
    assert not dlg.btn_fit_face.isEnabled()          # no image yet, and an origin plane
    dlg.close()
