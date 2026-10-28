"""In a sketch, M and F are the sketch's Move and Fillet; the window's menu shortcuts with the same letter
(Move Body, Fit View) only act outside a sketch."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    w = MainWindow()
    w.doc.add_box(10, 10, 10)
    w.show()
    QTest.qWait(300)
    yield w
    w.viewport.set_sketch_tool("NONE")
    w.close()


def _press(win, key, mods=Qt.KeyboardModifier.NoModifier):
    win.activateWindow()
    win.viewport.setFocus()
    QApplication.processEvents()
    QTest.keyClick(win.viewport, key, mods)
    QApplication.processEvents()


def test_m_and_f_go_to_the_sketch_tools_in_a_sketch(win):
    win.doc.start_sketch("XY")
    _press(win, Qt.Key.Key_M)
    assert win.viewport.sketch_tool == "MOVE"
    assert win.inspector.current_tool_dlg is None          # not the Move Body panel
    _press(win, Qt.Key.Key_F)
    assert win.viewport.sketch_tool == "FILLET"
    _press(win, Qt.Key.Key_M, Qt.KeyboardModifier.ShiftModifier)
    assert win.viewport.sketch_tool == "MIRROR"


def test_m_opens_move_body_outside_a_sketch(win):
    _press(win, Qt.Key.Key_M)
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and "Move" in dlg.windowTitle()
    dlg.reject()
