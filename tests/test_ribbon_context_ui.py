"""The buttons that fit what is selected get an accent border (nothing moves); Settings sits level with the other
buttons."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def _suggested(win):
    return {cid for cid, b in win.ribbon.command_buttons.items() if b.property("suggested")}


def test_body_selection_suggests_body_tools(win):
    win.doc.add_box(10, 10, 10)
    win.doc.add_box(5, 5, 5, translation=[20, 0, 0])
    a, b = list(win.doc.bodies)
    win.doc.select_body(a)
    assert {"fillet", "chamfer"} <= _suggested(win) and "extrude" not in _suggested(win)
    win.doc.select_body(b, multi=True)
    assert "fillet" not in _suggested(win)
    assert ("combine" in _suggested(win)) or ("modify_body" in _suggested(win))     # flat or in the Body dropdown
    win.doc.select_body(None)
    assert not _suggested(win)


def test_profile_selection_suggests_extrude(win):
    sk = win.doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    win.doc.finish_sketch()
    win.doc.selected_profile = (sk.sketch_id, 0)
    win.viewport.profile_picked.emit()
    assert {"extrude", "revolve", "emboss"} <= _suggested(win)


def test_settings_is_level_with_the_group_buttons(win):
    lay = win.ribbon.solid_tab.layout()
    item = next(lay.itemAt(i) for i in range(lay.count())
                if lay.itemAt(i).widget() is win.ribbon.command_buttons["settings"])
    assert item.alignment() & Qt.AlignmentFlag.AlignTop
