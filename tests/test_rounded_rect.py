"""The Rounded Rect sketch tool: corners with filleted arcs, overall dimensions, corner guides, and hole tracking."""
import math
import pytest

from shapely.geometry import Polygon

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchArc, SketchCircle, SketchLine
from omacad.model.sketch_snap import SketchSnapper


def area_of(sk):
    return sum(p.area for p in sk.profiles) if hasattr(sk.profiles[0], "area") else sk.profiles[0].polygon.area


def _make_rect(w=60, h=40, r=10):
    d = Document()
    sk = d.start_sketch("XY")
    lines = sk.add_rounded_rect((0, 0), (w, h), r)
    return d, sk, lines


def _guides(sk):
    return [e for e in sk.entities if isinstance(e, SketchLine) and e.is_construction]


def _corner_points(sk):
    return sorted({(round(g.p2[0], 6), round(g.p2[1], 6)) for g in _guides(sk)})


# =========================================================================
# 1. Basic Geometry & Formulas
# =========================================================================

@pytest.mark.parametrize("w,h,r", [(40.0, 24.0, 3.0), (30.0, 30.0, 8.0)])
def test_area_matches_formula(w, h, r):
    sk = Document().start_sketch("XY")
    sk.add_rounded_rect((0, 0), (w, h), r)
    assert len([e for e in sk.entities if e.entity_type == "arc"]) == 4
    assert len(sk.profiles) == 1
    expected = w * h - (4 - math.pi) * r * r
    assert area_of(sk) == pytest.approx(expected, rel=2e-3)


def test_radius_is_capped_by_the_short_side():
    sk = Document().start_sketch("XY")
    sk.add_rounded_rect((0, 0), (40, 10), 100.0)
    radii = [d.value for d in sk.dimensions if d.dim_type == "RADIUS"]
    assert len(radii) == 4 and all(r <= 5.0 for r in radii)


def test_undo_removes_the_whole_shape():
    d = Document()
    sk = d.start_sketch("XY")
    before = sk.to_dict()
    sk.add_rounded_rect((0, 0), (20, 20), 2.0)
    d.record_sketch_change(sk, before)
    d.undo()
    assert not sk.entities


def test_outline_preview_stays_inside_the_box():
    pts = Sketch.rounded_rect_outline((10, 5), (50, 25), 4.0)
    assert min(p[0] for p in pts) == pytest.approx(10) and max(p[0] for p in pts) == pytest.approx(50)
    assert min(p[1] for p in pts) == pytest.approx(5) and max(p[1] for p in pts) == pytest.approx(25)


def test_center_rounded_rect_is_centred_and_matches_formula():
    sk = Document().start_sketch("XY")
    sk.add_center_rounded_rect((5.0, -3.0), (25.0, 9.0), 3.0)
    assert len([e for e in sk.entities if e.entity_type == "arc"]) == 4
    poly = Polygon(sk.profiles[0].exterior_pts)
    cx, cy = poly.centroid.x, poly.centroid.y
    assert (cx, cy) == pytest.approx((5.0, -3.0), abs=1e-6)
    assert poly.area == pytest.approx(40 * 24 - (4 - math.pi) * 9.0, rel=2e-3)


# =========================================================================
# 2. Corner Guides & Snapping
# =========================================================================

def test_two_guides_per_corner_meet_at_the_sharp_corner():
    _, sk, _ = _make_rect(30, 20, 4)
    guides = _guides(sk)
    assert len(guides) == 8
    assert _corner_points(sk) == [(0, 0), (0, 20), (30, 0), (30, 20)]
    for g in guides:
        assert math.hypot(g.p2[0] - g.p1[0], g.p2[1] - g.p1[1]) == pytest.approx(4)
        assert g.p1[0] == pytest.approx(g.p2[0]) or g.p1[1] == pytest.approx(g.p2[1])
    assert not [x for x in sk.dimensions if x.dim_type == "LENGTH"]


def test_profile_is_still_the_rounded_rectangle():
    _, sk, _ = _make_rect(30, 20, 4)
    assert len(sk.profiles) == 1
    assert sk.profiles[0].area == pytest.approx(30 * 20 - (4 - math.pi) * 16, rel=1e-3)


def test_guides_follow_width_and_radius_changes():
    d, sk, _ = _make_rect(30, 20, 4)
    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 50)
    assert _corner_points(sk) == [(0, 0), (0, 20), (50, 0), (50, 20)]
    fillet = next(x for x in sk.dimensions if x.dim_type == "RADIUS")
    assert d.update_dimension(sk.sketch_id, fillet.dim_id, 6)
    arc = sk.get_entity(fillet.target_entity_id)
    for gid in arc.fillet_info["guides"]:
        g = sk.get_entity(gid)
        assert math.hypot(g.p2[0] - g.p1[0], g.p2[1] - g.p1[1]) == pytest.approx(6, abs=1e-3)
    assert _corner_points(sk) == [(0, 0), (0, 20), (50, 0), (50, 20)]


def test_sharp_corner_is_a_snap_point():
    _, sk, _ = _make_rect(30, 20, 4)
    snap = SketchSnapper.snap(raw_uv=(29.6, 19.7), sketch=sk, snap_distance=1.0, grid_step=5.0,
                              enable_grid_snap=False, enable_geom_snap=True)
    assert snap.uv == pytest.approx((30, 20))


# =========================================================================
# 3. Overall Sizing & Wall Tracking
# =========================================================================

def test_dimensions_are_the_overall_size():
    _, sk, _ = _make_rect(60, 40, 10)
    by = {x.name: x for x in sk.dimensions}
    assert by["Width"].dim_type == "PT_LINE_DIST" and by["Width"].value == pytest.approx(60)
    assert by["Height"].dim_type == "PT_LINE_DIST" and by["Height"].value == pytest.approx(40)
    assert not [x for x in sk.dimensions if x.dim_type == "LENGTH"]


def test_changing_the_width_keeps_radii_and_moves_the_hole_with_its_wall():
    d, sk, lines = _make_rect(60, 40, 10)
    left = lines[3]
    c = sk.add_circle((15, 30), 5)
    d.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 15, refs=[left.entity_id], pts=["center"])
    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 90)
    xs = [e.p1[0] for e in sk.entities if isinstance(e, SketchLine)] + [e.p2[0] for e in sk.entities if isinstance(e, SketchLine)]
    assert max(xs) - min(xs) == pytest.approx(90, abs=1e-3)
    arcs = [e for e in sk.entities if isinstance(e, SketchArc)]
    assert len(arcs) == 4
    for a in arcs:
        assert a.get_circle_params()[1] == pytest.approx(10.0, abs=1e-3)
    assert abs(c.center[0] - left.p1[0]) == pytest.approx(15.0, abs=1e-3)


def test_a_hole_measured_from_the_far_wall_and_the_top_follows_height_and_width():
    d, sk, lines = _make_rect(60, 40, 10)
    bottom, right, top, left = lines
    c = sk.add_circle((50, 30), 4)
    d.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 10, refs=[right.entity_id], pts=["center"])
    d.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", c.entity_id, 10, refs=[top.entity_id], pts=["center"])
    for name, val in (("Width", 100), ("Height", 70)):
        dim = next(x for x in sk.dimensions if x.name == name)
        assert d.update_dimension(sk.sketch_id, dim.dim_id, val)
    assert abs(right.p1[0] - c.center[0]) == pytest.approx(10, abs=1e-3)
    assert abs(top.p1[1] - c.center[1]) == pytest.approx(10, abs=1e-3)
    assert abs(right.p1[0] - left.p1[0]) == pytest.approx(100, abs=1e-3)
    assert abs(top.p1[1] - bottom.p1[1]) == pytest.approx(70, abs=1e-3)


def test_widening_keeps_the_arcs_joined_to_the_walls():
    d, sk, _ = _make_rect(60, 40, 10)
    width = next(x for x in sk.dimensions if x.name == "Width")
    assert d.update_dimension(sk.sketch_id, width.dim_id, 90)
    ends = [p for e in sk.entities if isinstance(e, SketchLine) for p in (e.p1, e.p2)]
    for arc in (e for e in sk.entities if isinstance(e, SketchArc)):
        assert arc.get_circle_params()[1] == pytest.approx(10)
        for p in (arc.p_start, arc.p_end):
            assert min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in ends) < 1e-6
    assert len(sk.profiles) == 1
    assert sk.profiles[0].area == pytest.approx(90 * 40 - (4 - math.pi) * 100, rel=2e-3)
