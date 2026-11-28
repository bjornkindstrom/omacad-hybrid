"""Extrude modeling, boolean cuts, twist, and profile selection tests."""
import math
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.kernel import CadKernel
from omacad.model import quality
from omacad.model.timeline import ExtrudeFeature

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Moved Prism Extrude Cut (Report 20261020-220439)
# ==============================================================================

def test_pocket_cut_on_moved_prism_leaves_no_wall_above_floor():
    doc = Exporter.load_project(str(DATA_DIR / "extrude_cut_moved_hex_skin.omacad"))
    doc.timeline.recompute(doc)
    body = doc.bodies["body_prism_1"]
    assert abs(body.manifold.volume() - 346.41016 * 25.0) < 0.5
    verts = np.asarray(body.manifold.to_mesh().vert_properties)[:, :3]
    assert not np.any(verts[:, 2] > 25.0 + 1e-3)
    walls = [f for f in body.faces if abs(f.normal[2]) < 1e-3]
    assert walls and max(f.area for f in walls) < 25.0 * 11.6


# ==============================================================================
# Extrude Cut Coplanar Cap (Request 20261013-220451)
# ==============================================================================

def test_extrude_cut_has_no_coplanar_cap():
    doc = Exporter.load_project(str(DATA_DIR / "extrude_cut_coplanar_cap.omacad"))
    doc.timeline.recompute(doc)
    b = next(iter(doc.bodies.values()))
    has_cap = any(abs(f.normal[0] + 1.0) < 1e-3 and abs(f.origin[0] - 77.9547) < 1e-3 and abs(f.area - 90.077) < 1e-2 for f in b.faces)
    assert not has_cap
    front_wall = [f for f in b.faces if abs(f.normal[0] - 1.0) < 1e-3 and abs(f.origin[0] - 77.9547) < 1e-3]
    assert len(front_wall) == 1
    assert abs(front_wall[0].area - 799.97689) < 1e-2


# ==============================================================================
# Threaded Shell Cut & Coincident Wall Fuzz
# ==============================================================================

def test_extrude_cut_through_threaded_shell_resolves_coincident_wall():
    doc = Exporter.load_project(str(DATA_DIR / "extrude_cut_thread_fuzz.omacad"))
    body_id = "body_cylinder_1"
    before = doc.step_states[9][body_id]
    cutter = doc.timeline.features[9].build_solid(doc)
    expected = before - CadKernel.grown(cutter, 1e-6)

    body = doc.bodies[body_id]
    mesh = body.manifold.to_mesh()
    assert body.manifold.volume() == pytest.approx(expected.volume(), abs=0.1)
    assert len(mesh.tri_verts) < 6_500


def _wall_area(solid, r0, r1, z0, z1):
    mesh = solid.to_mesh()
    p = np.asarray(mesh.vert_properties)[:, :3][np.asarray(mesh.tri_verts)]
    c = p.mean(axis=1)
    r = np.hypot(c[:, 0], c[:, 1])
    area = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) / 2
    return float(area[(r > r0) & (r < r1) & (c[:, 2] > z0) & (c[:, 2] < z1)].sum())


def test_extrude_cut_of_lid_plug_at_360_segments_leaves_no_strips():
    old = quality.circle_segments()
    quality.set_circle_segments(360)
    try:
        doc = Exporter.load_project(str(DATA_DIR / "extrude_cut_lid_plug_360.omacad"))
    finally:
        quality.set_circle_segments(old)
    lid = doc.bodies["body_cylinder_7"].manifold
    assert _wall_area(doc.step_states[9]["body_cylinder_7"], 13.9, 14.05, 40.05, 45.95) > 500
    assert _wall_area(lid, 13.9, 14.05, 40.05, 45.95) == 0.0
    assert lid.volume() == pytest.approx(7528.5044, abs=1e-3)


# ==============================================================================
# Open Shapes & Nested Coplanar Profiles
# ==============================================================================

H = 10.0


def _nested_doc():
    d = Exporter.load_project(str(DATA_DIR / "coplanar_sketches_nested.omacad"))
    d.timeline.recompute(d)
    return d


def _extrude_nested(d, selected_extra=()):
    extra, refs, holes = ExtrudeFeature.selection_parts(d, "sketch_1", 0, list(selected_extra))
    feat = ExtrudeFeature("t", "t", "sketch_1", 0, H, "new_body", extra_profiles=extra, extra_refs=refs, holes=holes)
    return feat, feat.build_solid(d), holes


def _profile_area(d, sid):
    return d.sketches[sid].profiles[0].area


def test_shapes_inside_the_big_profile_stay_open():
    d = _nested_doc()
    feat, solid, holes = _extrude_nested(d)
    assert {h[0] for h in holes} == {"sketch_2", "sketch_3"}
    want = (_profile_area(d, "sketch_1") - _profile_area(d, "sketch_2") - _profile_area(d, "sketch_3")) * H
    assert solid.volume() == pytest.approx(want, rel=1e-6)


def test_shift_clicking_a_shape_from_another_sketch_fills_it_in():
    d = _nested_doc()
    feat, solid, holes = _extrude_nested(d, [("sketch_2", 0)])
    assert {h[0] for h in holes} == {"sketch_3"}
    want = (_profile_area(d, "sketch_1") - _profile_area(d, "sketch_3")) * H
    assert solid.volume() == pytest.approx(want, rel=1e-6)


def test_the_open_shapes_survive_save_load_and_hidden_sketches(tmp_path):
    d = _nested_doc()
    extra, refs, holes = ExtrudeFeature.selection_parts(d, "sketch_1", 0, [])
    d.extrude_profile("sketch_1", 0, H, "new_body", extra_profiles=extra, extra_refs=refs, holes=holes)
    path = str(tmp_path / "a.omacad")
    Exporter.save_project(d, path)
    d2 = Exporter.load_project(path)
    for sk in d2.sketches.values():
        sk.visible = False
    d2.timeline.recompute(d2)
    body = next(iter(d2.bodies.values()))
    want = (_profile_area(d, "sketch_1") - _profile_area(d, "sketch_2") - _profile_area(d, "sketch_3")) * H
    assert body.manifold.volume() == pytest.approx(want, rel=1e-6)


# ==============================================================================
# Extrude with Twist (Lennart #85)
# ==============================================================================

def _hexagon_doc(twist, centre=(20.0, 10.0), r=10.0, height=40.0):
    doc = Document()
    sk = doc.start_sketch("XY")
    pts = [(centre[0] + r * math.cos(math.radians(60 * k)), centre[1] + r * math.sin(math.radians(60 * k))) for k in range(6)]
    for k in range(6):
        sk.add_line(pts[k], pts[(k + 1) % 6])
    sk.solve_profiles()
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, height, "new_body", twist=twist)
    return doc, pts


def test_twisted_hexagon_keeps_its_area_and_turns_about_its_centre():
    doc, pts = _hexagon_doc(90.0)
    m = next(iter(doc.bodies.values())).manifold
    area = Polygon(pts).area
    assert abs(m.volume() - area * 40.0) < 3e-4 * area * 40.0
    top = Polygon(m.slice(40.0 - 1e-6).to_polygons()[0])
    mid = Polygon(m.slice(20.0).to_polygons()[0])
    assert abs(top.centroid.x - 20.0) < 1e-3 and abs(top.centroid.y - 10.0) < 1e-3
    want_top = Polygon([(20 + 10 * math.cos(math.radians(60 * k + 90)), 10 + 10 * math.sin(math.radians(60 * k + 90))) for k in range(6)])
    want_mid = Polygon([(20 + 10 * math.cos(math.radians(60 * k + 45)), 10 + 10 * math.sin(math.radians(60 * k + 45))) for k in range(6)])
    assert top.symmetric_difference(want_top).area < 1e-3 * area
    assert mid.symmetric_difference(want_mid).area < 1e-3 * area
    assert top.symmetric_difference(Polygon(pts)).area > 10.0


def test_twist_is_saved_and_editable(tmp_path):
    doc, _ = _hexagon_doc(60.0)
    path = tmp_path / "t.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    idx = next(i for i, f in enumerate(again.timeline.features) if f.feature_type == "extrude")
    assert again.timeline.features[idx].twist == 60.0
    assert again.edit_feature(idx, twist=-120.0)
    top = Polygon(next(iter(again.bodies.values())).manifold.slice(40.0 - 1e-6).to_polygons()[0])
    want = Polygon([(20 + 10 * math.cos(math.radians(60 * k - 120)), 10 + 10 * math.sin(math.radians(60 * k - 120))) for k in range(6)])
    assert top.symmetric_difference(want).area < 0.3


# ==============================================================================
# Mirror Body-Creating Extrude
# ==============================================================================

def test_mirror_copies_hole_made_by_the_body_creating_extrude():
    doc = Exporter.load_project(str(DATA_DIR / "mirror_hole_in_first_extrude.omacad"))
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    before = body.manifold.volume()
    ids = [f.feature_id for f in doc.timeline.features]
    doc.add_pattern(ids, kind="mirror", mirror_mode="xy")
    after = next(iter(doc.bodies.values())).manifold.volume()
    assert before - after == pytest.approx(3 * 856, rel=0.02)


# ==============================================================================
# Face Sketch Isolation (Report 20261108-073007)
# ==============================================================================

def test_sketch_on_face_ignores_unrelated_coplanar_body_edges():
    doc = Exporter.load_project(str(DATA_DIR / "extrude_face_sketch_circles_20261108.omacad"))
    sk5 = doc.sketches["sketch_5"]
    assert sk5.parent_body_id == "body_extrude_15"

    doc.refresh_sketch_references(sk5)

    circle_profiles = [p for p in sk5.profiles if 1900.0 < p.area < 2000.0]
    assert len(circle_profiles) == 2, f"Expected 2 intact circle profiles, got {len(circle_profiles)}"

    circle_idx = sk5.profiles.index(circle_profiles[0])
    doc.extrude_profile(sk5.sketch_id, circle_idx, distance=10.0, operation="new_body")
    feat = doc.timeline.features[-1]
    extrude_body = doc.bodies.get(f"body_{feat.feature_id}")
    assert extrude_body is not None
    assert 19000.0 < extrude_body.manifold.volume() < 20000.0


def test_extrude_join_inner_face_flush_with_ring_leaves_no_top_circle():
    """Extruding a cylinder's inner top face (Face to Sketch) up to flush with a joined outer ring must
    merge cleanly without leaving a seam void or inner circle edge on the flat top face."""
    from omacad.model import quality
    from omacad.model.faces_surfaces import compute_planar_faces_and_edges
    from omacad.model.kernel import CadKernel
    from omacad.model.sketch import SketchPlane

    prev = quality.circle_segments()
    try:
        for segs in (72, 96):
            quality.set_circle_segments(segs)
            doc = Document()
            sk1 = doc.start_sketch("XY")
            sk1.add_circle((0, 0), 7.0)
            doc.finish_sketch()
            doc.extrude_profile(sk1.sketch_id, 0, 26.0, "new_body")

            plane = SketchPlane.from_face([0, 0, 1], [0, 0, 26])
            sk2 = doc.start_sketch_on_plane(plane)
            sk2.add_circle((0, 0), 7.0)
            sk2.add_circle((0, 0), 12.5)
            doc.finish_sketch()
            ring_idx = max(range(len(sk2.profiles)), key=lambda i: len(sk2.profiles[i].interior_holes))
            doc.extrude_profile(sk2.sketch_id, ring_idx, 1.0, "join")

            body = next(iter(doc.bodies.values()))
            faces = compute_planar_faces_and_edges(body.manifold, body.body_id)[0]
            f26 = next(f for f in faces if abs(f.origin[2] - 26.0) < 0.01 and f.normal[2] > 0.9)
            sk3, pidx = doc.face_to_sketch(f26)
            doc.extrude_profile(sk3.sketch_id, pidx, 1.0, "join")

            body = next(iter(doc.bodies.values()))
            assert body.manifold.genus() == 0
            assert not CadKernel.has_sheets(body.manifold)
            sl = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
            mid = sl.mean(axis=1)
            top = np.abs(mid[:, 2] - 27.0) < 0.01
            assert not np.any(np.hypot(mid[top, 0], mid[top, 1]) < 10.0)
    finally:
        quality.set_circle_segments(prev)
