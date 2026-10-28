"""#65: a sketch can be copied (browser > right-click > Duplicate): same plane and shapes, a new step, undoable."""
from omacad.io.exporter import Exporter
from omacad.model.document import Document


def test_duplicate_sketch_is_a_new_step_with_the_same_shapes(tmp_path):
    doc = Document()
    sk = doc.start_sketch("XZ")
    sk.add_rect((0, 0), (10, 5))
    sk.add_circle((20, 2), 3)
    doc.finish_sketch()
    copy = doc.duplicate_sketch(sk.sketch_id)
    assert copy.sketch_id != sk.sketch_id and copy.name == f"{sk.name} (copy)"
    assert len(copy.entities) == len(sk.entities) and len(copy.profiles) == len(sk.profiles) == 2
    assert (copy.plane.normal == sk.plane.normal).all()
    assert doc.timeline.features[-1].feature_id == f"feat_{copy.sketch_id}"
    doc.extrude_profile(copy.sketch_id, 0, 4.0, "new_body")       # the copy is a sketch like any other
    path = tmp_path / "d.omacad"
    Exporter.save_project(doc, str(path))
    assert len(Exporter.load_project(str(path)).sketches) == 2
    doc.undo()
    doc.undo()
    assert copy.sketch_id not in doc.sketches
