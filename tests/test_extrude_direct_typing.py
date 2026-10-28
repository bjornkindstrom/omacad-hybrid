"""Tests that Extrude distance input is immediately ready for direct typing."""

import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication
from omacad.model.document import Document
from omacad.ui.viewport import Viewport3D
from omacad.ui.dialogs import ExtrudeDialog
import omacad.ui.dialogs as dialogs_mod


class DummySideHost:
    def __init__(self):
        self.inspector = self
        self.current_tool_dlg = None

    def dock(self, dlg):
        self.current_tool_dlg = dlg


def test_extrude_dialog_focus_and_direct_typing():
    QApplication.instance() or QApplication([])

    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((0.0, 0.0), 15.0)
    doc.finish_sketch()
    assert len(sk.profiles) == 1

    view = Viewport3D(doc)
    host = DummySideHost()
    dialogs_mod.SIDE_HOST = host

    dlg = ExtrudeDialog(doc, view, embedded=True)
    dlg.place(view.size())
    dlg.show()
    dlg.focus_primary()

    line_edit = dlg.spn_dist.lineEdit()
    assert line_edit is not None
    assert line_edit.hasSelectedText()

    # User picks a profile in the 3D viewport -> dlg.select_profile + focus_primary
    dlg.select_profile((sk.sketch_id, 0))
    dlg.focus_primary()
    assert line_edit.hasSelectedText()

    # Direct typing via viewport key event forwards to spn_dist
    evt = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_5, Qt.KeyboardModifier.NoModifier, "5")
    view.keyPressEvent(evt)

    assert "5" in line_edit.text()

    # Enter key via viewport finishes / accepts the tool dialog
    accepted = []
    dlg.accepted.connect(lambda: accepted.append(True))
    evt_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(evt_enter)

    assert accepted == [True]
    dialogs_mod.SIDE_HOST = None
