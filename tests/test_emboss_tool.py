"""The Emboss tool in the window: button, auto-picked letters, live preview, Effect follows the depth, OK = one undo step."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    doc = w.doc
    doc.add_box(60.0, 40.0, 10.0, center="bottom_center")
    top = max(next(iter(doc.bodies.values())).faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin))
    sk.add_text("HI", (0.0, 0.0), height=12.0, h_align="center", v_align="middle")
    doc.finish_sketch()
    return w


def _volume(w):
    return next(iter(w.doc.bodies.values())).manifold.volume()


def test_emboss_button_and_menu_entry_exist(win):
    from omacad.ui.ribbon import RibbonButton
    assert any(b.raw_text.strip() == "Emboss" for b in win.ribbon.solid_tab.findChildren(RibbonButton))
    from PySide6.QtGui import QAction
    assert any(a.text().startswith("Emboss") for a in win.menuBar().findChildren(QAction))


def test_it_starts_with_the_letters_picked_and_previews(win):
    win.prompt_emboss()
    dlg = win._emboss_dlg
    assert win.doc.selected_profile is not None and len(win.doc.selected_extra) == 1       # H and I
    assert "2 profile" in dlg.lbl_info.text()
    assert win.viewport.preview_mesh is not None                                            # the green preview
    assert win.viewport.preview_op == "join"
    dlg.spn_depth.setValue(-1.0)
    assert dlg.cmb_effect.currentData() == "deboss" and win.viewport.preview_op == "cut"    # the sign decides the effect
    dlg.cmb_effect.setCurrentIndex(0)
    assert dlg.spn_depth.value() == pytest.approx(1.0)                                      # ... and the effect decides the sign
    dlg.reject()
    assert win.viewport.preview_mesh is None and win._emboss_dlg is None


def test_ok_embosses_the_letters_in_one_undo_step(win):
    v0 = _volume(win)
    sk = next(iter(win.doc.sketches.values()))
    area = next(e for e in sk.entities if e.entity_type == "text").geometry().area
    win.prompt_emboss()
    win._emboss_dlg.spn_depth.setValue(2.0)
    win._emboss_dlg.accept()
    assert _volume(win) == pytest.approx(v0 + 2.0 * area, rel=2e-3)
    assert win.doc.timeline.features[-1].feature_type == "emboss"
    win.doc.undo()
    assert _volume(win) == pytest.approx(v0, rel=1e-9)


def test_select_all_text_button_and_edit_from_the_timeline(win):
    win.doc.selected_profile, win.doc.selected_extra = None, []
    win.prompt_emboss()
    dlg = win._emboss_dlg
    win.doc.selected_profile, win.doc.selected_extra = None, []
    dlg.btn_text.click()
    assert win.doc.selected_profile is not None and len(win.doc.selected_extra) == 1
    dlg.accept()
    feat = win.doc.timeline.features[-1]
    assert feat.depth == pytest.approx(1.0)
    from omacad.ui import feature_edit
    from omacad.ui.dialogs import EmbossDialog
    EmbossDialog.exec = lambda self: (self.spn_depth.setValue(-0.5), True)[1]
    assert feature_edit.can_edit(feat) and feature_edit.edit_feature(win, win.doc, len(win.doc.timeline.features) - 1)
    assert win.doc.timeline.features[-1].effect == "deboss" and win.doc.timeline.features[-1].depth == pytest.approx(-0.5)


def test_without_any_sketch_it_says_what_to_do(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    w = MainWindow()
    w.prompt_emboss()
    assert shown and "text" in shown[0].lower() and getattr(w, "_emboss_dlg", None) is None
