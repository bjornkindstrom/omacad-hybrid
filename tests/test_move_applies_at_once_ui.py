"""Move: every drag of the arrows (and every finished pick) becomes a real step at once, so the next move starts from
where the body is now and everything after rebuilds; no OK between moves. Esc keeps the applied moves (each is one
undo step) and drops only what was not applied yet."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(10, 10, 10)
    return w


def _min_x(win):
    return next(iter(win.doc.bodies.values())).manifold.bounding_box()[0]


def _moves(win):
    return [f for f in win.doc.timeline.features if f.feature_type == "move"]


def _drag(win, axis, delta):
    win.viewport.move_gizmo_dragged.emit(axis, delta)
    win.viewport.move_gizmo_finished.emit()
    QApplication.processEvents()


def test_two_drags_without_ok_are_two_applied_moves(win):
    win.prompt_move_body()
    dlg = win.inspector.current_tool_dlg
    _drag(win, "X", 10.0)
    assert len(_moves(win)) == 1 and _min_x(win) == pytest.approx(10.0)
    assert dlg.spn_dx.value() == 0.0 and win.inspector.current_tool_dlg is dlg     # panel stays, ready for more
    _drag(win, "X", 5.0)
    assert len(_moves(win)) == 2 and _min_x(win) == pytest.approx(15.0)
    dlg.accept()
    assert len(_moves(win)) == 2                                                    # OK adds no empty step
    win.doc.undo()
    assert _min_x(win) == pytest.approx(10.0)


def test_escape_keeps_applied_moves_and_drops_the_pending_one(win):
    win.prompt_move_body()
    dlg = win.inspector.current_tool_dlg
    _drag(win, "X", 10.0)
    dlg.spn_dy.setValue(7.0)                     # typed, not applied yet
    dlg.reject()
    assert len(_moves(win)) == 1 and _min_x(win) == pytest.approx(10.0)
    assert next(iter(win.doc.bodies.values())).manifold.bounding_box()[1] == pytest.approx(0.0)


def test_starting_a_pick_applies_the_typed_move_first(win):
    win.prompt_move_body()
    dlg = win.inspector.current_tool_dlg
    dlg.spn_dx.setValue(20.0)
    dlg.btn_points.setChecked(True)              # point to point picks on the body where it is now
    assert len(_moves(win)) == 1 and _min_x(win) == pytest.approx(20.0)
    dlg.btn_points.setChecked(False)
    dlg.reject()
