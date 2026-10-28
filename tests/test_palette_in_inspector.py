"""The sketch palette lives in the right-hand inspector instead of floating over the canvas."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from omacad.model.document import Document


def test_palette_is_hosted_by_the_inspector():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.side_panel import InspectorPanel
    from omacad.ui.sketch_palette import SketchPalette
    panel = InspectorPanel(Document())
    palette = SketchPalette()
    panel.set_palette(palette)
    assert palette.parentWidget() is not None and panel.isAncestorOf(palette)
    before = palette.pos()
    palette.place_default(panel.size())   # no floating placement any more
    assert palette.pos() == before
