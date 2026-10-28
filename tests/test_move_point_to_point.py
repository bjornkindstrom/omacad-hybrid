"""Move a body point to point (from a snap point on it to a point on another body) and rotate about a picked point.
The picked points are stored with the step and found again after a rebuild, so the move follows size changes."""
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.geometry import euler_xyz_matrix


def _bounds(body):
    bb = body.manifold.bounding_box()
    return np.array(bb[:3]), np.array(bb[3:])


def _scene():
    """A rounded block 30 x 20 x 10 at the origin and a 10 mm box moved off to (50, 40, 0)."""
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (30, 20), 4)
    d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 10)
    block_id = next(iter(d.bodies))
    d.add_box(10, 10, 10)
    box_id = next(b for b in d.bodies if b != block_id)
    d.move_body(box_id, 50, 40, 0, pivot="origin")
    return d, sk, block_id, box_id


def test_hidden_corner_lands_on_a_corner_of_the_other_body_and_follows_a_wider_block():
    d, sk, block_id, box_id = _scene()
    frm = {"body": block_id, "kind": "corner", "xyz": [30.0, 20.0, 10.0]}
    to = {"body": box_id, "kind": "end", "xyz": [50.0, 40.0, 0.0]}
    d.move_body(block_id, from_point=frm, to_point=to)
    lo, hi = _bounds(d.bodies[block_id])
    assert hi == pytest.approx((50, 40, 0), abs=1e-3)       # the block's top back corner sits on the box corner
    assert lo == pytest.approx((20, 20, -10), abs=1e-3)

    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 40)
    lo, hi = _bounds(d.bodies[block_id])
    assert hi == pytest.approx((50, 40, 0), abs=1e-3)       # the corner moved with the size, the move followed it
    assert lo == pytest.approx((10, 20, -10), abs=1e-3)


def test_rotation_about_a_picked_point_keeps_that_point_still():
    d = Document()
    d.add_box(10, 10, 10)
    bid = next(iter(d.bodies))
    d.move_body(bid, rz=90, pivot="point", from_point={"body": bid, "kind": "end", "xyz": [10.0, 0.0, 0.0]})
    lo, hi = _bounds(d.bodies[bid])
    assert lo == pytest.approx((0, -10, 0), abs=1e-3)       # a quarter turn counter-clockwise about the corner (10, 0):
    assert hi == pytest.approx((10, 0, 10), abs=1e-3)       # that corner stays where it was


def test_rotate_and_carry_point_to_point_with_an_extra_offset():
    d, _, block_id, box_id = _scene()
    frm = {"body": block_id, "kind": "end", "xyz": [4.0, 0.0, 0.0]}
    to = {"body": None, "kind": "fixed", "xyz": [100.0, 0.0, 0.0]}
    d.move_body(block_id, dz=5, rz=30, pivot="center", from_point=frm, to_point=to)
    body = d.bodies[block_id]
    vol_before = 30 * 20 * 10 - (4 - np.pi) * 16 * 10
    assert body.manifold.volume() == pytest.approx(vol_before, rel=2e-3)
    # the tangent point (4, 0, 0) is now at (100, 0, 5): check against the rotated original block
    centre = np.array([15.0, 10.0, 5.0])
    moved = centre + euler_xyz_matrix(0, 0, 30) @ (np.array([4.0, 0, 0]) - centre)
    expected_shift = np.array([100.0, 0, 5]) - moved
    lo, _ = _bounds(body)
    corners = np.array([[x, y, z] for x in (0, 30) for y in (0, 20) for z in (0, 10)], dtype=float)
    turned = (centre + (corners - centre) @ euler_xyz_matrix(0, 0, 30).T) + expected_shift
    # the rounded block lies inside the turned box of its sharp corners; its lowest z is exact
    assert lo[2] == pytest.approx(turned[:, 2].min(), abs=1e-3)


def test_points_survive_save_and_load():
    d, _, block_id, box_id = _scene()
    frm = {"body": block_id, "kind": "corner", "xyz": [30.0, 20.0, 10.0]}
    to = {"body": box_id, "kind": "end", "xyz": [50.0, 40.0, 0.0]}
    d.move_body(block_id, from_point=frm, to_point=to)
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(d))
    lo, hi = _bounds(loaded.bodies[block_id])
    assert hi == pytest.approx((50, 40, 0), abs=1e-3)
    move = [f for f in loaded.timeline.features if f.feature_type == "move"][-1]
    assert move.from_point == frm and move.to_point == to


def test_move_activate_copy_preserves_source_and_replays_copy():
    d = Document()
    d.add_box(10, 8, 6)
    source_id = next(iter(d.bodies))
    source_volume = d.bodies[source_id].manifold.volume()
    feat = d.move_body(source_id, dx=25, rz=90, copy_body=True)
    copy_id = feat.target_body_id   # the copy has its own Box step, then a plain move (#108)
    assert not feat.copy_body and copy_id != source_id
    assert set(d.bodies) == {source_id, copy_id}
    assert d.bodies[source_id].manifold.volume() == pytest.approx(source_volume)
    assert d.bodies[copy_id].manifold.volume() == pytest.approx(source_volume)
    assert d.bodies[copy_id].manifold.bounding_box()[0] > 20
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(d))
    assert set(restored.bodies) == {source_id, copy_id}
    assert restored.bodies[source_id].manifold.volume() == pytest.approx(source_volume)
    assert restored.bodies[copy_id].manifold.volume() == pytest.approx(source_volume)
    d.undo()
    assert set(d.bodies) == {source_id}
