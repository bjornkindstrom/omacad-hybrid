"""Voronoi styles, Relaxation, Hole shape, Rounding and Opening: exact walls, sizes and volumes, closed round a cylinder."""
import json
import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import manifold3d as m3d
import numpy as np
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shapely import affinity
from shapely.geometry import box
from shapely.strtree import STRtree

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.cell_patterns import VORONOI_STYLES, finish_cells, hotspot_positions, voronoi_cells
from omacad.model.features.honeycomb import HoneycombFeature, best_fit

HERE = os.path.dirname(__file__)
ROOM = box(-47.0, -47.0, 47.0, 47.0)
P = dict(shape="voronoi", size=7.0, wall=1.2, margin=3.0, depth=1.0, through=True, angle=0.0, partial=False, randomness=100.0, seed=1,
         fine_size=2.0, inner_wall=0.6)
STYLED = [dict(style="gradient"), dict(style="hotspot"), dict(style="hotspot", hotspots=3), dict(style="radial"),
          dict(style="nested", size=16.0, fine_size=2.5), dict(style="triangles", fine_size=3.0), dict(relaxation=5)]
PLATE = m3d.Manifold.cube((100.0, 100.0, 2.0), True)
PLATE_REF = {"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, 1.0]}
R, H = 25.0, 60.0
TUBE = m3d.Manifold.cylinder(H, R, R, 256) - m3d.Manifold.cylinder(H + 2.0, R - 3.0, R - 3.0, 256).translate((0, 0, -1))
TUBE_REF = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": R, "length": H, "internal": False}


def cells_of(**over):
    return best_fit({**P, **over}, ROOM, (0.0, 0.0))


def smallest_gap(cells):
    tree = STRtree(cells)
    gap = math.inf
    for i, cell in enumerate(cells):
        for j in tree.query(cell.buffer(3.0)):
            if int(j) != i:
                gap = min(gap, cell.distance(cells[int(j)]))
    return gap


def median_area(cells, low, high):
    return float(np.median([c.area for c in cells if low <= c.centroid.y <= high]))


def test_the_defaults_change_nothing():
    plain = voronoi_cells(P["size"], P["wall"], 0.0, ROOM.bounds, (0.0, 0.0))
    made = cells_of()
    assert len(made) > 100 and sum(c.area for c in made) == pytest.approx(
        sum(c.area for c in plain if ROOM.contains(c)))
    cells = [box(0, 0, 1, 1)]
    assert finish_cells(cells, P, ROOM.bounds, (0.0, 0.0)) is cells


@pytest.mark.parametrize("over", [s for s in STYLED if s.get("style") != "nested"])
def test_every_style_keeps_the_wall_between_its_cells(over):
    cells = cells_of(**over)
    assert len(cells) > 50
    assert smallest_gap(cells) >= P["wall"] - 1e-6


def test_gradient_goes_from_the_smallest_cell_at_the_bottom_to_cell_size_at_the_top():
    cells = cells_of(style="gradient", randomness=0.0)
    hexagon = lambda across: math.sqrt(3.0) / 2.0 * across * across
    assert median_area(cells, -47.0, -40.0) == pytest.approx(hexagon(2.2), rel=0.35)      # just above the finest (2 mm)
    assert median_area(cells, 35.0, 47.0) == pytest.approx(hexagon(6.5), rel=0.35)        # nearly Cell size


def test_rotation_turns_the_gradient():
    flipped = cells_of(style="gradient", angle=180.0, randomness=0.0)
    assert median_area(flipped, -47.0, -35.0) > 2.0 * median_area(flipped, 35.0, 47.0)
    sideways = cells_of(style="gradient", angle=90.0, randomness=0.0)      # up is now -x
    right = np.median([c.area for c in sideways if c.centroid.x > 30.0])
    left = np.median([c.area for c in sideways if c.centroid.x < -30.0])
    assert left > 2.0 * right


def test_hotspot_cells_are_smallest_round_the_spot_and_grow_outward():
    cells = cells_of(style="hotspot")
    near = [c.area for c in cells if math.hypot(c.centroid.x, c.centroid.y) < 8.0]
    far = [c.area for c in cells if math.hypot(c.centroid.x, c.centroid.y) > 35.0]
    assert np.median(far) > 4.0 * np.median(near)


def test_further_hotspots_come_from_the_seed_and_the_first_stays_in_the_middle():
    spots = hotspot_positions(dict(hotspots=3, seed=1), ROOM.bounds, (0.0, 0.0))
    assert len(spots) == 3 and spots[0] == (0.0, 0.0)
    assert all(ROOM.contains(box(x, y, x + 1e-6, y + 1e-6)) for x, y in spots)
    assert spots != hotspot_positions(dict(hotspots=3, seed=2), ROOM.bounds, (0.0, 0.0))
    assert len(cells_of(style="hotspot", hotspots=3)) > len(cells_of(style="hotspot"))


def test_radial_cells_grow_with_the_radius_on_rings_round_the_middle():
    cells = cells_of(style="radial", randomness=0.0)
    near = [c.area for c in cells if math.hypot(c.centroid.x, c.centroid.y) < 15.0]
    far = [c.area for c in cells if math.hypot(c.centroid.x, c.centroid.y) > 35.0]
    assert np.median(far) > 2.0 * np.median(near)
    radii = sorted(round(math.hypot(c.centroid.x, c.centroid.y), 0) for c in cells)
    assert len(set(radii)) < 0.25 * len(radii)      # few distinct radii: they lie on rings


def test_nested_cells_stay_inside_big_cells_with_their_thick_walls_unbroken():
    parents = voronoi_cells(16.0, 1.2, 0.0, ROOM.bounds, (0.0, 0.0), None, 100.0, 1)
    cells = best_fit({**P, "style": "nested", "size": 16.0, "fine_size": 2.5, "partial": True}, ROOM, (0.0, 0.0))
    assert len(cells) > 3 * len([p for p in parents if ROOM.contains(p)])
    tree = STRtree(parents)
    for cell in cells:
        hit = tree.query(cell.buffer(-1e-6), predicate="within")
        assert len(hit) == 1
    assert smallest_gap(cells) >= 0.6 - 1e-6


def test_triangles_are_triangles():
    cells = cells_of(style="triangles", fine_size=3.0)
    assert len(cells) > 100
    assert all(len(c.exterior.coords) == 4 for c in cells)


def test_relaxation_evens_the_cells_out_and_rebuilds_alike():
    spread = lambda cells: float(np.std([c.area for c in cells]) / np.mean([c.area for c in cells]))
    assert spread(cells_of(relaxation=10)) < 0.6 * spread(cells_of())
    a, b = cells_of(relaxation=5), cells_of(relaxation=5)
    assert [c.wkb for c in a] == [c.wkb for c in b]
    assert [c.wkb for c in a] != [c.wkb for c in cells_of(relaxation=5, seed=2)]


@pytest.mark.parametrize("over", STYLED)
def test_every_style_closes_round_a_cylinder_without_overlap(over):
    period = 2.0 * math.pi * R
    room = box(-period, 3.0, 2.0 * period, H - 3.0)
    cells = best_fit({**P, **over, "partial": True}, room, (period / 2.0, H / 2.0), period)
    assert len(cells) > 50
    assert all(-20.0 <= c.centroid.x <= period + 20.0 for c in cells)      # about one turn; a cell may lie over the seam
    tiled = cells + [affinity.translate(c, period) for c in cells] + [affinity.translate(c, -period) for c in cells]
    tree = STRtree(tiled)
    for i, cell in enumerate(cells):
        for j in tree.query(cell, predicate="intersects"):
            assert int(j) == i or cell.intersection(tiled[int(j)]).area < 1e-6


@pytest.mark.parametrize("over", STYLED + [dict(hole="circle", opening=25.0, opening_end=90.0), dict(rounding=80.0)])
def test_a_plate_loses_exactly_the_cells_area_through_its_thickness(over):
    params = {**P, **over}
    solid, count, skipped = HoneycombFeature.compute(PLATE, [PLATE_REF], params)
    cells = best_fit(params, box(-47.0, -47.0, 47.0, 47.0), (0.0, 0.0))
    assert skipped == 0 and count == len(cells) > 10
    assert PLATE.volume() - solid.volume() == pytest.approx(sum(c.area for c in cells) * 2.0, rel=1e-6)
    assert solid.genus() == count and len(solid.decompose()) == 1


def test_opening_scales_each_hole_and_fades_across_the_face():
    full = cells_of()
    half = cells_of(opening=50.0, opening_end=50.0)
    assert len(half) == len(full)
    assert sum(c.area for c in half) == pytest.approx(sum(c.area for c in full) / 4.0)
    assert all(a.buffer(1e-6).contains(b) or a.intersection(b).area > 0.99 * b.area for a, b in zip(full, half))
    faded = cells_of(opening=20.0, opening_end=100.0)
    share = [b.area / a.area for a, b in zip(full, faded)]
    ys = [a.centroid.y for a in full]
    assert np.corrcoef(ys, share)[0, 1] > 0.9
    assert min(share) == pytest.approx(0.2 ** 2, abs=0.03) and max(share) == pytest.approx(1.0, abs=0.1)
    assert cells_of(opening=0.0, opening_end=0.0) == []


def test_rounding_keeps_every_cell_inside_its_own_and_100_is_close_to_a_circle():
    full = cells_of()
    rounded = cells_of(rounding=100.0)
    assert len(rounded) == len(full)         # also the long thin cells survive
    assert sum(c.area for c in rounded) < sum(c.area for c in full)
    for a, b in zip(full, rounded):
        assert a.buffer(1e-3).contains(b)


@pytest.mark.parametrize("hole, corners", [("square", 4), ("triangle", 3), ("pentagon", 5), ("hexagon", 6), ("octagon", 8), ("star", 10)])
def test_hole_shapes_have_their_corners_and_stay_inside_their_cells(hole, corners):
    full = cells_of()
    holes = cells_of(hole=hole)
    assert len(holes) == len(full)
    for a, b in zip(full, holes):
        assert len(b.exterior.coords) == corners + 1
        assert a.buffer(1e-3).contains(b)


def test_a_circle_hole_is_the_largest_circle_in_its_cell_and_opening_sets_its_size():
    cell = box(0.0, 0.0, 20.0, 10.0)
    circle = finish_cells([cell], {"hole": "circle"}, (0, 0, 20, 10), (10, 5))[0]
    assert circle.area == pytest.approx(math.pi * 25.0, rel=0.01)
    half = finish_cells([cell], {"hole": "circle", "opening": 50.0, "opening_end": 50.0}, (0, 0, 20, 10), (10, 5))[0]
    assert half.area == pytest.approx(circle.area / 4.0, rel=1e-6)
    hexagon = finish_cells([box(0, 0, 10, 10)], {"hole": "hexagon"}, (0, 0, 10, 10), (5, 5))[0]
    assert hexagon.area == pytest.approx(1.5 * math.sqrt(3.0) * 25.0, rel=0.01)


@pytest.mark.parametrize("over", [dict(style="gradient"), dict(style="radial"), dict(style="triangles", fine_size=3.0),
                                  dict(hole="circle", opening=30.0, opening_end=90.0)])
def test_a_tube_gets_a_clean_cut_all_the_way_round(over):
    solid, count, skipped = HoneycombFeature.compute(TUBE, [TUBE_REF], {**P, **over, "partial": False})
    assert skipped == 0 and count > 20
    assert solid.status() == m3d.Error.NoError
    assert solid.genus() == TUBE.genus() + count and len(solid.decompose()) == 1


@pytest.fixture(scope="module")
def pot():
    QApplication.instance() or QApplication([])
    doc = Document()
    with open(os.path.join(HERE, "data", "voronoi_pot.omacad"), encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    index, feat = next((i, f) for i, f in enumerate(doc.timeline.features) if f.feature_type == "honeycomb")
    doc.timeline.marker_index = index
    doc.timeline.recompute(doc)
    return doc.bodies[feat.target_body_id].manifold, feat.faces


@pytest.mark.parametrize("over", [dict(style="gradient"), dict(style="hotspot"), dict(style="radial"), dict(style="triangles", fine_size=4.0),
                                  dict(relaxation=3), dict(hole="circle", opening=40.0, opening_end=90.0)])
def test_the_pot_takes_every_style_as_one_piece(pot, over):
    solid, faces = pot
    result, count, skipped = HoneycombFeature.compute(solid, faces, {**P, "size": 6.0, "wall": 1.5, "margin": 4.0, **over})
    assert skipped == 0 and count > 40
    assert result.status() == m3d.Error.NoError
    assert len(result.decompose()) == 1


def test_too_many_cells_say_so_in_the_panel_instead_of_only_no_room():
    from omacad.ui.dialogs.surface_texture_dlg import preview_texture
    _solid, info = preview_texture("honeycomb", PLATE, [PLATE_REF], {**P, "size": 0.15, "wall": 0.1, "style": "gradient", "fine_size": 0.1})
    assert "too many" in info


def test_settings_are_saved_and_older_files_get_the_defaults():
    QApplication.instance() or QApplication([])
    doc = Document()
    body = doc.add_box(60, 60, 2)
    face = max(body.faces, key=lambda f: f.normal[2])
    from omacad.model.features.offset_face import plane_face_ref
    feat = doc.add_honeycomb(body.body_id, [plane_face_ref(face)], **{**P, "style": "gradient", "hole": "star", "relaxation": 3, "rounding": 20.0,
                                                                     "opening": 80.0, "opening_end": 60.0, "fine_size": 3.0, "hotspots": 2})
    volume = doc.bodies[body.body_id].manifold.volume()
    copy = Document()
    Exporter.apply_dict(copy, Exporter.document_to_dict(doc))
    copy.timeline.recompute(copy)
    again = next(f for f in copy.timeline.features if f.feature_type == "honeycomb")
    assert (again.style, again.hole, again.relaxation, again.rounding, again.opening, again.opening_end, again.fine_size, again.hotspots) == (
        "gradient", "star", 3, 20.0, 80.0, 60.0, 3.0, 2)
    assert copy.bodies[body.body_id].manifold.volume() == pytest.approx(volume)
    assert doc.edit_feature(doc.timeline.features.index(feat), style="radial")
    assert doc.bodies[body.body_id].manifold.volume() != pytest.approx(volume)

    data = {k: v for k, v in feat.to_dict().items() if k in ("shape", "size", "wall")}
    old = HoneycombFeature("f", "C", "b", **data)
    assert (old.style, old.hole, old.relaxation, old.rounding, old.opening, old.opening_end) == ("even", "cell", 0, 0.0, 100.0, 100.0)
    assert HoneycombFeature("f", "C", "b", style="nope", hole="nope").style == "even"
    assert all(s in VORONOI_STYLES for s in ("even", "gradient", "hotspot", "radial", "nested", "triangles"))


def test_the_docked_panel_shows_the_fields_of_the_chosen_style(tmp_path):
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    win.doc.add_box(40, 30, 20)
    win.prompt_surface_texture()
    dlg = win.inspector.current_tool_dlg
    QTest.qWait(50)
    page = dlg.pages["honeycomb"]
    seen = lambda key: page.spins[key].isVisible()
    assert page.cmb_hole.isVisible() and seen("opening") and seen("opening_end") and seen("rounding")      # any cell shape
    assert not page.cmb_style.isVisible() and not seen("relaxation") and not seen("fine_size")
    page.cmb_shape.setCurrentText("Voronoi")
    assert page.cmb_style.isVisible() and seen("relaxation") and seen("seed") and not seen("fine_size")
    page.cmb_style.setCurrentText("Gradient")
    assert seen("fine_size") and not seen("inner_wall") and not seen("hotspots")
    page.cmb_style.setCurrentText("Hotspot")
    assert seen("hotspots")
    page.cmb_style.setCurrentText("Nested")
    assert seen("inner_wall") and not seen("hotspots")
    page.cmb_style.setCurrentText("Radial")
    assert not seen("relaxation")
    page.cmb_hole.setCurrentText("Star")
    params = dlg.params()
    assert (params["style"], params["hole"]) == ("radial", "star")
    dlg.reject()
    win.close()
