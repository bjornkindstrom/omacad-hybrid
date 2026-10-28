"""Esc always leaves the current function, innermost first."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402


@pytest.fixture
def view():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport import Viewport3D
    return Viewport3D(Document())


def esc(view):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))


def test_esc_leaves_sketch_tool_then_tool_panel_then_selection(view):
    sent = []
    view.menu_command.connect(sent.append)
    view.active_tool_title = lambda: "Extrude"
    view.doc.start_sketch("XY")
    view.set_sketch_tool("LINE")
    esc(view)
    assert view.sketch_tool == "NONE" and sent == []
    view.doc.finish_sketch()
    esc(view)
    assert sent == ["tool_cancel"]
    view.active_tool_title = lambda: None
    view.doc.selected_profile = ("sketch_1", 0)
    esc(view)
    assert view.doc.selected_profile is None
