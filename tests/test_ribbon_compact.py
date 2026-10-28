"""Ribbon buttons are icon-only by default (name in the tooltip); the setting brings the labels back."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from omacad.model.document import Document
from omacad.ui import ribbon as ribbon_mod
from omacad.ui.settings import get_settings


def test_icon_only_and_tooltip_then_labels():
    QApplication.instance() or QApplication([])
    st = get_settings()
    assert st.get("show_button_labels") is False   # default
    r = ribbon_mod.Ribbon(Document())
    btn = ribbon_mod.RibbonButton("Create\nSketch", "✏️")
    btn.setToolTip("Make a sketch")
    assert btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert "Create Sketch" in btn.toolTip() and "Make a sketch" in btn.toolTip()
    for b in r.findChildren(ribbon_mod.RibbonButton):
        assert b.toolTip().startswith("<b>")
    compact_h = r.solid_tab.sizeHint().height()      # (the tab widget itself is as high as the tallest page: the sketch one)
    st.set("show_button_labels", True)
    r.rebuild_ribbon()
    assert r.solid_tab.sizeHint().height() > compact_h
    assert ribbon_mod.RibbonButton("A", "✏️").toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon


def test_all_ribbon_buttons_are_the_same_size_with_and_without_names():
    QApplication.instance() or QApplication([])
    st = get_settings()
    r = ribbon_mod.Ribbon(Document())
    try:
        for labels in (False, True):
            st.set("show_button_labels", labels)
            r.rebuild_ribbon()
            sizes = {(b.minimumWidth(), b.minimumHeight()) for b in r.findChildren(ribbon_mod.RibbonButton)}
            assert len(sizes) == 1, (labels, sizes)                    # solid and sketch tab alike
    finally:
        st.set("show_button_labels", False)
