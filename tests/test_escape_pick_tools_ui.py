"""Esc in a tool whose whole session is face picking (Shell, Offset Face, Move) cancels the tool; it used to stop
only the picking and leave a panel that could no longer pick, with the status saying "Create Sketch cancelled"."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(20, 20, 20)
    w.doc.selected_body_ids = [next(iter(w.doc.bodies))]
    return w


@pytest.mark.parametrize("prompt", ["prompt_shell", "prompt_offset_face", "prompt_move_body"])
def test_escape_cancels_a_face_picking_tool(win, prompt):
    getattr(win, prompt)()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and win.viewport.plane_pick_mode
    win._escape_pressed()
    QApplication.processEvents()
    assert win.inspector.current_tool_dlg is None
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not win.viewport.plane_pick_mode
    assert all(b.visible for b in win.doc.bodies.values())


def test_escape_in_offset_plane_pick_says_offset_plane(win):
    win.prompt_offset_plane()
    win._escape_pressed()
    assert not win.viewport.plane_pick_mode
    assert win.status_label.text() == "Offset Plane cancelled."
