"""An imported SVG keeps its curves: the sketch holds the file's Beziers, not a coarse polygon of them.

Report 20261106-160150: a logo with a 39-unit viewBox came in as 82 straight lines, 2.7 % short of its area, because Qt
flattens curves to about half a unit whatever size the drawing is.
"""

import json
import math

import pytest
from shapely.geometry import LineString, Polygon

from omacad.model.sketch import Sketch, SketchPlane
from omacad.model.sketch_entities import SketchLine, SketchSpline
from omacad.model.svg_importer import arc_to_cubics, parse_svg_to_geometry, parse_svg_to_sketch_entities

# The report's file: an ellipse with a bat shaped hole, 15 cubic Beziers and one straight line.
BAT = """<svg viewBox="0 -3.5 39 39" xmlns="http://www.w3.org/2000/svg">
<path d="M19.5 4.25c-10.77 0-19.5 5.261-19.5 11.75s8.73 11.75 19.5 11.75 19.5-5.261 19.5-11.75-8.73-11.75-19.5-11.75zM30.555 23.53c0 0.062 1.951-2.357 0.39-3.981-1.874-2.124-5.116 1.056-5.116 1.056-2.562-5.059-6.424 3.145-6.424 3.145s-3.348-7.731-6.221-3.047c0.062 0-2.383-2.793-4.819-1.481-1.749 1.749 0 4.091 0 4.091-9.119-3.186-9.712-12.492 2.952-16.286-3.576 4.481 6.59 10.649 5.84-0.344l2.155 1.89c0 0 2.171-1.796 2.171-1.921-0.25 10.993 9.369 4.544 6.121 0.484 11.429 3.308 13.381 11.21 2.951 16.394z"/>
</svg>"""
FIRST_CURVE = ((19.5, 4.25), (8.73, 4.25), (0.0, 9.511), (0.0, 16.0))   # the file's first Bezier, Y down


def _sketch(svg, **kwargs):
    sketch = Sketch("s", "S", SketchPlane.create_named("XY"))
    sketch.entities.extend(parse_svg_to_sketch_entities(svg, **kwargs))
    sketch.solve_profiles()
    return sketch


def _bezier(points, t):
    p0, c1, c2, p3 = points
    s = 1.0 - t
    return tuple(s**3 * a + 3 * s * s * t * b + 3 * s * t * t * c + t**3 * d for a, b, c, d in zip(p0, c1, c2, p3))


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
        h00, h10, h01, h11 = 2*t**3 - 3*t*t + 1, t**3 - 2*t*t + t, -2*t**3 + 3*t*t, t**3 - t*t
        assert h00*p1[0] + h10*m1[0] + h01*p2[0] + h11*m2[0] == pytest.approx(x, abs=1e-9)
        assert h00*p1[1] + h10*m1[1] + h01*p2[1] + h11*m2[1] == pytest.approx(-y, abs=1e-9)


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
    # a quarter of the ellipse, tightest at its tip: no visible corner between two chords
    steps = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(points, points[1:])]
    turns = [abs((b - a + math.pi) % (2 * math.pi) - math.pi) for a, b in zip(steps, steps[1:])]
    assert max(turns) < math.radians(6.0)


def test_the_logo_makes_its_two_profiles_with_the_true_area():
    sketch = _sketch(BAT)
    assert len(sketch.profiles) == 2
    ellipse = math.pi * 19.5 * 11.75
    outer = max(sketch.profiles, key=lambda p: p.area)
    inner = min(sketch.profiles, key=lambda p: p.area)
    # four Beziers make the ellipse with the usual control points, 0.03 % off it at most (they bulge 0.027 % of r)
    assert Polygon(outer.exterior_pts).area == pytest.approx(ellipse, rel=1e-3)
    assert outer.area + inner.area == pytest.approx(ellipse, rel=1e-3)
    assert inner.area == pytest.approx(ellipse - 364.88, rel=2e-3)


def test_the_curves_survive_saving():
    sketch = _sketch(BAT)
    again = Sketch.from_dict(json.loads(json.dumps(sketch.to_dict())))
    again.solve_profiles()
    assert [p.area for p in again.profiles] == pytest.approx([p.area for p in sketch.profiles])


def test_the_filled_geometry_does_not_shrink_on_a_small_viewbox():
    """What Surface Texture uses: 355.06 before, for a true area of 364.88."""
    assert parse_svg_to_geometry(BAT).area == pytest.approx(364.88, rel=2e-3)


@pytest.mark.parametrize("scale", [0.1, 1.0, 100.0])
def test_a_circle_is_round_at_any_size(scale):
    r = 15.0 * scale
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"><circle cx="{50 * scale}" cy="{50 * scale}" r="{r}"/></svg>'
    assert parse_svg_to_geometry(svg).area == pytest.approx(math.pi * r * r, rel=2e-3)
    assert all(isinstance(e, SketchSpline) for e in parse_svg_to_sketch_entities(svg))
    assert _sketch(svg).profiles[0].area == pytest.approx(math.pi * r * r, rel=2e-3)


def test_an_arc_is_curves_on_the_true_circle():
    # half a circle of radius 10 from (10, 0) to (-10, 0)
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
