"""Emboss / Deboss feature tests: text on a face raised by a depth or pressed in.

Covers flat faces, cylindrical wrapping, compound surfaces, revolved bodies, and patterns.
"""
from pathlib import Path
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import detect_cylinder_surface, ray_mesh_hit
from omacad.model.features.emboss import EmbossFeature
from omacad.model.sketch import SketchPlane

DATA_DIR = Path(__file__).parent / "data"
BOX = (60.0, 40.0, 10.0)


# =========================================================================
# Helpers
# =========================================================================

def _scene(text="HI", height=12.0, anchor=(0.0, 0.0), **kw):
    doc = Document()
    doc.add_box(*BOX, center="bottom_center")
    body = next(iter(doc.bodies))
    top = max(doc.bodies[body].faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin))
    t = sk.add_text(text, anchor, height=height, h_align="center", v_align="middle", **kw)
    doc.finish_sketch()
    return doc, body, sk, t


def _text_profiles(sk):
    return sk.text_profile_indices()


def _volume(doc, body):
    return doc.bodies[body].manifold.volume()


# =========================================================================
# 1. Basic Emboss / Deboss & Volumes
# =========================================================================

def test_text_profile_indices_are_the_letters_not_the_counters():
    doc, body, sk, t = _scene("O")
    idx = _text_profiles(sk)
    assert len(idx) == 1 and sk.profiles[idx[0]].interior_holes
    assert len(sk.profiles) == 3


def test_emboss_adds_the_exact_volume_and_deboss_removes_it():
    doc, body, sk, t = _scene("HI")
    idx = _text_profiles(sk)
    area = t.geometry().area
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 1.5, extra_profiles=idx[1:])
    assert _volume(doc, body) == pytest.approx(base + area * 1.5, rel=2e-3)
    assert len(doc.bodies) == 1
    top = doc.bodies[body].manifold.bounding_box()[5]
    assert top == pytest.approx(BOX[2] + 1.5, abs=1e-3)
    doc.undo()
    assert _volume(doc, body) == pytest.approx(base, rel=1e-9)
    doc.add_emboss(sk.sketch_id, idx[0], -2.0, extra_profiles=idx[1:])
    assert _volume(doc, body) == pytest.approx(base - area * 2.0, rel=2e-3)
    assert doc.bodies[body].manifold.bounding_box()[5] == pytest.approx(BOX[2], abs=1e-6)


def test_the_counter_of_an_o_stays_open_when_embossed():
    doc, body, sk, t = _scene("O", height=20.0)
    idx = _text_profiles(sk)
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 1.0)
    assert _volume(doc, body) == pytest.approx(base + t.geometry().area * 1.0, rel=2e-3)


def test_flip_goes_the_other_way_and_shift_and_turn_move_the_text():
    doc, body, sk, t = _scene("HI")
    idx = _text_profiles(sk)
    doc.add_emboss(sk.sketch_id, idx[0], 1.0, flip=True, extra_profiles=idx[1:])
    assert doc.bodies[body].manifold.bounding_box()[5] == pytest.approx(BOX[2], abs=1e-6)

    doc2, body2, sk2, t2 = _scene("HI")
    idx2 = _text_profiles(sk2)
    doc2.add_emboss(sk2.sketch_id, idx2[0], 1.0, dx=10.0, dy=5.0, extra_profiles=idx2[1:])
    top = doc2.bodies[body2].manifold
    letters = top.trim_by_plane((0, 0, 1), BOX[2] + 0.5)
    x0, y0, _, x1, y1, _ = letters.bounding_box()
    bx0, by0, bx1, by1 = t2.bbox()
    assert (x0, y0, x1, y1) == pytest.approx((bx0 + 10.0, by0 + 5.0, bx1 + 10.0, by1 + 5.0), abs=0.05)

    doc3, body3, sk3, t3 = _scene("HI")
    idx3 = _text_profiles(sk3)
    doc3.add_emboss(sk3.sketch_id, idx3[0], 1.0, rotation=90.0, extra_profiles=idx3[1:])
    r = doc3.bodies[body3].manifold.trim_by_plane((0, 0, 1), BOX[2] + 0.5).bounding_box()
    assert (r[3] - r[0], r[4] - r[1]) == pytest.approx((t3.bbox()[3] - t3.bbox()[1], t3.bbox()[2] - t3.bbox()[0]), abs=0.1)


def test_save_load_and_edit_keep_working():
    doc, body, sk, t = _scene("HI")
    idx = _text_profiles(sk)
    v0 = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 1.0, extra_profiles=idx[1:])
    feat = doc.timeline.features[-1]
    assert feat.feature_type == "emboss" and feat.effect == "emboss"
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert loaded.timeline.features[-1].feature_type == "emboss"
    assert next(iter(loaded.bodies.values())).manifold.volume() == pytest.approx(_volume(doc, body), rel=1e-9)
    doc.edit_feature(len(doc.timeline.features) - 1, depth=-1.0)
    assert doc.timeline.features[-1].effect == "deboss"
    assert _volume(doc, body) == pytest.approx(v0 - t.geometry().area * 1.0, rel=2e-3)


def test_emboss_on_text_along_a_circle():
    doc = Document()
    doc.add_cylinder(20.0, 6.0, name="Coin")
    body = next(iter(doc.bodies))
    top = max(doc.bodies[body].faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin).centered_on(top.tris))
    ring = sk.add_circle((0.0, 0.0), 14.0, is_construction=True)
    t = sk.add_text("COIN * TEXT *", height=4.0, path_id=ring.entity_id, h_align="center")
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    assert idx
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 0.8, extra_profiles=idx[1:])
    assert _volume(doc, body) == pytest.approx(base + t.geometry().area * 0.8, rel=3e-3)


def test_embossed_letter_can_be_copied_round_a_circle_with_the_pattern_tool():
    doc = Document()
    doc.add_cylinder(20.0, 6.0, name="Coin")
    body = next(iter(doc.bodies))
    top = max(doc.bodies[body].faces, key=lambda f: f.normal[2])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(top.normal, top.origin))
    t = sk.add_text("A", (14.0, 0.0), height=4.0, h_align="center", v_align="middle")
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    base = _volume(doc, body)
    doc.add_emboss(sk.sketch_id, idx[0], 0.8, extra_profiles=idx[1:])
    one = _volume(doc, body) - base
    assert one == pytest.approx(t.geometry().area * 0.8, rel=3e-3)
    emboss_id = doc.timeline.features[-1].feature_id
    doc.add_pattern([emboss_id], "circular", count1=6, angle=360.0, about="body")
    assert _volume(doc, body) == pytest.approx(base + 6 * one, rel=5e-3)


# =========================================================================
# 2. Wrapping on Cylinders
# =========================================================================

CYL_R, CYL_H, CYL_GAP = 20.0, 40.0, 3.5


def _cyl_scene(depth):
    doc = Document()
    doc.add_cylinder(CYL_R, CYL_H)
    body = next(iter(doc.bodies))
    n = np.array([1.0, 0.0, 0.0])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(n, n * (CYL_R + CYL_GAP)))
    t = sk.add_text("HI", (0.0, 20.0), height=10.0, h_align="center", v_align="middle")
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    doc.add_emboss(sk.sketch_id, idx[0], depth, extra_profiles=idx[1:])
    return doc, body


def test_emboss_reaches_the_cylinder_and_stands_depth_above_it():
    doc, body = _cyl_scene(1.0)
    assert len(doc.bodies) == 1
    mesh = doc.bodies[body].manifold
    x_max = mesh.bounding_box()[3]
    assert x_max == pytest.approx(CYL_R + 1.0, abs=0.05)
    assert mesh.volume() > np.pi * CYL_R * CYL_R * CYL_H + 1.0


def test_deboss_wraps_too():
    doc, body = _cyl_scene(-1.0)
    mesh = doc.bodies[body].manifold
    assert mesh.volume() < np.pi * CYL_R * CYL_R * CYL_H - 1.0
    assert mesh.bounding_box()[3] == pytest.approx(CYL_R, abs=0.05)


def test_long_text_with_centroid_beside_the_cylinder_still_wraps():
    doc = Document()
    doc.add_cylinder(CYL_R, CYL_H)
    body = next(iter(doc.bodies))
    n = np.array([1.0, 0.0, 0.0])
    sk = doc.start_sketch_on_plane(SketchPlane.from_face(n, n * (CYL_R + CYL_GAP)))
    sk.add_text("Testar att andra", (-15.0, 20.0), height=10.0)
    doc.finish_sketch()
    idx = sk.text_profile_indices()
    doc.add_emboss(sk.sketch_id, idx[0], 1.0, extra_profiles=idx[1:])
    mesh = doc.bodies[body].manifold
    assert len(doc.bodies) == 1
    assert mesh.bounding_box()[3] == pytest.approx(CYL_R + 1.0, abs=0.05)


def test_reported_deboss_slot_leaves_no_detached_skin():
    doc = Exporter.load_project(str(DATA_DIR / "deboss_slot_flap.omacad"))
    solid = next(iter(doc.bodies.values())).manifold
    section = solid.slice(30.0)
    assert len(section.to_polygons()) == 2
    radius = doc.sketches["sketch_1"].entities[0].radius
    expected_area = np.pi * (5.0**2 - 3.0**2) - (2 * radius / 5.0) * (5.0**2 - 4.0**2) / 2
    assert section.area() == pytest.approx(expected_area, abs=0.04)
    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    assert next(iter(loaded.bodies.values())).manifold.volume() == pytest.approx(solid.volume())


# =========================================================================
# 3. Compound surfaces & Special cylinder fits
# =========================================================================

def test_cylinder_fit_ignores_the_fillet_that_joins_the_wall():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_behind_fillet_wall.omacad"))
    mesh = doc.bodies["body_cylinder_1"].render_mesh
    hit = ray_mesh_hit(mesh, np.array([1e4, -3.0, 19.0]), np.array([-1.0, 0.0, 0.0]))
    cyl = detect_cylinder_surface(mesh, hit[1])
    assert cyl is not None
    assert abs(cyl["radius"] - 20.0) < 0.05
    assert abs(abs(cyl["axis"][2]) - 1.0) < 1e-3


def test_emboss_wraps_the_letters_onto_the_wall_not_the_plane_behind():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_behind_fillet_wall.omacad"))
    sketch = doc.sketches["sketch_2"]
    feat = EmbossFeature("t", "t", "sketch_2", 0, 1.0)
    tool = feat.build_solid(doc)
    assert tool is not None
    v = np.asarray(tool.to_mesh().vert_properties)[:, :3]
    radial = np.hypot(v[:, 0], v[:, 1])
    assert radial.max() < 21.5
    assert radial.min() < 20.5
    assert len(sketch.profiles) == 5


def test_text_lands_on_the_wall_and_round_corner():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_flat_and_round.omacad"))
    lid = doc.bodies["body_extrude_9"].manifold
    tool = EmbossFeature("t", "t", "sketch_4", 0, 1.0, extra_profiles=[1, 2, 3, 4]).build_solid(doc)
    bb = np.array(tool.bounding_box())
    assert bb[1] > -31.5
    assert bb[3] <= 45.0 + 1e-6
    assert (tool ^ lid).volume() > 0.5
    pts = np.asarray(tool.to_mesh().vert_properties)[:, :3]
    near_corner = pts[pts[:, 0] > 43.0]
    assert near_corner[:, 1].max() > -29.0


def test_emboss_joins_the_lid():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_flat_and_round.omacad"))
    before = doc.bodies["body_extrude_9"].manifold.volume()
    doc.add_emboss("sketch_4", 0, 1.0, extra_profiles=[1, 2, 3, 4])
    lid = doc.bodies["body_extrude_9"].manifold
    assert lid.volume() - before > 5.0
    assert len(doc.bodies) == 2


def test_flat_wall_of_tapered_prism_is_not_a_cylinder():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_tapered_prism.omacad"))
    mesh = list(doc.bodies.values())[0].render_mesh
    sketch = doc.sketches["sketch_1"]
    origin = np.asarray(sketch.plane.origin, dtype=float)
    normal = np.asarray(sketch.plane.normal, dtype=float)
    hit = ray_mesh_hit(mesh, origin + normal * 60.0, -normal)
    assert hit is not None
    assert detect_cylinder_surface(mesh, hit[1]) is None


def test_emboss_on_tapered_prism_extrudes_straight_from_the_flat_wall():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_tapered_prism.omacad"))
    feat = EmbossFeature("t", "t", "sketch_1", 0, 1.0)
    tool = feat.build_solid(doc)
    assert tool is not None
    sketch = doc.sketches["sketch_1"]
    M = np.vstack([np.asarray(sketch.plane.get_transform_matrix_3x4(), dtype=float).reshape(3, 4), [0, 0, 0, 1]])
    local = (np.linalg.inv(M) @ np.hstack([np.asarray(tool.to_mesh().vert_properties)[:, :3],
                                           np.ones((len(tool.to_mesh().vert_properties), 1))]).T).T[:, 2]
    assert abs((local.max() - local.min()) - (1.0 + 0.02)) < 1e-3


# =========================================================================
# 4. Revolved surfaces (Vase & Bowl)
# =========================================================================

def test_vase_every_letter_touches_the_wall():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_vase.omacad"))
    emboss = next(f for f in doc.timeline.features if f.feature_type == "emboss")
    doc.timeline.marker_index = doc.timeline.features.index(emboss)
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values())).manifold
    sketch = doc.sketches[emboss.sketch_id]
    region = emboss.region(doc, sketch, [emboss.profile_idx] + list(emboss.extra_profiles))

    tool = emboss.build_solid(doc)
    letters = tool.decompose()
    assert len(letters) == len(region.geoms) == 4
    for letter in letters:
        assert (letter ^ body).volume() > 1.0
    assert len((tool + body).decompose()) == 1


def test_vase_letters_stand_the_depth_above_the_wall():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_vase.omacad"))
    emboss = next(f for f in doc.timeline.features if f.feature_type == "emboss")
    doc.timeline.marker_index = doc.timeline.features.index(emboss)
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values())).manifold
    sketch = doc.sketches[emboss.sketch_id]
    region = emboss.region(doc, sketch, [emboss.profile_idx] + list(emboss.extra_profiles))
    raised = (emboss.build_solid(doc) - body).volume()
    assert region.area * emboss.depth <= raised <= 1.05 * region.area * emboss.depth


def test_vase_report_document_rebuilds_into_one_body():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_vase.omacad"))
    body = next(iter(doc.bodies.values())).manifold
    assert len(body.decompose()) == 1


def test_bowl_wall_is_found_round_its_own_axis():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_bowl.omacad"))
    emboss = next(f for f in doc.timeline.features if f.feature_type == "emboss")
    doc.timeline.marker_index = doc.timeline.features.index(emboss)
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    hit = ray_mesh_hit(body.render_mesh, np.array([200.0, 0.0, 20.0]), np.array([-1.0, 0.0, 0.0]))
    cyl = detect_cylinder_surface(body.render_mesh, hit[1])
    assert cyl is not None and not cyl["is_internal"]
    assert abs(cyl["axis"] @ [0.0, 0.0, 1.0]) > 1 - 1e-9
    p = np.asarray(cyl["origin"])
    assert np.hypot(p[0], p[1]) < 1e-6
    assert abs(cyl["radius"] - (200.0 - hit[0])) < 0.5


def test_bowl_letters_stand_upright_on_the_wall():
    doc = Exporter.load_project(str(DATA_DIR / "emboss_on_bowl.omacad"))
    emboss = next(f for f in doc.timeline.features if f.feature_type == "emboss")
    doc.timeline.marker_index = doc.timeline.features.index(emboss)
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    sketch = doc.sketches[emboss.sketch_id]
    region = emboss.region(doc, sketch, [emboss.profile_idx] + list(emboss.extra_profiles))

    tool = emboss.build_solid(doc)
    letters = tool.decompose()
    assert len(letters) == len(region.geoms) == 4
    z0 = sketch.plane.origin[2]
    _, miny, _, maxy = region.bounds
    lo, hi = tool.bounding_box()[2], tool.bounding_box()[5]
    assert abs(lo - (z0 + miny)) < 0.02 and abs(hi - (z0 + maxy)) < 0.02
    for letter in letters:
        assert (letter ^ body.manifold).volume() > 1.0
    raised = (tool - body.manifold).volume()
    assert 0.97 * region.area * emboss.depth <= raised <= 1.05 * region.area * emboss.depth
    assert len((tool + body.manifold).decompose()) == 1
