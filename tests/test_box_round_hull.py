"""Box with an outer round: the rounded corners are the hull of balls, not a stack of slabs.

Report 20261031-091740: changing the box's Outer round in the browser rebuilt a stepped, very heavy solid
(~20k triangles with dark slab ridges) where the Fillet tool gives a smooth, light one.
"""
import math
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.features.primitives import BoxFeature

DOC = Path(__file__).parent / "data" / "box_outer_round_browser.omacad"


def _rounded_box_volume(L, W, H, r):
    """Steiner formula for a box with every edge rounded to r (rolling ball)."""
    a, b, c = L - 2 * r, W - 2 * r, H - 2 * r
    return a * b * c + 2 * r * (a * b + b * c + c * a) + math.pi * r * r * (a + b + c) + 4 / 3 * math.pi * r**3


@pytest.mark.parametrize("r", [2.0, 5.0, 10.0])
def test_outer_round_volume_matches_the_rolling_ball_shape(r):
    solid = BoxFeature("b", "b", 50.0, 50.0, 25.0, center="bottom_center", outer_round=r).build_solid()
    assert solid.volume() == pytest.approx(_rounded_box_volume(50, 50, 25, r), rel=1e-3)
    assert solid.genus() == 0
    assert solid.bounding_box() == pytest.approx((-25, -25, 0, 25, 25, 25))


def test_outer_round_is_light_and_smooth_not_a_stack_of_slabs():
    solid = BoxFeature("b", "b", 50.0, 50.0, 25.0, center="bottom_center", outer_round=2.0).build_solid()
    assert solid.num_tri() < 6000   # the stepped build had ~19 000 triangles here


def test_report_document_rebuilds_the_box_light():
    doc = Exporter.load_project(str(DOC))
    body = doc.bodies["body_box_1"]
    assert body.manifold.volume() == pytest.approx(61159, rel=2e-3)
    assert body.manifold.num_tri() < 8000   # the report's model had 20 326 triangles
