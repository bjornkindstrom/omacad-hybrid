"""Tests for linked control point spline offset:
- Offset copy points update when original spline changes shape.
- Maintains the chosen offset distance.
- Shows offset symbol badge in sketch mode.
- Unlinking via constraint removal makes it independent.
"""
import pytest
from shapely.geometry import LineString, Point
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchSpline
from omacad.ui.viewport.viewport import Viewport3D


def _setup_app():
    if QApplication.instance() is None:
        QApplication([])


def test_control_spline_offset_creates_link_and_constraint():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    assert src.control_points
    new = sk.offset_entities([src.entity_id], 5.0)
    assert len(new) == 1
    copy = new[0]
    assert isinstance(copy, SketchSpline) and copy.control_points
    assert copy.offset_info is not None
    assert copy.offset_info["source_id"] == src.entity_id
    assert copy.offset_info["distance"] == 5.0
    # Constraint created
    offset_constraints = [c for c in sk.constraints if c.ctype == "OFFSET"]
    assert len(offset_constraints) == 1
    assert offset_constraints[0].refs == [copy.entity_id, src.entity_id]


def test_offset_copy_follows_when_original_moves_control_points():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    dist = 6.0
    copy = sk.offset_entities([src.entity_id], dist)[0]
    pts_before = list(copy.points)

    # Move a control point on the original spline
    sk.move_spline_point(src.entity_id, 2, (50.0, 10.0))

    # The copy's points must have followed
    assert copy.points != pts_before

    # Verify that the offset distance is maintained
    exact2 = LineString(src.get_points(64)).offset_curve(dist)
    for p in copy.get_points(64):
        assert exact2.distance(Point(p)) < max(0.1, 0.05 * abs(dist))


def test_offset_badge_symbol_visible_in_sketch_mode():
    _setup_app()
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 4.0)[0]

    view = Viewport3D(doc)
    view.resize(800, 600)
    view.align_to_plane(sk.plane)
    view.sketch_palette.chk_show_constraints.setChecked(False)  # Even with show all unchecked

    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        view.draw_constraint_badges(p)
    finally:
        p.end()
        view.close()

    # The badge for the offset constraint must be created
    offset_c = next(c for c in sk.constraints if c.ctype == "OFFSET")
    assert any(cid == offset_c.cid for _, cid in view.constraint_badges)
    assert Viewport3D.CONSTRAINT_GLYPHS["OFFSET"] == "⧉"


def test_offset_spline_protected_from_independent_modification():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0)[0]

    with pytest.raises(ValueError, match="offset spline is controlled"):
        sk.move_spline_point(copy.entity_id, 1, (10, 10))

    with pytest.raises(ValueError, match="Offset spline is linked"):
        sk.insert_spline_point(copy.entity_id, (30, 20))


def test_unlinking_offset_constraint_makes_spline_independent():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0)[0]
    offset_c = next(c for c in sk.constraints if c.ctype == "OFFSET")

    # Remove the constraint (simulate clicking badge)
    assert doc.remove_constraint(sk.sketch_id, offset_c.cid)
    assert copy.offset_info is None

    # Now it can be edited independently
    sk.move_spline_point(copy.entity_id, 1, (30.0, 35.0))
    assert copy.points[1] == (30.0, 35.0)

    # And moving original no longer alters copy
    copy_pts = list(copy.points)
    sk.move_spline_point(src.entity_id, 2, (50.0, 50.0))
    assert copy.points == copy_pts


def test_serialization_preserves_offset_link():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 7.0)[0]

    data = sk.to_dict()
    restored = Sketch.from_dict(data)
    r_copy = restored.get_entity(copy.entity_id)
    assert r_copy.offset_info is not None
    assert r_copy.offset_info["source_id"] == src.entity_id
    assert r_copy.offset_info["distance"] == 7.0

    # Moving src in restored sketch still updates copy
    r_src = restored.get_entity(src.entity_id)
    restored.move_spline_point(r_src.entity_id, 2, (50.0, 30.0))
    exact_restored = LineString(r_src.get_points(64)).offset_curve(7.0)
    for p in r_copy.get_points(64):
        assert exact_restored.distance(Point(p)) < max(0.1, 0.05 * 7.0)


def test_insert_control_point_on_original_updates_offset_copy():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0)[0]
    pts_before = list(copy.points)

    # Insert a point into original spline
    sk.insert_spline_point(src.entity_id, (35.0, 15.0))
    assert len(src.points) == 6

    # Offset copy should automatically have updated its points to follow
    assert copy.points != pts_before
    exact = LineString(src.get_points(64)).offset_curve(5.0)
    for p in copy.get_points(64):
        assert exact.distance(Point(p)) < max(0.1, 0.05 * 5.0)


def test_solver_dimension_update_propagates_to_offset_copy():
    doc = Document()
    sk = doc.start_sketch("XY")
    ref_line = sk.add_line((0, -50), (0, 50))
    src = sk.add_spline([(10, 0), (30, 20), (70, 20), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 4.0)[0]
    pts_before = list(copy.points)

    # Add a dimension between ref_line and original spline pt1
    dim = sk.add_dimension("HORIZ_DIST", ref_line.entity_id, 30.0, refs=[src.entity_id], pts=["p1", "pt1"])
    assert doc.update_dimension(sk.sketch_id, dim.dim_id, 45.0)

    # Original pt1 moved
    assert src.points[1][0] == pytest.approx(45.0)
    # Copy points followed
    assert copy.points != pts_before
    exact = LineString(src.get_points(64)).offset_curve(4.0)
    for p in copy.get_points(64):
        assert exact.distance(Point(p)) < max(0.1, 0.05 * 4.0)


def test_offset_control_spline_unlinked_option():
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 5.0, link_splines=False)[0]
    assert copy.offset_info is None
    assert not any(c.ctype == "OFFSET" for c in sk.constraints)

    # Since it's unlinked, points can be edited directly immediately
    sk.move_spline_point(copy.entity_id, 1, (20.0, 20.0))
    assert copy.points[1] == (20.0, 20.0)

    # Moving src does not affect copy
    copy_pts = list(copy.points)
    sk.move_spline_point(src.entity_id, 2, (50.0, 50.0))
    assert copy.points == copy_pts


