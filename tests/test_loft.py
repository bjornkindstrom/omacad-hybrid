"""Loft feature tests: multi-section transitions, hollow profiles, smooth interpolation, twist, and surface normals."""
from pathlib import Path
import os
import numpy as np
import pytest
import trimesh

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import compute_planar_faces

DATA_DIR = Path(__file__).parent / "data"


# =========================================================================
# 1. Hollow Profiles & Multi-section Lofts
# =========================================================================

def test_report_preserves_openings_at_both_ends():
    doc = Exporter.load_project(str(DATA_DIR / "loft_hollow_profiles.omacad"))
    feat = doc.timeline.features[-1]
    body = next(iter(doc.bodies.values())).manifold
    assert body.genus() == 1
    assert body.volume() < 150000
    for sid, idx, sig in feat.sections:
        from omacad.model.features.base import find_profile
        sketch = doc.sketches[sid]
        profile = sketch.profiles[find_profile(sketch, idx, sig)]
        z = sketch.plane.origin[2]
        cut = body.slice(z + (0.0001 if z == 0 else -0.0001))
        assert cut.area() == pytest.approx(profile.area, rel=0.003)


def _hollow_three_sections():
    doc = Document()
    profiles = []
    for z, half in ((0, 20), (10, 15), (30, 25)):
        plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], z, origin=(0, 0, 0)))
        s = doc.start_sketch_on_plane(plane)
        s.add_rect((-half, -half), (half, half))
        s.add_rect((-half + 5, -half + 5), (half - 5, half - 5))
        doc.finish_sketch()
        profiles.append((s.sketch_id, next(i for i, p in enumerate(s.profiles) if p.interior_holes)))
    return doc, profiles


def test_three_sections_keep_five_mm_walls_and_roundtrip(tmp_path):
    doc, profiles = _hollow_three_sections()
    doc.add_loft(profiles)
    body = next(iter(doc.bodies.values())).manifold
    assert body.volume() == pytest.approx(10 * (700 + 500) / 2 + 20 * (500 + 900) / 2, abs=0.01)
    assert body.genus() == 1
    p = tmp_path / "loft.omacad"
    Exporter.save_project(doc, str(p))
    again = Exporter.load_project(str(p))
    assert next(iter(again.bodies.values())).manifold.volume() == pytest.approx(body.volume())


def test_loft_circle_to_smaller_circle_is_a_frustum():
    import math
    doc = Document()
    a = doc.start_sketch("XY")
    a.add_circle((0, 0), 10)
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 20.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_circle((0, 0), 5)
    doc.finish_sketch()
    doc.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)])
    m = next(iter(doc.bodies.values())).manifold
    want = math.pi * 20 / 3 * (100 + 50 + 25)
    assert abs(m.volume() - want) < 0.01 * want
    assert not a.visible and not b.visible           # used sketches are tucked away like after an Extrude


def test_mismatched_holes_are_reported():
    from omacad.model.features.sweep import LoftFeature
    doc, profiles = _hollow_three_sections()
    sid, _ = profiles[-1]
    profiles[-1] = (sid, next(i for i, p in enumerate(doc.sketches[sid].profiles) if not p.interior_holes))
    feat = LoftFeature("test", "Test", [LoftFeature.section_ref(doc, *p) for p in profiles])
    with pytest.raises(ValueError, match="same number of holes"):
        feat.build_solid(doc)


# =========================================================================
# 2. Smooth vs Linear Transitions
# =========================================================================

def test_loft_smooth_transition():
    doc = Document()
    s1 = doc.start_sketch("XY")
    s1.add_circle((0.0, 0.0), 20.0)
    doc.finish_sketch()

    pl2 = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 30.0, origin=(0, 0, 0)))
    s2 = doc.start_sketch_on_plane(pl2)
    s2.add_circle((0.0, 0.0), 30.0)
    doc.finish_sketch()

    pl3 = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 60.0, origin=(0, 0, 0)))
    s3 = doc.start_sketch_on_plane(pl3)
    s3.add_circle((0.0, 0.0), 15.0)
    doc.finish_sketch()

    f_linear = doc.add_loft([(s1.sketch_id, 0), (s2.sketch_id, 0), (s3.sketch_id, 0)], smooth=False)
    vol_linear = list(doc.bodies.values())[-1].manifold.volume()

    doc2 = Document()
    s1_2 = doc2.start_sketch("XY")
    s1_2.add_circle((0.0, 0.0), 20.0)
    doc2.finish_sketch()

    pl2_2 = doc2.construction_plane(doc2.add_construction_plane(doc2.origin_planes["XY"], 30.0, origin=(0, 0, 0)))
    s2_2 = doc2.start_sketch_on_plane(pl2_2)
    s2_2.add_circle((0.0, 0.0), 30.0)
    doc2.finish_sketch()

    pl3_2 = doc2.construction_plane(doc2.add_construction_plane(doc2.origin_planes["XY"], 60.0, origin=(0, 0, 0)))
    s3_2 = doc2.start_sketch_on_plane(pl3_2)
    s3_2.add_circle((0.0, 0.0), 15.0)
    doc2.finish_sketch()

    f_smooth = doc2.add_loft([(s1_2.sketch_id, 0), (s2_2.sketch_id, 0), (s3_2.sketch_id, 0)], smooth=True)
    vol_smooth = list(doc2.bodies.values())[-1].manifold.volume()

    assert f_smooth.smooth is True
    assert f_linear.smooth is False
    assert vol_smooth > 0 and vol_linear > 0
    assert abs(vol_smooth - vol_linear) > 10.0

    d = Exporter.document_to_dict(doc2)
    doc_reloaded = Document()
    Exporter.apply_dict(doc_reloaded, d)
    assert doc_reloaded.timeline.features[-1].smooth is True


# =========================================================================
# 3. Smooth Skin & Planar Faces
# =========================================================================

def test_rectangle_to_circle_loft_is_one_smooth_skin():
    doc = Exporter.load_project(str(DATA_DIR / "loft_square_to_circle.omacad"))
    m = next(b for b in doc.bodies.values() if b.name == "Loft 1").manifold
    v = np.asarray(m.to_mesh().vert_properties[:, :3])
    assert np.allclose(v[:, :2].min(axis=0), [-75, -40]) and np.allclose(v[:, :2].max(axis=0), [75, 100])
    bottom = v[np.abs(v[:, 2]) < 1e-6][:, :2]
    for corner in ([-75, -40], [75, -40], [75, 100], [-75, 100]):
        assert np.linalg.norm(bottom - corner, axis=1).min() < 1e-4
    assert len(compute_planar_faces(m)) <= 6
    tm = trimesh.Trimesh(v, m.to_mesh().tri_verts, process=False)
    ends = np.abs(np.diff(v[tm.face_adjacency_edges][:, :, 2], axis=1)).ravel() < 1e-6
    folds = np.degrees(tm.face_adjacency_angles[~ends])
    assert np.sum(folds > 10.0) <= 48


def test_rectangle_to_smaller_rectangle_loft_is_an_exact_frustum():
    doc = Document()
    a = doc.start_sketch("XY")
    a.add_rect((-15, -10), (15, 10))
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 10.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_rect((-7.5, -5), (7.5, 5))
    doc.finish_sketch()
    doc.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)])
    m = next(iter(doc.bodies.values())).manifold
    assert abs(m.volume() - 10 / 3 * (600 + 150 + 300)) < 1e-3


def test_curved_skin_hides_the_bottom_face_from_hover():
    from types import SimpleNamespace
    from omacad.ui.viewport.viewport import Viewport3D

    doc = Exporter.load_project(str(DATA_DIR / "loft_square_to_circle.omacad"))
    for b in doc.bodies.values():
        b.visible = b.name == "Loft 1"
    vp = SimpleNamespace(doc=doc, _ray_hits_body_aabb=Viewport3D._ray_hits_body_aabb)
    origin, down = np.array([0.0, 30.0, 200.0]), np.array([0.0, 0.0, -1.0])
    assert not Viewport3D._surface_in_front(vp, origin, down, 150.0)
    side = np.array([0.0, -200.0, 5.0])
    assert Viewport3D._surface_in_front(vp, side, np.array([0.0, 1.0, 0.0]), 250.0)


# =========================================================================
# 4. Loft Twist
# =========================================================================

def _square_loft(twist):
    doc = Document()
    a = doc.start_sketch("XY")
    a.add_rect((-10, -10), (10, 10))
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 30.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_rect((-10, -10), (10, 10))
    doc.finish_sketch()
    doc.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)], twist=twist)
    return doc


def test_twisted_loft_keeps_every_slice_and_turns_the_top():
    doc = _square_loft(45.0)
    m = next(iter(doc.bodies.values())).manifold
    assert 0.995 * 12000 < m.volume() <= 12000 + 1e-6
    v = np.asarray(m.to_mesh().vert_properties[:, :3])
    top = v[np.abs(v[:, 2] - 30) < 1e-6][:, :2]
    assert np.linalg.norm(top - [0, 10 * 2**0.5], axis=1).min() < 1e-3
    mid = v[np.abs(v[:, 2] - 15) < 0.5][:, :2]
    assert np.linalg.norm(mid, axis=1).max() > 10 * 2**0.5 - 1e-3


def test_untwisted_loft_unchanged_and_twist_survives_save_and_edit(tmp_path):
    doc = _square_loft(0.0)
    top = np.asarray(next(iter(doc.bodies.values())).manifold.to_mesh().vert_properties)[:, :2]
    assert np.linalg.norm(top - [10, 10], axis=1).min() < 1e-6
    feat = next(f for f in doc.timeline.features if f.feature_type == "loft")
    doc.edit_feature(doc.timeline.features.index(feat), twist=90.0)
    f = tmp_path / "t.omacad"
    Exporter.save_project(doc, str(f))
    again = Exporter.load_project(str(f))
    assert next(x for x in again.timeline.features if x.feature_type == "loft").twist == 90.0


# =========================================================================
# 5. Loft Shading & Normals (Request #232)
# =========================================================================

def test_232_loft_no_inverted_normals_and_retains_smooth_shading():
    doc = Exporter.load_project(str(DATA_DIR / "request_232_loft_shading.omacad"))
    body = list(doc.bodies.values())[0]
    rm = body.render_mesh

    V = rm.vertices.reshape(-1, 3, 3)
    N = rm.normals.reshape(-1, 3, 3)

    fn = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)

    dots = (N * fn[:, None, :]).sum(axis=2)
    assert dots.min() >= -1e-6, f"Found inverted vertex normals: min dot {dots.min()}"

    mid = (V[:, :, 2].mean(axis=1) > 100) & (V[:, :, 2].mean(axis=1) < 400)
    diffs = np.linalg.norm(N[mid, 1] - N[mid, 0], axis=1) + np.linalg.norm(N[mid, 2] - N[mid, 0], axis=1)
    smooth_count = int((diffs > 0.01).sum())
    total_mid = int(mid.sum())
    assert smooth_count > 0.8 * total_mid, f"Expected >80% smooth triangles in mid section, got {smooth_count}/{total_mid}"
