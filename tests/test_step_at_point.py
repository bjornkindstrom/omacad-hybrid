"""Clicking a surface finds the step that made it (used to pick what to pattern or mirror)."""
import pytest

from omacad.model.document import Document


def build():
    doc = Document()
    doc.add_box(40, 40, 10)
    doc.auto_include_edges = False
    sk = doc.start_sketch("XY")
    sk.add_circle((20, 20), 3)
    doc.finish_sketch()
    doc.extrude_profile(list(doc.sketches)[-1], 0, 10, "cut")
    doc.timeline.recompute(doc)
    return doc


def test_hole_wall_belongs_to_the_cut_and_the_top_to_the_box():
    doc = build()
    names = [f.name for f in doc.timeline.features]
    cut_idx = max(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "extrude")
    box_idx = next(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "box")
    assert doc.step_at_point((23, 20, 5)) == cut_idx, names
    assert doc.step_at_point((5, 5, 10)) == box_idx, names
    assert doc.step_at_point((100, 100, 100)) is None
