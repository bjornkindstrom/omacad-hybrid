"""A step can be moved out of its object into a new one, with the steps that build a new body from it (#103)."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DOC = str(Path(__file__).parent / "data" / "project_shelled_rim.omacad")


def _fid(doc, name):
    return next(f.feature_id for f in doc.timeline.features if f.name == name)


def test_sketch_on_the_rim_moves_to_its_own_object_and_back_with_undo():
    doc = Exporter.load_project(DOC)
    h = doc.object_history
    h.sync(doc)
    box = h.owners[_fid(doc, "Shell 1")]
    sk3 = _fid(doc, "Sketch 3")
    assert h.owners[sk3] == box
    volume = sum(b.manifold.volume() for b in doc.bodies.values())
    new = doc.move_to_new_object(sk3)
    h.sync(doc)
    assert h.owners[sk3] == new and h.objects[new].name == "Sketch 3"
    assert sk3 not in h.objects[box].feature_ids and _fid(doc, "Sketch 2") in h.objects[box].feature_ids
    assert sum(b.manifold.volume() for b in doc.bodies.values()) == pytest.approx(volume)
    # kept through save/load
    again = Document()
    Exporter.apply_dict(again, Exporter.document_to_dict(doc))
    again.object_history.sync(again)
    assert again.object_history.owners[sk3] == new
    doc.undo()
    doc.object_history.sync(doc)
    assert doc.object_history.owners[sk3] == box


def test_lid_plate_keeps_its_object_and_a_lone_step_cannot_move():
    doc = Exporter.load_project(DOC)
    sk3 = _fid(doc, "Sketch 3")
    sk = doc.sketches["sketch_3"]
    big = max(range(len(sk.profiles)), key=lambda i: sk.profiles[i].area)
    doc.extrude_profile("sketch_3", big, 3.0, operation="new_body")
    ext = doc.timeline.features[-1].feature_id
    h = doc.object_history
    h.sync(doc)
    lid = h.owners[ext]
    assert lid != h.owners[sk3]                # a new body is an object of its own already
    bodies = set(doc.bodies)
    new = doc.move_to_new_object(sk3)
    h.sync(doc)
    assert h.owners[ext] == lid and set(doc.bodies) == bodies
    with pytest.raises(ValueError):
        doc.move_to_new_object(sk3)            # alone in its object now
