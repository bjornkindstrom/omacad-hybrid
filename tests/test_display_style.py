"""View > Display Style: shaded with edges, shaded, wireframe and hidden line; remembered in Settings."""
import pytest
from PySide6.QtWidgets import QApplication


def test_styles_set_what_is_drawn_and_are_remembered():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    from omacad.ui.settings import get_settings
    win = MainWindow()
    try:
        vp = win.viewport
        assert vp.display_style == "shaded_edges" and vp.show_edges and not vp.wireframe_only
        win.set_display_style("shaded")
        assert not vp.show_edges and not vp.wireframe_only
        win.set_display_style("wireframe")
        assert vp.wireframe_only and vp.show_edges
        win.set_display_style("hidden_line")
        assert vp.display_style == "hidden_line" and get_settings().get("display_style") == "hidden_line"
        assert win._style_actions["hidden_line"].isChecked()
        with pytest.raises(ValueError):
            vp.display_style = "cartoon"
    finally:
        win.doc.modified = False
        win.deleteLater()
