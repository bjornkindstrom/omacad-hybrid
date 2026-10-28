"""A step that fails while the history rebuilds is marked (red chip, the reason in its tooltip) instead of only
printed; the rest of the history still builds."""
import pytest

from omacad.model.document import Document
from omacad.model.features.primitives import CylinderFeature


def test_failed_step_keeps_its_reason_and_the_rest_builds(monkeypatch):
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(3, 20)
    doc.add_box(5, 5, 5, translation=[30, 0, 0])

    def boom(self, d):
        raise ValueError("radius too small")
    monkeypatch.setattr(CylinderFeature, "execute", boom)
    doc.timeline.clear_cache()
    doc.timeline.recompute(doc)
    feats = doc.timeline.features
    assert feats[1].error == "radius too small"
    assert feats[0].error == "" and feats[2].error == ""
    assert len(doc.bodies) == 2
    monkeypatch.undo()
    doc.timeline.clear_cache()
    doc.timeline.recompute(doc)
    assert feats[1].error == "" and len(doc.bodies) == 3


def test_timeline_chip_says_why(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from omacad.ui.timeline_bar import FeatureNodeWidget
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 10)
    feat = doc.timeline.features[0]
    feat.error = "wall thicker than the box"
    chip = FeatureNodeWidget(1, feat, True)
    assert chip.toolTip().startswith("Failed: wall thicker than the box")
