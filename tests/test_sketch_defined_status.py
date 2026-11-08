"""SolidWorks-style status per entity: fully defined geometry is black, the rest stays blue."""
from omacad.model.document import Document
from omacad.model.sketch_solver import entity_defined, solve_sketch


def test_fixed_line_is_defined_and_a_hanging_line_is_not():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (10.0, 0.0))
    b = sk.add_line((10.0, 0.0), (10.0, 5.0))
    sk.dimensions.clear()                   # add_line gives every line a length dimension
    doc.add_constraints(sk.sketch_id, [("FIX", [a.entity_id], []),
                                       ("COINCIDENT", [b.entity_id, a.entity_id], ["p1", "p2"]),
                                       ("VERTICAL", [b.entity_id], [])])
    a, b = sk.get_entity(a.entity_id), sk.get_entity(b.entity_id)
    assert sk.dof == 1                      # b's length is still free
    assert entity_defined(sk, a)
    assert not entity_defined(sk, b)


def test_a_dimension_makes_the_last_line_black():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (10.0, 0.0))
    b = sk.add_line((10.0, 0.0), (10.0, 5.0))
    c = sk.add_line((30.0, 30.0), (40.0, 35.0))     # unrelated, free
    sk.dimensions.clear()
    doc.add_constraints(sk.sketch_id, [("FIX", [a.entity_id], []),
                                       ("COINCIDENT", [b.entity_id, a.entity_id], ["p1", "p2"]),
                                       ("VERTICAL", [b.entity_id], []),
                                       ("HORIZONTAL", [c.entity_id], [])])
    b, c = sk.get_entity(b.entity_id), sk.get_entity(c.entity_id)
    assert not entity_defined(sk, b)
    sk.add_dimension("LENGTH", b.entity_id, 5.0)
    assert solve_sketch(sk).ok
    assert entity_defined(sk, b)
    assert not entity_defined(sk, c)


def test_a_line_drawn_after_the_solve_is_not_black():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (10.0, 0.0))
    doc.add_constraints(sk.sketch_id, [("FIX", [a.entity_id], [])])
    assert sk.dof == 0
    new = sk.add_line((5.0, 5.0), (8.0, 9.0))
    assert entity_defined(sk, sk.get_entity(a.entity_id))
    assert not entity_defined(sk, new)


def test_no_constraints_means_nothing_is_black():
    sk = Document().start_sketch()
    line = sk.add_line((0.0, 0.0), (10.0, 0.0))
    solve_sketch(sk)
    assert not entity_defined(sk, line)
