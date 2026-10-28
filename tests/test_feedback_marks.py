"""The report dialog: zoom around the pointer and draw marks that end up in the picture sent along."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture
def canvas():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QColor, QPixmap
    from omacad.ui.feedback_dialog import MarkableImage
    pm = QPixmap(400, 300)
    pm.fill(QColor(255, 255, 255))
    w = MarkableImage(pm)
    w.resize(800, 600)
    w.fit()
    return w


def test_zoom_keeps_the_point_under_the_pointer(canvas):
    from PySide6.QtCore import QPointF
    pos = QPointF(300, 200)
    before = canvas.to_image(pos)
    canvas.zoom_at(pos, 2.5)
    after = canvas.to_image(pos)
    assert (after.x(), after.y()) == pytest.approx((before.x(), before.y()), abs=1e-6)
    assert canvas.scale > 2.0


def test_marks_are_drawn_into_the_image_and_can_be_undone(canvas):
    from PySide6.QtCore import QPointF
    canvas.marks.append(("rect", [QPointF(100, 100), QPointF(200, 180)]))
    img = canvas.annotated_image()
    c = img.pixelColor(100, 140)                  # on the rectangle's left edge
    assert c.red() > 200 and c.green() < 100
    assert img.pixelColor(150, 140).green() > 200  # inside is untouched
    canvas.undo()
    assert canvas.marks == []


def test_dialog_has_no_marked_image_until_something_is_drawn():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPixmap
    from omacad.ui.feedback_dialog import FeedbackDialog
    pm = QPixmap(100, 100)
    pm.fill()
    dlg = FeedbackDialog(None, pm)
    assert dlg.marked_image() is None
    dlg.image.marks.append(("arrow", [QPointF(10, 10), QPointF(80, 80)]))
    assert dlg.marked_image() is not None
