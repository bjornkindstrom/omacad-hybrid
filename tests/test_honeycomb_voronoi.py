"""Honeycomb's Voronoi cells: exact sizes and walls, stable layouts, a closed pattern round a cylinder, saved settings."""
import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import manifold3d as m3d
import pytest
from PySide6.QtWidgets import QApplication
from shapely import affinity
from shapely.geometry import box
from shapely.ops import unary_union

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.honeycomb import HoneycombFeature, VORONOI_MIN_AREA, lattice, voronoi_cells

HEX = math.sqrt(3) / 2 * 6.0 ** 2          # hexagon 6 mm across flats
P = dict(shape="voronoi", size=6.0, wall=1.5, margin=3.0, depth=1.0, through=True, angle=0.0, partial=False,
         randomness=100.0, seed=1)
PLATE = m3d.Manifold.cube((80, 60, 2))
TOP = {"kind": "plane", "normal": [0, 0, 1], "origin": [40, 30, 2]}
BOUNDS = (0.0, 0.0, 80.0, 60.0)


def key(cell):
    return tuple(round(v, 6) for v in cell.bounds)


def test_no_randomness_gives_hexagons_of_exactly_the_cell_size():
    cells = voronoi_cells(6.0, 1.5, 0.0, BOUNDS, (40.0, 30.0), randomness=0.0)
    inner = [c for c in cells if box(*BOUNDS).contains(c)]
    assert len(inner) > 40
    assert [c.area for c in inner] == pytest.approx([HEX] * len(inner), rel=1e-9)


@pytest.mark.parametrize("seed", [1, 2, 77])
def test_neighbouring_cells_keep_the_wall_and_no_cell_is_a_speck(seed):
    cells = voronoi_cells(6.0, 1.5, 0.0, BOUNDS, (40.0, 30.0), seed=seed)
    assert all(c.area >= VORONOI_MIN_AREA * 36.0 for c in cells)
    near = [(a, b) for i, a in enumerate(cells) for b in cells[i + 1:] if a.distance(b) < 3.0]
    assert near
    assert min(a.distance(b) for a, b in near) == pytest.approx(1.5, abs=1e-6)


def test_cells_are_really_irregular_and_average_the_requested_size():
    cells = [c for c in voronoi_cells(6.0, 0.0, 0.0, BOUNDS, (40.0, 30.0)) if box(*BOUNDS).contains(c)]
    areas = [c.area for c in cells]
    assert max(areas) > 1.3 * min(areas)
    assert sum(areas) / len(areas) == pytest.approx(HEX, rel=0.05)     # one site per lattice cell of the same area


def test_the_same_seed_rebuilds_alike_and_another_seed_does_not():
    a = lattice("voronoi", 6.0, 1.5, 0.0, BOUNDS, (40.0, 30.0))
    assert [key(c) for c in a] == [key(c) for c in lattice("voronoi", 6.0, 1.5, 0.0, BOUNDS, (40.0, 30.0))]
    assert {key(c) for c in a} != {key(c) for c in lattice("voronoi", 6.0, 1.5, 0.0, BOUNDS, (40.0, 30.0), seed=2)}


def test_a_larger_face_keeps_the_cells_it_already_had():
    """The body grows: the layout must not reshuffle."""
    small = voronoi_cells(6.0, 1.5, 0.0, (20.0, 15.0, 60.0, 45.0), (40.0, 30.0))
    large = {key(c) for c in voronoi_cells(6.0, 1.5, 0.0, (0.0, 0.0, 80.0, 60.0), (40.0, 30.0))}
    inner = [c for c in small if box(25.0, 20.0, 55.0, 40.0).contains(c)]
    assert inner and all(key(c) in large for c in inner)


def test_rotation_turns_the_whole_layout_about_the_anchor():
    plain = voronoi_cells(6.0, 1.5, 0.0, BOUNDS, (40.0, 30.0))
    turned = voronoi_cells(6.0, 1.5, 30.0, BOUNDS, (40.0, 30.0))
    target = {tuple(round(v, 4) for v in affinity.rotate(c, 30.0, origin=(40.0, 30.0)).bounds) for c in plain}
    near_centre = [c for c in turned if c.centroid.distance(box(35.0, 25.0, 45.0, 35.0)) < 1e-9]
    assert near_centre and all(tuple(round(v, 4) for v in c.bounds) in target for c in near_centre)


def test_too_many_cells_are_refused():
    with pytest.raises(ValueError, match="too many"):
        voronoi_cells(0.1, 0.0, 0.0, (0.0, 0.0, 1000.0, 1000.0), (500.0, 500.0))


def test_plate_loses_exactly_the_cells():
    m, n, skipped = HoneycombFeature.compute(PLATE, [TOP], P)
    assert skipped == 0 and n > 20
    assert m.genus() == n                                           # every cell a hole, none merged
    room = box(3.0, 3.0, 77.0, 57.0)
    cells = [c for c in voronoi_cells(6.0, 1.5, 0.0, room.bounds, (40.0, 30.0)) if room.contains(c)]
    assert len(cells) == n
    assert PLATE.volume() - m.volume() == pytest.approx(sum(c.area for c in cells) * 2.0, rel=1e-6)


def test_pattern_closes_round_a_cylinder_without_a_seam():
    period = 2 * math.pi * 15.0
    z = (0.0, 0.0, period, 40.0)
    cells = voronoi_cells(6.0, 1.5, 0.0, z, (period / 2.0, 20.0), period=period)
    # the next turn of the same pattern fits the gaps: every cell keeps the wall to every copy
    copies = [affinity.translate(c, period, 0.0) for c in cells] + [affinity.translate(c, -period, 0.0) for c in cells]
    together = cells + copies
    assert unary_union(together).area == pytest.approx(sum(c.area for c in together), rel=1e-9)
    tail = [c for c in cells if c.bounds[2] > period - 8.0]
    assert min(a.distance(b) for a in tail for b in copies if a.distance(b) < 3.0) == pytest.approx(1.5, abs=1e-6)


def test_round_wall_of_a_cup_gets_whole_holes():
    QApplication.instance() or QApplication([])
    doc = Document()
    cup = doc.add_cylinder(15, 40, wall_thickness=2).manifold
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 15.0, "length": 40.0, "internal": False}
    m, n, skipped = HoneycombFeature.compute(cup, [ref], P)
    assert skipped == 0 and n > 5
    assert m.genus() == cup.genus() + n
    assert m.volume() < cup.volume()


def test_settings_survive_save_edit_and_undo():
    QApplication.instance() or QApplication([])
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


def test_panel_shows_randomness_and_seed_only_for_voronoi():
    from omacad.model.document import Document
    from omacad.ui.dialogs import SurfaceTextureDialog
    from omacad.model.features.honeycomb import SHAPES
    QApplication.instance() or QApplication([])
    dlg = SurfaceTextureDialog(Document())
    dlg.show()
    page = dlg.pages["honeycomb"]
    assert not page.spins["randomness"].isVisible() and not page.spins["seed"].isVisible()
    page.cmb_shape.setCurrentIndex(SHAPES.index("voronoi"))
    assert page.spins["randomness"].isVisible() and page.spins["seed"].isVisible()
    page.spins["seed"].setValue(5)
    params = dlg.params()
    assert (params["shape"], params["seed"], params["randomness"]) == ("voronoi", 5.0, 100.0)
    dlg.close()
