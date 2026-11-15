"""Ribbon UI layout, buttons, compact mode, context suggestions, and auto-sizing tests."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui import ribbon as ribbon_mod
from omacad.ui.main_window import MainWindow
from omacad.ui.settings import get_settings


# ==============================================================================
# Button Labels & Tooltips
# ==============================================================================

def test_icon_only_and_tooltip_then_labels():
    QApplication.instance() or QApplication([])
    st = get_settings()
    assert st.get("show_button_labels") is False
    r = ribbon_mod.Ribbon(Document())
    btn = ribbon_mod.RibbonButton("Create\nSketch", "✏️")
    btn.setToolTip("Make a sketch")
    assert btn.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert "Create Sketch" in btn.toolTip() and "Make a sketch" in btn.toolTip()
    for b in r.findChildren(ribbon_mod.RibbonButton):
        assert b.toolTip().startswith("<b>")
    compact_h = r.solid_tab.sizeHint().height()
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
            assert len(sizes) == 1, (labels, sizes)
    finally:
        st.set("show_button_labels", False)


# ==============================================================================
# Context Suggestions
# ==============================================================================

@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    yield w
    w.close()


def _suggested(win):
    return {cid for cid, b in win.ribbon.command_buttons.items() if b.property("suggested")}


def test_body_selection_suggests_body_tools(win):
    win.doc.add_box(10, 10, 10)
    win.doc.add_box(5, 5, 5, translation=[20, 0, 0])
    a, b = list(win.doc.bodies)
    win.doc.select_body(a)
    assert {"fillet", "chamfer"} <= _suggested(win) and "extrude" not in _suggested(win)
    win.doc.select_body(b, multi=True)
    assert "fillet" not in _suggested(win)
    assert ("combine" in _suggested(win)) or ("modify_body" in _suggested(win))
    win.doc.select_body(None)
    assert not _suggested(win)


def test_profile_selection_suggests_extrude(win):
    sk = win.doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    win.doc.finish_sketch()
    win.doc.selected_profile = (sk.sketch_id, 0)
    win.viewport.profile_picked.emit()
    assert {"extrude", "revolve", "emboss"} <= _suggested(win)


def test_settings_is_level_with_the_group_buttons(win):
    lay = win.ribbon.solid_tab.layout()
    item = next(lay.itemAt(i) for i in range(lay.count())
                if lay.itemAt(i).widget() is win.ribbon.command_buttons["settings"])
    assert item.alignment() & Qt.AlignmentFlag.AlignTop


# ==============================================================================
# Dynamic Height Following Content (Requests #33/#34)
# ==============================================================================

def _fits(r):
    pages = max(r.solid_tab.sizeHint().height(), r.sketch_tab.sizeHint().height())
    return r.tabs.height() >= pages


def test_ribbon_height_follows_content():
    QApplication.instance() or QApplication([])
    st = get_settings()
    r = ribbon_mod.Ribbon(Document())
    assert _fits(r)
    st.set("button_scale", 1.5)
    try:
        r.update_button_scale()
        assert _fits(r)
        assert r.tabs.height() > ribbon_mod.ribbon_height(1.0)
    finally:
        st.set("button_scale", 1.0)
