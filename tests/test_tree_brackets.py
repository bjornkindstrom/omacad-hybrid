"""Tree Brackets script: a square-pyramid Christmas tree of square aluminium tubes. The tube lengths given are the
cut lengths: with the corner and top brackets placed, every tube sits exactly from socket stop to socket stop, no
tube touches a bracket, sockets stay closed and separate, and both parts lie flat on the bed for printing."""
import importlib.util
import math

import pytest

from omacad.model.document import Document
from omacad.scripting import folder as sfolder
from omacad.scripting.loader import read_info
from omacad.scripting.runner import run_script

EX = sfolder.EXAMPLES / "tree_brackets.py"
_spec = importlib.util.spec_from_file_location("tree_brackets_example", EX)
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)


def _params(**kw):
    p = {x["name"]: x["default"] for x in tb.PARAMS}
    p.update(kw)
    return p


@pytest.mark.parametrize("kw", [{}, dict(base_tube_length=300, leg_tube_length=600, tube_size=15),
                                dict(base_tube_length=800, leg_tube_length=700)])
def test_tube_lengths_close_the_pyramid(kw):
    p = _params(**kw)
    s = tb.Sizes(p)
    assert 2 * s.a == pytest.approx(p["base_tube_length"] + 2 * s.stop_base)
    assert s.n == pytest.approx(p["leg_tube_length"] + s.stop_leg + s.stop_top, abs=1e-6)
    assert s.n == pytest.approx(math.sqrt(2 * s.a ** 2 + s.h ** 2))


def test_tubes_clear_the_brackets_and_sockets_are_closed():
    p = _params(hole_diameter=0.0)
    s = tb.Sizes(p)
    corner, top = tb.corner_bracket(s, p), tb.top_bracket(s, p)
    assert corner.genus() == 0 and top.genus() == 0           # blind sockets, none breaks into another
    z0 = s.outer / 2.0
    corners = tb._join([corner.rotate([0, 0, r]).translate([x, y, z0]) for x, y, r in tb._corner_places(s)])
    tubes = tb.assembled_tubes(s, p["tube_size"])
    assert (tubes ^ corners).volume() == pytest.approx(0.0, abs=1e-3)
    assert (tubes ^ top.translate([0, 0, z0 + s.h])).volume() == pytest.approx(0.0, abs=1e-3)
    assert tubes.volume() == pytest.approx(4 * p["tube_size"] ** 2 * (p["base_tube_length"] + p["leg_tube_length"]))


def test_script_lays_out_printable_parts_and_lists_in_the_star_menu():
    doc = Document()
    res = run_script(doc, EX, {})
    bodies = list(doc.bodies.values())
    assert len(bodies) == 2 and all(b.manifold.bounding_box()[2] == pytest.approx(0.0, abs=1e-6) for b in bodies)
    assert "cut 4 tubes of 400 mm and 4 of 1000 mm" in res.messages[0]
    assert read_info(EX).family == "star_brackets"


def test_legs_too_short_for_the_base_are_refused():
    with pytest.raises(ValueError):
        tb.Sizes(_params(base_tube_length=1000, leg_tube_length=200))


def test_corner_web_stiffens_the_corner_and_its_size_counts():
    s = tb.Sizes(_params())                     # without the leg support, whose foot covers a small web
    plain = tb.corner_bracket(s, _params(corner_web=False, leg_support="none")).volume()
    small = tb.corner_bracket(s, _params(corner_web_size=10.0, leg_support="none")).volume()
    big = tb.corner_bracket(s, _params(corner_web_size=30.0, leg_support="none"))
    assert plain < small < big.volume()
    assert big.genus() == tb.corner_bracket(s, _params(corner_web=False)).genus()    # no socket or hole blocked
    assert tb.corner_bracket(s, _params(corner_web_size=40.0)).volume() > tb.corner_bracket(s, _params()).volume()
    assert big.bounding_box()[2] == pytest.approx(-s.outer / 2.0)                     # still flat on the bed


def test_top_bracket_is_only_as_long_as_its_sockets_need_and_has_no_post():
    p = _params()
    s = tb.Sizes(p)
    lo = tb.top_bracket(s, p).bounding_box()
    assert lo[5] == pytest.approx(s.outer / 2.0)                  # flat top, nothing standing on it
    assert lo[5] - lo[2] <= (s.stop_top + s.depth) + s.outer       # socket length, no extra hub
    assert "star_post" not in {x["name"] for x in tb.PARAMS}
    assert s.stop_top < 40.0                                       # was 49 mm with the old rule of thumb


@pytest.mark.parametrize("style", ["pyramid", "fins", "collar", "block"])
@pytest.mark.parametrize("holes", [3.5, 0.0])
def test_every_leg_support_adds_material_without_blocking_anything(style, holes):
    p = _params(hole_diameter=holes, leg_support=style)
    s = tb.Sizes(p)
    off = tb.corner_bracket(s, _params(hole_diameter=holes, leg_support="none"))
    on = tb.corner_bracket(s, p)
    assert on.volume() > off.volume() * 1.02
    assert on.genus() == off.genus()                               # every socket and screw hole still open
    assert on.bounding_box() == pytest.approx(off.bounding_box())  # nothing outside the bracket's own box
    z0 = s.outer / 2.0
    corners = tb._join([on.rotate([0, 0, r]).translate([x, y, z0]) for x, y, r in tb._corner_places(s)])
    assert (tb.assembled_tubes(s, p["tube_size"]) ^ corners).volume() == pytest.approx(0.0, abs=1e-3)


def test_leg_support_is_a_choice_with_pyramid_first():
    param = next(x for x in tb.PARAMS if x["name"] == "leg_support")
    assert param["type"] == "choice" and param["default"] == "pyramid"
    assert param["choices"] == ["pyramid", "fins", "collar", "block", "none"]
