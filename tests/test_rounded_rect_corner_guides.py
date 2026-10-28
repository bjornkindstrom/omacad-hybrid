"""A rounded rectangle gets construction lines from its sides out to the sharp corners, where they meet:
snap points for a pivot. They follow when the size or the radius changes (the fillet re-seats them) and never become part of the profile."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchLine
from omacad.model.sketch_snap import SketchSnapper


def _make():
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (30, 20), 4)
    return d, sk


def _guides(sk):
    return [e for e in sk.entities if isinstance(e, SketchLine) and e.is_construction]


def _corner_points(sk):
    return sorted({(round(g.p2[0], 6), round(g.p2[1], 6)) for g in _guides(sk)})


def test_two_guides_per_corner_meet_at_the_sharp_corner():
    _, sk = _make()
    guides = _guides(sk)
    assert len(guides) == 8
    assert _corner_points(sk) == [(0, 0), (0, 20), (30, 0), (30, 20)]
    for g in guides:
        assert math.hypot(g.p2[0] - g.p1[0], g.p2[1] - g.p1[1]) == pytest.approx(4)   # tangent point to corner
        assert g.p1[0] == pytest.approx(g.p2[0]) or g.p1[1] == pytest.approx(g.p2[1])  # along its side
    assert not [x for x in sk.dimensions if x.dim_type == "LENGTH"]


def test_profile_is_still_the_rounded_rectangle():
    _, sk = _make()
    assert len(sk.profiles) == 1
    assert sk.profiles[0].area == pytest.approx(30 * 20 - (4 - math.pi) * 16, rel=1e-3)


def test_guides_follow_width_and_radius_changes():
    d, sk = _make()
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
    _, sk = _make()
    snap = SketchSnapper.snap(raw_uv=(29.6, 19.7), sketch=sk, snap_distance=1.0, grid_step=5.0,
                              enable_grid_snap=False, enable_geom_snap=True)
    assert snap.uv == pytest.approx((30, 20))
