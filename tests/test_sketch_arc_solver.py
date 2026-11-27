"""Drawn arcs are part of the sketch solver: their radius, ends and centre follow dimensions and relations, and
lines joined to them follow the arc (fillet and projected arcs keep their own rules)."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchArc
from omacad.model.sketch_solver import solve_sketch, solver_arc


def _radius_dim(sk, arc):
    return next(d for d in sk.dimensions if d.target_entity_id == arc.entity_id and d.dim_type == "RADIUS")


def _on_arc(arc, tol=1e-6):
    centre, r = arc.get_circle_params()[:2]
    return all(abs(math.dist(p, centre) - r) < tol for p in (arc.p_start, arc.p_mid, arc.p_end))


@pytest.mark.parametrize("mid", [(0.0, 10.0), (0.0, -10.0)])      # counter-clockwise and clockwise arcs
def test_radius_dimension_drives_a_drawn_arc_and_keeps_its_side(mid):
    doc = Document()
    sk = doc.start_sketch()
    arc = sk.add_arc((10.0, 0.0), mid, (-10.0, 0.0))
    assert solver_arc(arc)
    assert doc.update_dimension(sk.sketch_id, _radius_dim(sk, arc).dim_id, 15.0)
    arc = doc.active_sketch.get_entity(arc.entity_id)
    assert arc.get_circle_params()[1] == pytest.approx(15.0, abs=1e-6) and _on_arc(arc)
    assert math.copysign(1, arc.p_mid[1]) == math.copysign(1, mid[1])       # still bulges the same way


def test_a_line_joined_to_an_arc_end_follows_the_radius():
    doc = Document()
    sk = doc.start_sketch()
    arc = sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    line = sk.add_line((12.0, -2.0), (30.0, -20.0))
    assert doc.add_constraints(sk.sketch_id, [("ARC_END", [line.entity_id, arc.entity_id], ["p1", "p_start"])])
    line = doc.active_sketch.get_entity(line.entity_id)
    assert line.p1 == pytest.approx((10.0, 0.0), abs=1e-6)                 # the line went to the arc
    assert doc.update_dimension(sk.sketch_id, _radius_dim(doc.active_sketch, arc).dim_id, 6.0)
    sk = doc.active_sketch
    arc, line = sk.get_entity(arc.entity_id), sk.get_entity(line.entity_id)
    assert arc.get_circle_params()[1] == pytest.approx(6.0, abs=1e-6)
    assert line.p1 == pytest.approx(arc.p_start, abs=1e-6)                  # and stays on its end


def test_arc_centre_takes_a_distance_dimension_and_counts_in_the_degrees_of_freedom():
    doc = Document()
    sk = doc.start_sketch()
    arc = sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    wall = sk.add_line((-30.0, -5.0), (30.0, -5.0))
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [wall.entity_id], [])])
    free_before = doc.active_sketch.dof
    assert doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", arc.entity_id, 8.0,
                                        refs=[wall.entity_id], pts=["center"])
    sk = doc.active_sketch
    arc, wall = sk.get_entity(arc.entity_id), sk.get_entity(wall.entity_id)
    centre = arc.get_circle_params()[0]
    assert abs(centre[1] - wall.p1[1]) == pytest.approx(8.0, abs=1e-6) and _on_arc(arc)
    assert solve_sketch(sk).dof == free_before - 1          # one freedom less (the arc's centre height)


def test_equal_and_tangent_work_with_arcs():
    doc = Document()
    sk = doc.start_sketch()
    arc = sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    circle = sk.add_circle((40.0, 0.0), 4.0)
    sk.dimensions = [d for d in sk.dimensions if d.target_entity_id != circle.entity_id]
    assert doc.add_constraints(sk.sketch_id, [("EQUAL", [arc.entity_id, circle.entity_id], [])])
    sk = doc.active_sketch
    arc, circle = sk.get_entity(arc.entity_id), sk.get_entity(circle.entity_id)
    assert circle.radius == pytest.approx(arc.get_circle_params()[1], abs=1e-6)
    line = sk.add_line((-20.0, 14.0), (20.0, 13.0))
    assert doc.add_constraints(sk.sketch_id, [("TANGENT", [line.entity_id, arc.entity_id], [])])
    sk = doc.active_sketch
    arc, line = sk.get_entity(arc.entity_id), sk.get_entity(line.entity_id)
    (cx, cy), r = arc.get_circle_params()[:2]
    (x1, y1), (x2, y2) = line.p1, line.p2
    dist = abs((cx - x1) * (y2 - y1) - (cy - y1) * (x2 - x1)) / math.dist(line.p1, line.p2)
    assert dist == pytest.approx(r, abs=1e-5)


def test_fillet_and_projected_arcs_keep_their_own_rules():
    doc = Document()
    sk = doc.start_sketch()
    fillet = SketchArc(sk._new_entity_id("arc"), (1.0, 0.0), (0.7, 0.7), (0.0, 1.0))
    fillet.fillet_info = {"line_a": "x", "line_b": "y"}
    assert not solver_arc(fillet)
    projected = sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    projected.projected = True
    line = sk.add_line((3.0, 12.0), (5.0, 30.0))
    assert doc.add_constraints(sk.sketch_id, [("POINT_ON_CIRCLE", [projected.entity_id, line.entity_id], ["p1"])])
    sk = doc.active_sketch
    projected = sk.get_entity(projected.entity_id)
    assert projected.p_start == (10.0, 0.0) and projected.p_end == (-10.0, 0.0)   # a body edge never moves
    assert math.hypot(*sk.get_entity(line.entity_id).p1) == pytest.approx(10.0, abs=1e-6)


def test_arc_solving_survives_save_and_load():
    from omacad.model.sketch import Sketch
    doc = Document()
    sk = doc.start_sketch()
    arc = sk.add_arc((10.0, 0.0), (0.0, -10.0), (-10.0, 0.0))
    doc.update_dimension(sk.sketch_id, _radius_dim(sk, arc).dim_id, 12.0)
    again = Sketch.from_dict(doc.active_sketch.to_dict())
    assert solve_sketch(again).ok
    a = again.get_entity(arc.entity_id)
    assert a.get_circle_params()[1] == pytest.approx(12.0, abs=1e-6) and a.p_mid[1] < 0


def test_arc_points_can_be_picked_for_dimensions_but_not_a_fillet_arcs():
    from omacad.model.sketch import point_names
    doc = Document()
    sk = doc.start_sketch()
    arc = sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    assert set(point_names(arc)) == {"p_start", "p_end", "center"}
    fillet = SketchArc("f", (1.0, 0.0), (0.7, 0.7), (0.0, 1.0))
    fillet.fillet_info = {"line_a": "x", "line_b": "y"}
    assert point_names(fillet) == ()
    line = sk.add_line((-30.0, 20.0), (30.0, 20.0))
    assert doc.add_dimension_constraint(sk.sketch_id, "DISTANCE", arc.entity_id, 25.0,
                                        refs=[line.entity_id], pts=["p_end", "p1"])
    sk = doc.active_sketch
    assert math.dist(sk.get_entity(arc.entity_id).p_end, sk.get_entity(line.entity_id).p1) == pytest.approx(25.0, abs=1e-6)
    assert _on_arc(sk.get_entity(arc.entity_id))


# ---- slots

def _slot_dim(sk, slot, kind):
    return next(d for d in sk.dimensions if d.target_entity_id == slot.entity_id and d.dim_type == kind)


def test_slot_length_and_width_drive_it_in_the_solver_and_it_takes_line_relations():
    doc = Document()
    sk = doc.start_sketch()
    slot = sk.add_slot((0.0, 0.0), (20.0, 3.0), 4.0)
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [slot.entity_id], [])])
    slot = doc.active_sketch.get_entity(slot.entity_id)
    assert slot.center1[1] == pytest.approx(slot.center2[1], abs=1e-6)                 # its axis is level
    assert math.dist(slot.center1, slot.center2) == pytest.approx(math.hypot(20.0, 3.0), abs=1e-6)
    assert doc.update_dimension(sk.sketch_id, _slot_dim(doc.active_sketch, slot, "LENGTH").dim_id, 30.0)
    assert doc.update_dimension(sk.sketch_id, _slot_dim(doc.active_sketch, slot, "DIAMETER").dim_id, 6.0)
    slot = doc.active_sketch.get_entity(slot.entity_id)
    assert math.dist(slot.center1, slot.center2) == pytest.approx(30.0, abs=1e-6)
    assert slot.radius == pytest.approx(3.0, abs=1e-6) and slot.center1[1] == pytest.approx(slot.center2[1], abs=1e-6)


def test_slot_centre_is_placed_by_a_distance_dimension():
    doc = Document()
    sk = doc.start_sketch()
    slot = sk.add_slot((0.0, 0.0), (20.0, 0.0), 4.0)
    wall = sk.add_line((-10.0, -15.0), (40.0, -15.0))
    doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [wall.entity_id], []), ("HORIZONTAL", [slot.entity_id], [])])
    assert doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", slot.entity_id, 9.0,
                                        refs=[wall.entity_id], pts=["center1"])
    sk = doc.active_sketch
    slot, wall = sk.get_entity(slot.entity_id), sk.get_entity(wall.entity_id)
    assert abs(slot.center1[1] - wall.p1[1]) == pytest.approx(9.0, abs=1e-6)
    assert slot.radius == pytest.approx(4.0, abs=1e-6)


# ---- relations an arc or circle gets when it is drawn (sketch plan step 4)

def test_an_arc_drawn_from_a_line_end_is_joined_and_tangent_and_stays_so():
    from omacad.model.sketch_solver import curve_auto_relations
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((-20.0, 0.0), (0.0, 0.0))
    arc = sk.add_arc((0.0, 0.0), (10.0, 10.0), (20.0, 0.0))       # starts at the line's end, not tangent
    specs = curve_auto_relations(sk, arc)
    assert ("ARC_END", [line.entity_id, arc.entity_id], ["p2", "p_start"]) in specs
    tangent_arc = sk.add_arc((0.0, 0.0), (7.07106781, 2.92893219), (10.0, 10.0))   # centre (0, 10): tangent to the line
    specs = curve_auto_relations(sk, tangent_arc)
    assert ("TANGENT", [line.entity_id, tangent_arc.entity_id], []) in specs
    assert doc.auto_constrain(sk, specs) == len(specs)
    assert doc.update_dimension(sk.sketch_id, _radius_dim(sk, tangent_arc).dim_id, 6.0)
    sk = doc.active_sketch
    line, t = sk.get_entity(line.entity_id), sk.get_entity(tangent_arc.entity_id)
    (cx, cy), r = t.get_circle_params()[:2]
    assert r == pytest.approx(6.0, abs=1e-6) and t.p_start == pytest.approx(line.p2, abs=1e-6)
    (x1, y1), (x2, y2) = line.p1, line.p2
    to_line = abs((cx - x1) * (y2 - y1) - (cy - y1) * (x2 - x1)) / math.dist(line.p1, line.p2)
    assert to_line == pytest.approx(6.0, abs=1e-5)                 # still tangent at the joined end


def test_a_circle_centred_on_a_point_or_a_centre_keeps_it():
    from omacad.model.sketch_solver import curve_auto_relations
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (20.0, 0.0))
    ring = sk.add_circle((20.0, 0.0), 5.0)
    assert curve_auto_relations(sk, ring) == [("COINCIDENT", [line.entity_id, ring.entity_id], ["p2", "center"])]
    inner = sk.add_circle((20.0, 0.0), 2.0)
    assert ("CONCENTRIC", [inner.entity_id, ring.entity_id], []) in curve_auto_relations(sk, inner) or \
        curve_auto_relations(sk, inner)[0][0] == "COINCIDENT"
