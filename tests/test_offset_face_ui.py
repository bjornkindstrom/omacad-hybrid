"""Offset Face UI, interactive viewport picking, tool prompts, and multi-face editing."""
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.faces_hit_tests import detect_cylinder_surface
from omacad.model.features.offset_face import plane_face_ref
from omacad.model.kernel import CadKernel
from omacad.ui import feature_edit
from omacad.ui.main_window import MainWindow
from omacad.ui.viewport import picker_mixin
from omacad.ui.viewport.viewport import Viewport3D

_app = QApplication.instance() or QApplication([])
REPORT_PROJECT = Path(__file__).parent.parent / ".state" / "data" / "feedback" / "20261115-082920" / "document.omacad"
SECTION_DOC = "tests/data/offset_face_section_thread.omacad"


@pytest.fixture
def win():
    window = MainWindow()
    window.resize(1000, 700)
    window.doc.add_box(20.0, 10.0, 5.0)
    yield window
    if window.inspector.current_tool_dlg is not None:
        window.inspector.current_tool_dlg.reject()
    window.close()
    window.deleteLater()
    _app.processEvents()


@pytest.fixture
def viewport(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from omacad.model.document import Document
    from omacad.ui import settings as settings_mod
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    d = Document()
    d.add_cylinder(10, 20)
    v = Viewport3D(d)
    v.resize(900, 700)
    v.begin_plane_pick("offset_face")
    return v


def _hover(v, world):
    v._hover_patch_time = 0.0
    x, y = v.world_to_screen(np.asarray(world, dtype=float))
    v._update_offset_hover(x, y)
    return x, y


# =========================================================================
# Tool lifecycle & basic prompts
# =========================================================================

def test_offset_face_tool_adds_one_undoable_step(win):
    doc = win.doc
    body = next(iter(doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    win.prompt_offset_face(top)
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


def test_preselected_curved_patch_in_prompt_offset_face(win):
    doc = Exporter.load_project(str(REPORT_PROJECT))
    win.attach_document(doc)
    b3 = doc.bodies["body_cylinder_3"]
    mesh = b3.render_mesh
    for i in range(len(mesh.vertices) // 3):
        cyl = detect_cylinder_surface(mesh, i)
        if cyl and cyl["is_internal"]:
            tris = mesh.curved_surface(i)
            break

    win.viewport.selected_faces = [("body_cylinder_3", tris)]
    win.prompt_offset_face()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None
    assert len(dlg.faces) == 1
    assert dlg.faces[0]["kind"] == "cylinder"
    assert dlg.faces[0]["internal"] is True
    assert dlg.body_id == "body_cylinder_3"

    point, normal = dlg.drag_frame(b3)
    assert np.dot(point[:2], normal[:2]) < 0


# =========================================================================
# Viewport hover & picking
# =========================================================================

def test_cylinder_wall_lights_up_and_picks(viewport):
    v = viewport
    picked = []
    v.offset_face_picked.connect(lambda ref, bid: picked.append(ref))
    x, y = _hover(v, (7.0, 7.0, 10.0))
    assert v.hover_patch is not None and len(v.hover_patch) > 24 and v.hover_plane is None
    v._offset_face_click(x, y)
    assert picked and picked[0]["kind"] == "cylinder"


def test_flat_face_lights_up_as_a_face(viewport):
    v = viewport
    _hover(v, (0.0, 0.0, 20.0))
    assert v.hover_patch is None and v.hover_plane is not None and v.hover_plane[0] == "face"


class _StubViewport(Viewport3D):
    def __init__(self):
        pass


def test_pick_goes_through_the_cut_away_half(monkeypatch):
    doc = Exporter.load_project(SECTION_DOC)
    nut = doc.bodies["body_cylinder_2"]
    vp = _StubViewport()
    vp.doc, vp.plane_pick_purpose, vp.shell_target_body_id = doc, "offset_face", nut.body_id
    vp.get_matrices = lambda: (None, None, None)
    vp.width = vp.height = lambda: 100
    p, keep = np.zeros(3), np.array([0.0, -1.0, 0.0])
    vp.section = {"origin": p, "normal": np.array([0.0, 1.0, 0.0]), "offset": 0.0, "flip": False,
                  "meshes": {b.body_id: CadKernel.extract_render_mesh(b.manifold.trim_by_plane(tuple(keep), 0.0))
                             for b in doc.bodies.values()}}
    monkeypatch.setattr(picker_mixin, "ray_from_screen", lambda *a: (np.array([0.0, 100.0, 20.0]), np.array([0.0, -1.0, 0.0])))
    hit = vp._pick_surface(0, 0)
    assert hit is not None
    assert hit["point"][1] < 0 and abs(hit["point"][1]) < 23
    assert not vp._section_keeps([0.0, 5.0, 0.0]) and vp._section_keeps([0.0, -5.0, 0.0])


# =========================================================================
# Multi-face selection & editing
# =========================================================================

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


# =========================================================================
# Visual inspection (requires real display or OpenGL context)
# =========================================================================

THREAD_DOC = str(Path(__file__).parent / "data" / "offset_face_coil_stuck.omacad")


def _picture(win, app, doc):
    import time
    win.attach_document(doc)
    win.showFullScreen()
    t = time.time()
    while time.time() - t < 1.5:
        app.processEvents()
    vp = win.viewport
    vp.azimuth, vp.elevation, vp.distance = 193.3, 22.0, 16.0
    vp.target = np.array([0.0, 0.0, 15.0])
    doc.bodies["body_cylinder_1"].visible = False
    for sid in doc.sections:
        doc.set_section_active(sid, True)
    for _ in range(40):
        app.processEvents()
    vp.update()
    for _ in range(20):
        app.processEvents()
    img = vp.grabFramebuffer()
    if img.isNull():
        return None
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, :w].astype(float)
    return a[int(h * 0.1):int(h * 0.5), int(w * 0.3):int(w * 0.7)]


def _stripes(c) -> float:
    return float(np.abs(np.diff(c, axis=1)).mean() / max(np.abs(np.diff(c, axis=0)).mean(), 1e-9))


def _thread_doc(mode):
    doc = Exporter.load_project(THREAD_DOC)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    if mode == "thread":
        doc.add_offset_face("body_split_2", last.faces, -0.2)
    elif mode == "mesh":
        last.suppressed = False
        doc.timeline.recompute(doc)
    return doc


@pytest.mark.desktop
def test_thread_offset_looks_as_clean_as_the_original():
    app = QApplication.instance() or QApplication([])
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    ratios = {}
    for mode in ("orig", "thread", "mesh"):
        win = MainWindow()
        pic = _picture(win, app, _thread_doc(mode))
        win.close()
        if pic is None or pic.std() < 1.0:
            pytest.skip("no GL picture (offscreen)")
        ratios[mode] = _stripes(pic)
    assert ratios["thread"] < ratios["orig"] * 1.2, ratios
    assert ratios["mesh"] > ratios["thread"] * 1.3, ratios
