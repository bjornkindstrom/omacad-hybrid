"""Shell feature UI dialog and face picking regression tests."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui import dialogs
from omacad.ui.dialogs.shell_dlg import ShellDialog
from omacad.ui.main_window import MainWindow
from omacad.ui.numeric_slider import NumericSlider
from omacad.ui.viewport import Viewport3D
from omacad.ui import feature_edit

DATA_DIR = Path(__file__).parent / "data"


def _two_boxes():
    doc = Document()
    for cx in (0, 40):
        sk = doc.start_sketch("XY")
        sk.add_rect((cx, 0), (cx + 10, 10))
        doc.finish_sketch()
        doc.extrude_profile(sk.sketch_id, 0, 10.0)
    return doc


def test_toggle_face_uses_numpy():
    assert dialogs.np is np


def test_shell_pick_hits_hidden_target_body_only(monkeypatch):
    doc = _two_boxes()
    a, b = list(doc.bodies.values())
    a.visible = False
    vp = SimpleNamespace(doc=doc, plane_pick_mode=True, plane_pick_purpose="shell_face",
                         shell_target_body_id=a.body_id, width=lambda: 100, height=lambda: 100,
                         get_matrices=lambda: (None, None, None),
                         _origin_quadrant_size=lambda: 100.0)
    top = next(f for f in a.faces if f.normal[2] > 0.9)
    monkeypatch.setattr("omacad.ui.viewport.ray_from_screen",
                        lambda *args: (np.array([5.0, 5.0, 50.0]), np.array([0.0, 0.0, -1.0])))
    hit = Viewport3D._pick_plane_target(vp, 0, 0)
    assert hit[0] == "face" and hit[1].body_id == a.body_id
    assert np.allclose(hit[1].normal, top.normal)
    monkeypatch.setattr("omacad.ui.viewport.ray_from_screen",
                        lambda *args: (np.array([45.0, 5.0, 50.0]), np.array([0.0, 0.0, -1.0])))
    assert Viewport3D._pick_plane_target(vp, 0, 0) is None


def test_shell_with_picked_open_face_can_be_saved():
    doc = _two_boxes()
    a = next(iter(doc.bodies.values()))
    top = next(f for f in a.faces if f.normal[2] > 0.9)
    pick = {"normal": [float(x) for x in top.normal], "origin": [float(x) for x in top.origin], "body_id": a.body_id, "_face": top}
    doc.add_shell(a.body_id, 1.0, open_faces=[pick])
    idx = next(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "shell")
    doc.edit_feature(idx, open_faces=[dict(pick)])
    json.dumps(Exporter.document_to_dict(doc))


@pytest.mark.parametrize("initial_direction", [0, 1, 2])
def test_docked_shell_keeps_thickness_controls(initial_direction):
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.viewport.paintGL = lambda: None
    win.viewport.initializeGL = lambda: None
    doc_path = str(DATA_DIR / "shell_panel.omacad")
    doc = Exporter.load_project(doc_path)
    dlg = ShellDialog(doc, win)
    dlg.cmb_dir.setCurrentIndex(initial_direction)
    try:
        win.dock(dlg)
        app.processEvents()
        for direction in [initial_direction, 2, 0, 1, 2]:
            dlg.cmb_dir.setCurrentIndex(direction)
            app.processEvents()
            for field, label, visible in (
                (dlg.spn_thickness, dlg.lbl_thick, True),
                (dlg.spn_thickness2, dlg.lbl_thick2, direction == 2),
            ):
                wrapper = field.parentWidget()
                assert isinstance(wrapper, NumericSlider)
                assert field.isVisibleTo(dlg) == visible
                assert label.isVisibleTo(dlg) == visible
                assert wrapper.isVisibleTo(dlg) == visible
                assert wrapper.slider.isVisibleTo(dlg) == visible
        dlg.spn_thickness.setValue(3.5)
        assert dlg.get_values()[1] == 3.5
        dlg.spn_thickness.parentWidget().slider.setValue(1000)
        assert dlg.get_values()[1] == dlg.spn_thickness.value() > 3.5
    finally:
        dlg.reject()
        win.close()


def test_edit_shell_dialog_shows_the_step_values():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    w.doc.add_cylinder(20, 40)
    bid = next(iter(w.doc.bodies))
    w.doc.add_shell(bid, 3.0, open_faces=[{"normal": [0, 0, 1], "origin": [0, 0, 40]}], direction="both", thickness2=1.5)
    w.doc.timeline.recompute(w.doc)
    seen = {}

    def fake_exec(win, doc, dlg, preview, ids, **_):
        preview()
        seen.update(dir=dlg.direction(), t=dlg.spn_thickness.value(), t2=dlg.spn_thickness2.value(),
                    faces=len(dlg.open_faces), preview=w.viewport.preview_mesh is not None)
        return False
    orig = feature_edit._exec_with_preview
    feature_edit._exec_with_preview = fake_exec
    try:
        feature_edit.edit_feature(w, w.doc, len(w.doc.timeline.features) - 1)
    finally:
        feature_edit._exec_with_preview = orig
    assert seen == {"dir": "both", "t": 3.0, "t2": 1.5, "faces": 1, "preview": True}
    w.close()
