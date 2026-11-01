"""Object histories keep identity across edits, replay, undo and file loading."""
import pytest
from omacad.model.document import Document
from omacad.io.exporter import Exporter


def test_sketch_and_extrude_share_history_and_independent_primitive_does_not():
    doc = Document()
    sk = doc.start_sketch('XY')
    sk.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5)
    doc.add_box(2, 3, 4, translation=(30, 0, 0))
    doc.timeline.recompute(doc)
    histories = list(doc.object_history.objects.values())
    assert len(histories) == 2
    assert len(histories[0].feature_ids) == 2
    assert len(histories[1].feature_ids) == 1
    data = Exporter.document_to_dict(doc)
    restored = Document()
    Exporter.apply_dict(restored, data)
    assert restored.object_history.owners == doc.object_history.owners
    assert list(restored.bodies) == list(doc.bodies)


def test_local_rollback_keeps_unrelated_later_body_and_can_resume():
    doc = Document()
    first = doc.add_box(10, 10, 10)
    root = doc.timeline.last_added.feature_id
    doc.add_shell(first.body_id, 1)
    second = doc.add_box(3, 4, 5, translation=(30, 0, 0))
    doc.timeline.recompute(doc)
    owner = doc.object_history.owners[root]
    doc.object_step_to(owner, root)
    assert doc.bodies[first.body_id].manifold.volume() == pytest.approx(1000)
    assert doc.bodies[second.body_id].manifold.volume() == pytest.approx(60)
    doc.object_fast_forward(owner)
    assert doc.bodies[first.body_id].manifold.volume() < 1000
    assert second.body_id in doc.bodies


def test_dimension_formula_edit_and_undo_restore_history_and_geometry():
    doc = Document()
    body = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    owners = dict(doc.object_history.owners)
    doc.edit_feature_dimension(fid, 'height', '2*8')
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(1600)
    assert doc.timeline.last_added.exprs['height'] == '2*8'
    doc.undo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(1000)
    assert doc.object_history.owners == owners
    with pytest.raises(ValueError):
        doc.edit_feature_dimension(fid, 'height', 'unknown_parameter')


def test_legacy_project_gets_object_histories_without_geometry_changes():
    doc = Document()
    doc.add_box(10, 20, 30)
    data = Exporter.document_to_dict(doc)
    data.pop('object_history')
    data.pop('format_version')
    restored = Document()
    Exporter.apply_dict(restored, data)
    assert len(restored.object_history.objects) == 1
    assert next(iter(restored.bodies.values())).manifold.volume() == pytest.approx(6000)


def test_suppressed_root_keeps_object_and_its_steps():
    doc = Document()
    doc.add_box(10, 10, 10)
    oid = next(iter(doc.object_history.objects))
    doc.toggle_suppress(0)
    assert not doc.bodies
    assert oid in doc.object_history.objects
    assert len(doc.object_history.objects[oid].feature_ids) == 1


def test_independent_object_is_not_executed_when_an_earlier_object_changes(monkeypatch):
    doc = Document()
    doc.add_box(10, 10, 10)
    first = doc.timeline.last_added.feature_id
    second = doc.add_box(3, 4, 5, translation=(30, 0, 0))
    doc.timeline.recompute(doc)
    feat = doc.timeline.last_added
    calls = []
    original = feat.execute
    monkeypatch.setattr(feat, 'execute', lambda d: (calls.append(True), original(d)))
    doc.edit_feature_dimension(first, 'height', '20')
    assert not calls
    assert doc.bodies[second.body_id].manifold.volume() == pytest.approx(60)


def test_linked_branch_and_independent_copy_have_separate_histories():
    doc = Document()
    source = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    linked = doc.branch_object(fid, source.body_id)
    frozen = doc.branch_object(fid, source.body_id, linked=False)
    assert len(doc.object_history.objects) == 3
    doc.edit_feature_dimension(fid, 'height', '20')
    assert doc.bodies[linked.body_id].manifold.volume() == pytest.approx(2000)
    assert doc.bodies[frozen.body_id].manifold.volume() == pytest.approx(1000)
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert restored.bodies[linked.body_id].manifold.volume() == pytest.approx(2000)
    assert len(restored.object_history.objects) == 3


def test_inserting_into_object_keeps_later_steps_and_other_objects():
    doc = Document()
    first = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    shell = doc.add_shell(first.body_id, 1)
    second = doc.add_box(2, 3, 4, translation=(30, 0, 0))
    doc.timeline.recompute(doc)
    oid = doc.object_history.owners[fid]
    doc.object_insert_after(oid, fid)
    doc.move_body(first.body_id, dx=5)
    types = [f.feature_type for f in doc.timeline.features]
    assert types == ['box', 'move', 'shell', 'box']
    assert second.body_id in doc.bodies
    assert shell.feature_id in doc.object_history.objects[oid].feature_ids
    assert not doc.object_history.markers


def test_split_results_have_their_own_history_and_keep_frozen_source():
    from omacad.model.sketch import SketchPlane
    doc = Document()
    source = doc.add_box(10, 10, 10)
    root = doc.timeline.last_added.feature_id
    plane = doc.add_construction_plane(SketchPlane.create_named('XY'), 5)
    split = doc.split_body(source.body_id, plane)
    child_id = 'body_' + split.feature_id
    doc.move_body(child_id, dx=20)
    child_step = doc.timeline.last_added.feature_id
    assert doc.object_history.owners[child_step] != doc.object_history.owners[root]
    doc.edit_feature_dimension(root, 'height', '20')
    assert doc.bodies[source.body_id].manifold.volume() == pytest.approx(500)
    assert doc.bodies[child_id].manifold.volume() == pytest.approx(500)
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert loaded.object_history.owners[child_step] == doc.object_history.owners[child_step]


def test_shared_sketch_updates_both_objects_and_branch_delete_dependency():
    doc = Document()
    sketch = doc.start_sketch('XY')
    sketch.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sketch.sketch_id, 0, 5)
    doc.extrude_profile(sketch.sketch_id, 0, 8)
    assert len(doc.object_history.objects) == 2
    sketch_feature = doc.timeline.features[0].feature_id
    assert all(sketch_feature in doc.object_history.dependencies[f.feature_id] for f in doc.timeline.features[1:])


def test_new_cut_remembers_targets_when_an_unrelated_body_moves_into_it():
    doc = Document()
    target = doc.add_box(10, 10, 10)
    unrelated = doc.add_box(10, 10, 10, translation=(30, 0, 0))
    sketch = doc.start_sketch('XY')
    sketch.add_rect((2, 2), (8, 8))
    doc.finish_sketch()
    doc.extrude_profile(sketch.sketch_id, 0, 5, operation='cut')
    cut = doc.timeline.last_added
    assert cut.target_body_ids == [target.body_id]
    # Move the second root into the cutter by changing its original placement.
    doc.timeline.features[1].translation = [0, 0, 0]
    doc.timeline.recompute(doc)
    assert doc.bodies[unrelated.body_id].manifold.volume() == pytest.approx(1000)
    assert doc.bodies[target.body_id].manifold.volume() == pytest.approx(820)


def test_shell_replay_does_not_make_an_unrelated_existing_object_a_dependency():
    doc = Document()
    first = doc.add_box(10, 10, 10)
    root = doc.timeline.last_added.feature_id
    second = doc.add_box(5, 5, 5, translation=(30, 0, 0))
    other = doc.timeline.last_added.feature_id
    shell = doc.add_shell(first.body_id, 1)
    assert doc.object_history.outputs[shell.feature_id] == [first.body_id]
    assert other not in doc.object_history.dependencies[shell.feature_id]
    doc.move_body(second.body_id, dx=5)
    assert shell.feature_id not in doc.object_history.dependencies[doc.timeline.last_added.feature_id]
    doc.object_step_to(doc.object_history.owners[root], root)
    assert second.body_id in doc.bodies


def test_units_and_invalid_dimension_transaction():
    doc = Document()
    doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    doc.edit_feature_dimension(fid, 'height', '2 cm')
    assert doc.timeline.last_added.height == 20
    state = doc.snapshot()
    with pytest.raises(ValueError):
        doc.edit_feature_dimension(fid, 'height', '-1 mm')
    assert doc.snapshot() == state


def test_deleting_source_deletes_linked_branch_but_keeps_independent_copy():
    doc = Document()
    body = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    doc.branch_object(fid, body.body_id)
    independent = doc.branch_object(fid, body.body_id, linked=False)
    removed = doc.delete_feature(0)
    assert len(removed) == 2
    assert list(doc.bodies) == [independent.body_id]
    doc.undo()
    assert len(doc.bodies) == 3


def test_switching_new_body_extrude_to_cut_selects_and_remembers_targets():
    doc = Document()
    body = doc.add_box(10, 10, 10)
    sk = doc.start_sketch('XY')
    sk.add_rect((2, 2), (8, 8))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5, operation='new_body')
    doc.edit_feature(2, operation='cut')
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(820)
    assert doc.timeline.last_added.target_body_ids == [body.body_id]


def test_future_file_version_is_rejected_before_changing_document():
    doc = Document()
    doc.add_box(10, 10, 10)
    state = doc.snapshot()
    with pytest.raises(ValueError, match='newer version'):
        Exporter.apply_dict(doc, dict(state, format_version=100))
    assert doc.snapshot() == state


def test_combined_tool_objects_become_branches_of_the_target_object():
    """Björn: Jar with Lid put every tool cylinder (neck, bore, chamfer cones) on the main trunk of Objects."""
    from omacad.model.jar import JarSpec
    doc = Document()
    ids = doc.add_jar(JarSpec())
    history = doc.object_history
    by_name = {obj.name: obj for obj in history.objects.values()}
    assert [o.name for o in history.objects.values() if o.parent_id is None] == ['Jar', 'Lid']
    jar, lid = by_name['Jar'], by_name['Lid']
    assert by_name['Neck'].parent_id == jar.object_id
    assert by_name['Thread chamfer'].parent_id == jar.object_id
    assert by_name['Thread chamfer cone'].parent_id == by_name['Thread chamfer'].object_id
    assert by_name['Lid bore'].parent_id == lid.object_id
    assert by_name['Lid mouth chamfer'].parent_id == lid.object_id
    assert ids['jar'] in jar.body_ids and ids['lid'] in lid.body_ids
    # a combine that keeps its tool (the lid is cut by the jar) leaves the tool on its own trunk
    assert jar.parent_id is None
    neck_join = by_name['Neck'].consumed_by
    assert set(history.children(jar.object_id)[neck_join]) == {by_name['Neck'].object_id}


def test_linked_object_follows_later_steps_of_the_original():
    doc = Document()
    source = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    linked = doc.branch_object(fid, source.body_id)
    doc.add_box(1, 1, 1, translation=(40, 0, 0))            # an unrelated object stays where it is
    doc.add_shell(source.body_id, 1)                        # a step the original gets after the link
    shelled = doc.bodies[source.body_id].manifold.volume()
    assert shelled < 1000
    assert doc.bodies[linked.body_id].manifold.volume() == pytest.approx(shelled)
    order = [f.feature_type for f in doc.timeline.features]
    assert order.index('shell') < order.index('branch')
    doc.edit_feature_dimension(fid, 'height', '20')
    assert doc.bodies[linked.body_id].manifold.volume() == pytest.approx(doc.bodies[source.body_id].manifold.volume())
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert restored.bodies[linked.body_id].manifold.volume() == pytest.approx(doc.bodies[source.body_id].manifold.volume())


def test_linked_object_keeps_its_own_steps_behind_the_original():
    doc = Document()
    source = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    linked = doc.branch_object(fid, source.body_id)
    doc.move_body(linked.body_id, dx=30)                    # the copy's own step
    doc.add_shell(source.body_id, 1)                        # then the original changes
    ids = [f.feature_id for f in doc.timeline.features]
    types = [f.feature_type for f in doc.timeline.features]
    assert types.index('shell') < types.index('branch') < types.index('move')
    copy_body = doc.bodies[linked.body_id].manifold
    assert copy_body.volume() == pytest.approx(doc.bodies[source.body_id].manifold.volume())
    assert copy_body.bounding_box()[0] > 15          # the copy kept its own move
    assert len(ids) == len(set(ids))


def test_link_from_the_primitive_step_is_the_whole_object_and_follows_it():
    """Report 20261101-141324: a linked object made from the menu of the object's first step (the Box) stopped at
    the plain box instead of being the object with its extrude."""
    import os
    path = os.path.join(os.path.dirname(__file__), 'data', 'linked_copy_of_primitive_step.omacad')
    doc = Exporter.load_project(path)
    doc.timeline.features = [f for f in doc.timeline.features if f.feature_type != 'branch']
    doc.timeline.marker_index = len(doc.timeline.features)
    doc.timeline.recompute(doc)
    original = doc.bodies['body_box_1'].manifold
    assert original.volume() == pytest.approx(50 * 50 * 25 + 20 * 20 * 15)
    linked = doc.branch_object('box_1', 'body_box_1')
    assert doc.timeline.last_added.follow is True
    copy = doc.bodies[linked.body_id].manifold
    assert copy.volume() == pytest.approx(original.volume())
    assert copy.bounding_box()[5] == pytest.approx(original.bounding_box()[5])   # the extruded block is on it too
    doc.edit_feature_dimension('extrude_3', 'distance', '30')
    assert doc.bodies[linked.body_id].manifold.volume() == pytest.approx(50 * 50 * 25 + 20 * 20 * 30)


def test_link_made_right_after_a_primitive_follows_a_sketch_and_extrude_on_it():
    from omacad.model.sketch_entities import SketchPlane
    import numpy as np
    doc = Document()
    source = doc.add_box(10, 10, 10)
    linked = doc.branch_object(doc.timeline.last_added.feature_id, source.body_id)
    plane = SketchPlane('FACE', np.array([0.0, 0.0, 10.0]), np.array([1.0, 0.0, 0.0]),
                        np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]))
    sk = doc.start_sketch_on_plane(plane)
    sk.add_rect((3, 3), (7, 7))
    doc.finish_sketch()
    profile = min(range(len(sk.profiles)), key=lambda i: abs(sk.profiles[i].area - 16))
    doc.extrude_profile(sk.sketch_id, profile, 5, operation='join')
    assert doc.bodies[source.body_id].manifold.volume() == pytest.approx(1000 + 80)
    assert doc.bodies[linked.body_id].manifold.volume() == pytest.approx(1000 + 80)


def test_copies_are_placed_to_the_right_of_the_original():
    doc = Document()
    source = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    linked = doc.branch_object(fid, source.body_id)
    independent = doc.branch_object(fid, source.body_id, linked=False)
    right = doc.bodies[source.body_id].manifold.bounding_box()[3]
    for body in (linked, independent):
        lo = doc.bodies[body.body_id].manifold.bounding_box()[0]
        assert lo > right                                   # beside, not touching
    assert (doc.bodies[source.body_id].manifold ^ doc.bodies[linked.body_id].manifold).volume() == pytest.approx(0)
