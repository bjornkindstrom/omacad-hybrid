"""Fill pattern: regular polygons of 3..8 sides get a tight lattice with exactly `gap` mm between neighbours."""
import math

import pytest
from shapely import affinity
from shapely.geometry import Polygon

from omacad.model.timeline import _best_pattern


def regular(n, r=10.0, rot=0.0):
    return Polygon([(r * math.cos(rot + 2 * math.pi * k / n), r * math.sin(rot + 2 * math.pi * k / n)) for k in range(n)])


def cell_area_per_copy(foot, gap):
    members, v1, v2 = _best_pattern(foot, gap)
    return abs(v1[0] * v2[1] - v1[1] * v2[0]) / len(members), members, v1, v2


@pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize("rot", [0.0, 0.3])
def test_lattice_keeps_gap_and_does_not_overlap(n, rot):
    foot, gap = regular(n, rot=rot), 2.0
    _, members, v1, v2 = cell_area_per_copy(foot, gap)
    c = foot.centroid
    inv = affinity.rotate(foot, 180, origin=(c.x, c.y))
    shapes = []
    for i in range(-2, 3):
        for j in range(-2, 3):
            for turned, off in members:
                shapes.append(affinity.translate(inv if turned else foot, i * v1[0] + j * v2[0] + off[0], i * v1[1] + j * v2[1] + off[1]))
    for a in range(len(shapes)):
        for b in range(a + 1, len(shapes)):
            assert shapes[a].distance(shapes[b]) >= 2.0 - 1e-4


def test_square_is_a_square_grid_and_hexagon_a_honeycomb():
    gap = 2.0
    sq = regular(4, rot=math.pi / 4)             # 14.14 mm square
    side = sq.bounds[2] - sq.bounds[0]
    area, *_ = cell_area_per_copy(sq, gap)
    assert area == pytest.approx((side + gap) ** 2, rel=5e-3)
    hx = regular(6)
    apothem = 10.0 * math.cos(math.pi / 6)
    area, *_ = cell_area_per_copy(hx, gap)
    assert area == pytest.approx((2 * apothem + gap) ** 2 * math.sqrt(3) / 2, rel=5e-3)


@pytest.mark.parametrize("n", [3, 5])
def test_odd_polygons_pair_up_with_a_turned_copy(n):
    area, members, *_ = cell_area_per_copy(regular(n), 1.0)
    assert len(members) == 2


@pytest.mark.parametrize("sides", [3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize("mode", ["stagger", "triangular"])
def test_fill_a_plate_with_polygon_holes(sides, mode):
    import numpy as np
    from omacad.model.document import Document
    from omacad.model.sketch import SketchPlane
    d = Document()
    d.add_box(80, 80, 5)
    d.auto_include_edges = False
    sk = d.start_sketch_on_plane(SketchPlane.from_face(np.array([0., 0, 1]), np.array([0., 0, 5])))
    sk.add_polygon((12, 12), (12 + 5, 12), sides)
    d.finish_sketch()
    d.extrude_profile(list(d.sketches)[-1], 0, -3, "cut")
    d.timeline.recompute(d)
    ext = [f for f in d.timeline.features if f.feature_type == "extrude"][-1]
    d.add_pattern([ext.feature_id], kind="fill", spacing1=2.0, spacing2=3.0, count1=0.0, mirror_mode=mode)
    feat = d.timeline.features[-1]
    body = next(iter(d.bodies.values()))
    rem, _ = feat.compute(d, body.body_id)
    pieces = rem.decompose()
    assert len(pieces) >= 12
    from shapely.geometry import Polygon
    polys = [Polygon(max(p.project().to_polygons(), key=len)) for p in pieces]
    for a in range(len(polys)):
        for b in range(a + 1, len(polys)):
            assert polys[a].distance(polys[b]) >= 2.0 - 1e-3
