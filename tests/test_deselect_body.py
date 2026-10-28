"""A click in empty space (not on a body, not on a profile) clears the body selection."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402


def test_empty_click_deselects(monkeypatch):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport import Viewport3D
    d = Document()
    d.add_box(20, 20, 10)
    bid = next(iter(d.bodies))
    d.select_body(bid)
    v = Viewport3D(d)
    monkeypatch.setattr(v, "pick_profile", lambda x, y: None)
    monkeypatch.setattr(v, "pick_body", lambda x, y: None)       # nothing under the cursor
    pt = QPointF(5, 5)
    v._press_pos = pt
    v.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, pt, pt, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert d.selected_body_ids == []
    d.select_body(bid)
    monkeypatch.setattr(v, "pick_body", lambda x, y: bid)         # a click on the body keeps the selection
    v._press_pos = pt
    v.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, pt, pt, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert d.selected_body_ids == [bid]
