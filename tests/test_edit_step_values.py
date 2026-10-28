"""Editing a step: counts stay whole numbers, a prism keeps three sides at least, and 'Auto' in an Extrude edit
decides against the bodies before the step."""
from omacad.model.document import Document


def test_formula_for_prism_sides_stays_a_whole_number():
    doc = Document()
    doc.add_prism(10, 5, sides=6)
    feat = doc.timeline.features[0]
    feat.exprs = {"sides": "7.4"}
    doc.refresh_parameters()
    assert feat.sides == 7 and isinstance(feat.sides, int)
    feat.exprs = {"sides": "1"}
    doc.refresh_parameters()
    assert feat.sides == 3


def test_edit_cannot_make_a_two_sided_prism():
    doc = Document()
    doc.add_prism(10, 5, sides=6)
    doc.edit_feature(0, sides=2)
    assert doc.timeline.features[0].sides == 3


def test_auto_extrude_edit_decides_against_the_bodies_before_the_step():
    """A box, then a sketch on its top extruded upward with Auto (= join). Deciding against the bodies after the
    step (which contain the extrusion itself) would call it a cut."""
    import pytest
    pytest.importorskip("PySide6")
    from omacad.model.features.extrude import ExtrudeFeature
    from omacad.model.sketch import SketchPlane
    from omacad.ui.feature_edit import _StateBefore
    doc = Document()
    doc.add_box(20, 20, 10)
    sk = doc.start_sketch_on_plane(SketchPlane.from_face([0, 0, 1], [0, 0, 10]))
    sk.add_rect((-2, -2), (2, 2))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5.0, "auto")
    doc.timeline.recompute(doc)
    idx = len(doc.timeline.features) - 1
    tmp = ExtrudeFeature("tmp", "tmp", sk.sketch_id, 0, 5.0, "auto")
    assert tmp.resolve_operation(doc) == "cut"                        # the old, wrong reading
    assert tmp.resolve_operation(_StateBefore(doc, doc.step_states[idx])) == "join"
