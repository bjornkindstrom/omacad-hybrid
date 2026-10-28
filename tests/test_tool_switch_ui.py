"""Opening a tool while another is open ends the first one as Cancel would: no stranded preview, hidden body,
pick mode or busy flag. A short value prompt asked from inside a tool brings that tool back afterwards."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(20, 20, 20)
    return w


def test_second_tool_cancels_the_first(win):
    bid = next(iter(win.doc.bodies))
    win.doc.selected_body_ids = [bid]
    win.prompt_shell()
    shell = win.inspector.current_tool_dlg
    assert shell is not None and not win.doc.bodies[bid].visible        # Shell hides the body behind its preview
    win.prompt_box()
    box = win.inspector.current_tool_dlg
    assert box is not shell and shell.result() == QDialog.DialogCode.Rejected
    assert win.doc.bodies[bid].visible
    box.reject()
    QApplication.processEvents()
    assert win.inspector.current_tool_dlg is None and win._busy_reason() is None
    assert win.viewport.preview_mesh is None
    assert len(win.doc.bodies) == 1


def test_extrude_can_be_opened_again_after_another_tool(win):
    sk = win.doc.start_sketch("XY")
    sk.add_rect((30, 0), (40, 10))
    win.doc.finish_sketch()
    win.prompt_extrude()
    first = win._extrude_dlg
    assert first is not None
    win.prompt_box()
    assert win._extrude_dlg is None
    win.inspector.current_tool_dlg.reject()
    win.prompt_extrude()
    assert win._extrude_dlg is not None and win._extrude_dlg is not first
    assert win.inspector.current_tool_dlg is win._extrude_dlg
    win._extrude_dlg.reject()


def test_value_prompt_inside_a_tool_returns_to_it(win):
    win.prompt_box()
    box = win.inspector.current_tool_dlg
    prompt = QDialog()
    prompt._nested = True
    win.inspector.dock_tool(prompt)
    assert not getattr(box, "_tool_done", False)               # Box stays open behind the prompt
    prompt.accept()
    assert win.inspector.current_tool_dlg is box
    box.reject()
