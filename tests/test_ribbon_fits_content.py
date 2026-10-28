"""Requests #33/#34 (Windows): the ribbon had a fixed height, so bigger buttons or fonts clipped the buttons and hid the
second row of constraint buttons. The height now follows the content."""
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui import ribbon as ribbon_mod
from omacad.ui.settings import get_settings


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
