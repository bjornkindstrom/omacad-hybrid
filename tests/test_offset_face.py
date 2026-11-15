"""Offset Face: flat faces move along their normal, full cylinders (holes, pins) change radius. Exact volumes."""
import math
from pathlib import Path

import manifold3d as m3d
import numpy as np
import pytest

import omacad.model.features.offset_face as of
from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import compute_planar_faces
from omacad.model.faces_hit_tests import detect_cylinder_surface
from omacad.model.features.offset_face import (
    OffsetFaceFeature,
    cylinder_face_ref,
    plane_face_ref,
    surface_face_ref,
)
from omacad.model.features.thread import ThreadFeature
from omacad.model import quality

DATA_DIR = Path(__file__).parent / "data"
REPORT_PROJECT = Path(__file__).parent.parent / ".state" / "data" / "feedback" / "20261115-082920" / "document.omacad"
THREAD_DOC = str(DATA_DIR / "offset_face_coil_stuck.omacad")
LID, JAR = "body_cylinder_1", "body_split_2"


def _top(m):
    return max(compute_planar_faces(m), key=lambda f: f.normal[2] + 1e-6 * f.origin[2])


def _tube(r_outer, r_inner, h):
    n = quality.circle_segments()
    return m3d.Manifold.cylinder(h, r_outer, r_outer, n) - m3d.Manifold.cylinder(h, r_inner, r_inner, n)


def _thread_doc(path=THREAD_DOC):
    doc = Exporter.load_project(path)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    return doc, last


def _gap_in_thread(doc) -> float:
    """Smallest distance between lid and jar inside the threaded zone (z 10..20; the lid rests on the floor and rim)."""
    lid = doc.bodies[LID].manifold.trim_by_plane((0, 0, -1), -19.7).trim_by_plane((0, 0, 1), 10.3)
    return doc.bodies[JAR].manifold.min_gap(lid, 1.0)


# =========================================================================
# Planar faces
# =========================================================================

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


# =========================================================================
# Cylindrical faces (holes, pins, thin walls)
# =========================================================================

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


def test_cylinder_offset_leaves_one_clean_body():
    """Offset on cylinder outer wall leaves no slivers."""
    doc = Exporter.load_project(str(DATA_DIR / "offset_face_cylinder_slivers.omacad"))
    top = doc.bodies["body_cylinder_1"].manifold      # the upper part after the split, 19 mm radius after the offset
    assert len(top.decompose()) == 1                  # no hair-thin pieces left of the old wall
    n = 96
    area = 0.5 * n * 19.0 ** 2 * math.sin(2 * math.pi / n)
    assert abs(top.volume() - area * 10.0) / (area * 10.0) < 1e-3


def test_inward_cylinder_offset_thickens_thin_wall():
    """Inward offset face on thin-walled cup thickens wall cleanly without ballooning outer diameter."""
    doc = Exporter.load_project(str(REPORT_PROJECT))
    b3 = doc.bodies["body_cylinder_3"]
    mesh = b3.render_mesh
    for i in range(len(mesh.vertices) // 3):
        cyl = detect_cylinder_surface(mesh, i)
        if cyl and cyl["is_internal"]:
            break
    ref = cylinder_face_ref(cyl)

    feat = doc.add_offset_face("body_cylinder_3", [ref], 0.5)
    assert feat.skipped == 0
    b3_after = doc.bodies["body_cylinder_3"]
    bb = b3_after.manifold.bounding_box()
    # Outer cylinder wall radius must remain 35.0 mm (not balloon to 36.7+ mm)
    assert abs(bb[0] - (-35.0)) < 0.05 and abs(bb[3] - 35.0) < 0.05
    assert abs(bb[1] - (-35.0)) < 0.05 and abs(bb[4] - 35.0) < 0.05
    assert abs(bb[2] - 0.0) < 0.05 and abs(bb[5] - 10.0) < 0.05

    polys = b3_after.manifold.slice(5.0).to_polygons()
    radii = [float(np.mean(np.hypot(p[:, 0], p[:, 1]))) for p in polys]
    assert any(abs(r - 35.0) < 0.05 for r in radii)
    assert any(abs(r - 33.5) < 0.05 for r in radii)


def test_outward_cylinder_offset_thins_wall():
    """Outward offset face on thin-walled cup thins wall without deleting/obliterating it."""
    doc = Exporter.load_project(str(REPORT_PROJECT))
    b3 = doc.bodies["body_cylinder_3"]
    mesh = b3.render_mesh
    for i in range(len(mesh.vertices) // 3):
        cyl = detect_cylinder_surface(mesh, i)
        if cyl and cyl["is_internal"]:
            break
    ref = cylinder_face_ref(cyl)

    feat = doc.add_offset_face("body_cylinder_3", [ref], -0.5)
    assert feat.skipped == 0
    b3_after = doc.bodies["body_cylinder_3"]
    bb = b3_after.manifold.bounding_box()
    assert abs(bb[0] - (-35.0)) < 0.05 and abs(bb[3] - 35.0) < 0.05
    assert abs(bb[5] - 10.0) < 0.05

    polys = b3_after.manifold.slice(5.0).to_polygons()
    radii = [float(np.mean(np.hypot(p[:, 0], p[:, 1]))) for p in polys]
    assert any(abs(r - 35.0) < 0.05 for r in radii)
    assert any(abs(r - 34.5) < 0.05 for r in radii)


# =========================================================================
# Curved and thread surfaces
# =========================================================================

def test_curved_surface_offset_moves_a_sphere_and_a_flat_patch():
    sphere = m3d.Manifold.sphere(10.0, 64)
    v0 = sphere.volume()
    pick = {"point": [0.0, 0.0, 10.0], "normal": [0.0, 0.0, 1.0]}
    out, skipped = OffsetFaceFeature.compute(sphere, [surface_face_ref(pick)], 0.5)
    assert skipped == 0 and abs(out.volume() / v0 - (10.5 / 10.0) ** 3) < 0.02
    box = m3d.Manifold.cube((20, 10, 5))
    top = {"point": [10.0, 5.0, 5.0], "normal": [0.0, 0.0, 1.0]}
    up, skipped = OffsetFaceFeature.compute(box, [surface_face_ref(top)], 1.0)
    assert skipped == 0 and abs(up.volume() - 20 * 10 * 6) < 1e-3


def test_same_patch_clicked_twice_moves_once():
    box = m3d.Manifold.cube((20, 10, 5))
    refs = [surface_face_ref({"point": [5.0, 5.0, 5.0], "normal": [0, 0, 1]}),
            surface_face_ref({"point": [15.0, 3.0, 5.0], "normal": [0, 0, 1]})]
    out, _ = OffsetFaceFeature.compute(box, refs, 1.0)
    assert abs(out.volume() - 20 * 10 * 6) < 1e-3


def test_thread_tolerance_grows_and_shrinks_the_coil():
    from omacad.model.kernel import CadKernel
    bolt = CadKernel.create_thread(10.0, 2.0, 12.0, False, 0.0, "round")
    v = np.asarray(bolt.to_mesh().vert_properties)[:, :3]
    p = v[int(np.hypot(v[:, 0], v[:, 1]).argmax())]
    ref = surface_face_ref({"point": p, "normal": [p[0], p[1], 0.0] / np.hypot(p[0], p[1])})
    more, s1 = OffsetFaceFeature.compute(bolt, [ref], 0.2)
    less, s2 = OffsetFaceFeature.compute(bolt, [ref], -0.2)
    assert s1 == s2 == 0 and str(more.status()) == str(less.status()) == "Error.NoError"
    assert more.volume() > bolt.volume() + 20 > bolt.volume() - 20 > less.volume()


def test_thread_flank_offset_folds_no_triangle():
    doc = Exporter.load_project(str(DATA_DIR / "offset_face_thread_folds.omacad"))
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    before = doc.bodies[last.target_body_id].manifold
    cap = {}
    orig = of.m3d.Mesh

    class Capture(orig):
        def __init__(self, **kw):
            cap.update(kw)
            super().__init__(**kw)

    of.m3d.Mesh = Capture
    try:
        after = of.offset_surfaces(before, last.faces, last.distance)
    finally:
        of.m3d.Mesh = orig
    assert after is not None and after.volume() < before.volume()
    mesh = before.to_mesh()
    t = np.asarray(mesh.tri_verts)
    v = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    n0 = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    w = np.asarray(cap["vert_properties"], dtype=np.float64)[:, :3]
    n1 = np.cross(w[t[:, 1]] - w[t[:, 0]], w[t[:, 2]] - w[t[:, 0]])
    real = np.linalg.norm(n0, axis=1) > 2e-4
    assert ((np.einsum("ij,ij->i", n0, n1) < 0) & real).sum() == 0


def test_micro_triangles_do_not_freeze_vertices():
    doc = Exporter.load_project(str(DATA_DIR / "offset_face_coil_stuck.omacad"))
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    before = doc.bodies[last.target_body_id].manifold
    cap = {}
    orig = of.m3d.Mesh

    class Capture(orig):
        def __init__(self, **kw):
            cap.update(kw)
            super().__init__(**kw)

    of.m3d.Mesh = Capture
    try:
        after = of.offset_surfaces(before, last.faces, last.distance)
    finally:
        of.m3d.Mesh = orig
    assert after is not None and after.volume() < before.volume()
    v = np.asarray(before.to_mesh().vert_properties, dtype=np.float64)[:, :3]
    w = np.asarray(cap["vert_properties"], dtype=np.float64)[:, :3]
    d = np.linalg.norm(w - v, axis=1)
    stuck = int(((d > 0) & (d < 1e-3)).sum())
    assert stuck < 20, stuck


def test_surface_of_the_coil_is_recognised_and_signed():
    doc, last = _thread_doc()
    thread, sign, shift = doc._thread_offset(last.faces)
    assert isinstance(thread, ThreadFeature) and sign == -1 and list(shift) == [0.0, 0.0, -10.0]


def test_minus_gives_the_jar_clearance_and_leaves_the_lid():
    doc, last = _thread_doc()
    lid0, jar0, grow0 = doc.bodies[LID].manifold.volume(), doc.bodies[JAR].manifold.volume(), doc.timeline.features[4].grow
    assert _gap_in_thread(doc) < 1e-6
    feat = doc.add_offset_face(JAR, last.faces, -0.2)
    assert feat.feature_type == "offset_face" and feat.faces[0]["kind"] == "thread" and feat.skipped == 0
    assert doc.timeline.features[4].grow == grow0
    assert abs(doc.bodies[LID].manifold.volume() - lid0) < 1e-6
    jar = doc.bodies[JAR].manifold
    assert jar.volume() < jar0 - 100 and len(jar.decompose()) == 1 and jar.status().name == "NoError"
    assert 0.18 < _gap_in_thread(doc) < 0.21
    doc.undo()
    assert abs(doc.bodies[JAR].manifold.volume() - jar0) < 1e-6


def test_plus_adds_material_into_the_lid():
    doc, last = _thread_doc()
    feat = doc.add_offset_face(JAR, last.faces, 0.1)
    assert feat.skipped == 0


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
