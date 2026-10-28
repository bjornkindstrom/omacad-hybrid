"""Lay a face on a plane: the body turns and moves so that face rests on the plane."""
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.geometry import euler_xyz_degrees, rotation_aligning


def faces_of(doc):
    doc.timeline.recompute(doc)
    return next(iter(doc.bodies.values())).faces


def test_euler_matches_manifold_rotate():
    import manifold3d as m3d
    rng = np.random.default_rng(1)
    for _ in range(20):
        a, b = rng.normal(size=3), rng.normal(size=3)
        R = rotation_aligning(a, b)
        box = m3d.Manifold.cube((3, 5, 7))
        got = box.rotate(list(euler_xyz_degrees(R))).to_mesh().vert_properties[:, :3]
        want = box.to_mesh().vert_properties[:, :3] @ R.T
        assert np.allclose(np.sort(got, axis=0), np.sort(want, axis=0), atol=1e-4)


@pytest.mark.parametrize("pick", range(6))
def test_each_face_ends_up_on_the_ground(pick):
    doc = Document()
    doc.add_box(10, 20, 30)
    doc.move_body(next(iter(doc.bodies)), 5, 6, 7, 20, 35, 50)   # start tilted
    faces = sorted(faces_of(doc), key=lambda f: (round(f.area, 3), tuple(np.round(f.normal, 3))))
    face = faces[pick]
    bid = face.body_id
    doc.lay_face_on(bid, face.normal, face.origin, (0, 0, 0), (0, 0, 1))
    doc.timeline.recompute(doc)
    mesh = doc.bodies[bid].render_mesh
    v = mesh.vertices
    assert v[:, 2].min() == pytest.approx(0.0, abs=1e-4)
    bottom = [f for f in doc.bodies[bid].faces if np.allclose(f.normal, (0, 0, -1), atol=1e-4) and abs(f.origin[2]) < 1e-4]
    assert bottom and bottom[0].area == pytest.approx(face.area, rel=1e-4)
    assert doc.undo_label() == "Lay flat"
