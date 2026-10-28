"""While a tool panel is open, Delete and the timeline do not swap the bodies it works on; a solid tool started
in a sketch finishes the sketch first."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(20, 20, 20)
    w.doc.add_cylinder(5, 30)
    w.doc.selected_body_ids = [next(iter(w.doc.bodies))]
    return w


def test_delete_waits_for_the_open_tool(win):
    win.prompt_shell()
    win.on_delete_selected()
    assert len(win.doc.bodies) == 2
    assert "Finish or cancel" in win.status_label.text()
    win.inspector.current_tool_dlg.reject()
    win.on_delete_selected()
    assert len(win.doc.bodies) == 1 and win.status_label.text() == "Deleted 1 body."


def test_delete_with_nothing_selected_says_so(win):
    win.doc.selected_body_ids = []
    win.on_delete_selected()
    assert len(win.doc.bodies) == 2 and win.status_label.text() == "Nothing selected to delete."


def test_timeline_does_not_roll_back_under_an_open_tool(win):
    win.prompt_shell()
    win.timeline_bar.on_rewind()
    win.timeline_bar.on_step_back()
    assert win.doc.timeline.marker_index == 2
    win.inspector.current_tool_dlg.reject()
    win.timeline_bar.on_step_back()
    assert win.doc.timeline.marker_index == 1


def test_extrude_started_in_a_sketch_finishes_the_sketch(win):
    sk = win.doc.start_sketch("XY")
    sk.add_rect((40, 0), (50, 10))
    win.prompt_extrude()
    assert win.doc.active_sketch is None
    assert any(f.feature_type == "sketch" for f in win.doc.timeline.features)
    assert win._extrude_dlg is not None
    win._extrude_dlg.reject()
