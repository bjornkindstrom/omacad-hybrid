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


def test_contact_shadow_only_under_bodies_on_the_ground_and_not_in_a_sketch():
    QApplication.instance() or QApplication([])
    from omacad.model.document import Document
    from omacad.ui.settings import get_settings
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    doc.add_box(20, 10, 5)
    corners, uvs = vp.contact_shadow_quad()
    assert len(corners) == len(uvs) == 6 and abs(float(corners[0][2])) < 0.1     # on the ground, under the box
    doc.add_sphere(5, translation=[0, 0, 60])                  # floating well above: no shadow of its own
    assert len(vp.contact_shadow_quad()[0]) == 6
    get_settings()._data["ground_shadow"] = False
    assert vp.contact_shadow_quad() is None
    get_settings()._data["ground_shadow"] = True
    doc.start_sketch()
    assert vp.contact_shadow_quad() is None
    vp.deleteLater()
