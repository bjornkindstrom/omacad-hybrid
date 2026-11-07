"""An independent copy has its own steps: every setting of the original can be changed on the copy, and neither follows
the other. It is made as the body stood after the step it was asked from."""
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane

HERE = os.path.dirname(__file__)


def steps_of(doc, body):
    history = doc.object_history
    owner = next(o for o in history.objects.values() if body.body_id in o.body_ids)
    return [doc.timeline.features[history.index(doc, f)] for f in owner.feature_ids]


def size(doc, body_id):
    lo = doc.bodies[body_id].manifold.bounding_box()
    return tuple(round(lo[i + 3] - lo[i], 6) for i in range(3))


def test_a_box_copy_has_its_own_box_step_and_each_side_edits_alone():
    doc = Document()
    source = doc.add_box(10, 20, 30)
    copy = doc.branch_object("box_1", source.body_id, linked=False)
    assert copy.name == "Box 1 Copy" and copy.body_id != source.body_id
    assert [f.feature_type for f in steps_of(doc, copy)] == ["box", "move"]
    box = steps_of(doc, copy)[0]
    assert doc.edit_feature_dimension(box.feature_id, "height", "50") is not False
    assert size(doc, copy.body_id) == (10, 20, 50) and size(doc, source.body_id) == (10, 20, 30)
    doc.edit_feature_dimension("box_1", "length", "40")
    assert size(doc, source.body_id)[0] == 40 and size(doc, copy.body_id)[0] == 10
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
    steps = steps_of(doc, copy)
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
    assert [f.feature_type for f in steps_of(doc, copy)] == ["box", "move"]
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
    steps = steps_of(doc, copy)
    assert [f.feature_type for f in steps] == ["box", "branch", "delete_body", "move"]
    assert set(doc.bodies) == {source.body_id, linked.body_id, copy.body_id}
    doc.edit_feature_dimension("box_1", "height", "20")
    assert size(doc, linked.body_id)[2] == 20 and size(doc, copy.body_id)[2] == 10
    doc.edit_feature_dimension(steps[0].feature_id, "height", "35")
    assert size(doc, copy.body_id)[2] == 35 and size(doc, linked.body_id)[2] == 20 and size(doc, source.body_id)[2] == 20


def test_the_pot_copy_can_change_its_cells():
    QApplication.instance() or QApplication([])
    doc = Document()
    with open(os.path.join(HERE, "data", "voronoi_pot.omacad"), encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    cells = next(f for f in doc.timeline.features if f.feature_type == "honeycomb")
    volume = doc.bodies[cells.target_body_id].manifold.volume()
    copy = doc.branch_object(cells.feature_id, cells.target_body_id, linked=False)
    steps = steps_of(doc, copy)
    twin = next(f for f in steps if f.feature_type == "honeycomb")
    assert twin.feature_id != cells.feature_id and twin.target_body_id == copy.body_id
    assert doc.bodies[copy.body_id].manifold.volume() == pytest.approx(volume, rel=1e-6)
    assert doc.edit_feature(doc.timeline.features.index(twin), size=9.0)
    assert doc.bodies[copy.body_id].manifold.volume() != pytest.approx(volume, rel=1e-3)
    assert doc.bodies[cells.target_body_id].manifold.volume() == pytest.approx(volume, rel=1e-6)


def split_box():
    """A 40 mm box split at x = 10 (report 20261104-221433), both halves standing."""
    doc = Document()
    source = doc.add_box(40, 10, 10)
    left, right = source.manifold.bounding_box()[0], source.manifold.bounding_box()[3]
    plane = doc.add_construction_plane(SketchPlane.create_named("YZ"), left + 30)
    split = doc.split_body(source.body_id, plane)
    assert right - left == pytest.approx(40)
    return doc, source.body_id, split, split.result_body_id


@pytest.mark.parametrize("by_move", [True, False])
def test_a_copy_of_a_sliced_body_is_that_slice_only(by_move):
    doc, kept, split, half = split_box()
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
    doc, kept, split, half = split_box()
    volumes = {b: doc.bodies[b].manifold.volume() for b in (kept, half)}
    history = doc.object_history
    own_split = history.objects[history.owners[next(f.feature_id for f in doc.timeline.features
                                                     if half in history.outputs.get(f.feature_id, []))]].feature_ids[-1]
    copy = doc.branch_object(own_split, half, linked=False)   # the half's own object ends in its own Split step
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


def test_the_removed_half_leaves_no_empty_row_in_the_browser():
    from omacad.ui.browser import BrowserTree
    from omacad.ui.object_browser import add_histories
    from PySide6.QtWidgets import QTreeWidgetItem
    QApplication.instance() or QApplication([])
    doc, kept, split, half = split_box()
    doc.delete_body(half)
    copy = doc.branch_object(split.feature_id, kept, linked=False)
    tree = BrowserTree(doc)
    root = QTreeWidgetItem(["root"])
    add_histories(tree, root)
    objects = root.child(0)
    labels = [objects.child(i).text(0) for i in range(objects.childCount())]
    assert labels.count("Split Body 1 result") == 0     # deleted, so the row with its Delete step has left too (#176)
    assert copy.body_id in doc.bodies
