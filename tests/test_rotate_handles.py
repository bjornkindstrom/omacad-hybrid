"""Björn #107/#111: curved arrows beside the selected body (X red, Y green, Z blue) turn it about its centre in 15°
steps, straight arrows slide it along an axis in whole millimetres; the release is one Move step."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.viewport.resize(900, 700)
    w.doc.add_box(40, 20, 10)
    return w


def test_handles_only_on_one_selected_body_outside_a_sketch(win):
    rh = win.viewport.rotate_handles
    assert rh.handles() == {}
    win.doc.selected_body_ids = list(win.doc.bodies)
    assert set(rh.handles()) == {"X", "Y", "Z", "MX", "MY", "MZ"}
    win.doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    assert rh.handles() == {}


def test_dragging_the_z_arrow_turns_the_body_in_steps_and_undo_takes_it_back(win):
    doc, vp = win.doc, win.viewport
    bid = next(iter(doc.bodies))
    doc.selected_body_ids = [bid]
    rh = vp.rotate_handles
    pos, tangent, _out = rh.handles()["Z"]
    assert rh.press(*pos)
    rh.move(*(pos + tangent * 120))
    angle = rh.drag["angle"]
    assert angle != 0 and angle % 15 == 0
    assert vp.display_override and bid in vp.display_override        # live preview of the turned body
    assert rh.release()
    assert not vp.display_override
    move = doc.timeline.features[-1]
    assert move.feature_type == "move" and (move.rx, move.ry, move.rz) == (0, 0, angle) and move.pivot == "center"
    lo, hi = np.array(doc.bodies[bid].manifold.bounding_box()).reshape(2, 3)
    a = np.radians(angle)
    assert hi[0] - lo[0] == pytest.approx(40 * abs(np.cos(a)) + 20 * abs(np.sin(a)), abs=1e-6)
    assert (lo + hi)[:2] / 2 == pytest.approx([20, 10], abs=1e-6)     # about its own centre
    assert doc.selected_body_ids == [bid]
    doc.undo()
    assert [f.feature_type for f in doc.timeline.features] == ["box"]


def test_escape_cancels_a_turn(win):
    doc, vp = win.doc, win.viewport
    doc.selected_body_ids = list(doc.bodies)
    rh = vp.rotate_handles
    pos, tangent, _out = rh.handles()["X"]
    rh.press(*pos)
    rh.move(*(pos + tangent * 120))
    assert rh.cancel() and not vp.display_override
    assert not rh.release()
    assert [f.feature_type for f in doc.timeline.features] == ["box"]


@pytest.mark.parametrize("handle, axis", [("MX", 0), ("MY", 1), ("MZ", 2)])
def test_dragging_a_straight_arrow_slides_the_body_along_its_axis(win, handle, axis):
    doc, vp = win.doc, win.viewport
    bid = next(iter(doc.bodies))
    doc.selected_body_ids = [bid]
    before = np.array(doc.bodies[bid].manifold.bounding_box())
    rh = vp.rotate_handles
    pos, along, _ = rh.handles()[handle]
    centre = before.reshape(2, 3).mean(axis=0)
    ends = vp.project_points(np.array([centre, centre + np.eye(3)[axis]]))[0]
    outwards = np.sign(np.dot(ends[1] - ends[0], along))                 # dragging along the arrow: + or - axis
    assert rh.press(*pos)
    rh.move(*(pos + along * 80))
    dist = rh.drag["dist"]
    assert dist != 0 and np.sign(dist) == outwards and dist == int(dist)   # whole millimetres
    assert vp.display_override and bid in vp.display_override
    assert rh.release()
    move = doc.timeline.features[-1]
    shift = [move.dx, move.dy, move.dz]
    assert shift[axis] == dist and sum(abs(v) for v in shift) == abs(dist)
    assert (move.rx, move.ry, move.rz) == (0, 0, 0)
    after = np.array(doc.bodies[bid].manifold.bounding_box())
    expected = before.copy()
    expected[[axis, axis + 3]] += dist
    assert after == pytest.approx(expected, abs=1e-6)
    doc.undo()
    assert np.array(doc.bodies[bid].manifold.bounding_box()) == pytest.approx(before)


def test_sliding_onto_a_face_of_another_body_lines_them_up(win):
    """Björn: start moving, point at a face of another body, and they line up along that axis."""
    doc, vp = win.doc, win.viewport
    bid = next(iter(doc.bodies))                       # 40 x 20 x 10
    doc.add_box(20, 20, 30)
    other = next(b for b in doc.bodies if b != bid)
    doc.move_body(other, dx=60)
    doc.selected_body_ids = [bid]
    rh = vp.rotate_handles
    pos, along, _ = rh.handles()["MZ"]
    assert rh.press(*pos)
    top = vp.world_to_screen(np.array([70.0, 10.0, 30.0]))      # on the tall box's top face
    rh.move(*top)
    assert rh.drag["snap"] is not None and rh.drag["dist"] in (20.0, 30.0)   # top or bottom flush with z = 30
    side = vp.world_to_screen(np.array([60.0, 10.0, 15.0]))      # a side face: along the drag, so no lining up
    rh.move(*side)
    assert rh.drag["snap"] is None and rh.drag["dist"] == int(rh.drag["dist"])
    rh.move(*top)
    dist = rh.drag["dist"]
    rh.release()
    lo, hi = np.array(doc.bodies[bid].manifold.bounding_box()).reshape(2, 3)
    assert 30.0 in (pytest.approx(lo[2]), pytest.approx(hi[2])) and lo[2] == pytest.approx(dist)
