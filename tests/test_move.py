"""Move feature modeling, point-to-point, face-to-face, body copying and object history tests."""
from pathlib import Path
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.geometry import euler_xyz_matrix, face_centroid, face_to_face_values

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Move Copy Own Steps (Björn #108)
# ==============================================================================

DOC_COPY = DATA_DIR / "move_copy_own_steps.omacad"


def _box(body):
    return [round(v, 3) for v in body.manifold.bounding_box()]


def test_copy_rebuilds_the_whole_object_and_edits_stay_on_the_copy():
    doc = Exporter.load_project(str(DOC_COPY))
    volume = doc.bodies["body_extrude_2"].manifold.volume()
    move = doc.move_body("body_extrude_2", dx=49, copy_body=True)
    copy_id = move.target_body_id
    assert set(doc.bodies) == {"body_extrude_2", copy_id}
    assert doc.bodies[copy_id].manifold.volume() == pytest.approx(volume, rel=1e-6)
    assert _box(doc.bodies[copy_id]) == [49, 0, 0, 84, 56, 20]

    history = doc.object_history
    owner = history.owners[move.feature_id]
    steps = [doc.timeline.features[history.index(doc, f)] for f in history.objects[owner].feature_ids]
    assert [f.feature_type for f in steps] == ["sketch", "extrude", "fillet", "fillet", "sketch", "extrude", "fillet", "move"]
    assert history.owners["extrude_2"] != owner

    extrude = next(f for f in steps if f.feature_type == "extrude")
    doc.edit_feature_dimension(extrude.feature_id, "distance", "30")
    assert _box(doc.bodies[copy_id])[5] == pytest.approx(30)
    assert _box(doc.bodies["body_extrude_2"]) == [0, 0, 0, 35, 56, 20]
    assert doc.bodies["body_extrude_2"].manifold.volume() == pytest.approx(volume, rel=1e-6)

    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert _box(restored.bodies[copy_id])[5] == pytest.approx(30)

    doc.undo()
    doc.undo()
    assert set(doc.bodies) == {"body_extrude_2"}
    assert len(doc.timeline.features) == 7


def test_a_sketch_of_the_copy_is_its_own():
    doc = Exporter.load_project(str(DOC_COPY))
    move = doc.move_body("body_extrude_2", dx=49, copy_body=True)
    sketches = [f.sketch.sketch_id for f in doc.timeline.features if f.feature_type == "sketch"]
    assert len(set(sketches)) == 4
    copy_extrude = next(f for f in doc.timeline.features if f"body_{f.feature_id}" == move.target_body_id)
    assert copy_extrude.sketch_id not in ("sketch_1", "sketch_2")
    doc.sketches[copy_extrude.sketch_id].entities.clear()
    assert doc.sketches["sketch_1"].entities


# ==============================================================================
# Face to Face Move Geometry
# ==============================================================================

def _f2f_scene():
    doc = Document()
    doc.add_box(20, 20, 10)
    a = next(iter(doc.bodies))
    doc.add_box(6, 6, 4)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=40, dy=7, dz=3, rx=25, ry=-15, rz=70)
    return doc, a, b


def _f2f_face(doc, bid, normal):
    faces = doc.bodies[bid].faces
    score = lambda f: float(np.dot(f.normal, normal))
    return max(faces, key=score)


def _f2f_centre(doc, bid):
    b = doc.bodies[bid]
    return (np.asarray(b.render_mesh.bounds_min, float) + np.asarray(b.render_mesh.bounds_max, float)) * 0.5


def _f2f_apply(doc, a, b, mode, centre_on):
    src = _f2f_face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _f2f_face(doc, a, np.array([0.0, 0.0, 1.0]))
    vals = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst), _f2f_centre(doc, b),
                               True, mode, centre_on)
    doc.move_body(b, *vals, pivot="center")
    return src, dst


def test_touch_puts_the_face_on_the_target_face_centred():
    doc, a, b = _f2f_scene()
    src, dst = _f2f_apply(doc, a, b, "touch", True)
    f = _f2f_face(doc, b, np.array([0.0, 0.0, -1.0]))
    assert np.allclose(f.normal, [0, 0, -1], atol=1e-4)
    assert np.allclose(face_centroid(f), face_centroid(dst), atol=1e-3)
    overlap = (doc.bodies[a].manifold ^ doc.bodies[b].manifold).volume()
    assert overlap < 1e-4


_TARGET = [None]


def _moved_face_match(doc, bid, src):
    return min((g for g in doc.bodies[bid].faces if abs(g.area - src.area) < 1e-3 * src.area),
               key=lambda g: np.linalg.norm(face_centroid(g) - _TARGET[0]))


def test_flush_turns_the_face_to_look_the_same_way():
    doc, a, b = _f2f_scene()
    src = _f2f_face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _f2f_face(doc, a, np.array([0.0, 0.0, 1.0]))
    _TARGET[0] = face_centroid(dst)
    vals = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst), _f2f_centre(doc, b),
                               True, "flush", True)
    doc.move_body(b, *vals, pivot="center")
    f = _moved_face_match(doc, b, src)
    assert np.allclose(face_centroid(f), face_centroid(dst), atol=1e-3)
    assert np.allclose(f.normal, dst.normal, atol=1e-4)


def test_not_centred_only_moves_along_the_normal():
    doc, a, b = _f2f_scene()
    before = _f2f_centre(doc, b)
    src = _f2f_face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _f2f_face(doc, a, np.array([0.0, 0.0, 1.0]))
    dx, dy, dz, rx, ry, rz = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst),
                                                 before, True, "touch", False)
    assert np.allclose(np.cross([dx, dy, dz], dst.normal), 0.0, atol=1e-9)


def test_slide_does_not_turn():
    doc, a, b = _f2f_scene()
    src = _f2f_face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _f2f_face(doc, a, np.array([0.0, 0.0, 1.0]))
    v = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst), _f2f_centre(doc, b), True, "slide", True)
    assert np.allclose(v[3:], 0.0)


# ==============================================================================
# Point to Point Move
# ==============================================================================

def _bounds(body):
    bb = body.manifold.bounding_box()
    return np.array(bb[:3]), np.array(bb[3:])


def _p2p_scene():
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
    d, sk, block_id, box_id = _p2p_scene()
    frm = {"body": block_id, "kind": "corner", "xyz": [30.0, 20.0, 10.0]}
    to = {"body": box_id, "kind": "end", "xyz": [50.0, 40.0, 0.0]}
    d.move_body(block_id, from_point=frm, to_point=to)
    lo, hi = _bounds(d.bodies[block_id])
    assert hi == pytest.approx((50, 40, 0), abs=1e-3)
    assert lo == pytest.approx((20, 20, -10), abs=1e-3)

    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 40)
    lo, hi = _bounds(d.bodies[block_id])
    assert hi == pytest.approx((50, 40, 0), abs=1e-3)
    assert lo == pytest.approx((10, 20, -10), abs=1e-3)


def test_rotation_about_a_picked_point_keeps_that_point_still():
    d = Document()
    d.add_box(10, 10, 10)
    bid = next(iter(d.bodies))
    d.move_body(bid, rz=90, pivot="point", from_point={"body": bid, "kind": "end", "xyz": [10.0, 0.0, 0.0]})
    lo, hi = _bounds(d.bodies[bid])
    assert lo == pytest.approx((0, -10, 0), abs=1e-3)
    assert hi == pytest.approx((10, 0, 10), abs=1e-3)


def test_rotate_and_carry_point_to_point_with_an_extra_offset():
    d, _, block_id, box_id = _p2p_scene()
    frm = {"body": block_id, "kind": "end", "xyz": [4.0, 0.0, 0.0]}
    to = {"body": None, "kind": "fixed", "xyz": [100.0, 0.0, 0.0]}
    d.move_body(block_id, dz=5, rz=30, pivot="center", from_point=frm, to_point=to)
    body = d.bodies[block_id]
    vol_before = 30 * 20 * 10 - (4 - np.pi) * 16 * 10
    assert body.manifold.volume() == pytest.approx(vol_before, rel=2e-3)
    centre = np.array([15.0, 10.0, 5.0])
    moved = centre + euler_xyz_matrix(0, 0, 30) @ (np.array([4.0, 0, 0]) - centre)
    expected_shift = np.array([100.0, 0, 5]) - moved
    lo, _ = _bounds(body)
    corners = np.array([[x, y, z] for x in (0, 30) for y in (0, 20) for z in (0, 10)], dtype=float)
    turned = (centre + (corners - centre) @ euler_xyz_matrix(0, 0, 30).T) + expected_shift
    assert lo[2] == pytest.approx(turned[:, 2].min(), abs=1e-3)


def test_points_survive_save_and_load():
    d, _, block_id, box_id = _p2p_scene()
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
    copy_id = feat.target_body_id
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


# ==============================================================================
# Move to New Object (Object History) (#103)
# ==============================================================================

DOC_OBJECT = DATA_DIR / "project_shelled_rim.omacad"


def _fid(doc, name):
    return next(f.feature_id for f in doc.timeline.features if f.name == name)


def test_sketch_on_the_rim_moves_to_its_own_object_and_back_with_undo():
    doc = Exporter.load_project(str(DOC_OBJECT))
    h = doc.object_history
    h.sync(doc)
    box = h.owners[_fid(doc, "Shell 1")]
    sk3 = _fid(doc, "Sketch 3")
    assert h.owners[sk3] == box
    volume = sum(b.manifold.volume() for b in doc.bodies.values())
    new = doc.move_to_new_object(sk3)
    h.sync(doc)
    assert h.owners[sk3] == new and h.objects[new].name == "Sketch 3"
    assert sk3 not in h.objects[box].feature_ids and _fid(doc, "Sketch 2") in h.objects[box].feature_ids
    assert sum(b.manifold.volume() for b in doc.bodies.values()) == pytest.approx(volume)
    again = Document()
    Exporter.apply_dict(again, Exporter.document_to_dict(doc))
    again.object_history.sync(again)
    assert again.object_history.owners[sk3] == new
    doc.undo()
    doc.object_history.sync(doc)
    assert doc.object_history.owners[sk3] == box


def test_lid_plate_keeps_its_object_and_a_lone_step_cannot_move():
    doc = Exporter.load_project(str(DOC_OBJECT))
    sk3 = _fid(doc, "Sketch 3")
    sk = doc.sketches["sketch_3"]
    big = max(range(len(sk.profiles)), key=lambda i: sk.profiles[i].area)
    doc.extrude_profile("sketch_3", big, 3.0, operation="new_body")
    ext = doc.timeline.features[-1].feature_id
    h = doc.object_history
    h.sync(doc)
    lid = h.owners[ext]
    assert lid != h.owners[sk3]
    bodies = set(doc.bodies)
    new = doc.move_to_new_object(sk3)
    h.sync(doc)
    assert h.owners[ext] == lid and set(doc.bodies) == bodies
    with pytest.raises(ValueError):
        doc.move_to_new_object(sk3)
