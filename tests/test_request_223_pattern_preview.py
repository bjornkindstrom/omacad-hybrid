"""#223: the Fill pattern preview of a sketch-on-face cut crashed (the preview feature is not in the timeline)."""
from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.features.pattern import PatternFeature

DATA = Path(__file__).parent / "data" / "request_223_fill_pattern.json"


def test_fill_preview_of_unsaved_pattern_computes():
    doc = Exporter.load_project(str(DATA))
    doc.timeline.recompute(doc)
    ids = [f.feature_id for f in doc.timeline.features if f.name in ("Sketch 2", "Extrude 2")]
    feat = PatternFeature("tmp", "tmp", ids, "fill", spacing1=4.0, spacing2=8.0)
    results = [feat.compute(doc, bid) for bid in list(doc.bodies)]
    assert any(r is not None for r in results)
    assert feat.copies > 1


def test_pattern_dialog_survives_fill_preview():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.attach_document(Exporter.load_project(str(DATA)))
    win.prompt_pattern("fill")
    dlg = win._pattern_dlg
    assert dlg is not None
    assert "copies will be made" in dlg.lbl_info.text()
    dlg.reject()
    assert win._pattern_dlg is None
    win.close()
