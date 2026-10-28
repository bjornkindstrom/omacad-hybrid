"""Report 20261024-064212: a rectangle with four sketch fillets; changing the length of a straight side (the flat
between two fillets) did nothing, because the arcs are not in the solver and the refit pulled the side back."""
import math
import os

from omacad.io.exporter import Exporter

DOC = os.path.join(os.path.dirname(__file__), "data", "filleted_rect_side_length.omacad")


def test_side_between_fillets_takes_the_new_length():
    doc = Exporter.load_project(DOC)
    sk = doc.sketches["sketch_1"]
    assert doc.update_dimension("sketch_1", "d2", 40.0)
    right, top, left = (sk.get_entity(i) for i in ("line_2", "line_3", "line_4"))
    assert math.isclose(abs(right.p2[1] - right.p1[1]), 40.0, abs_tol=1e-6)
    # the part grows by 18 mm: top wall moves up, left wall and the radii follow
    assert math.isclose(top.p1[1], 58.0, abs_tol=1e-6) and math.isclose(top.p2[1], 58.0, abs_tol=1e-6)
    assert math.isclose(abs(left.p1[1] - left.p2[1]), 33.0, abs_tol=1e-6)
    radii = {d.dim_id: d.value for d in sk.dimensions if d.dim_type == "RADIUS"}
    for arc_id, dim_id in (("arc_5", "d3"), ("arc_6", "d4"), ("arc_7", "d5"), ("arc_8", "d6")):
        assert math.isclose(sk.get_entity(arc_id).get_circle_params()[1], radii[dim_id], abs_tol=1e-6)
    assert math.isclose(next(d.value for d in sk.dimensions if d.dim_id == "d2"), 40.0, abs_tol=1e-6)
    assert len(sk.solve_profiles()) == 1
    doc.undo()
    right = doc.sketches["sketch_1"].get_entity("line_2")
    assert math.isclose(abs(right.p2[1] - right.p1[1]), 22.0, abs_tol=1e-6)
