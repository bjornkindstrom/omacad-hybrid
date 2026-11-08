"""SolidWorks-style over defined feedback: a refused constraint names the clashing elements."""
from omacad.model.document import Document


def test_refused_constraint_reports_the_clash():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (10.0, 0.0))
    b = sk.add_line((0.0, 5.0), (10.0, 6.0))
    sk.dimensions.clear()
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [a.entity_id], []), ("FIX", [a.entity_id], [])])
    assert doc.add_constraints(sk.sketch_id, [("PERPENDICULAR", [a.entity_id, b.entity_id], [])])
    assert not doc.add_constraints(sk.sketch_id, [("PARALLEL", [a.entity_id, b.entity_id], [])])
    assert doc.last_message.startswith("Over defined")
    sid, ids, _t = doc.last_conflicts
    assert sid == sk.sketch_id and b.entity_id in ids
    assert not any(c.ctype == "PARALLEL" for c in sk.constraints)


def test_a_good_solve_has_no_conflicts():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (10.0, 1.0))
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [a.entity_id], [])])
    assert doc.last_conflicts is None and not sk.conflict_ids
