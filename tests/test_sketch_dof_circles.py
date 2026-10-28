"""#84: a circle placed with Smart Circle (diameter + two distances to lines) is fully defined. The solver's
workplane normal used to sit in the free group and add 3 phantom degrees of freedom to every sketch with a
circle, so a completely dimensioned sketch still said "under defined"."""
from omacad.model.document import Document
from omacad.model.sketch_solver import solve_sketch


def test_smart_circle_dimensions_leave_no_freedom():
    doc = Document()
    sk = doc.start_sketch("XY")
    a = sk.add_line((0.0, 0.0), (40.0, 0.0))
    b = sk.add_line((0.0, 0.0), (0.0, 30.0))
    c = sk.add_circle((10.0, 10.0), 2.5)     # comes with its diameter dimension, as Smart Circle makes it
    doc.add_constraints(sk.sketch_id, [("FIX", [a.entity_id], []), ("FIX", [b.entity_id], [])])
    doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 10.0, refs=[a.entity_id], pts=["center"])
    doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 10.0, refs=[b.entity_id], pts=["center"])
    assert solve_sketch(sk).dof == 0
