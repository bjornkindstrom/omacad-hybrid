import pytest
from omacad.ui.smart_circle import ACROSS, DOWN, SIZE, SmartCircle, nearest_axis_line

WALLS = [((0, 0), (0, 50), "left"), ((60, 0), (60, 50), "right"), ((0, 0), (60, 0), "bottom"),
         ((0, 50), (60, 50), "top"), ((0, 0), (30, 30), "diag")]


def _sc():
    s = SmartCircle()
    s.segments = WALLS
    return s


def _type(s, text):
    s.text = text


def test_nearest_vertical_and_horizontal_ignore_slanted_lines():
    assert nearest_axis_line(WALLS, (50, 10), True)[2] == "right"
    assert nearest_axis_line(WALLS, (5, 10), True)[2] == "left"
    assert nearest_axis_line(WALLS, (20, 45), False)[2] == "top"
    assert nearest_axis_line([((0, 0), (30, 30), "d")], (1, 1), True) is None


def test_full_flow_with_numbers_only():
    s = _sc()
    s.mouse = (50, 10)
    assert s.accept() == "need_size"
    _type(s, "8")
    assert s.accept() == "next" and s.stage == ACROSS and s.diameter == 8
    s.mouse = (48, 20)                       # right wall is nearest, mouse on its left
    _type(s, "10")
    assert s.centre() == (50, 20)            # 10 in from x=60
    assert s.accept() == "next" and s.stage == DOWN
    s.mouse = (15, 44)                       # top wall, mouse below it
    _type(s, "6")
    assert s.centre() == (50, 44)
    assert s.accept() == "done"
    assert s.dimension[ACROSS][0][2] == "right" and s.dimension[ACROSS][1] == 10
    assert s.dimension[DOWN][0][2] == "top"
    assert s.centre() == (50, 44)


def test_empty_step_takes_the_mouse_and_makes_no_dimension():
    s = _sc()
    s.mouse = (30, 25)
    _type(s, "5"); s.accept()
    s.mouse = (22, 25); assert s.accept() == "next"
    s.mouse = (22, 31); assert s.accept() == "done"
    assert s.centre() == (22, 31) and not s.dimension


def test_negative_distance_flips_side_and_backspace_goes_back():
    s = _sc()
    s.mouse = (5, 25)
    _type(s, "4"); s.accept()
    _type(s, "-3")
    assert s.centre()[0] == -3               # mouse is right of x=0, minus puts it on the other side
    s.text = ""
    assert s.back() and s.stage == SIZE


def test_typed_distance_without_a_line_is_refused():
    s = SmartCircle()
    s.mouse = (1, 1)
    _type(s, "4"); s.accept()
    _type(s, "2")
    assert s.accept() == "no_line"


# ---- slanted lines: any angle, right-angle distance from the centre ---------------------------------

def test_step_two_measures_at_right_angles_to_a_slanted_line():
    import math
    from omacad.ui.smart_circle import foot_on_line, signed_distance
    seg = ((0, 0), (30, 30), "diag")
    s = SmartCircle()
    s.segments = [seg]
    s.mouse = (20, 5)                         # below-right of the diagonal
    _type(s, "6"); s.accept()
    _type(s, "10")
    c = s.centre()
    assert abs(signed_distance(seg, c)) == pytest.approx(10.0)
    assert signed_distance(seg, c) * signed_distance(seg, s.mouse) > 0      # on the mouse's side
    assert c[0] - s.mouse[0] == pytest.approx(-(c[1] - s.mouse[1]))          # moved along the normal (1, -1)
    assert foot_on_line(seg, c)[0] == pytest.approx(foot_on_line(seg, c)[1])
    assert s.accept() == "next" and s.dimension[ACROSS][1] == 10


def test_two_non_parallel_lines_fix_the_centre_exactly():
    import math
    from omacad.ui.smart_circle import signed_distance
    diag = ((0, 0), (30, 30), "diag")
    bottom = ((0, 0), (60, 0), "bottom")
    s = SmartCircle()
    s.segments = [diag, bottom, ((0, 50), (60, 50), "top")]
    s.mouse = (20, 5)
    _type(s, "6"); s.accept()
    s.mouse = (30, 3); _type(s, "7"); assert s.accept() == "next"       # nearest line: the bottom edge or the diagonal
    first = s.dimension[ACROSS][0]
    s.mouse = (30, 4); _type(s, "9")
    assert s.guide() is not None
    assert s.accept() == "done"
    c = s.centre()
    assert abs(signed_distance(first, c)) == pytest.approx(7.0)
    assert abs(signed_distance(s.dimension[DOWN][0], c)) == pytest.approx(9.0)
    assert s.dimension[DOWN][0][2] != first[2]


def test_step_three_skips_lines_parallel_to_the_first():
    s = SmartCircle()
    left, right, top = ((0, 0), (0, 50), "left"), ((60, 0), (60, 50), "right"), ((0, 50), (60, 50), "top")
    s.segments = [left, right, top]
    s.mouse = (50, 25)
    _type(s, "4"); s.accept()
    s.mouse = (52, 25); _type(s, "10"); s.accept()
    assert s.stage == DOWN
    s.mouse = (51, 25)                        # right next to the right wall, but that one is parallel to the first
    assert s.guide()[2] == "top"
    s.segments = [left, right]
    assert s.guide() is None and (_type(s, "5") or s.accept()) == "no_line"


# =========================================================================
# Corner guide mapping & solver wall tracking
# =========================================================================

def _ent(sk, eid):
    return next(e for e in sk.entities if e.entity_id == eid)


def test_guide_lines_map_to_their_walls():
    from omacad.model.document import Document
    from omacad.model.sketch import SketchLine

    doc = Document()
    sk = doc.start_sketch("XY")
    walls = sk.add_rounded_rect((0, 0), (40, 30), 5.0)
    guides = sk.corner_guide_walls()
    assert len(guides) == 8
    wall_ids = {w.entity_id for w in walls}
    for gid, wid in guides.items():
        g, w = _ent(sk, gid), _ent(sk, wid)
        assert isinstance(g, SketchLine) and g.is_construction and wid in wall_ids
        (x1, y1), (x2, y2) = w.p1, w.p2
        for p in (g.p1, g.p2):
            assert (p[0] - x1) * (y2 - y1) - (p[1] - y1) * (x2 - x1) == pytest.approx(0.0, abs=1e-6)


def test_circle_measured_from_corner_guide_follows_the_wall():
    from pathlib import Path
    from omacad.io.exporter import Exporter
    from omacad.model.sketch_solver import solve_sketch

    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "smart_circle_corner_guide.omacad"))
    sk = next(iter(doc.sketches.values()))
    assert solve_sketch(sk).ok
    top, left, circle = _ent(sk, "line_3"), _ent(sk, "line_4"), _ent(sk, "circle_17")
    d11 = next(d for d in sk.dimensions if d.dim_id == "d11")
    assert d11.refs == ["line_3"]
    assert top.p1[1] - circle.center[1] == pytest.approx(5.0, abs=1e-4)
    assert circle.center[0] - left.p1[0] == pytest.approx(5.0, abs=1e-4)
    for dim, value in (("d7", 80.0), ("d8", 90.0)):
        assert doc.update_dimension(sk.sketch_id, dim, value)
        top, left, bottom, circle = _ent(sk, "line_3"), _ent(sk, "line_4"), _ent(sk, "line_1"), _ent(sk, "circle_17")
        assert top.p1[1] - circle.center[1] == pytest.approx(5.0, abs=1e-4)
        assert circle.center[0] - left.p1[0] == pytest.approx(5.0, abs=1e-4)
    assert top.p1[1] - bottom.p1[1] == pytest.approx(90.0, abs=1e-4)

