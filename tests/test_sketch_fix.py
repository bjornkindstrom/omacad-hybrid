"""Fix Sketch closes what was drawn into a face with the fewest changes: joins near-miss ends, extends a line that
stops short, removes doubles, and closes an open chain with one line. A closed sketch is left alone."""
import pytest

from omacad.model.document import Document
from omacad.model.sketch_fix import fix_sketch, free_ends


def _sketch():
    return Document().start_sketch("XY")


def _area(sk):
    return sum(p.area for p in sk.profiles)


def test_rectangle_with_a_small_gap_is_joined():
    sk = _sketch()
    sk.add_line((0, 0), (20, 0))
    sk.add_line((20, 0), (20, 10))
    sk.add_line((20, 10), (0, 10))
    sk.add_line((0, 10), (0, 0.3))           # misses the start by 0.3 mm
    sk.solve_profiles()
    assert not sk.profiles
    done = fix_sketch(sk)
    assert done == ["joined 1 gap(s)"]
    assert len(sk.profiles) == 1 and _area(sk) == pytest.approx(200.0, rel=1e-6)   # square corner, not skewed
    assert not free_ends(sk)


def test_open_u_gets_one_closing_line():
    sk = _sketch()
    sk.add_line((0, 10), (0, 0))
    sk.add_line((0, 0), (20, 0))
    sk.add_line((20, 0), (20, 10))
    done = fix_sketch(sk)
    assert done == ["closed 1 opening(s) with a line"]
    assert len(sk.entities) == 4 and _area(sk) == pytest.approx(200.0)


def test_line_stopping_short_of_another_is_extended():
    sk = _sketch()
    sk.add_line((-8, 0), (20, 0))             # bottom runs past the left side
    sk.add_line((20, 0), (20, 10))
    sk.add_line((20, 10), (-4.6, 10))        # top stops 0.4 mm short of the left side
    sk.add_line((-5, 12), (-5, -3))           # left side, longer than the shape
    done = fix_sketch(sk)
    assert done == ["extended or trimmed 1 line end(s) to touch"]
    assert len(sk.profiles) == 1 and _area(sk) == pytest.approx(250.0, rel=1e-6)


def test_doubled_line_goes_and_a_closed_sketch_is_left_alone():
    sk = _sketch()
    sk.add_rect((0, 0), (10, 10))
    sk.add_line((0, 0), (10, 0))
    assert fix_sketch(sk) == ["removed 1 empty or doubled line(s)"]
    assert fix_sketch(sk) == [] and len(sk.profiles) == 1


def test_arc_with_a_line_closes_into_a_d():
    sk = _sketch()
    sk.add_arc((0, 0), (5, 5), (10, 0))
    sk.add_line((0.2, 0), (9.8, 0))           # just short at both ends
    fix_sketch(sk)
    assert len(sk.profiles) == 1 and sk.profiles[0].area > 30


def test_a_lone_line_is_not_turned_into_a_zero_face():
    sk = _sketch()
    sk.add_line((0, 0), (10, 0))
    assert fix_sketch(sk) == [] and not sk.profiles


def test_two_lines_meeting_at_a_corner_both_run_to_it():
    sk = _sketch()
    sk.add_line((0, 0), (19.7, 0))            # stops short of the corner
    sk.add_line((20, 0.4), (20, 10))          # starts above it
    sk.add_line((20, 10), (0, 10))
    sk.add_line((0, 10), (0, 0))
    fix_sketch(sk)
    assert _area(sk) == pytest.approx(200.0, rel=1e-6)


def test_fix_sketch_button_is_one_undo_step():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow()
    sk = w.doc.start_sketch("XY")
    sk.add_line((0, 10), (0, 0))
    sk.add_line((0, 0), (20, 0))
    sk.add_line((20, 0), (20, 10))
    sk.solve_profiles()
    w.ribbon.command_buttons["fix_sketch"].click()
    assert len(sk.profiles) == 1 and "closed 1 opening" in w.status_label.text()
    w.doc.undo()
    assert len(w.doc.active_sketch.entities) == 3 and not w.doc.active_sketch.solve_profiles()
    w.close()
