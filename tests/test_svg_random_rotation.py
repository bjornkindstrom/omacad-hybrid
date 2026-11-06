"""Surface Texture › Cells › SVG: every cell can turn by its own random angle, and the wall between cells stays."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import itertools
import math

import manifold3d as m3d
import pytest
from PySide6.QtWidgets import QApplication
from shapely import affinity

from omacad.model.features.honeycomb import HoneycombFeature, lattice
from omacad.model.document import Document
from omacad.ui.dialogs import SurfaceTextureDialog

# a long thin bar: the shape that collides first when it turns in a grid fitted to it unturned
BAR = """<svg xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0" width="100" height="20"/></svg>"""
BOUNDS = (-40.0, -40.0, 40.0, 40.0)
SIZE, WALL = 10.0, 1.0


@pytest.fixture
def bar(tmp_path):
    path = tmp_path / "bar.svg"
    path.write_text(BAR)
    return str(path)


def _cells(bar, turn, seed=1, bounds=BOUNDS, period=None):
    return lattice("svg", SIZE, WALL, 0.0, bounds, (0.0, 0.0), period, 100.0, seed, bar, turn)


def _direction(cell):
    """The bar's long side as an angle in [0, 180)."""
    x, y = cell.minimum_rotated_rectangle.exterior.xy
    sides = [(x[i + 1] - x[i], y[i + 1] - y[i]) for i in (0, 1)]
    dx, dy = max(sides, key=lambda s: s[0] ** 2 + s[1] ** 2)
    return math.degrees(math.atan2(dy, dx)) % 180.0


def _centre(cell):
    return cell.centroid.x, cell.centroid.y


def test_no_random_rotation_keeps_the_cells_as_they_were(bar):
    assert {round(_direction(c), 6) % 180.0 for c in _cells(bar, 0.0)} <= {0.0, 180.0}
    assert all(a.equals(b) for a, b in zip(_cells(bar, 0.0, seed=1), _cells(bar, 0.0, seed=99)))


@pytest.mark.parametrize("limit", [5.0, 30.0, 90.0, 180.0])
def test_turned_cells_keep_the_wall_between_them(bar, limit):
    cells = _cells(bar, limit)
    assert len(cells) > 4
    assert min(a.distance(b) for a, b in itertools.combinations(cells, 2)) >= WALL - 1e-2


def test_the_turn_stays_within_the_limit_and_differs_per_cell(bar):
    cells = _cells(bar, 20.0)
    folded = [d - 180.0 if d > 90.0 else d for d in map(_direction, cells)]     # the bar is the same at 0 and 180
    assert max(abs(d) for d in folded) <= 20.0 + 1e-6
    assert len({round(d, 1) for d in folded}) > 0.5 * len(folded)
    assert max(folded) - min(folded) > 20.0                                     # both ways, not one
    # the random numbers alone would draw alike for the cells at (i, j) and (-i, -j)
    turns = {tuple(round(v, 6) + 0.0 for v in _centre(c)): d for c, d in zip(cells, folded)}
    alike = [c for c, d in turns.items() if (c[0] or c[1]) and abs(turns[(-c[0] + 0.0, -c[1] + 0.0)] - d) < 1e-6]
    assert not alike


def test_the_seed_chooses_the_turns_and_rebuilds_alike(bar):
    first = _cells(bar, 180.0, seed=1)
    assert all(a.equals(b) for a, b in zip(first, _cells(bar, 180.0, seed=1)))
    assert not all(a.equals(b) for a, b in zip(first, _cells(bar, 180.0, seed=2)))


def test_a_cell_keeps_its_turn_when_the_face_grows(bar):
    small = {tuple(round(v, 6) for v in _centre(c)): _direction(c) for c in _cells(bar, 180.0)}
    large = {tuple(round(v, 6) for v in _centre(c)): _direction(c) for c in _cells(bar, 180.0, bounds=(-80, -80, 80, 80))}
    assert len(large) > len(small)
    for centre, direction in small.items():
        assert large[centre] == pytest.approx(direction)


def test_turned_cells_close_round_a_cylinder_with_the_wall_kept(bar):
    period = 100.0
    cells = _cells(bar, 180.0, bounds=(-50.0, -8.0, 50.0, 8.0), period=period)
    assert cells
    wrapped = cells + [affinity.translate(c, period) for c in cells] + [affinity.translate(c, -period) for c in cells]
    assert min(a.distance(b) for a, b in itertools.combinations(wrapped, 2)) >= WALL - 1e-2


def test_through_cut_removes_exactly_the_turned_cells(bar):
    side, height = 80.0, 3.0
    solid = m3d.Manifold.cube((side, side, height), True)
    ref = {"kind": "plane", "origin": [0.0, 0.0, height / 2.0], "normal": [0.0, 0.0, 1.0]}
    params = {"shape": "svg", "svg_path": bar, "size": SIZE, "wall": WALL, "margin": 3.0, "depth": 1.0, "through": True,
              "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 4, "style": "even", "fine_size": 2.0,
              "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0, "opening_end": 100.0,
              "relaxation": 0, "hole": "cell", "random_rotation": 180.0}
    result, count, skipped = HoneycombFeature.compute(solid, [ref], params)
    assert skipped == 0 and count > 0
    assert solid.volume() - result.volume() == pytest.approx(count * SIZE * (SIZE / 5.0) * height, rel=1e-3)


def test_the_setting_is_saved_and_old_steps_have_none():
    feature = HoneycombFeature("h", "Cells 1", "b", random_rotation=45.0)
    assert feature.params()["random_rotation"] == 45.0
    assert HoneycombFeature("h", "Cells 1", "b").random_rotation == 0.0
    assert "random_rotation" in HoneycombFeature.PARAMS


def test_the_panel_offers_it_only_for_svg_cells_and_reads_it_back():
    QApplication.instance() or QApplication([])
    dlg = SurfaceTextureDialog(Document(), feature=HoneycombFeature("h", "Cells 1", "b", shape="svg", svg_path="x.svg",
                                                                    random_rotation=33.0, seed=7))
    dlg.show()
    page = dlg.pages["honeycomb"] if hasattr(dlg, "pages") else dlg.page
    assert page.spins["random_rotation"].isVisible() and page.spins["seed"].isVisible()
    assert page.params()["random_rotation"] == 33.0 and page.params()["seed"] == 7
    page.cmb_shape.setCurrentIndex(0)
    assert not page.spins["random_rotation"].isVisible() and not page.spins["seed"].isVisible()
    dlg.close()
