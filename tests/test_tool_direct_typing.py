"""Every tool panel takes a number typed straight in the 3D view, and Enter is OK (Fillet, Chamfer, Shell, ...)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QEvent  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
import omacad.ui.dialogs as dialogs_mod  # noqa: E402
from omacad.model.document import Document  # noqa: E402
from omacad.ui.dialogs.fillet_dlg import RoundEdgesDialog  # noqa: E402
from omacad.ui.dialogs.shell_dlg import ShellDialog  # noqa: E402
from omacad.ui.dialogs.offset_face_dlg import OffsetFaceDialog  # noqa: E402
from omacad.ui.viewport import Viewport3D  # noqa: E402


class Host:
    def __init__(self, dlg):
        self.inspector = self
        self.current_tool_dlg = dlg


def _key(view, key, text=""):
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text))


@pytest.fixture
def view():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(20, 20, 10)
    v = Viewport3D(doc)
    yield v
    dialogs_mod.SIDE_HOST = None
    v.close()


@pytest.mark.parametrize("make, field", [
    (lambda doc: RoundEdgesDialog(kind="fillet"), "spn_size"),
    (lambda doc: RoundEdgesDialog(kind="chamfer"), "spn_size"),
    (lambda doc: ShellDialog(doc), None),
    (lambda doc: OffsetFaceDialog(), "spn_dist"),
])
def test_typing_in_the_view_fills_the_main_field_and_enter_is_ok(view, make, field):
    dlg = make(view.doc)
    dialogs_mod.SIDE_HOST = Host(dlg)
    dlg.show()
    view.setFocus()
    target = getattr(dlg, field) if field else dlg.primary_field()
    assert target is not None and target is dlg.primary_field()
    _key(view, Qt.Key.Key_4, "4")
    assert target.lineEdit().text().startswith("4")          # the old value was replaced, not appended to
    accepted = []
    dlg.accepted.connect(lambda: accepted.append(True))
    _key(view, Qt.Key.Key_Return)
    assert accepted == [True]
    assert target.value() == pytest.approx(4)
    dlg.close()


def test_backspace_still_undoes_the_last_picked_edge(view):
    dlg = RoundEdgesDialog(kind="fillet")
    dialogs_mod.SIDE_HOST = Host(dlg)
    dlg.show()
    view.edge_pick_mode = True
    view.selected_edges = ["a", "b"]
    before = dlg.spn_size.lineEdit().text()
    _key(view, Qt.Key.Key_Backspace)
    assert view.selected_edges == ["a"]
    assert dlg.spn_size.lineEdit().text() == before
    dlg.close()


def test_tab_walks_the_number_fields_only():
    """#47: Tab in a tool panel goes from number to number (skipping lists and buttons), wrapping round."""
    from omacad.ui.dialogs.extrude_dlg import ExtrudeDialog
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    dlg = ExtrudeDialog(doc)
    dlg.show()
    QApplication.processEvents()
    fields = dlg.number_fields()
    assert dlg.spn_dist in fields and dlg.spn_twist in fields
    assert all(f.isVisibleTo(dlg) for f in fields)
    dlg.spn_dist.setFocus()
    seen = []
    for _ in range(len(fields)):
        dlg.focusNextPrevChild(True)
        w = dlg.focusWidget()
        seen.append(next(f for f in fields if f is w or f.isAncestorOf(w)))
    assert seen[-1] is dlg.spn_dist and len(set(map(id, seen))) == len(fields)
    dlg.close()
