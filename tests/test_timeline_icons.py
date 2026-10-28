"""The four playback buttons of the timeline use drawn icons (the arrow emoji did not render)."""
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui.timeline_bar import TimelineBar


def test_buttons_have_icons_and_no_text():
    QApplication.instance() or QApplication([])
    bar = TimelineBar(Document())
    for btn in (bar.btn_rewind, bar.btn_prev, bar.btn_next, bar.btn_ff):
        assert btn.text() == "" and not btn.icon().isNull()
        assert not btn.icon().pixmap(16, 16).toImage().isNull()
    bar.update_icons()
