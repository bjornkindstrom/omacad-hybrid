"""Honeycomb / Surface Texture (Cells) feature tests: lattices, Voronoi, revolved surfaces, and cup axes."""
import json
import math
import os
from pathlib import Path

import manifold3d as m3d
import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces_hit_tests import detect_cylinder_surface
from omacad.model.features.cell_patterns import VORONOI_MIN_AREA
from omacad.model.features.honeycomb import (
    SHAPES,
    HoneycombFeature,
    fit_cells,
    lattice,
    revolved_voronoi_cells,
    voronoi_cells,
)
from omacad.model.features.knurl import apply_knurl
from omacad.model.features.offset_face import _frame
from omacad.model.features.revolved_surface import RevolvedSurface, revolved_surface

DATA_DIR = Path(__file__).parent / "data"
HEX = math.sqrt(3) / 2 * 6.0**2
P = dict(shape="hexagon", size=6.0, wall=1.5, margin=3.0, depth=1.0, through=True, angle=0.0, partial=False)
PLATE = m3d.Manifold.cube((40, 30, 2))
TOP = {"kind": "plane", "normal": [0, 0, 1], "origin": [20, 15, 2]}


# =========================================================================
# 1. Basic Shapes & Plates
# =========================================================================

@pytest.mark.parametrize("shape, cells, area", [
    ("hexagon", 11, HEX), ("circle", 11, None), ("square", 12, 36.0), ("diamond", 8, 36.0),
    ("triangle", 8, math.sqrt(3) / 4 * (6.0 * math.sqrt(3))**2)])
def test_plate_through_every_shape(shape, cells, area):
    m, n, skipped = HoneycombFeature.compute(PLATE, [TOP], dict(P, shape=shape))
    assert (n, skipped) == (cells, 0)
    assert m.genus() == cells
    if area is not None:
        assert PLATE.volume() - m.volume() == pytest.approx(cells * area * 2.0, rel=1e-6)


def _doc_box():
    doc = Document()
    body = doc.add_box(40, 30, 20, wall_thickness=2)
    return doc, body


def test_through_a_box_wall_leaves_the_opposite_wall():
    _, body = _doc_box()
    front = {"kind": "plane", "normal": [0, -1, 0], "origin": [20, 0, 10]}
    m, n, _ = HoneycombFeature.compute(body.manifold, [front], P)
    assert n > 0
    assert body.manifold.volume() - m.volume() == pytest.approx(n * HEX * 2.0, rel=1e-6)
    back = m3d.Manifold.cube((40, 2, 20)).translate((0, 28, 0))
    assert (m ^ back).volume() == pytest.approx((body.manifold ^ back).volume(), rel=1e-9)


def test_fixed_depth_does_not_pierce():
    _, body = _doc_box()
    front = {"kind": "plane", "normal": [0, -1, 0], "origin": [20, 0, 10]}
    m, n, _ = HoneycombFeature.compute(body.manifold, [front], dict(P, through=False, depth=1.0))
    assert body.manifold.volume() - m.volume() == pytest.approx(n * HEX * 1.0, rel=1e-6)
    assert m.genus() == body.manifold.genus()


def test_round_wall_of_a_cup_all_the_way_round():
    doc = Document()
    cup = doc.add_cylinder(15, 40, wall_thickness=2).manifold
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 15.0, "length": 40.0, "internal": False}
    m, n, skipped = HoneycombFeature.compute(cup, [ref], P)
    assert skipped == 0 and n % 12 == 0
    assert m.genus() == cup.genus() + n
    assert cup.volume() - m.volume() == pytest.approx(n * HEX * (15**2 - 13**2) / 30.0, rel=0.02)
    bottom = m3d.Manifold.cube((40, 40, 2)).translate((-20, -20, 0))
    assert (m ^ bottom).volume() == pytest.approx((cup ^ bottom).volume(), rel=1e-9)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("angle", [0.0, 90.0])
def test_lattice_closes_round_a_cylinder_without_overlap(shape, angle):
    circ = 2 * math.pi * 15.0
    cells = lattice(shape, 6.0, 1.5, angle, (0, 0, circ, 30), (circ / 2, 15), period=circ)
    copies = cells + [affinity.translate(c, circ) for c in cells]
    gaps = [a.distance(b) for i, a in enumerate(copies) for b in copies[i + 1:] if a.distance(b) < 1.4]
    assert not gaps
    assert unary_union(cells).area == pytest.approx(sum(c.area for c in cells), rel=1e-9)


def test_document_save_load_and_undo(tmp_path):
    doc, body = _doc_box()
    v0 = body.manifold.volume()
    front = {"kind": "plane", "normal": [0, -1, 0], "origin": [20, 0, 10]}
    feat = doc.add_honeycomb(body.body_id, [front], **dict(P, shape="square"))
    v1 = doc.bodies[body.body_id].manifold.volume()
    assert v0 - v1 == pytest.approx(feat.cells * 36.0 * 2.0, rel=1e-6)
    path = tmp_path / "honeycomb.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    assert next(iter(again.bodies.values())).manifold.volume() == pytest.approx(v1, rel=1e-9)
    idx = doc.timeline.features.index(feat)
    assert doc.edit_feature(idx, shape="hexagon")
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(v0 - feat.cells * HEX * 2.0, rel=1e-6)
    doc.undo()
    doc.undo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(v0, rel=1e-9)


# =========================================================================
# 2. Filleted Cup Axis Detection & Penetration Depths
# =========================================================================

def _cup():
    doc = Exporter.load_project(str(DATA_DIR / "honeycomb_filleted_cup.omacad"))
    honey = doc.timeline.features[1]
    honey.suppressed = True
    doc.timeline.recompute(doc)
    return doc, honey


def test_the_wall_beside_a_fillet_is_picked_with_its_true_axis():
    doc, _ = _cup()
    mesh = doc.bodies["body_cylinder_1"].render_mesh
    tri = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    for deg in (0, 67, 200):
        d = np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0])
        i = int(np.flatnonzero((nrm @ d > 0.99) & (np.abs(nrm[:, 2]) < 1e-6))[0])
        cyl = detect_cylinder_surface(mesh, i)
        assert cyl["axis"] == pytest.approx([0, 0, 1], abs=1e-6)
        assert cyl["origin"] == pytest.approx([0, 0, 2], abs=1e-6)
        assert cyl["radius"] == pytest.approx(20.0, abs=1e-5)


def test_saved_leaning_axis_still_cuts_every_cell_through_the_wall_only():
    doc, honey = _cup()
    before = doc.bodies["body_cylinder_1"].manifold.volume()
    honey.suppressed = False
    doc.timeline.recompute(doc)
    m = doc.bodies["body_cylinder_1"].manifold
    assert honey.cells == 64
    assert m.genus() == 64
    assert before - m.volume() == pytest.approx(64 * HEX * (20**2 - 18**2) / (2 * 20), rel=2e-3)


def test_through_from_inside_the_material_stops_where_it_ends():
    import omacad.model.features.honeycomb as H
    doc, _ = _cup()
    rays = H._Rays(doc.bodies["body_cylinder_1"].manifold)
    d = H._depths([np.array([19.8, 0.0, 20.0])], [np.array([-1.0, 0.0, 0.0])], rays, None)[0]
    assert d == pytest.approx(1.8 + H.OVERSHOOT, abs=0.02)


# =========================================================================
# 3. Voronoi Cells (Randomness, Sizing, Bounds & Cylinder Seams)
# =========================================================================

VORONOI_P = dict(shape="voronoi", size=6.0, wall=1.5, margin=3.0, depth=1.0, through=True, angle=0.0, partial=False,
                 randomness=100.0, seed=1)
VORONOI_PLATE = m3d.Manifold.cube((80, 60, 2))
VORONOI_TOP = {"kind": "plane", "normal": [0, 0, 1], "origin": [40, 30, 2]}
VORONOI_BOUNDS = (0.0, 0.0, 80.0, 60.0)


def _voronoi_key(cell):
    return tuple(round(v, 6) for v in cell.bounds)


def test_no_randomness_gives_hexagons_of_exactly_the_cell_size():
    cells = voronoi_cells(6.0, 1.5, 0.0, VORONOI_BOUNDS, (40.0, 30.0), randomness=0.0)
    inner = [c for c in cells if box(*VORONOI_BOUNDS).contains(c)]
    assert len(inner) > 40
    assert [c.area for c in inner] == pytest.approx([HEX] * len(inner), rel=1e-9)


@pytest.mark.parametrize("seed", [1, 2, 77])
def test_neighbouring_cells_keep_the_wall_and_no_cell_is_a_speck(seed):
    cells = voronoi_cells(6.0, 1.5, 0.0, VORONOI_BOUNDS, (40.0, 30.0), seed=seed)
    assert all(c.area >= VORONOI_MIN_AREA * 36.0 for c in cells)
    near = [(a, b) for i, a in enumerate(cells) for b in cells[i + 1:] if a.distance(b) < 3.0]
    assert near
    assert min(a.distance(b) for a, b in near) == pytest.approx(1.5, abs=1e-6)


def test_cells_are_really_irregular_and_average_the_requested_size():
    cells = [c for c in voronoi_cells(6.0, 0.0, 0.0, VORONOI_BOUNDS, (40.0, 30.0)) if box(*VORONOI_BOUNDS).contains(c)]
    areas = [c.area for c in cells]
    assert max(areas) > 1.3 * min(areas)
    assert sum(areas) / len(areas) == pytest.approx(HEX, rel=0.05)


def test_the_same_seed_rebuilds_alike_and_another_seed_does_not():
    a = lattice("voronoi", 6.0, 1.5, 0.0, VORONOI_BOUNDS, (40.0, 30.0))
    assert [_voronoi_key(c) for c in a] == [_voronoi_key(c) for c in lattice("voronoi", 6.0, 1.5, 0.0, VORONOI_BOUNDS, (40.0, 30.0))]
    assert {_voronoi_key(c) for c in a} != {_voronoi_key(c) for c in lattice("voronoi", 6.0, 1.5, 0.0, VORONOI_BOUNDS, (40.0, 30.0), seed=2)}


def test_a_larger_face_keeps_the_cells_it_already_had():
    small = voronoi_cells(6.0, 1.5, 0.0, (20.0, 15.0, 60.0, 45.0), (40.0, 30.0))
    large = {_voronoi_key(c) for c in voronoi_cells(6.0, 1.5, 0.0, (0.0, 0.0, 80.0, 60.0), (40.0, 30.0))}
    inner = [c for c in small if box(25.0, 20.0, 55.0, 40.0).contains(c)]
    assert inner and all(_voronoi_key(c) in large for c in inner)


def test_rotation_turns_the_whole_layout_about_the_anchor():
    plain = voronoi_cells(6.0, 1.5, 0.0, VORONOI_BOUNDS, (40.0, 30.0))
    turned = voronoi_cells(6.0, 1.5, 30.0, VORONOI_BOUNDS, (40.0, 30.0))
    target = {tuple(round(v, 4) for v in affinity.rotate(c, 30.0, origin=(40.0, 30.0)).bounds) for c in plain}
    near_centre = [c for c in turned if c.centroid.distance(box(35.0, 25.0, 45.0, 35.0)) < 1e-9]
    assert near_centre and all(tuple(round(v, 4) for v in c.bounds) in target for c in near_centre)


def test_too_many_cells_are_refused():
    with pytest.raises(ValueError, match="too many"):
        voronoi_cells(0.1, 0.0, 0.0, (0.0, 0.0, 1000.0, 1000.0), (500.0, 500.0))


def test_voronoi_plate_loses_exactly_the_cells():
    m, n, skipped = HoneycombFeature.compute(VORONOI_PLATE, [VORONOI_TOP], VORONOI_P)
    assert skipped == 0 and n > 20
    assert m.genus() == n
    room = box(3.0, 3.0, 77.0, 57.0)
    cells = [c for c in voronoi_cells(6.0, 1.5, 0.0, room.bounds, (40.0, 30.0)) if room.contains(c)]
    assert len(cells) == n
    assert VORONOI_PLATE.volume() - m.volume() == pytest.approx(sum(c.area for c in cells) * 2.0, rel=1e-6)


def test_pattern_closes_round_a_cylinder_without_a_seam():
    period = 2 * math.pi * 15.0
    z = (0.0, 0.0, period, 40.0)
    cells = voronoi_cells(6.0, 1.5, 0.0, z, (period / 2.0, 20.0), period=period)
    copies = [affinity.translate(c, period, 0.0) for c in cells] + [affinity.translate(c, -period, 0.0) for c in cells]
    together = cells + copies
    assert unary_union(together).area == pytest.approx(sum(c.area for c in together), rel=1e-9)
    tail = [c for c in cells if c.bounds[2] > period - 8.0]
    assert min(a.distance(b) for a in tail for b in copies if a.distance(b) < 3.0) == pytest.approx(1.5, abs=1e-6)


def test_round_wall_of_a_cup_gets_whole_holes():
    doc = Document()
    cup = doc.add_cylinder(15, 40, wall_thickness=2).manifold
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 15.0, "length": 40.0, "internal": False}
    m, n, skipped = HoneycombFeature.compute(cup, [ref], VORONOI_P)
    assert skipped == 0 and n > 5
    assert m.genus() == cup.genus() + n
    assert m.volume() < cup.volume()


def test_voronoi_settings_survive_save_edit_and_undo():
    doc = Document()
    body = doc.add_box(80, 60, 2)
    faces = [{"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, 2]}]
    feat = doc.add_honeycomb(body.body_id, faces, shape="voronoi", size=6.0, wall=1.5, randomness=70.0, seed=9)
    assert feat.cells > 0
    made = doc.bodies[body.body_id].manifold.volume()

    copy = Document()
    Exporter.apply_dict(copy, Exporter.document_to_dict(doc))
    copy.timeline.recompute(copy)
    again = next(f for f in copy.timeline.features if f.feature_type == "honeycomb")
    assert (again.shape, again.randomness, again.seed) == ("voronoi", 70.0, 9)
    assert copy.bodies[body.body_id].manifold.volume() == pytest.approx(made)

    assert doc.edit_feature(doc.timeline.features.index(feat), seed=10)
    assert doc.bodies[body.body_id].manifold.volume() != pytest.approx(made)
    doc.undo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(made)


def test_a_file_saved_before_voronoi_keeps_its_cells():
    feat = HoneycombFeature("f", "H", "b", shape="hexagon")
    data = {k: v for k, v in feat.to_dict().items() if k not in ("randomness", "seed")}
    old = HoneycombFeature("f", "H", "b", **{k: data[k] for k in HoneycombFeature.PARAMS if k in data})
    assert old.shape == "hexagon" and old.randomness == 100.0 and old.seed == 1


# =========================================================================
# 4. Revolved Surfaces & Pots
# =========================================================================

POT_P = dict(shape="voronoi", size=5.0, wall=1.5, margin=0.0, depth=1.0, through=True, angle=0.0, partial=True,
             randomness=100.0, seed=1)


@pytest.fixture(scope="module")
def pot():
    doc = Document()
    with open(DATA_DIR / "voronoi_pot.omacad", encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    index, feat = next((i, f) for i, f in enumerate(doc.timeline.features) if f.feature_type == "honeycomb")
    doc.timeline.marker_index = index
    doc.timeline.recompute(doc)
    return doc.bodies[feat.target_body_id].manifold, feat.faces[0]


def _surface_of(pot):
    solid, ref = pot
    return revolved_surface(solid, _frame(ref["origin"], ref["axis"]), ref)


def _holes_by_height(solid, base, heights):
    return [base.slice(z).area() - solid.slice(z).area() for z in heights]


def test_the_pot_is_read_as_a_revolved_wall_from_its_foot_to_its_rim(pot):
    surface = _surface_of(pot)
    assert surface is not None and not surface.internal
    assert surface.R == pytest.approx(39.6, abs=0.1)
    assert surface.z[0] < 1.0 and surface.z[-1] > 74.0
    assert surface.r.min() < 5.0


def test_cells_cover_the_whole_wall_and_every_one_is_a_hole(pot):
    solid, ref = pot
    result, cells, skipped = HoneycombFeature.compute(solid, [ref], POT_P)
    assert skipped == 0 and cells > 200
    assert result.status() == m3d.Error.NoError
    assert len(result.decompose()) == 1
    removed = _holes_by_height(result, solid, (8.0, 15.0, 25.0, 35.0, 45.0, 55.0, 65.0))
    assert min(removed) > 5.0, removed

    whole, count, _ = HoneycombFeature.compute(solid, [ref], dict(POT_P, margin=3.0, partial=False))
    assert count > 200 and len(whole.decompose()) == 1
    assert whole.genus() == solid.genus() + count


def test_voronoi_cells_keep_their_true_size_and_wall_up_the_pot(pot):
    surface = _surface_of(pot)
    low, high = surface.usable(6.5)
    room = box(-surface.period, surface.y_at(low), 2.0 * surface.period, surface.y_at(high))
    cells = fit_cells(revolved_voronoi_cells(surface, low, high, 5.0, 1.5), room, False)
    assert len(cells) > 200
    scale = np.array([float(surface.scale_at_y(c.centroid.y)) for c in cells])
    areas = np.array([c.area for c in cells]) * scale**2
    wide, narrow = areas[scale > 0.9], areas[(scale > 0.3) & (scale < 0.65)]
    assert len(wide) > 20 and len(narrow) > 20
    assert np.median(narrow) == pytest.approx(np.median(wide), rel=0.3)

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
    result, _, _ = HoneycombFeature.compute(solid, [ref], POT_P)
    surface = _surface_of(pot)
    for z in (20.0, 40.0, 60.0):
        inner = [np.asarray(r) for r in solid.slice(z).to_polygons() if len(r) > 3]
        hollow = min(np.hypot(*r.T).max() for r in inner)
        kept = [np.hypot(*np.asarray(r).T).min() for r in result.slice(z).to_polygons()]
        assert min(kept) >= hollow * 0.97, z
    bottom = result.slice(0.3).area()
    assert bottom == pytest.approx(solid.slice(0.3).area(), rel=1e-6)
    assert surface.usable(6.5)[0] > surface.s[0]


def test_a_fixed_depth_stays_a_skin_on_the_surface(pot):
    solid, ref = pot
    result, cells, _ = HoneycombFeature.compute(solid, [ref], dict(POT_P, through=False, depth=0.4, margin=3.0))
    assert cells > 200
    assert len(result.decompose()) == 1
    assert result.genus() == solid.genus()
    assert 0 < solid.volume() - result.volume() < 0.4 * 20000.0


def test_lattice_shapes_follow_the_wall_too(pot):
    solid, ref = pot
    result, cells, skipped = HoneycombFeature.compute(solid, [ref], dict(POT_P, shape="hexagon"))
    assert skipped == 0 and cells > 50
    assert min(_holes_by_height(result, solid, (15.0, 35.0, 65.0))) > 1.0


def test_the_same_settings_rebuild_alike(pot):
    solid, ref = pot
    assert (HoneycombFeature.compute(solid, [ref], POT_P)[0].volume()
            == pytest.approx(HoneycombFeature.compute(solid, [ref], POT_P)[0].volume()))
    assert (HoneycombFeature.compute(solid, [ref], dict(POT_P, seed=2))[0].volume()
            != pytest.approx(HoneycombFeature.compute(solid, [ref], POT_P)[0].volume()))


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
    profile = np.column_stack((np.linspace(10.0, 30.0, 201), np.linspace(0.0, 20.0, 201)))
    surface = RevolvedSurface(profile, False)
    length = 20.0 * math.sqrt(2.0)
    assert surface.s[-1] == pytest.approx(length)
    assert surface.y[-1] == pytest.approx(30.0 * math.sqrt(2.0) * math.log(3.0), rel=1e-4)
    assert surface.scale_at_y(surface.y[0]) == pytest.approx(10.0 / 30.0)
    point, normal = surface.centre(0.0, surface.y_at(length / 2.0))
    assert point == pytest.approx([20.0, 0.0, 10.0])
    assert normal == pytest.approx([math.sqrt(0.5), 0.0, -math.sqrt(0.5)])
