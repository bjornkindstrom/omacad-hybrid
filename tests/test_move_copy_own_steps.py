"""Björn #108: a copy made with Move gets its own steps, so every parameter of the copy can be changed
without touching the original."""
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DOC = "tests/data/move_copy_own_steps.omacad"


def _box(body):
    return [round(v, 3) for v in body.manifold.bounding_box()]


def test_copy_rebuilds_the_whole_object_and_edits_stay_on_the_copy():
    doc = Exporter.load_project(DOC)
    volume = doc.bodies["body_extrude_2"].manifold.volume()
    move = doc.move_body("body_extrude_2", dx=49, copy_body=True)
    copy_id = move.target_body_id
    assert set(doc.bodies) == {"body_extrude_2", copy_id}
    assert doc.bodies[copy_id].manifold.volume() == pytest.approx(volume, rel=1e-6)
    assert _box(doc.bodies[copy_id]) == [49, 0, 0, 84, 56, 20]

    history = doc.object_history
    owner = history.owners[move.feature_id]
    steps = [doc.timeline.features[history.index(doc, f)] for f in history.objects[owner].feature_ids]
    assert [f.feature_type for f in steps] == ["sketch", "extrude", "fillet", "fillet", "sketch", "extrude", "fillet", "move"]
    assert history.owners["extrude_2"] != owner

    extrude = next(f for f in steps if f.feature_type == "extrude")
    doc.edit_feature_dimension(extrude.feature_id, "distance", "30")
    assert _box(doc.bodies[copy_id])[5] == pytest.approx(30)
    assert _box(doc.bodies["body_extrude_2"]) == [0, 0, 0, 35, 56, 20]
    assert doc.bodies["body_extrude_2"].manifold.volume() == pytest.approx(volume, rel=1e-6)

    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert _box(restored.bodies[copy_id])[5] == pytest.approx(30)

    doc.undo()
    doc.undo()
    assert set(doc.bodies) == {"body_extrude_2"}
    assert len(doc.timeline.features) == 7


def test_a_sketch_of_the_copy_is_its_own():
    doc = Exporter.load_project(DOC)
    move = doc.move_body("body_extrude_2", dx=49, copy_body=True)
    sketches = [f.sketch.sketch_id for f in doc.timeline.features if f.feature_type == "sketch"]
    assert len(set(sketches)) == 4
    copy_extrude = next(f for f in doc.timeline.features if f"body_{f.feature_id}" == move.target_body_id)
    assert copy_extrude.sketch_id not in ("sketch_1", "sketch_2")
    doc.sketches[copy_extrude.sketch_id].entities.clear()   # what the copy's sketch holds is not the original's
    assert doc.sketches["sketch_1"].entities
