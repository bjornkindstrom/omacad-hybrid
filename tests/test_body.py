"""Body model attributes, colors, points, and snap targets regression tests."""
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.body_points import body_points, nearest_point, tangent_corner
from omacad.model.document import Document
from omacad.model.timeline import BoxFeature


# ==============================================================================
# Body Color Persistence & Undo
# ==============================================================================

def test_set_body_color_and_reset():
    doc = Document()
    doc.add_box(10.0, 10.0, 10.0)
    body_id = "body_1" if "body_1" in doc.bodies else next(iter(doc.bodies))
    body = doc.bodies[body_id]

    assert body.color == Document.DEFAULT_BODY_COLOR

    custom_col = [1.0, 0.0, 0.0, 1.0]
    doc.set_body_color(body_id, custom_col)
    assert doc.bodies[body_id].color == custom_col
    assert doc.body_colors[body_id] == custom_col

    data = Exporter.document_to_dict(doc)
    assert "body_colors" in data
    assert data["body_colors"][body_id] == custom_col

    doc2 = Document()
    doc2.add_box(10.0, 10.0, 10.0)
    Exporter.apply_dict(doc2, data)
    assert doc2.body_colors[body_id] == custom_col

    doc.timeline.recompute(doc)
    assert doc.bodies[body_id].color == custom_col

    doc.set_body_color(body_id, None)
    assert doc.bodies[body_id].color == Document.DEFAULT_BODY_COLOR
    assert body_id not in doc.body_colors

    doc.undo()
    assert doc.bodies[body_id].color == custom_col

    doc.undo()
    assert doc.bodies[body_id].color == Document.DEFAULT_BODY_COLOR


# ==============================================================================
# Body Snap Points
# ==============================================================================

def _rounded_block(r=4.0):
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (30, 20), r)
    d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 10)
    return d, next(iter(d.bodies.values()))


def _set(points, kind):
    return sorted(tuple(round(float(c), 4) for c in p.xyz) for p in points if p.kind == kind)


def test_box_has_its_eight_corners_as_ends():
    d = Document()
    d.add_box(30, 20, 10)
    pts = body_points(next(iter(d.bodies.values())))
    assert len(_set(pts, "end")) == 8
    assert not _set(pts, "corner")
    xs, ys, zs = zip(*_set(pts, "end"))
    assert (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) == pytest.approx((30, 20, 10))


def test_box_has_centres_of_top_and_bottom_faces():
    d = Document()
    d.add_box(30, 20, 10)
    body = next(iter(d.bodies.values()))
    points = {p.kind: p.xyz for p in body_points(body) if p.kind in ("top_center", "bottom_center")}
    assert points["bottom_center"] == pytest.approx((15, 10, 0), abs=1e-3)
    assert points["top_center"] == pytest.approx((15, 10, 10), abs=1e-3)
    assert nearest_point(body, (0, 0, 0), "top_center").xyz == pytest.approx((15, 10, 10), abs=1e-3)


def test_sphere_has_top_and_bottom_extreme_centres():
    d = Document()
    d.add_sphere(5)
    points = {p.kind: p.xyz for p in body_points(next(iter(d.bodies.values())))
              if p.kind in ("top_center", "bottom_center")}
    assert points["bottom_center"] == pytest.approx((0, 0, -5), abs=1e-3)
    assert points["top_center"] == pytest.approx((0, 0, 5), abs=1e-3)


def test_rounded_block_gives_the_hidden_sharp_corners_and_the_tangent_points():
    _, body = _rounded_block()
    pts = body_points(body)
    corners = _set(pts, "corner")
    expected = sorted((x, y, z) for x in (0.0, 30.0) for y in (0.0, 20.0) for z in (0.0, 10.0))
    assert np.allclose(corners, expected, atol=1e-3)
    ends = _set(pts, "end")
    assert len(ends) == 16
    assert (4.0, 0.0, 0.0) in [tuple(round(c, 3) for c in e) for e in ends]
    corner = next(p for p in pts if p.kind == "corner")
    for g in corner.guides:
        assert float(np.linalg.norm(g - corner.xyz)) == pytest.approx(4.0, abs=1e-3)


def test_corner_stays_put_when_the_radius_changes():
    _, small = _rounded_block(2.0)
    _, large = _rounded_block(6.0)
    assert np.allclose(_set(body_points(small), "corner"), _set(body_points(large), "corner"), atol=1e-3)
    found = nearest_point(large, (30.2, 19.9, 10.1), "corner")
    assert found.xyz == pytest.approx((30, 20, 10), abs=1e-3)


def test_tangent_corner_of_a_quarter_turn():
    assert tangent_corner(np.array([1.0, 0, 0]), np.array([1.0, 0, 0]), np.array([2.0, 1, 0]),
                          np.array([0.0, 1, 0])) == pytest.approx((2, 0, 0))
    assert tangent_corner(np.array([0.0, 0, 0]), np.array([1.0, 0, 0]), np.array([0.0, 1, 0]),
                          np.array([1.0, 0, 0])) is None


def test_every_flat_face_has_its_centre():
    d = Document()
    d.add_box(30, 20, 10)
    pts = body_points(next(iter(d.bodies.values())))
    sides = sorted(_set(pts, "face_center"))
    assert np.allclose(sides, sorted([(0, 10, 5), (30, 10, 5), (15, 0, 5), (15, 20, 5)]), atol=1e-3)
    assert len(_set(pts, "top_center")) == len(_set(pts, "bottom_center")) == 1


def test_hole_has_circle_centres_top_and_bottom():
    d = Document()
    d.add_box(30, 20, 10)
    block = next(iter(d.bodies))
    d.add_cylinder(3, 10)
    pin = next(b for b in d.bodies if b != block)
    d.move_body(pin, 8, 10, 0, pivot="origin")
    d.combine_bodies(block, pin, "cut")
    body = d.bodies[block]
    assert _set(body_points(body), "center") == [(8.0, 10.0, 0.0), (8.0, 10.0, 10.0)]
    assert nearest_point(body, (7, 9, 9), "center").xyz == pytest.approx((8, 10, 10), abs=1e-3)


def test_cylinder_cap_centre_is_one_point():
    d = Document()
    d.add_cylinder(5, 10)
    pts = body_points(next(iter(d.bodies.values())))
    tops = [p for p in pts if np.linalg.norm(p.xyz - (0, 0, 10)) < 1e-3]
    assert [p.kind for p in tops] == ["top_center"]


def test_cylinder_ends_have_a_cross_of_five_points():
    doc = Document()
    doc.add_cylinder(5, 10)
    pts = body_points(next(iter(doc.bodies.values())))
    for z, centre in ((0.0, "bottom_center"), (10.0, "top_center")):
        at = [p for p in pts if abs(p.xyz[2] - z) < 1e-6]
        assert sorted(p.kind for p in at) == sorted([centre] + ["quadrant"] * 4)
        quads = sorted((round(p.xyz[0], 6) + 0.0, round(p.xyz[1], 6) + 0.0) for p in at if p.kind == "quadrant")
        assert quads == [(-5.0, 0.0), (0.0, -5.0), (0.0, 5.0), (5.0, 0.0)]


def test_point_to_point_by_the_side_of_a_cylinder_and_after_a_rebuild():
    doc = Document()
    a = doc.add_cylinder(5, 10).body_id
    b = doc.add_cylinder(3, 10, plane_origin=[40, 20, 0], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0]).body_id
    frm = {"body": b, "kind": "quadrant", "xyz": [37.0, 20.0, 0.0]}
    to = {"body": a, "kind": "quadrant", "xyz": [5.0, 0.0, 0.0]}
    doc.move_body(b, from_point=frm, to_point=to)
    lo = doc.bodies[b].manifold.bounding_box()
    assert lo[0] == pytest.approx(5.0, abs=1e-6) and lo[1] == pytest.approx(-3.0, abs=1e-6)
    doc.edit_feature(0, radius=8.0)
    assert doc.bodies[b].manifold.bounding_box()[0] == pytest.approx(8.0, abs=1e-6)


# ==============================================================================
# Linked Body Copies Following Parent Operations
# ==============================================================================

def test_linked_copy_follows_cut_from_sketch_on_face():
    from omacad.model.sketch import SketchPlane
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (100, 100))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 50.0)
    orig_feat = doc.timeline.last_added
    orig_body_id = f"body_{orig_feat.feature_id}"

    link_body = doc.branch_object(orig_feat.feature_id, orig_body_id, linked=True)
    doc.move_body(link_body.body_id, dx=200.0)

    face = [f for f in doc.bodies[orig_body_id].faces if f.normal[2] > 0.9][0]
    plane = SketchPlane.from_face(face.normal, face.origin)
    plane.face = face
    face_sk = doc.start_sketch_on_plane(plane)
    face_sk.add_circle((50, 50), 20.0)
    doc.finish_sketch()

    doc.extrude_profile(face_sk.sketch_id, 0, -25.0, operation="cut")
    v_cut = doc.bodies[orig_body_id].manifold.volume()

    assert doc.bodies[orig_body_id].manifold.volume() == pytest.approx(v_cut)
    assert doc.bodies[link_body.body_id].manifold.volume() == pytest.approx(v_cut)

    types = [f.feature_type for f in doc.timeline.features]
    assert types == ["sketch", "extrude", "sketch", "extrude", "branch", "move"]

    doc.undo()
    assert doc.bodies[orig_body_id].manifold.volume() == pytest.approx(500000.0)
    assert doc.bodies[link_body.body_id].manifold.volume() == pytest.approx(500000.0)

    doc.redo()
    assert doc.bodies[orig_body_id].manifold.volume() == pytest.approx(v_cut)
    assert doc.bodies[link_body.body_id].manifold.volume() == pytest.approx(v_cut)

    data = Exporter.document_to_dict(doc)
    loaded = Document()
    Exporter.apply_dict(loaded, data)
    assert loaded.bodies[orig_body_id].manifold.volume() == pytest.approx(v_cut)
    assert loaded.bodies[link_body.body_id].manifold.volume() == pytest.approx(v_cut)


def test_problem_report_20261108_linked_copy_follows_extrude_2_cut():
    from pathlib import Path
    fixture = Path(__file__).parent / "data" / "extrude_face_sketch_circles_20261108.omacad"
    doc = Exporter.load_project(str(fixture))
    sk5 = doc.sketches["sketch_5"]
    assert sk5.parent_body_id == "body_extrude_15"
    doc.refresh_sketch_references(sk5)

    circle_profiles = [p for p in sk5.profiles if 1900.0 < p.area < 2000.0]
    assert len(circle_profiles) == 2
    idx = sk5.profiles.index(circle_profiles[0])

    doc.extrude_profile(sk5.sketch_id, idx, distance=-50.0, operation="cut")

    b_orig = doc.bodies["body_extrude_15"]
    b_link = doc.bodies["body_branch_16"]
    assert b_orig.manifold.volume() == pytest.approx(b_link.manifold.volume(), rel=1e-5)
    assert b_orig.manifold.volume() < 9000000.0
