"""Offset Face: flat faces move along their normal, full cylinders (holes, pins) change radius. Exact volumes."""
import math

import manifold3d as m3d
import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import compute_planar_faces
from omacad.model.features.offset_face import OffsetFaceFeature, plane_face_ref
from omacad.model import quality


def _top(m):
    return max(compute_planar_faces(m), key=lambda f: f.normal[2] + 1e-6 * f.origin[2])


def test_push_top_face_out_and_in():
    box = m3d.Manifold.cube((20, 10, 5))
    ref = plane_face_ref(_top(box))
    up, skipped = OffsetFaceFeature.compute(box, [ref], 2.0)
    assert skipped == 0 and abs(up.volume() - 20 * 10 * 7) < 1e-6
    down, skipped = OffsetFaceFeature.compute(box, [ref], -1.5)
    assert skipped == 0 and abs(down.volume() - 20 * 10 * 3.5) < 1e-6


def test_side_face_of_l_shape_moves_only_that_face():
    l_shape = m3d.Manifold.cube((20, 10, 5)) + m3d.Manifold.cube((5, 10, 15))   # a wall on one end
    side = next(f for f in compute_planar_faces(l_shape) if f.normal[0] > 0.99 and abs(f.origin[0] - 5) < 1e-6)   # wall side, z 5..15
    out, skipped = OffsetFaceFeature.compute(l_shape, [plane_face_ref(side)], -1.0)
    assert skipped == 0 and abs(out.volume() - (l_shape.volume() - 1.0 * 10 * 10)) < 1e-6


def test_slanted_neighbour_is_not_overshot():
    """Growing the top of a wedge must not stick out past the slanted side (convex edge)."""
    wedge = m3d.Manifold.extrude(m3d.CrossSection([[(0, 0), (10, 0), (6, 10), (4, 10)]]), 5.0)
    top = max(compute_planar_faces(wedge), key=lambda f: f.origin[2] if abs(f.normal[1]) > 0.99 else -1e9)
    out, skipped = OffsetFaceFeature.compute(wedge, [plane_face_ref(top)], 1.0)
    assert skipped == 0 and out.volume() > wedge.volume()
    bb = out.bounding_box()
    assert bb[4] <= 11.0 + 1e-6


def _tube(r_outer, r_inner, h):
    n = quality.circle_segments()
    return m3d.Manifold.cylinder(h, r_outer, r_outer, n) - m3d.Manifold.cylinder(h, r_inner, r_inner, n)


def test_hole_and_pin_radius_offsets_follow_polygon_area():
    n = quality.circle_segments()
    area = lambda r: 0.5 * n * r * r * math.sin(2 * math.pi / n)
    tube = _tube(10, 4, 8)
    hole = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 4.0, "length": 8.0, "internal": True}
    smaller, skipped = OffsetFaceFeature.compute(tube, [hole], 0.3)    # + = material added, hole shrinks to 3.7
    assert skipped == 0
    assert abs(smaller.volume() - (area(10) - area(3.7)) * 8) < 1e-4
    pin = dict(hole, radius=10.0, internal=False)
    thinner, skipped = OffsetFaceFeature.compute(tube, [pin], -0.5)    # pin shrinks to 9.5
    assert skipped == 0
    assert abs(thinner.volume() - (area(9.5) - area(4)) * 8) < 1e-4


def test_document_feature_roundtrip_and_undo(tmp_path):
    doc = Document()
    doc.add_box(20, 10, 5)
    body = next(iter(doc.bodies.values()))
    v0 = body.manifold.volume()
    feat = doc.add_offset_face(body.body_id, [plane_face_ref(_top(body.manifold))], 1.0)
    assert feat is not None and abs(next(iter(doc.bodies.values())).manifold.volume() - v0 - 200.0) < 1e-6
    path = str(tmp_path / "o.omacad")
    Exporter.save_project(doc, path)
    again = Exporter.load_project(path)
    assert abs(next(iter(again.bodies.values())).manifold.volume() - v0 - 200.0) < 1e-6
    doc.undo()
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - v0) < 1e-6


def test_curved_surface_offset_moves_a_sphere_and_a_flat_patch():
    from omacad.model.features.offset_face import surface_face_ref
    sphere = m3d.Manifold.sphere(10.0, 64)
    v0 = sphere.volume()
    pick = {"point": [0.0, 0.0, 10.0], "normal": [0.0, 0.0, 1.0]}
    out, skipped = OffsetFaceFeature.compute(sphere, [surface_face_ref(pick)], 0.5)
    assert skipped == 0 and abs(out.volume() / v0 - (10.5 / 10.0) ** 3) < 0.02
    box = m3d.Manifold.cube((20, 10, 5))        # a flat patch: its vertices move along its normal, walls stretch
    top = {"point": [10.0, 5.0, 5.0], "normal": [0.0, 0.0, 1.0]}
    up, skipped = OffsetFaceFeature.compute(box, [surface_face_ref(top)], 1.0)
    assert skipped == 0 and abs(up.volume() - 20 * 10 * 6) < 1e-3


def test_same_patch_clicked_twice_moves_once():
    from omacad.model.features.offset_face import surface_face_ref
    box = m3d.Manifold.cube((20, 10, 5))
    refs = [surface_face_ref({"point": [5.0, 5.0, 5.0], "normal": [0, 0, 1]}),
            surface_face_ref({"point": [15.0, 3.0, 5.0], "normal": [0, 0, 1]})]
    out, _ = OffsetFaceFeature.compute(box, refs, 1.0)
    assert abs(out.volume() - 20 * 10 * 6) < 1e-3


def test_thread_tolerance_grows_and_shrinks_the_coil():
    from omacad.model.features.offset_face import surface_face_ref
    from omacad.model.kernel import CadKernel
    bolt = CadKernel.create_thread(10.0, 2.0, 12.0, False, 0.0, "round")
    v = np.asarray(bolt.to_mesh().vert_properties)[:, :3]
    p = v[int(np.hypot(v[:, 0], v[:, 1]).argmax())]               # a point on the outer thread
    ref = surface_face_ref({"point": p, "normal": [p[0], p[1], 0.0] / np.hypot(p[0], p[1])})
    more, s1 = OffsetFaceFeature.compute(bolt, [ref], 0.2)
    less, s2 = OffsetFaceFeature.compute(bolt, [ref], -0.2)
    assert s1 == s2 == 0 and str(more.status()) == str(less.status()) == "Error.NoError"
    assert more.volume() > bolt.volume() + 20 > bolt.volume() - 20 > less.volume()
