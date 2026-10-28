"""The bottom bar is gone: the status message, the sketch status and the units are painted into the 3D view like the
Azimuth line, and there is no Report problem button there (F10 and Help > Report problem remain)."""
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication, QPushButton, QStatusBar

from omacad.ui.main_window import MainWindow


def _win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    return w


def test_no_status_bar_and_no_report_button():
    w = _win()
    assert w.findChildren(QStatusBar) == []
    assert not [b for b in w.findChildren(QPushButton) if "Report problem" in b.text()]
    from PySide6.QtGui import QAction
    assert any(a.text().startswith("Report problem") for a in w.findChildren(QAction))     # Help > Report problem (F10)


def test_status_text_is_drawn_into_the_view_and_still_logged():
    from omacad import applog
    w = _win()
    drawn = []

    class Rec(QPainter):
        def drawText(self, *a):
            drawn.append(a[-1])

    w.status_label.setText("Offset Face: click a face")
    w.lbl_sketch_status.setText("Sketch 1 (XY)")
    img = QImage(900, 600, QImage.Format.Format_ARGB32)
    p = Rec(img)
    w.viewport._draw_status_text(p, 900, 600)
    p.end()
    assert "Offset Face: click a face" in drawn
    assert any("Sketch 1 (XY)" in t and "Units: mm" in t for t in drawn)
    w.progress_bar.setVisible(True)                               # busy shows in the same line
    drawn.clear()
    p = Rec(img)
    w.viewport._draw_status_text(p, 900, 600)
    p.end()
    assert any(t.startswith("Working…") for t in drawn)
    assert "Offset Face: click a face" in applog.tail(20)          # still goes into the log sent with problem reports


def test_report_problem_is_f10_because_omarchy_owns_f9():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QAction
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow()
    act = next(a for a in w.findChildren(QAction) if a.text().startswith("Report problem"))
    assert act.shortcut().toString() == "F10"
    assert not any(a.shortcut().toString() == "F9" for a in w.findChildren(QAction))
