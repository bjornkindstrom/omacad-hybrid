"""Spline model tests: interpolation, control point splines, offset linking, constraints, and solver dimensions."""
import json
import math
import os
from pathlib import Path
import pytest
from shapely.geometry import LineString, Point, Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchSpline, move_entity, rotate_entity
from omacad.model.sketch_solver import _solver_entities

DATA_DIR = Path(__file__).parent / "data"
REPORT_DATA = DATA_DIR / "control_spline_dimension.json"


def _report_doc():
    doc = Document()
    with open(REPORT_DATA, encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    return doc


# =========================================================================
# 1. Spline Curves & Interpolation
# =========================================================================

def test_spline_interpolates_picked_points_and_roundtrips():
    points = [(0, 0), (5, 8), (10, 0)]
    spline = SketchSpline("spline_1", points)
    sampled = spline.get_points()
    assert sampled[0] == points[0]
    assert sampled[-1] == points[-1]
    assert all(point in sampled for point in points)
    assert len(spline.to_lines()) == 32
    assert SketchSpline.from_dict(spline.to_dict()).points == points


def test_control_point_spline_bends_toward_interior_points_without_crossing_them():
    points = [(0, 0), (0, 10), (10, 10), (10, 0)]
    sketch = Sketch("control", plane=SketchPlane.create_named("XY"))
    spline = sketch.add_spline(points, control_points=True)
    curve = spline.get_points()
    assert curve[0] == (0, 0) and curve[-1] == (10, 0)
    assert max(p[1] for p in curve) == 7.5
    assert (0, 10) not in curve and (10, 10) not in curve
    assert Sketch.from_dict(sketch.to_dict()).entities[0].control_points
    sketch.move_spline_point(spline.entity_id, 1, (0, 20))
    assert max(p[1] for p in spline.get_points()) > 7.5
    sketch.add_line((10, 0), (0, 0))
    assert sketch.profiles


def test_spline_sketch_serialization_and_transformations():
    sketch = Sketch("sketch_1", plane=SketchPlane.create_named("XY"))
    spline = sketch.add_spline([(0, 0), (5, 8), (10, 0)])
    restored = Sketch.from_dict(sketch.to_dict())
    assert restored.entities[0].to_dict() == spline.to_dict()

    move_entity(spline, 2, -1)
    assert spline.points[0] == (2, -1)
    rotate_entity(spline, 90, (0, 0))
    assert abs(spline.points[0][0] - 1) < 1e-9
    assert abs(spline.points[0][1] - 2) < 1e-9


def _old_catmull(points, n=16):
    out = []
    for i in range(len(points) - 1):
        p0 = points[max(0, i - 1)]; p1, p2 = points[i], points[i + 1]; p3 = points[min(len(points) - 1, i + 2)]
        for j in range(n):
            t = j / n; t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t + (2*p0[k] - 5*p1[k] + 4*p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3*p1[k] - 3*p2[k] + p3[k]) * t3) for k in (0, 1)))
    return out + [points[-1]]


def test_default_tangents_match_old_curve_and_dict_is_unchanged():
    pts = [(0, 0), (5, 8), (10, 0), (14, 3)]
    sp = SketchSpline("s", pts)
    for a, b in zip(sp.get_points(), _old_catmull([tuple(map(float, p)) for p in pts])):
        assert abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


# =========================================================================
# 2. Control Spline Offset & Links
# =========================================================================

def test_control_spline_offset_creates_link_and_constraint():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    assert src.control_points
    new = sk.offset_entities([src.entity_id], 5.0)
    assert len(new) == 1
    copy = new[0]
    assert isinstance(copy, SketchSpline) and copy.control_points
    assert copy.offset_info is not None
    assert copy.offset_info["source_id"] == src.entity_id
    assert copy.offset_info["distance"] == 5.0
    offset_constraints = [c for c in sk.constraints if c.ctype == "OFFSET"]
    assert len(offset_constraints) == 1
    assert offset_constraints[0].refs == [copy.entity_id, src.entity_id]


def test_offset_copy_follows_when_original_moves_control_points():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    dist = 6.0
    copy = sk.offset_entities([src.entity_id], dist)[0]
    pts_before = list(copy.points)

    sk.move_spline_point(src.entity_id, 2, (50.0, 10.0))
    assert copy.points != pts_before
    exact2 = LineString(src.get_points(64)).offset_curve(dist)
    for p in copy.get_points(64):
        assert exact2.distance(Point(p)) < max(0.1, 0.05 * abs(dist))


def test_offset_spline_protected_from_independent_modification():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0)[0]
    with pytest.raises(ValueError, match="offset spline is controlled"):
        sk.move_spline_point(copy.entity_id, 1, (10, 10))
    with pytest.raises(ValueError, match="Offset spline is linked"):
        sk.insert_spline_point(copy.entity_id, (30, 20))


def test_unlinking_offset_constraint_makes_spline_independent():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0)[0]
    offset_c = next(c for c in sk.constraints if c.ctype == "OFFSET")
    assert doc.remove_constraint(sk.sketch_id, offset_c.cid)
    assert copy.offset_info is None
    sk.move_spline_point(copy.entity_id, 1, (30.0, 35.0))
    assert copy.points[1] == (30.0, 35.0)
    copy_pts = list(copy.points)
    sk.move_spline_point(src.entity_id, 2, (50.0, 50.0))
    assert copy.points == copy_pts


def test_serialization_preserves_offset_link():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 7.0)[0]
    data = sk.to_dict()
    restored = Sketch.from_dict(data)
    r_copy = restored.get_entity(copy.entity_id)
    assert r_copy.offset_info is not None
    assert r_copy.offset_info["source_id"] == src.entity_id
    assert r_copy.offset_info["distance"] == 7.0
    r_src = restored.get_entity(src.entity_id)
    restored.move_spline_point(r_src.entity_id, 2, (50.0, 30.0))
    exact_restored = LineString(r_src.get_points(64)).offset_curve(7.0)
    for p in r_copy.get_points(64):
        assert exact_restored.distance(Point(p)) < max(0.1, 0.05 * 7.0)


def test_insert_control_point_on_original_updates_offset_copy():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0)[0]
    pts_before = list(copy.points)
    sk.insert_spline_point(src.entity_id, (35.0, 15.0))
    assert len(src.points) == 6
    assert copy.points != pts_before
    exact = LineString(src.get_points(64)).offset_curve(5.0)
    for p in copy.get_points(64):
        assert exact.distance(Point(p)) < max(0.1, 0.05 * 5.0)


def test_solver_dimension_update_propagates_to_offset_copy():
    doc = Document()
    sk = doc.start_sketch("XY")
    ref_line = sk.add_line((0, -50), (0, 50))
    src = sk.add_spline([(10, 0), (30, 20), (70, 20), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 4.0)[0]
    pts_before = list(copy.points)
    dim = sk.add_dimension("HORIZ_DIST", ref_line.entity_id, 30.0, refs=[src.entity_id], pts=["p1", "pt1"])
    assert doc.update_dimension(sk.sketch_id, dim.dim_id, 45.0)
    assert src.points[1][0] == pytest.approx(45.0)
    assert copy.points != pts_before
    exact = LineString(src.get_points(64)).offset_curve(4.0)
    for p in copy.get_points(64):
        assert exact.distance(Point(p)) < max(0.1, 0.05 * 4.0)


def test_offset_control_spline_unlinked_option():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0, link_splines=False)[0]
    assert copy.offset_info is None
    assert not any(c.ctype == "OFFSET" for c in sk.constraints)
    sk.move_spline_point(copy.entity_id, 1, (20.0, 20.0))
    assert copy.points[1] == (20.0, 20.0)
    copy_pts = list(copy.points)
    sk.move_spline_point(src.entity_id, 2, (50.0, 50.0))
    assert copy.points == copy_pts


# =========================================================================
# 3. Dimensions & Spline Solver Integration
# =========================================================================

def test_distances_from_the_origin_hold_a_spline_point_and_undo_restores_it():
    doc = _report_doc()
    sid = doc.active_sketch.sketch_id
    doc.add_dimension_constraint(sid, "HORIZ_DIST", "line_4", 100.0, refs=["spline_1"], pts=["p1", "pt2"], offset=5)
    doc.add_dimension_constraint(sid, "VERT_DIST", "line_4", 60.0, refs=["spline_1"], pts=["p1", "pt2"], offset=5)
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    assert spline.points[2] == pytest.approx((100.0, 60.0))
    assert spline.points[1] == pytest.approx((55.0, 20.0))
    assert sk.dof == 0

    assert doc.update_dimension(sid, sk.dimensions[-1].dim_id, 70.0)
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    assert spline.points[2] == pytest.approx((100.0, 70.0))

    again = Sketch.from_dict(sk.to_dict())
    assert [d.pts for d in again.dimensions[-2:]] == [["p1", "pt2"], ["p1", "pt2"]]
    doc.undo()
    doc.undo()
    doc.undo()
    assert doc.active_sketch.get_entity("spline_1").points[2] == pytest.approx((95.0, 55.0))


def test_only_dimensioned_spline_points_enter_the_solver():
    doc = _report_doc()
    sk = doc.active_sketch
    assert not {"spline_1", "spline_3"} & set(_solver_entities(sk))
    doc.add_dimension_constraint(sk.sketch_id, "HORIZ_DIST", "line_4", 100.0, refs=["spline_1"], pts=["p1", "pt2"])
    assert doc.active_sketch.dof == 1


@pytest.mark.parametrize("distance", [3.0, -3.0, 10.0])
def test_offset_of_a_control_point_spline_is_a_control_point_spline_with_as_many_points(distance):
    sk = _report_doc().active_sketch
    for eid in ("spline_1", "spline_3"):
        src = sk.get_entity(eid)
        new = sk.offset_entities([eid], distance)
        assert len(new) == 1 and isinstance(new[0], SketchSpline)
        assert new[0].control_points and len(new[0].points) == len(src.points)
        original = LineString(src.get_points(64))
        fitted = LineString(new[0].get_points(64))
        assert fitted.hausdorff_distance(original.offset_curve(distance)) < 0.05
        for p in new[0].get_points(64):
            assert original.distance(Point(p)) == pytest.approx(abs(distance), abs=0.05)


def test_offset_past_the_curvature_radius_stays_control_point_splines_without_loops():
    sk = Sketch.from_dict(_report_doc().active_sketch.to_dict())
    wavy = sk.add_spline([(0, 0), (20, 25), (40, -25), (60, 25), (80, -25), (100, 0)], control_points=True)
    for distance in (5.0, 12.0, -12.0):
        new = sk.offset_entities([wavy.entity_id], distance)
        exact = LineString(wavy.get_points(64)).offset_curve(distance)
        assert new and all(isinstance(e, SketchSpline) and e.control_points for e in new)
        assert all(LineString(e.get_points(64)).is_simple for e in new)
        joined = [p for e in new for p in e.get_points(64)]
        assert max(exact.distance(Point(p)) for p in joined) < max(0.1, 0.05 * abs(distance))
        assert sum(len(e.points) for e in new) <= len(wavy.points) + 24 * len(new)


def test_add_control_point_goes_where_the_cursor_is_and_dimensions_keep_their_point():
    doc = _report_doc()
    sid = doc.active_sketch.sketch_id
    doc.add_dimension_constraint(sid, "HORIZ_DIST", "line_4", 100.0, refs=["spline_1"], pts=["p1", "pt2"])
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    assert sk.insert_spline_point("spline_1", (80.0, 30.0)) == 2
    assert spline.control_points and spline.points[2] == (80.0, 30.0) and len(spline.points) == 5
    assert sk.dimensions[-1].pts == ["p1", "pt3"]
    assert spline.points[3] == pytest.approx((100.0, 55.0))
    assert sk.insert_spline_point("spline_1", (118.0, 100.0)) == 4


@pytest.mark.parametrize("distance", [2.0, -2.0, 5.0])
def test_closed_control_point_spline_offsets_to_a_closed_one_with_as_many_points(distance):
    sk = Sketch.from_dict(_report_doc().active_sketch.to_dict())
    loop = sk.add_spline([(0, 0), (20, -5), (30, 20), (5, 30), (-10, 15), (0, 0)], control_points=True)
    new = sk.offset_entities([loop.entity_id], distance)
    assert len(new) == 1 and new[0].control_points and len(new[0].points) == len(loop.points)
    assert new[0].points[0] == pytest.approx(new[0].points[-1])
    exact = Polygon(loop.get_points(64)).buffer(distance, join_style="mitre", mitre_limit=10.0).exterior
    assert max(exact.distance(Point(p)) for p in new[0].get_points(64)) < max(0.1, 0.05 * abs(distance))
