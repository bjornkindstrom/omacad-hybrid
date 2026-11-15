"""SVG import, curve precision, sketch entities, and SVG cell texture patterns."""
import itertools
import json
import math
import tempfile
from pathlib import Path

import manifold3d as m3d
import pytest
from PySide6.QtWidgets import QApplication
from shapely import affinity
from shapely.geometry import LineString, Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.extrude import ExtrudeFeature
from omacad.model.features.honeycomb import HoneycombFeature, lattice
from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchLine, SketchSpline
from omacad.model.svg_importer import (
    arc_to_cubics,
    parse_svg_to_geometry,
    parse_svg_to_sketch_entities,
    svg_to_template,
)
from omacad.ui.dialogs import SurfaceTextureDialog
from tests.test_curved_surface_texture import _build_spline_wall_doc

# =========================================================================
# Sample SVGs
# =========================================================================

SVG_SAMPLE = """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="10" width="80" height="80"/>
  <circle cx="50" cy="50" r="15"/>
</svg>"""

SVG_STAR = """<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <polygon points="50,5 64,36 98,36 70,57 81,91 50,70 19,91 30,57 2,36 36,36"/>
</svg>"""

BAT = """<svg viewBox="0 -3.5 39 39" xmlns="http://www.w3.org/2000/svg">
<path d="M19.5 4.25c-10.77 0-19.5 5.261-19.5 11.75s8.73 11.75 19.5 11.75 19.5-5.261 19.5-11.75-8.73-11.75-19.5-11.75zM30.555 23.53c0 0.062 1.951-2.357 0.39-3.981-1.874-2.124-5.116 1.056-5.116 1.056-2.562-5.059-6.424 3.145-6.424 3.145s-3.348-7.731-6.221-3.047c0.062 0-2.383-2.793-4.819-1.481-1.749 1.749 0 4.091 0 4.091-9.119-3.186-9.712-12.492 2.952-16.286-3.576 4.481 6.59 10.649 5.84-0.344l2.155 1.89c0 0 2.171-1.796 2.171-1.921-0.25 10.993 9.369 4.544 6.121 0.484 11.429 3.308 13.381 11.21 2.951 16.394z"/>
</svg>"""

FIRST_CURVE = ((19.5, 4.25), (8.73, 4.25), (0.0, 9.511), (0.0, 16.0))


def _sketch(svg, **kwargs):
    sketch = Sketch("s", "S", SketchPlane.create_named("XY"))
    sketch.entities.extend(parse_svg_to_sketch_entities(svg, **kwargs))
    sketch.solve_profiles()
    return sketch


def _bezier(points, t):
    p0, c1, c2, p3 = points
    s = 1.0 - t
    return tuple(s**3 * a + 3 * s * s * t * b + 3 * s * t * t * c + t**3 * d for a, b, c, d in zip(p0, c1, c2, p3))


# =========================================================================
# 1. Parsing & Bezier Curve Precision
# =========================================================================

def test_svg_geometry_parsing():
    geom = parse_svg_to_geometry(SVG_SAMPLE)
    assert geom is not None
    assert geom.area > 0
    assert 5500 < geom.area < 6000

    polys, (w, h) = svg_to_template(geom, 20.0)
    assert len(polys) == 1
    assert max(w, h) == 20.0


def test_svg_import_to_sketch():
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(SVG_SAMPLE)
        f.flush()
        doc = Document()
        sketch = Exporter.import_svg_to_sketch(f.name, doc)
        assert sketch is not None
        assert len(sketch.entities) > 0
        assert len(sketch.profiles) == 2


def test_the_sketch_holds_one_curve_per_bezier_and_the_files_straight_line():
    entities = parse_svg_to_sketch_entities(BAT)
    assert sum(isinstance(e, SketchSpline) for e in entities) == 15
    assert sum(isinstance(e, SketchLine) for e in entities) == 1


def test_a_spline_is_the_files_bezier_exactly():
    spline = parse_svg_to_sketch_entities(BAT)[0]
    m1, m2 = spline.tangents[0], spline.tangents[1]
    p1, p2 = spline.points
    for t in (0.0, 0.2, 0.5, 0.77, 1.0):
        x, y = _bezier(FIRST_CURVE, t)
        h00, h10, h01, h11 = 2 * t**3 - 3 * t * t + 1, t**3 - 2 * t * t + t, -2 * t**3 + 3 * t * t, t**3 - t * t
        assert h00 * p1[0] + h10 * m1[0] + h01 * p2[0] + h11 * m2[0] == pytest.approx(x, abs=1e-9)
        assert h00 * p1[1] + h10 * m1[1] + h01 * p2[1] + h11 * m2[1] == pytest.approx(-y, abs=1e-9)


def test_scale_and_origin_move_the_curve_with_its_tangents():
    plain = parse_svg_to_sketch_entities(BAT)[0]
    moved = parse_svg_to_sketch_entities(BAT, origin=(5.0, -7.0), scale=2.0)[0]
    assert moved.points[0] == pytest.approx((plain.points[0][0] * 2 + 5, plain.points[0][1] * 2 - 7))
    assert moved.tangents[0] == pytest.approx((plain.tangents[0][0] * 2, plain.tangents[0][1] * 2))


def test_the_curve_on_screen_lies_within_the_chord_error_and_has_no_corners():
    entities = parse_svg_to_sketch_entities(BAT)
    points = entities[0].get_points()
    exact = [_bezier(FIRST_CURVE, i / 2000) for i in range(2001)]
    exact = [(x, -y) for x, y in exact]
    assert LineString(points).hausdorff_distance(LineString(exact)) < 0.006
    steps = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(points, points[1:])]
    turns = [abs((b - a + math.pi) % (2 * math.pi) - math.pi) for a, b in zip(steps, steps[1:])]
    assert max(turns) < math.radians(6.0)


def test_the_logo_makes_its_two_profiles_with_the_true_area():
    sketch = _sketch(BAT)
    assert len(sketch.profiles) == 2
    ellipse = math.pi * 19.5 * 11.75
    outer = max(sketch.profiles, key=lambda p: p.area)
    inner = min(sketch.profiles, key=lambda p: p.area)
    assert Polygon(outer.exterior_pts).area == pytest.approx(ellipse, rel=1e-3)
    assert outer.area + inner.area == pytest.approx(ellipse, rel=1e-3)
    assert inner.area == pytest.approx(ellipse - 364.88, rel=2e-3)


def test_the_curves_survive_saving():
    sketch = _sketch(BAT)
    again = Sketch.from_dict(json.loads(json.dumps(sketch.to_dict())))
    again.solve_profiles()
    assert [p.area for p in again.profiles] == pytest.approx([p.area for p in sketch.profiles])


def test_the_filled_geometry_does_not_shrink_on_a_small_viewbox():
    assert parse_svg_to_geometry(BAT).area == pytest.approx(364.88, rel=2e-3)


@pytest.mark.parametrize("scale", [0.1, 1.0, 100.0])
def test_a_circle_is_round_at_any_size(scale):
    r = 15.0 * scale
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"><circle cx="{50 * scale}" cy="{50 * scale}" r="{r}"/></svg>'
    assert parse_svg_to_geometry(svg).area == pytest.approx(math.pi * r * r, rel=2e-3)
    assert all(isinstance(e, SketchSpline) for e in parse_svg_to_sketch_entities(svg))
    assert _sketch(svg).profiles[0].area == pytest.approx(math.pi * r * r, rel=2e-3)


def test_an_arc_is_curves_on_the_true_circle():
    cubics = arc_to_cubics(10.0, 0.0, 10.0, 10.0, 0.0, False, True, -10.0, 0.0)
    assert len(cubics) == 2
    start = (10.0, 0.0)
    for c1, c2, end in cubics:
        for t in (0.25, 0.5, 0.75):
            assert math.hypot(*_bezier((start, c1, c2, end), t)) == pytest.approx(10.0, rel=1e-3)
        start = end
    assert start == pytest.approx((-10.0, 0.0))
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M10 0 A10 10 0 0 1 -10 0 A10 10 0 0 1 10 0 Z"/></svg>'
    assert parse_svg_to_geometry(svg).area == pytest.approx(math.pi * 100.0, rel=2e-3)
    assert _sketch(svg).profiles[0].area == pytest.approx(math.pi * 100.0, rel=2e-3)


def test_an_open_filled_path_still_makes_a_profile_and_a_lone_line_stays_open():
    triangle = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L10 0 L0 10"/></svg>'
    assert _sketch(triangle).profiles[0].area == pytest.approx(50.0)
    line = '<svg xmlns="http://www.w3.org/2000/svg"><line x1="0" y1="0" x2="10" y2="0"/></svg>'
    entities = parse_svg_to_sketch_entities(line)
    assert len(entities) == 1 and isinstance(entities[0], SketchLine)


def test_a_broken_file_imports_nothing():
    assert parse_svg_to_sketch_entities("<svg") == []
    assert parse_svg_to_geometry("<svg xmlns='http://www.w3.org/2000/svg'></svg>") is None


# =========================================================================
# 2. SVG Surface Texture Patterns
# =========================================================================

def test_svg_surface_texture_flat_face():
    doc = Document()
    sk = Sketch("s1", "Sketch 1", SketchPlane.create_named("XY"))
    for l in (
        SketchLine("l1", (0, 0), (100, 0)),
        SketchLine("l2", (100, 0), (100, 100)),
        SketchLine("l3", (100, 100), (0, 100)),
        SketchLine("l4", (0, 100), (0, 0)),
    ):
        sk.entities.append(l)
    sk.solve_profiles()
    doc.sketches[sk.sketch_id] = sk
    feat = ExtrudeFeature("e1", "Extrude", sk.sketch_id, 0, 10.0, "new_body")
    feat.execute(doc)
    body = doc.bodies["body_e1"]

    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(SVG_STAR)
        f.flush()
        params = {
            "shape": "svg", "svg_path": f.name, "size": 15.0, "wall": 3.0, "margin": 5.0, "depth": 2.0, "through": False,
            "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 1, "style": "even",
            "fine_size": 2.0, "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0,
            "opening_end": 100.0, "relaxation": 0, "hole": "cell"
        }
        ref = {"kind": "plane", "origin": [50.0, 50.0, 10.0], "normal": [0.0, 0.0, 1.0]}
        res, cells, skipped = HoneycombFeature.compute(body.manifold, [ref], params)
        assert skipped == 0
        assert cells > 0
        assert res.volume() < body.manifold.volume()


def test_svg_surface_texture_curved_wall():
    doc = _build_spline_wall_doc()
    body = doc.bodies["body_e1"]
    ref = {"kind": "surface", "point": [35.0, 25.0, 25.0], "normal": [0.0, -1.0, 0.0]}

    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(SVG_STAR)
        f.flush()
        params = {
            "shape": "svg", "svg_path": f.name, "size": 10.0, "wall": 2.5, "margin": 3.0, "depth": 1.0, "through": True,
            "angle": 0.0, "partial": False, "randomness": 100.0, "seed": 1, "style": "even",
            "fine_size": 2.0, "inner_wall": 0.8, "hotspots": 1, "rounding": 0.0, "opening": 100.0,
            "opening_end": 100.0, "relaxation": 0, "hole": "cell"
        }
        res, cells, skipped = HoneycombFeature.compute(body.manifold, [ref], params)
        assert skipped == 0
        assert cells > 0
        assert res.volume() < body.manifold.volume()


# =========================================================================
# 3. Random Rotation of SVG Cells
# =========================================================================

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
    folded = [d - 180.0 if d > 90.0 else d for d in map(_direction, cells)]
    assert max(abs(d) for d in folded) <= 20.0 + 1e-6
    assert len({round(d, 1) for d in folded}) > 0.5 * len(folded)
    assert max(folded) - min(folded) > 20.0
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
