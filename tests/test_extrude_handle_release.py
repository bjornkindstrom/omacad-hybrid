"""Letting go of the Extrude arrow after a drag ends interactive quality; the release crashed with NameError
(`quality` was not imported in the events module after the viewport was split up)."""
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from omacad.model import quality
from omacad.model.document import Document
from omacad.ui.viewport import Viewport3D


def test_release_after_dragging_the_extrude_arrow():
    QApplication.instance() or QApplication([])
    vp = Viewport3D(Document())
    finished = []
    vp.extrude_handle_drag_finished.connect(lambda: finished.append(True))
    vp._handle_drag = True
    quality.set_interactive_mode(True)
    ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    vp.mouseReleaseEvent(ev)
    assert finished and not quality.is_interactive_mode() and not vp._handle_drag
