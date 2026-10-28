"""The tool panel is as tall as its content needs (no scrolling unless the window is too small); tick boxes are visible."""
import pytest
from pathlib import Path
from PySide6.QtWidgets import QApplication

from omacad.ui import theme


def test_indicator_stylesheet_writes_both_images():
    QApplication.instance() or QApplication([])
    css = theme.indicator_stylesheet()
    assert "QListView::indicator:checked" in css and "QCheckBox::indicator:unchecked" in css
    import tempfile
    for name in ("check_off.svg", "check_on.svg"):
        assert "<svg" in (Path(tempfile.gettempdir()) / "omacad-ui" / name).read_text()


def test_panel_fits_its_content_and_scrolls_only_when_short_of_room():
    QApplication.instance() or QApplication([])
    from omacad.model.document import Document
    from omacad.ui.dialogs import PatternDialog
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    w.doc.add_box(10, 10, 10)
    w.doc.add_cylinder(3, 10)
    dlg = PatternDialog(w.doc, w)
    w.inspector.dock_tool(dlg)
    QApplication.processEvents()
    QApplication.processEvents()
    w.inspector.set_max_height(5000)          # (after the window settled: its resizes also set the limit)
    tall = w.inspector.height()
    assert tall < 5000                                    # not stretched to the window
    assert tall >= dlg.height()                            # everything fits: no vertical scrolling needed
    assert w.inspector.scroll.verticalScrollBar().maximum() == 0
    w.inspector.set_max_height(200)
    assert w.inspector.height() == 200                    # short of room: capped (and then it scrolls)
    assert w.inspector.scroll.horizontalScrollBarPolicy().name == "ScrollBarAlwaysOff"
