"""The report's window screenshot must contain the 3D view's painter overlay (dimensions etc.)."""
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from omacad.ui.main_window import MainWindow


class _Window(QWidget):
    grab_with_overlay = MainWindow.grab_with_overlay


def test_window_shot_includes_view_overlay():
    app = QApplication.instance() or QApplication([])
    win = _Window()
    win.resize(200, 100)
    win.viewport = QWidget(win)
    win.viewport.setGeometry(50, 20, 100, 60)
    win.show()
    view = QImage(100, 60, QImage.Format.Format_ARGB32)
    view.fill(QColor(255, 0, 0))
    shot = win.grab_with_overlay(view).toImage()
    assert QColor(shot.pixel(100, 50)).red() == 255 and QColor(shot.pixel(100, 50)).green() == 0
    assert QColor(shot.pixel(5, 5)) != QColor(255, 0, 0)


def test_window_shot_includes_panels_floating_on_the_view():
    """Browser/Inspector are children of the 3D view; the framebuffer picture must not paint over them."""
    QApplication.instance() or QApplication([])
    win = _Window()
    win.resize(200, 100)
    win.viewport = QWidget(win)
    win.viewport.setGeometry(50, 20, 100, 60)
    panel = QWidget(win.viewport)
    panel.setGeometry(10, 10, 30, 30)
    panel.setAutoFillBackground(True)
    pal = panel.palette()
    pal.setColor(panel.backgroundRole(), QColor(0, 0, 255))
    panel.setPalette(pal)
    win.show()
    view = QImage(100, 60, QImage.Format.Format_ARGB32)
    view.fill(QColor(255, 0, 0))
    shot = win.grab_with_overlay(view).toImage()
    r = shot.devicePixelRatio()
    assert QColor(shot.pixel(int((50 + 20) * r), int((20 + 20) * r))) == QColor(0, 0, 255)   # the panel on top
    assert QColor(shot.pixel(int((50 + 80) * r), int((20 + 50) * r))).red() == 255           # the view next to it
