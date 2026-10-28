"""Deleting a step warns about (and takes along) every later step built on it, also through an Extrude's hole or
extra-profile reference to another sketch and an Offset Face on a thread."""
from omacad.model.document import Document
from omacad.model.features.extrude import ExtrudeFeature
from omacad.model.features.offset_face import OffsetFaceFeature


def _two_sketches():
    doc = Document()
    ids = []
    for x in (0, 50):
        sk = doc.start_sketch("XY")
        sk.add_rect((x, 0), (x + 10, 10))
        doc.finish_sketch()
        ids.append(sk.sketch_id)
    return doc, ids


def test_extrude_using_a_hole_from_another_sketch_depends_on_it():
    doc, (a, b) = _two_sketches()
    doc.timeline.add_feature(ExtrudeFeature("extrude_x", "Extrude", a, 0, 5.0, "new_body", holes=[(b, 0, (0.0, 0.0))]))
    assert doc.dependents_of(1) == [2]


def test_offset_face_on_a_thread_depends_on_the_thread():
    doc = Document()
    doc.add_cylinder(10, 20)
    cyl = next(iter(doc.bodies))
    doc.add_thread(diameter=20, pitch=2, length=10, target_body_id=cyl, operation="join",
                   plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], host_length=20)
    thread_id = doc.timeline.features[1].feature_id
    doc.timeline.add_feature(OffsetFaceFeature("offset_face_x", "Offset Face", "body_other",
                                               [{"kind": "thread", "thread_id": thread_id, "sign": -1, "shift": [0, 0, 0]}]))
    assert 2 in doc.dependents_of(1)
