"""Text in a sketch (Fusion's Text and Text On Path): letters become profiles, counters become holes, the entity
moves/rotates/mirrors/saves like the others, and on a circle it follows the circle."""
import math

import numpy as np
import pytest
from shapely.geometry import Point

from omacad.model.sketch import Sketch, SketchPlane, SketchText


def _sketch():
    return Sketch("s1", plane=SketchPlane.create_named("XY"))


def test_height_is_the_capital_height_and_letter_spacing_widens():
    sk = _sketch()
    t = sk.add_text("H", height=10.0)
    x0, y0, x1, y1 = t.bbox()
    assert y1 - y0 == pytest.approx(10.0, abs=0.15)                 # a capital H is 10 mm tall
    wide = sk.add_text("II", height=10.0, spacing=100.0)
    tight = sk.add_text("II", height=10.0, spacing=0.0)
    assert (wide.bbox()[2] - wide.bbox()[0]) > (tight.bbox()[2] - tight.bbox()[0]) + 2.0


def test_alignment_puts_the_text_on_either_side_of_the_anchor():
    sk = _sketch()
    left = sk.add_text("HHH", (50.0, 20.0), height=8.0, h_align="left", v_align="bottom").bbox()
    centre = sk.add_text("HHH", (50.0, 20.0), height=8.0, h_align="center", v_align="middle").bbox()
    right = sk.add_text("HHH", (50.0, 20.0), height=8.0, h_align="right", v_align="top").bbox()
    assert left[0] >= 49.5 and left[1] == pytest.approx(20.0, abs=0.2)             # starts at the anchor, sits on it
    assert centre[0] < 50.0 < centre[2] and centre[1] < 20.0 < centre[3]
    assert right[2] <= 50.5 and right[3] == pytest.approx(20.0, abs=0.2)           # ends at the anchor, hangs from it


def test_the_letter_o_is_a_ring_and_its_counter_is_a_hole_in_the_profile():
    sk = _sketch()
    sk.add_text("O", height=20.0)
    ring = [p for p in sk.profiles if p.interior_holes]
    assert len(ring) == 1 and len(ring[0].interior_holes) == 1                     # the letter, with its counter cut out
    assert len(sk.profiles) == 2                                                   # (the counter is a profile of its own, like a ring and its circle)
    assert ring[0].area == pytest.approx(sk.entities[0].geometry().area, rel=1e-3)


def test_text_profiles_extrude_to_the_exact_volume():
    from omacad.model.document import Document
    doc = Document()
    sk = doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    t = sk.add_text("I", (0, 0), height=10.0)
    doc.finish_sketch()
    area = t.geometry().area
    prof = max(range(len(sk.profiles)), key=lambda i: sk.profiles[i].area)
    doc.extrude_profile(sk.sketch_id, prof, 3.0, "new_body")
    vol = next(iter(doc.bodies.values())).manifold.volume()
    assert vol == pytest.approx(area * 3.0, rel=1e-3)


def test_save_load_and_undo_snapshot_keep_the_text_and_its_path():
    sk = _sketch()
    circle = sk.add_circle((0.0, 0.0), 20.0)
    t = sk.add_text("ROUND", height=5.0, path_id=circle.entity_id, h_align="center")
    again = Sketch.from_dict(sk.to_dict())
    t2 = [e for e in again.entities if isinstance(e, SketchText)][0]
    assert t2.text == "ROUND" and t2.path_id == circle.entity_id and t2.sketch is again
    assert t2.geometry().bounds == pytest.approx(t.geometry().bounds, abs=1e-6)
    sk.restore_from_dict(sk.to_dict())                                             # the in-place restore used by undo
    assert [e for e in sk.entities if isinstance(e, SketchText)][0].sketch is sk


def test_text_on_a_circle_follows_it_and_moves_with_it():
    sk = _sketch()
    circle = sk.add_circle((10.0, 5.0), 20.0)
    t = sk.add_text("ABCDEF", height=4.0, path_id=circle.entity_id, h_align="center", placement="above")
    radii = [math.hypot(x - 10.0, y - 5.0) for p in t.polygons() for x, y in p.exterior.coords]
    assert min(radii) > 19.7 and max(radii) < 24.5                                  # above = outside the circle, 4 mm tall
    top = t.geometry().centroid
    assert abs(top.x - 10.0) < 3.0 and top.y > 5.0 + 19.0                           # centred on the top
    circle.center = (30.0, 5.0)                                                    # the path moves, the text follows
    moved = t.geometry().centroid
    assert moved.x == pytest.approx(top.x + 20.0, abs=0.05)
    below = sk.add_text("ABCDEF", height=4.0, path_id=circle.entity_id, h_align="center", placement="below")
    r_below = [math.hypot(x - 30.0, y - 5.0) for p in below.polygons() for x, y in p.exterior.coords]
    assert max(r_below) < 20.3 and min(r_below) > 15.5                              # below = inside it


def test_fit_to_path_spreads_the_text_over_the_whole_line():
    sk = _sketch()
    line = sk.add_line((0.0, 0.0), (100.0, 0.0))
    t = sk.add_text("AB", height=5.0, path_id=line.entity_id, fit=True)
    x0, _, x1, _ = t.bbox()
    assert x0 < 3.0 and x1 > 90.0


def test_move_rotate_and_mirror():
    from omacad.model.sketch import move_entity, rotate_entity
    sk = _sketch()
    t = sk.add_text("F", (10.0, 0.0), height=6.0)
    before = t.bbox()
    move_entity(t, 5.0, 2.0)
    after = t.bbox()
    assert (after[0] - before[0], after[1] - before[1]) == pytest.approx((5.0, 2.0), abs=1e-6)
    rotate_entity(t, 90.0, (0.0, 0.0))
    assert t.angle == pytest.approx(90.0) and t.anchor == pytest.approx((-2.0, 15.0), abs=1e-9)
    mirrored = sk.mirror_entities([t.entity_id], (0.0, 0.0), (0.0, 1.0))[0]     # across the vertical axis
    ax = mirrored.geometry().centroid.x
    assert ax == pytest.approx(-t.geometry().centroid.x, abs=1e-3)               # the picture is the reflection
    assert mirrored.geometry().centroid.y == pytest.approx(t.geometry().centroid.y, abs=1e-3)
    a, b = t.geometry(), mirrored.geometry()
    assert a.symmetric_difference(shapely_reflect_x(b)).area < 0.01 * a.area      # point for point


def shapely_reflect_x(g):
    from shapely import affinity
    return affinity.scale(g, xfact=-1.0, yfact=1.0, origin=(0, 0))


def test_explode_turns_the_text_into_lines_that_still_make_profiles():
    sk = _sketch()
    t = sk.add_text("O", height=10.0)
    n = len(t.to_lines())
    before = [p.area for p in sk.profiles]
    lines = sk.explode_text(t.entity_id)
    assert len(lines) == n and not any(isinstance(e, SketchText) for e in sk.entities)
    assert sorted(p.area for p in sk.profiles) == pytest.approx(sorted(before), rel=1e-6)      # the ring and its counter
