"""Timeline model tests: caching, recompute, step rollbacks, error states, and independent object branch steps."""
import json
import os
from pathlib import Path
import pytest

from omacad.io.exporter import Exporter
from omacad.model import quality
from omacad.model.document import Document
from omacad.model.features.extrude import ExtrudeFeature
from omacad.model.features.primitives import CylinderFeature
from omacad.model.sketch import SketchPlane
from omacad.ui.feature_edit import _StateBefore

DATA_DIR = Path(__file__).parent / "data"


# =========================================================================
# 1. Timeline Cache, Quality & Recompute
# =========================================================================

def _sketch_with_extrude():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5.0)
    return doc, sk.sketch_id


def test_sketch_edit_after_cached_recompute_is_kept():
    doc, sid = _sketch_with_extrude()
    doc.timeline.recompute(doc)
    doc.timeline.recompute(doc)          # second run restores the sketch step from the cache
    sk = doc.edit_sketch(sid)
    sk.add_rect((20, 0), (30, 10))
    doc.finish_sketch()
    assert len(doc.sketches[sid].entities) == 8
    assert len(doc.sketches[sid].profiles) == 2
    feat = next(f for f in doc.timeline.features if f.feature_type == "sketch")
    assert doc.sketches[sid] is feat.sketch


def test_new_step_at_a_rolled_back_marker_is_inserted_and_later_steps_stay():
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(5, 10)
    doc.add_box(20, 20, 20)
    later = [f.feature_id for f in doc.timeline.features[1:]]
    doc.timeline.step_to(1, doc)
    doc.add_cylinder(2, 3)
    ids = [f.feature_id for f in doc.timeline.features]
    assert ids[2:] == later and len(ids) == 4
    assert doc.timeline.marker_index == 2
    doc.timeline.fast_forward(doc)
    assert len(doc.bodies) == 4


def test_new_curve_smoothness_rebuilds_cached_steps():
    old = quality.circle_segments()
    try:
        quality.set_circle_segments(48)
        doc = Document()
        doc.add_cylinder(5, 10)
        doc.timeline.recompute(doc)
        quality.set_circle_segments(192)
        doc.timeline.recompute(doc)
        verts = len(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)
        assert verts == 2 * 192
    finally:
        quality.set_circle_segments(old)


def test_undo_runs_the_steps_again_so_their_results_are_there():
    """A thread following its host measures it while it runs; after undo the new step object must have it too."""
    doc = Document()
    doc.add_cylinder(20.0, 10.0)
    cyl = next(iter(doc.bodies))
    doc.add_thread(diameter=39.99, pitch=3.0, length=8.0, target_body_id=cyl, operation="join", profile="round",
                   plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0],
                   host_length=10.0, follow_host=True, host_offset=-0.01)
    doc.timeline.recompute(doc)
    before = doc.timeline.features[-1]._effective
    assert before is not None
    doc.add_box(5, 5, 5)
    doc.undo()
    assert doc.timeline.features[-1]._effective == before


def test_the_model_is_built_at_full_quality_even_if_interactive_mode_was_left_on():
    doc = Document()
    doc.add_cylinder(5, 10)
    quality.set_interactive_mode(True)          # e.g. a drag whose release was lost
    try:
        doc.timeline.clear_cache()
        doc.timeline.recompute(doc)
        verts = len(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)
        assert verts == 2 * quality.DEFAULT_SEGMENTS      # full quality (interactive would give 2 * 32)
        assert quality.is_interactive_mode()    # the flag itself is left as it was
    finally:
        quality.set_interactive_mode(False)


def test_a_new_step_is_built_at_full_quality_even_if_interactive_mode_was_left_on():
    doc = Document()
    quality.set_interactive_mode(True)
    try:
        doc.add_cylinder(5, 10)
        verts = len(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)
        assert verts == 2 * quality.DEFAULT_SEGMENTS and quality.is_interactive_mode()
    finally:
        quality.set_interactive_mode(False)


# =========================================================================
# 2. Failed Steps & Value Edits
# =========================================================================

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


# =========================================================================
# 3. Step Changes & Point Queries
# =========================================================================

def test_step_changes_gives_added_and_removed_material():
    doc = Document()
    doc.add_box(20, 20, 10)
    doc.add_box(10, 10, 10)
    doc.timeline.recompute(doc)
    added, removed = doc.step_changes(0)
    assert added.volume() == pytest.approx(4000, rel=1e-6) and removed is None
    assert doc.step_changes(99) == (None, None)


def test_fillet_step_reports_removed_material():
    doc = Exporter.load_project(str(DATA_DIR / "foot_fillet_over_rim_fillet.omacad"))
    doc.timeline.recompute(doc)
    idx = next(i for i, f in enumerate(doc.timeline.features) if f.name == "Fillet 1")
    added, removed = doc.step_changes(idx)
    assert removed is not None and removed.volume() > 0


def test_hole_wall_belongs_to_the_cut_and_the_top_to_the_box():
    doc = Document()
    doc.add_box(40, 40, 10)
    doc.auto_include_edges = False
    sk = doc.start_sketch("XY")
    sk.add_circle((20, 20), 3)
    doc.finish_sketch()
    doc.extrude_profile(list(doc.sketches)[-1], 0, 10, "cut")
    doc.timeline.recompute(doc)
    names = [f.name for f in doc.timeline.features]
    cut_idx = max(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "extrude")
    box_idx = next(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "box")
    assert doc.step_at_point((23, 20, 5)) == cut_idx, names
    assert doc.step_at_point((5, 5, 10)) == box_idx, names
    assert doc.step_at_point((100, 100, 100)) is None


# =========================================================================
# 4. Independent Object Copies & Steps
# =========================================================================

def _steps_of(doc, body):
    history = doc.object_history
    owner = next(o for o in history.objects.values() if body.body_id in o.body_ids)
    return [doc.timeline.features[history.index(doc, f)] for f in owner.feature_ids]


def _size(doc, body_id):
    lo = doc.bodies[body_id].manifold.bounding_box()
    return tuple(round(lo[i + 3] - lo[i], 6) for i in range(3))


def test_a_box_copy_has_its_own_box_step_and_each_side_edits_alone():
    doc = Document()
    source = doc.add_box(10, 20, 30)
    copy = doc.branch_object("box_1", source.body_id, linked=False)
    assert copy.name == "Box 1 Copy" and copy.body_id != source.body_id
    assert [f.feature_type for f in _steps_of(doc, copy)] == ["box", "move"]
    box = _steps_of(doc, copy)[0]
    assert doc.edit_feature_dimension(box.feature_id, "height", "50") is not False
    assert _size(doc, copy.body_id) == (10, 20, 50) and _size(doc, source.body_id) == (10, 20, 30)
    doc.edit_feature_dimension("box_1", "length", "40")
    assert _size(doc, source.body_id)[0] == 40 and _size(doc, copy.body_id)[0] == 10
    assert doc.bodies[copy.body_id].manifold.bounding_box()[2] == pytest.approx(doc.bodies[source.body_id].manifold.bounding_box()[2])


def test_sketch_extrude_and_shell_all_come_along_and_are_saved():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (20, 20))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 10, operation="new_body")
    body = doc.bodies[f"body_{doc.timeline.features[-1].feature_id}"]
    shell = doc.add_shell(body.body_id, 1.0)
    volume = doc.bodies[body.body_id].manifold.volume()
    copy = doc.branch_object(shell.feature_id, body.body_id, linked=False)
    steps = _steps_of(doc, copy)
    assert [f.feature_type for f in steps] == ["sketch", "extrude", "shell", "move"]
    assert doc.bodies[copy.body_id].manifold.volume() == pytest.approx(volume)
    assert steps[0].sketch.sketch_id != sk.sketch_id
    assert doc.bodies[copy.body_id].manifold.bounding_box()[0] > doc.bodies[body.body_id].manifold.bounding_box()[3]

    index = doc.timeline.features.index(steps[2])
    assert doc.edit_feature(index, thickness=2.0)
    assert doc.bodies[copy.body_id].manifold.volume() > volume
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(volume)

    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert restored.bodies[copy.body_id].manifold.volume() == pytest.approx(doc.bodies[copy.body_id].manifold.volume())


def test_a_copy_from_an_earlier_step_stops_at_that_step():
    doc = Document()
    source = doc.add_box(20, 20, 20)
    doc.add_shell(source.body_id, 2.0)
    copy = doc.branch_object("box_1", source.body_id, linked=False)
    assert [f.feature_type for f in _steps_of(doc, copy)] == ["box", "move"]
    assert doc.bodies[copy.body_id].manifold.volume() == pytest.approx(8000.0)


def test_one_undo_takes_the_whole_copy_away_and_deleting_the_original_keeps_it():
    doc = Document()
    source = doc.add_box(10, 10, 10)
    before = len(doc.timeline.features)
    copy = doc.branch_object("box_1", source.body_id, linked=False)
    assert len(doc.timeline.features) == before + 2
    doc.undo()
    assert len(doc.timeline.features) == before and copy.body_id not in doc.bodies
    doc.redo()
    assert copy.body_id in doc.bodies
    doc.delete_feature(0)
    assert list(doc.bodies) == [copy.body_id]
    assert doc.bodies[copy.body_id].manifold.volume() == pytest.approx(1000.0)


def test_a_copy_of_a_linked_copy_gets_the_originals_settings_and_no_longer_follows_it():
    doc = Document()
    source = doc.add_box(10, 10, 10)
    linked = doc.branch_object("box_1", source.body_id)
    link_step = linked.body_id.removeprefix("body_")
    copy = doc.branch_object(link_step, linked.body_id, linked=False)
    steps = _steps_of(doc, copy)
    assert [f.feature_type for f in steps] == ["box", "branch", "delete_body", "move"]
    assert set(doc.bodies) == {source.body_id, linked.body_id, copy.body_id}
    doc.edit_feature_dimension("box_1", "height", "20")
    assert _size(doc, linked.body_id)[2] == 20 and _size(doc, copy.body_id)[2] == 10
    doc.edit_feature_dimension(steps[0].feature_id, "height", "35")
    assert _size(doc, copy.body_id)[2] == 35 and _size(doc, linked.body_id)[2] == 20 and _size(doc, source.body_id)[2] == 20


def test_the_pot_copy_can_change_its_cells():
    doc = Document()
    with open(DATA_DIR / "voronoi_pot.omacad", encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    cells = next(f for f in doc.timeline.features if f.feature_type == "honeycomb")
    volume = doc.bodies[cells.target_body_id].manifold.volume()
    copy = doc.branch_object(cells.feature_id, cells.target_body_id, linked=False)
    steps = _steps_of(doc, copy)
    twin = next(f for f in steps if f.feature_type == "honeycomb")
    assert twin.feature_id != cells.feature_id and twin.target_body_id == copy.body_id
    assert doc.bodies[copy.body_id].manifold.volume() == pytest.approx(volume, rel=1e-6)
    assert doc.edit_feature(doc.timeline.features.index(twin), size=9.0)
    assert doc.bodies[copy.body_id].manifold.volume() != pytest.approx(volume, rel=1e-3)
    assert doc.bodies[cells.target_body_id].manifold.volume() == pytest.approx(volume, rel=1e-6)


def _split_box():
    doc = Document()
    source = doc.add_box(40, 10, 10)
    left, right = source.manifold.bounding_box()[0], source.manifold.bounding_box()[3]
    plane = doc.add_construction_plane(SketchPlane.create_named("YZ"), left + 30)
    split = doc.split_body(source.body_id, plane)
    assert right - left == pytest.approx(40)
    return doc, source.body_id, split, split.result_body_id


@pytest.mark.parametrize("by_move", [True, False])
def test_a_copy_of_a_sliced_body_is_that_slice_only(by_move):
    doc, kept, split, half = _split_box()
    volume = doc.bodies[kept].manifold.volume()
    assert volume != pytest.approx(doc.bodies[half].manifold.volume())
    doc.delete_body(half)
    if by_move:
        doc.move_body(kept, dx=100, copy_body=True)
        copy_id = doc.timeline.features[-1].target_body_id
    else:
        copy_id = doc.branch_object(split.feature_id, kept, linked=False).body_id
    assert set(doc.bodies) == {kept, copy_id}
    assert doc.bodies[copy_id].manifold.volume() == pytest.approx(volume)

    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert set(restored.bodies) == {kept, copy_id}
    doc.undo()
    assert set(doc.bodies) == {kept}


def test_the_other_half_can_be_copied_and_the_original_halves_stay():
    doc, kept, split, half = _split_box()
    volumes = {b: doc.bodies[b].manifold.volume() for b in (kept, half)}
    history = doc.object_history
    own_split = history.objects[history.owners[next(f.feature_id for f in doc.timeline.features
                                                     if half in history.outputs.get(f.feature_id, []))]].feature_ids[-1]
    copy = doc.branch_object(own_split, half, linked=False)
    assert set(doc.bodies) == {kept, half, copy.body_id}
    assert copy.manifold.volume() == pytest.approx(volumes[half])
    assert {b: doc.bodies[b].manifold.volume() for b in (kept, half)} == pytest.approx(volumes)


def test_a_body_the_copied_steps_only_touched_is_not_removed():
    doc = Document()
    target = doc.add_box(10, 10, 10)
    other = doc.add_box(5, 5, 5)
    doc.combine_bodies(target.body_id, other.body_id, "join", keep_tool=True)
    copy = doc.branch_object(doc.timeline.features[-1].feature_id, target.body_id, linked=False)
    assert set(doc.bodies) == {target.body_id, other.body_id, copy.body_id}
    assert copy.manifold.volume() == pytest.approx(doc.bodies[target.body_id].manifold.volume())
