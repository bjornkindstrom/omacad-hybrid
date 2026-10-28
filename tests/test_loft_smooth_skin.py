"""Report 20261024-065108: a loft from a rectangle to a circle showed ~110 small faces. Resampling to 128 points cut
the rectangle's corners off, and one quad per step between a straight side and the turning arc folded along its
diagonal (up to 39 degrees), so every strip was a face of its own."""
import os

import numpy as np
import trimesh

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import compute_planar_faces

DATA = os.path.join(os.path.dirname(__file__), "data", "loft_square_to_circle.omacad")


def test_rectangle_to_circle_loft_is_one_smooth_skin():
    doc = Exporter.load_project(DATA)
    m = next(b for b in doc.bodies.values() if b.name == "Loft 1").manifold
    v = np.asarray(m.to_mesh().vert_properties[:, :3])
    assert np.allclose(v[:, :2].min(axis=0), [-75, -40]) and np.allclose(v[:, :2].max(axis=0), [75, 100])
    bottom = v[np.abs(v[:, 2]) < 1e-6][:, :2]
    for corner in ([-75, -40], [75, -40], [75, 100], [-75, 100]):    # the rectangle keeps its corners
        assert np.linalg.norm(bottom - corner, axis=1).min() < 1e-4
    assert len(compute_planar_faces(m)) <= 6                     # bottom, top and the skin, not a face per strip
    tm = trimesh.Trimesh(v, m.to_mesh().tri_verts, process=False)
    ends = np.abs(np.diff(v[tm.face_adjacency_edges][:, :, 2], axis=1)).ravel() < 1e-6
    folds = np.degrees(tm.face_adjacency_angles[~ends])
    assert np.sum(folds > 10.0) <= 48                            # only the four corner creases near the bottom (was 232)


def test_rectangle_to_smaller_rectangle_loft_is_an_exact_frustum():
    doc = Document()
    a = doc.start_sketch("XY")
    a.add_rect((-15, -10), (15, 10))                           # perimeter 100: 128 even points miss the corners
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 10.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_rect((-7.5, -5), (7.5, 5))
    doc.finish_sketch()
    doc.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)])
    m = next(iter(doc.bodies.values())).manifold
    assert abs(m.volume() - 10 / 3 * (600 + 150 + 300)) < 1e-3


def test_curved_skin_hides_the_bottom_face_from_hover():
    """Only planar faces are pickable faces, so a ray through the curved skin used to light up the bottom behind it."""
    from types import SimpleNamespace
    from omacad.ui.viewport.viewport import Viewport3D

    doc = Exporter.load_project(DATA)
    for b in doc.bodies.values():
        b.visible = b.name == "Loft 1"
    vp = SimpleNamespace(doc=doc, _ray_hits_body_aabb=Viewport3D._ray_hits_body_aabb)
    origin, down = np.array([0.0, 30.0, 200.0]), np.array([0.0, 0.0, -1.0])
    assert not Viewport3D._surface_in_front(vp, origin, down, 150.0)      # the top face is the first surface
    side = np.array([0.0, -200.0, 5.0])                                   # through the skin onto the inside
    assert Viewport3D._surface_in_front(vp, side, np.array([0.0, 1.0, 0.0]), 250.0)
