"""A body the user hid (eye in the Browser) must stay hidden when the history is rebuilt, e.g. after Offset Face on a
thread: the lid (the big thread) came back into the jar after every rebuild."""
from pathlib import Path

from omacad.io.exporter import Exporter

DOC = str(Path(__file__).parent / "data" / "offset_face_coil_stuck.omacad")


def test_recompute_keeps_hidden_bodies_hidden():
    doc = Exporter.load_project(DOC)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    doc.bodies["body_cylinder_1"].visible = False
    doc.timeline.recompute(doc)
    assert not doc.bodies["body_cylinder_1"].visible and doc.bodies["body_split_2"].visible


def test_offset_face_on_thread_keeps_the_lid_hidden():
    doc = Exporter.load_project(DOC)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    doc.bodies["body_cylinder_1"].visible = False
    doc.add_offset_face("body_split_2", last.faces, -0.2)
    assert not doc.bodies["body_cylinder_1"].visible
