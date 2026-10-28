"""The Rounded Rect tool makes a rectangle with filleted corners in one step."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import Sketch


def area_of(sk):
    return sum(p.area for p in sk.profiles) if hasattr(sk.profiles[0], "area") else sk.profiles[0].polygon.area


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
    sk.add_center_rounded_rect((5.0, -3.0), (25.0, 9.0), 3.0)  # 40 x 24 around (5, -3)
    assert len([e for e in sk.entities if e.entity_type == "arc"]) == 4
    from shapely.geometry import Polygon
    poly = Polygon(sk.profiles[0].exterior_pts)
    cx, cy = poly.centroid.x, poly.centroid.y
    assert (cx, cy) == pytest.approx((5.0, -3.0), abs=1e-6)
    assert poly.area == pytest.approx(40 * 24 - (4 - math.pi) * 9.0, rel=2e-3)
