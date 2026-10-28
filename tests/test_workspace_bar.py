"""SOLID / SKETCH is a small bar in the 3D view directly above the Browser, not a row of the ribbon."""
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


def _win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    for _ in range(10):
        QApplication.processEvents()
    return w


def test_the_selector_is_over_the_browser_inside_the_view():
    w = _win()
    bar = w.workspace_bar
    assert bar.parent() is w.viewport and bar.isVisible()
    assert not w.ribbon.tabs.tabBar().isVisible()                 # no tab row inside the ribbon any more
    assert bar.geometry().bottom() <= w.browser.geometry().top()  # directly above the Browser ...
    assert bar.geometry().left() == w.browser.geometry().left()   # ... at its left edge
    assert w.browser.geometry().top() - bar.geometry().bottom() < 12


def test_the_bar_switches_the_ribbon_page_and_follows_sketch_mode():
    from omacad.model.sketch import SketchPlane
    w = _win()
    assert not w.workspace_bar.isTabVisible(1)                    # SKETCH only while sketching
    w.doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    assert w.workspace_bar.isTabVisible(1) and w.workspace_bar.currentIndex() == 1
    assert w.ribbon.tabs.currentIndex() == 1
    w.workspace_bar.setCurrentIndex(0)                            # clicking SOLID shows the solid ribbon page
    assert w.ribbon.tabs.currentIndex() == 0
    w.doc.finish_sketch()
    assert not w.workspace_bar.isTabVisible(1) and w.ribbon.tabs.currentIndex() == 0
