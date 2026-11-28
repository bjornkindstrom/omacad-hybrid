"""Sketch plan step 2: the sketch's freedom is known at all times without moving anything (status chip and free/defined
colours), and a refused relation or dimension offers what to replace so it fits, as one undo step."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.sketch_solver import sketch_freedom


def test_freedom_is_worked_out_without_moving_anything_even_with_no_relations():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (20.0, 3.0))
    before = (line.p1, line.p2)
    res = sketch_freedom(sk)
    assert res.ok and sk.dof == 3                       # 4 coordinates - the length dimension
    assert (line.p1, line.p2) == before and line.entity_id in sk.free_ids
    assert doc.sketch_status(sk) == "Under defined (3 DOF)"
    empty = doc.start_sketch()
    assert sketch_freedom(empty).dof is None and doc.sketch_status(empty) == ""


def test_vertical_on_a_level_line_turns_it_instead_of_failing():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (20.0, 1.0))
    assert doc.add_constraints(sk.sketch_id, [("VERTICAL", [line.entity_id], [])])
    line = doc.active_sketch.get_entity(line.entity_id)
    assert line.p1[0] == pytest.approx(line.p2[0], abs=1e-9)
    assert abs(line.p2[1] - line.p1[1]) == pytest.approx((20.0 ** 2 + 1.0) ** 0.5, abs=1e-6)   # its length holds


def test_a_refused_relation_offers_what_to_replace_and_replacing_is_one_undo_step():
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (20.0, 1.0))
    assert doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [line.entity_id], [])])
    assert not doc.add_constraints(sk.sketch_id, [("VERTICAL", [line.entity_id], [])])
    labels = [c["label"] for c in doc.conflict_offer["choices"]]
    assert labels == ["Horizontal on line 1"]
    assert doc.replace_conflict(0)
    sk = doc.active_sketch
    assert [c.ctype for c in sk.constraints] == ["VERTICAL"] and doc.conflict_offer is None
    doc.undo()
    assert [c.ctype for c in doc.active_sketch.constraints] == ["HORIZONTAL"]


def test_a_refused_dimension_offers_the_dimension_it_clashes_with():
    doc = Document()
    sk = doc.start_sketch()
    a = sk.add_line((0.0, 0.0), (20.0, 0.0))
    b = sk.add_line((20.0, 0.0), (20.0, 10.0))
    doc.add_constraints(sk.sketch_id, [("COINCIDENT", [a.entity_id, b.entity_id], ["p2", "p1"]),
                                       ("HORIZONTAL", [a.entity_id], []), ("VERTICAL", [b.entity_id], [])])
    sk = doc.active_sketch
    # a distance from a's start to b's end over-defines the corner (both lengths are dimensioned)
    assert not doc.add_dimension_constraint(sk.sketch_id, "HORIZ_DIST", a.entity_id, 30.0,
                                            refs=[b.entity_id], pts=["p1", "p2"])
    offer = doc.conflict_offer
    assert offer and any(c["label"].startswith("Length 20") for c in offer["choices"])
    i = next(i for i, c in enumerate(offer["choices"]) if c["label"].startswith("Length 20"))
    assert doc.replace_conflict(i)
    sk = doc.active_sketch
    a, b = sk.get_entity(a.entity_id), sk.get_entity(b.entity_id)
    assert abs(b.p2[0] - a.p1[0]) == pytest.approx(30.0, abs=1e-6)


def test_status_chip_says_what_state_the_sketch_is_in():
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    assert vp.sketch_status_chip() is None                      # nothing drawn yet
    line = sk.add_line((0.0, 0.0), (20.0, 1.0))
    sketch_freedom(sk)
    text, colour = vp.sketch_status_chip()
    assert text.startswith("Under defined · 3 DOF") and "1 element can move" in text
    doc.add_constraints(sk.sketch_id, [("FIX", [line.entity_id], [])])
    sketch_freedom(doc.active_sketch)
    assert vp.sketch_status_chip()[0] == "✓ Fully defined"
    other = doc.active_sketch.add_line((0.0, 5.0), (20.0, 6.0))
    doc.add_constraints(doc.active_sketch.sketch_id, [("HORIZONTAL", [other.entity_id], [])])
    assert not doc.add_constraints(doc.active_sketch.sketch_id, [("VERTICAL", [other.entity_id], [])])
    text, _ = vp.sketch_status_chip()
    assert text.startswith("⚠ Over defined") and "click to choose" in text and vp.conflict_choices
    vp.deleteLater()


def test_a_relation_between_fixed_elements_that_is_not_true_is_refused():
    """The solver skips relations whose elements are all fixed: Vertical on a fixed level line was accepted."""
    doc = Document()
    sk = doc.start_sketch()
    line = sk.add_line((0.0, 0.0), (20.0, 1.0))
    assert doc.add_constraints(sk.sketch_id, [("FIX", [line.entity_id], [])])
    assert not doc.add_constraints(doc.active_sketch.sketch_id, [("VERTICAL", [line.entity_id], [])])
    assert "fixed" in doc.last_message
    assert [c.ctype for c in doc.active_sketch.constraints] == ["FIX"]
    offer = doc.conflict_offer
    assert offer and any(c["label"].startswith("Fix") for c in offer["choices"])     # unfix it to make room
