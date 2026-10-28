"""OK pressed right after a value change: the pending preview must not run after the panel closed (it hid the
freshly rebuilt body and left a preview behind)."""
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(20, 20, 20)
    return w


def test_shell_ok_right_after_a_change_leaves_the_body_visible(win):
    bid = next(iter(win.doc.bodies))
    win.doc.selected_body_ids = [bid]
    win.prompt_shell()
    dlg = win.inspector.current_tool_dlg
    dlg.spn_thickness.setValue(dlg.spn_thickness.value() + 0.5)    # starts the 75 ms preview timer
    dlg.accept()
    QTest.qWait(200)
    assert all(b.visible for b in win.doc.bodies.values())
    assert win.viewport.preview_mesh is None


def test_offset_face_cancel_right_after_a_change_leaves_no_preview(win):
    from omacad.model.features.offset_face import plane_face_ref
    body = next(iter(win.doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    win.prompt_offset_face()
    dlg = win.inspector.current_tool_dlg
    dlg.toggle(plane_face_ref(top), body.body_id)                   # starts the 60 ms preview timer
    dlg.reject()
    QTest.qWait(200)
    assert all(b.visible for b in win.doc.bodies.values())
    assert win.viewport.preview_mesh is None


def test_box_preview_error_is_shown_not_a_crash(win, monkeypatch):
    from omacad.model.features.primitives import BoxFeature

    def boom(self):
        raise ValueError("wall thicker than the box")
    monkeypatch.setattr(BoxFeature, "build_solid", boom)
    win.prompt_box()
    dlg = win.inspector.current_tool_dlg
    dlg.spn_length.setValue(dlg.spn_length.value() + 1)
    QTest.qWait(150)
    assert "wall thicker" in dlg.lbl_problem.text()
    dlg.reject()
