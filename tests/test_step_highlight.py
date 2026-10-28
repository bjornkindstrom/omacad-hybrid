"""Clicking a timeline step colours what that step changed."""
import pytest

from omacad.model.document import Document


def test_step_changes_gives_added_and_removed_material():
    doc = Document()
    doc.add_box(20, 20, 10)
    doc.add_box(10, 10, 10)
    doc.timeline.recompute(doc)
    added, removed = doc.step_changes(0)
    assert added.volume() == pytest.approx(4000, rel=1e-6) and removed is None
    assert doc.step_changes(99) == (None, None)


def test_fillet_step_reports_removed_material():
    from omacad.io.exporter import Exporter
    from pathlib import Path
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "foot_fillet_over_rim_fillet.omacad"))
    doc.timeline.recompute(doc)
    idx = next(i for i, f in enumerate(doc.timeline.features) if f.name == "Fillet 1")
    added, removed = doc.step_changes(idx)
    assert removed is not None and removed.volume() > 0
