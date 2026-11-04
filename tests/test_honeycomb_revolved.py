"""Honeycomb on a surface of revolution: the whole wall of a pot gets cells, of even size for Voronoi, and only that wall."""
import json
import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import manifold3d as m3d
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from shapely.geometry import box

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.honeycomb import HoneycombFeature, fit_cells, revolved_voronoi_cells
from omacad.model.features.knurl import apply_knurl
from omacad.model.features.offset_face import _frame
from omacad.model.features.revolved_surface import RevolvedSurface, revolved_surface

HERE = os.path.dirname(__file__)
P = dict(shape="voronoi", size=5.0, wall=1.5, margin=0.0, depth=1.0, through=True, angle=0.0, partial=True,
         randomness=100.0, seed=1)


@pytest.fixture(scope="module")
def pot():
    """The pot from the report, before its Honeycomb step: (shelled solid, the picked face)."""
    QApplication.instance() or QApplication([])
    doc = Document()
    with open(os.path.join(HERE, "data", "voronoi_pot.omacad"), encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    index, feat = next((i, f) for i, f in enumerate(doc.timeline.features) if f.feature_type == "honeycomb")
    doc.timeline.marker_index = index
    doc.timeline.recompute(doc)
    return doc.bodies[feat.target_body_id].manifold, feat.faces[0]


def surface_of(pot):
    solid, ref = pot
    return revolved_surface(solid, _frame(ref["origin"], ref["axis"]), ref)


def holes_by_height(solid, base, heights):
    """Material removed from the section at each height."""
    return [base.slice(z).area() - solid.slice(z).area() for z in heights]


def test_the_pot_is_read_as_a_revolved_wall_from_its_foot_to_its_rim(pot):
    surface = surface_of(pot)
    assert surface is not None and not surface.internal
    assert surface.R == pytest.approx(39.6, abs=0.1)
    assert surface.z[0] < 1.0 and surface.z[-1] > 74.0
    assert surface.r.min() < 5.0        # the pointed foot


def test_cells_cover_the_whole_wall_and_every_one_is_a_hole(pot):
    solid, ref = pot
    result, cells, skipped = HoneycombFeature.compute(solid, [ref], P)
    assert skipped == 0 and cells > 200
    assert result.status() == m3d.Error.NoError
    assert len(result.decompose()) == 1             # no skins or loose pieces left behind
    # the report: only two bands near the belly had cells; now the neck, shoulder and lower wall do too
    removed = holes_by_height(result, solid, (8.0, 15.0, 25.0, 35.0, 45.0, 55.0, 65.0))
    assert min(removed) > 5.0, removed

    whole, count, _ = HoneycombFeature.compute(solid, [ref], dict(P, margin=3.0, partial=False))
    assert count > 200 and len(whole.decompose()) == 1
    assert whole.genus() == solid.genus() + count   # whole cells inside a margin: each is one clean hole, none merge


def test_voronoi_cells_keep_their_true_size_and_wall_up_the_pot(pot):
    surface = surface_of(pot)
    low, high = surface.usable(6.5)
    room = box(-surface.period, surface.y_at(low), 2.0 * surface.period, surface.y_at(high))
    cells = fit_cells(revolved_voronoi_cells(surface, low, high, 5.0, 1.5), room, False)
    assert len(cells) > 200
    scale = np.array([float(surface.scale_at_y(c.centroid.y)) for c in cells])
    areas = np.array([c.area for c in cells]) * scale ** 2
    wide, narrow = areas[scale > 0.9], areas[(scale > 0.3) & (scale < 0.65)]
    assert len(wide) > 20 and len(narrow) > 20
    assert np.median(narrow) == pytest.approx(np.median(wide), rel=0.3)  # the same size in the neck as on the belly

    gaps = []
    for i, a in enumerate(cells):
        for b in cells[i + 1:i + 40]:
            d = a.distance(b)
            if d * scale[i] < 3.0:
                gaps.append(d * (scale[i] + float(surface.scale_at_y(b.centroid.y))) / 2.0)
    assert np.median(gaps) == pytest.approx(1.5, rel=0.1)
    assert min(gaps) > 1.0


def test_a_cut_stays_in_the_wall_and_the_floor_is_not_crossed(pot):
    solid, ref = pot
    result, _, _ = HoneycombFeature.compute(solid, [ref], P)
    surface = surface_of(pot)
    # the wall is all that was cut: nothing further in than the inner surface, at any height
    for z in (20.0, 40.0, 60.0):
        inner = [np.asarray(r) for r in solid.slice(z).to_polygons() if len(r) > 3]
        hollow = min(np.hypot(*r.T).max() for r in inner)
        kept = [np.hypot(*np.asarray(r).T).min() for r in result.slice(z).to_polygons()]
        assert min(kept) >= hollow * 0.97, z
    bottom = result.slice(0.3).area()
    assert bottom == pytest.approx(solid.slice(0.3).area(), rel=1e-6)       # around the point stays closed
    assert surface.usable(6.5)[0] > surface.s[0]


def test_a_fixed_depth_stays_a_skin_on_the_surface(pot):
    solid, ref = pot
    result, cells, _ = HoneycombFeature.compute(solid, [ref], dict(P, through=False, depth=0.4, margin=3.0))
    assert cells > 200
    assert len(result.decompose()) == 1
    assert result.genus() == solid.genus()          # no cell goes through
    assert 0 < solid.volume() - result.volume() < 0.4 * 20000.0


def test_lattice_shapes_follow_the_wall_too(pot):
    solid, ref = pot
    result, cells, skipped = HoneycombFeature.compute(solid, [ref], dict(P, shape="hexagon"))
    assert skipped == 0 and cells > 50
    assert min(holes_by_height(result, solid, (15.0, 35.0, 65.0))) > 1.0


def test_the_same_settings_rebuild_alike(pot):
    solid, ref = pot
    assert (HoneycombFeature.compute(solid, [ref], P)[0].volume()
            == pytest.approx(HoneycombFeature.compute(solid, [ref], P)[0].volume()))
    assert (HoneycombFeature.compute(solid, [ref], dict(P, seed=2))[0].volume()
            != pytest.approx(HoneycombFeature.compute(solid, [ref], P)[0].volume()))


def test_knurl_refuses_such_a_face_instead_of_cutting_a_groove(pot):
    solid, ref = pot
    result, teeth, notes = apply_knurl(solid, [ref], dict(pattern="diamond", pitch=1.5, depth=0.6, angle=30.0, margin=0.0))
    assert teeth == 0 and "radius changes" in notes[0]
    assert result.volume() == pytest.approx(solid.volume())


def test_a_true_cylinder_is_not_a_revolved_surface_even_with_a_rounded_end():
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 15.0, "length": 40.0, "internal": False}
    M = _frame(ref["origin"], ref["axis"])
    pin = m3d.Manifold.cylinder(40.0, 15.0, 15.0, 180)
    assert revolved_surface(pin, M, ref) is None
    rounded = m3d.Manifold.cylinder(36.0, 15.0, 15.0, 180) + (
        m3d.Manifold.sphere(15.0, 180).scale((1.0, 1.0, 4.0 / 15.0)).translate((0.0, 0.0, 36.0)))
    assert revolved_surface(rounded, M, ref) is None


def test_a_cone_maps_lengths_along_the_slant():
    """A cone's flat pattern is known: y = R·ln(s)/sin(half angle) up to a constant, scale = r/R."""
    profile = np.column_stack((np.linspace(10.0, 30.0, 201), np.linspace(0.0, 20.0, 201)))
    surface = RevolvedSurface(profile, False)
    length = 20.0 * math.sqrt(2.0)
    assert surface.s[-1] == pytest.approx(length)
    assert surface.y[-1] == pytest.approx(30.0 * math.sqrt(2.0) * math.log(3.0), rel=1e-4)
    assert surface.scale_at_y(surface.y[0]) == pytest.approx(10.0 / 30.0)
    point, normal = surface.centre(0.0, surface.y_at(length / 2.0))
    assert point == pytest.approx([20.0, 0.0, 10.0])
    assert normal == pytest.approx([math.sqrt(0.5), 0.0, -math.sqrt(0.5)])
