"""Offset keeps arcs as arcs, lets radii follow and leaves no broken joints."""
import math

import pytest
from shapely.geometry import Polygon

from omacad.model.document import Document


def rounded_rect(r=3.0, w=40.0, h=24.0):
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rect((0, 0), (w, h))
    for pt, la, lb, _a, _b in sk.find_corners():
        sk.fillet_corner(la, lb, r, pt)
    return d, sk


def endpoints(entities):
    pts = []
    for e in entities:
        if e.entity_type == "line":
            pts += [e.p1, e.p2]
        elif e.entity_type == "arc":
            pts += [e.p_start, e.p_end]
    return pts


def is_closed_chain(entities, tol=1e-6):
    """Every end point is shared by exactly two elements."""
    pts = endpoints(entities)
    for p in pts:
        if sum(1 for q in pts if math.hypot(p[0] - q[0], p[1] - q[1]) < tol) != 2:
            return False
    return True


def shape_polygon(sk, ids):
    """The outline of some elements as a polygon (arcs sampled)."""
    from omacad.model.sketch_offset import build_chains, to_seg
    chain, closed = build_chains([to_seg(e) for e in sk.entities if e.entity_id in ids])[0]
    pts = []
    for s in chain:
        pts += s.points(64)[:-1]
    return Polygon(pts)


@pytest.mark.parametrize("dist", [-1.0, -2.0, 2.0, 4.0])
def test_rounded_rectangle_offset_follows_the_radii(dist):
    d, sk = rounded_rect(3.0)
    ids = [e.entity_id for e in sk.entities]
    base = shape_polygon(sk, ids)
    new = sk.offset_entities(ids, dist)
    assert [e.entity_type for e in new].count("arc") == 4 and [e.entity_type for e in new].count("line") == 4
    assert is_closed_chain(new), "the offset has broken joints"
    radii = sorted(round(math.hypot(e.p_start[0] - c[0], e.p_start[1] - c[1]), 3)
                   for e in new if e.entity_type == "arc" for c in [e.get_circle_params()[0]])
    assert radii == [pytest.approx(3.0 + dist, abs=1e-3)] * 4
    expected = base.buffer(dist, join_style=1, quad_segs=256).area
    assert shape_polygon(sk, [e.entity_id for e in new]).area == pytest.approx(expected, rel=2e-3)



def test_inward_offset_larger_than_the_radius_drops_the_arcs_and_stays_closed():
    d, sk = rounded_rect(3.0)
    ids = [e.entity_id for e in sk.entities]
    new = sk.offset_entities(ids, -3.5)
    assert all(e.entity_type == "line" for e in new) and len(new) == 4
    assert is_closed_chain(new)
    assert shape_polygon(sk, [e.entity_id for e in new]).area == pytest.approx((40 - 7) * (24 - 7), rel=1e-6)


def test_open_chain_of_a_line_an_arc_and_a_line():
    d = Document()
    sk = d.start_sketch("XY")
    sk.entities = []
    from omacad.model.sketch import SketchArc, SketchLine
    sk.entities += [SketchLine("a", (0, 0), (10, 0)), SketchArc("b", (10, 0), (13.5355339, 1.4644661), (15, 5)), SketchLine("c", (15, 5), (15, 15))]
    new = sk.offset_entities(["a", "b", "c"], 2.0)          # to the left of the travel direction
    types = [e.entity_type for e in new]
    assert types.count("line") == 2 and types.count("arc") == 1 and len(new) == 3
    arc = [e for e in new if e.entity_type == "arc"][0]
    centre, radius = arc.get_circle_params()[0], arc.get_circle_params()[1]
    assert radius == pytest.approx(5.0 - 2.0, abs=1e-3)
    line_a = [e for e in new if e.entity_type == "line"][0]
    assert line_a.p1[1] == pytest.approx(2.0) and line_a.p2[1] == pytest.approx(2.0)
    assert is_open_connected(new)


def is_open_connected(entities):
    pts = endpoints(entities)
    shared = [sum(1 for q in pts if math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-6) for p in pts]
    return shared.count(1) == 2 and all(n in (1, 2) for n in shared)


def test_offset_of_a_circle_and_lines_together():
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_circle((50, 50), 5)
    sk.add_rect((0, 0), (10, 10))
    new = sk.offset_entities([e.entity_id for e in sk.entities], -2)
    assert [e.entity_type for e in new].count("circle") == 1
    assert [e.entity_type for e in new if e.entity_type == "circle"][0] == "circle"
    c = [e for e in new if e.entity_type == "circle"][0]
    assert c.radius == pytest.approx(3.0)


@pytest.mark.parametrize("distance", [1.0, -1.0])
def test_open_spline_offset_distance_and_direction(distance):
    from shapely.geometry import LineString, Point
    from omacad.model.sketch import Sketch, SketchSpline

    sk = Document().start_sketch("XY")
    spline = sk.add_spline([(0, 0), (10, 5), (20, -5), (30, 0)])
    before = spline.to_dict()
    new = sk.offset_entities([spline.entity_id], distance)
    assert len(new) == 1 and isinstance(new[0], SketchSpline)
    original = LineString(spline.get_points(64))
    offset = LineString(new[0].get_points())
    assert offset.is_simple
    for point in new[0].get_points():
        assert original.distance(Point(point)) == pytest.approx(abs(distance), abs=0.15, rel=0.08)
    assert offset.hausdorff_distance(original.offset_curve(distance)) < max(0.18, abs(distance) * 0.08)
    # Initial tangent points up and right, so left is up and left.
    assert (new[0].points[0][0] < spline.points[0][0]) == (distance > 0)
    assert (new[0].points[0][1] > spline.points[0][1]) == (distance > 0)
    assert spline.to_dict() == before
    assert len(new[0].points) < len(spline.get_points(64))
    assert Sketch.from_dict(sk.to_dict()).to_dict() == sk.to_dict()


@pytest.mark.parametrize("distance", [1.0, -1.0, 100.0])
@pytest.mark.parametrize("reverse", [False, True])
def test_closed_spline_offset_is_closed_outward_for_positive_distance(distance, reverse):
    from shapely.geometry import LineString

    sk = Document().start_sketch("XY")
    points = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    spline = sk.add_spline(points[::-1] if reverse else points)
    original = Polygon(spline.get_points(64))
    new = sk.offset_entities([spline.entity_id], distance)
    assert len(new) == 1
    assert new[0].points[0] == new[0].points[-1]
    result = Polygon(new[0].get_points())
    assert result.is_valid
    expected = original.buffer(distance)
    assert result.area == pytest.approx(expected.area, rel=0.03)
    assert LineString(result.exterior).hausdorff_distance(expected.exterior) < max(0.18, abs(distance) * 0.08)


def test_collapsed_and_degenerate_spline_offsets_leave_originals_intact():
    from omacad.model.sketch import SketchSpline

    sk = Document().start_sketch("XY")
    sk.add_spline([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    sk.entities.extend([SketchSpline("empty", []), SketchSpline("point", [(1, 1)]),
                        SketchSpline("same", [(1, 1), (1, 1)])])
    before = sk.to_dict()
    assert sk.offset_entities([e.entity_id for e in sk.entities], -1000) == []
    assert sk.to_dict() == before


def test_spline_offset_in_mixed_selection_ignores_construction_and_unselected():
    sk = Document().start_sketch("XY")
    spline = sk.add_spline([(0, 0), (5, 8), (10, 0)])
    sk.add_spline([(0, 50), (5, 58), (10, 50)], is_construction=True)
    unselected = sk.add_spline([(0, 80), (5, 88), (10, 80)])
    sk.add_circle((50, 50), 5)
    sk.add_line((50, 0), (60, 0))
    new = sk.offset_entities([e.entity_id for e in sk.entities if e is not unselected], 1)
    assert sorted(e.entity_type for e in new) == ["circle", "line", "spline"]
    assert len({e.entity_id for e in sk.entities}) == len(sk.entities)
    assert spline in sk.entities and unselected in sk.entities


@pytest.mark.parametrize("distance", [1.0, -1000.0, None])
def test_spline_offset_ui_preview_commit_undo_and_empty_result(distance):
    from PySide6.QtWidgets import QApplication
    from omacad.ui.viewport.viewport import Viewport3D

    app = QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch("XY")
    spline = sk.add_spline([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    viewport = Viewport3D(doc)
    viewport.selected_entities = {spline.entity_id}
    messages = []
    viewport.status_message.connect(messages.append)
    before = sk.to_dict()
    undo_count = len(doc.undo_stack)

    def prompt(*args, **kwargs):
        kwargs["on_change"](1.0)
        assert viewport.offset_preview is not None
        assert sk.to_dict() == before
        return None if distance is None else (distance, None)

    viewport.prompt_dimension_value = prompt
    try:
        viewport.offset_selected()
        assert viewport.offset_preview is None
        if distance == 1.0:
            after = sk.to_dict()
            assert len(sk.entities) == 2
            assert len(doc.undo_stack) == undo_count + 1
            doc.undo()
            assert doc.active_sketch.to_dict() == before
            doc.redo()
            assert doc.active_sketch.to_dict() == after
        else:
            assert sk.to_dict() == before
            assert len(doc.undo_stack) == undo_count
            if distance is not None:
                assert "nothing could be offset" in messages[-1]
    finally:
        viewport.close()
        viewport.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("distance", [5.0, -5.0])
def test_requested_spline_offsets_at_the_entered_distance(distance):
    from shapely.geometry import LineString, Point

    sk = Document().start_sketch("XZ")
    # Lennart's #131 sketch: the curve shown selected in the attached screenshot.
    spline = sk.add_spline([(25, 0), (30, 10), (25, 25),
                            (19.07748031616211, 30.92251968383789), (15, 40)])
    original = LineString(spline.get_points(64))
    new = sk.offset_entities([spline.entity_id], distance)
    assert len(new) == 1
    assert LineString(new[0].get_points()).is_simple
    assert all(original.distance(Point(p)) == pytest.approx(abs(distance), abs=0.25, rel=0.08)
               for p in new[0].get_points())


def test_large_open_spline_offset_keeps_disconnected_parts_separate():
    from shapely.geometry import LineString, MultiLineString

    sk = Document().start_sketch("XY")
    spline = sk.add_spline([(0, 0), (10, 5), (20, -5), (30, 0)])
    target = LineString(spline.get_points(64)).offset_curve(100)
    assert target.geom_type == "MultiLineString"
    new = sk.offset_entities([spline.entity_id], 100)
    assert len(new) == len(target.geoms)
    result = MultiLineString([e.get_points() for e in new])
    assert all(part.is_simple for part in result.geoms)
    assert result.hausdorff_distance(target) < 1.0
