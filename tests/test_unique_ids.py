"""New steps, bodies and sketches never reuse an id after a delete (reuse overwrote existing work)."""
from omacad.model.document import Document


def test_box_after_deleting_a_middle_step_gets_its_own_body():
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(5, 10)
    doc.add_box(20, 20, 20)
    doc.delete_feature(1)
    doc.add_box(30, 30, 30)
    ids = [f.feature_id for f in doc.timeline.features]
    assert len(set(ids)) == len(ids) == 3
    assert sorted(round(b.manifold.volume()) for b in doc.bodies.values()) == [1000, 8000, 27000]


def test_new_sketch_after_deleting_the_first_does_not_replace_the_second():
    doc = Document()
    for x in (0, 50):
        sk = doc.start_sketch("XY")
        sk.add_rect((x, 0), (x + 10, 10))
        doc.finish_sketch()
    doc.delete_feature(0)
    second = next(iter(doc.sketches))
    new = doc.start_sketch("XY")
    new.add_circle((0, 0), 3)
    doc.finish_sketch()
    assert new.sketch_id != second
    assert len(doc.sketches) == 2
    assert len([f for f in doc.timeline.features if f.feature_type == "sketch"]) == 2


def test_rolled_back_sketch_id_is_not_reused():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    doc.finish_sketch()
    doc.timeline.step_to(0, doc)
    new = doc.start_sketch("XY")
    assert new.sketch_id != sk.sketch_id
