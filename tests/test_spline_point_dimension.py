"""Dimensions from a point of a control point spline (report 20261101-103242) and offset of a control point spline
into a control point spline with as many points."""
import json
import os
from types import SimpleNamespace

import pytest
from shapely.geometry import LineString, Point

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchSpline

DATA = os.path.join(os.path.dirname(__file__), "data", "control_spline_dimension.json")


def _report_doc():
    doc = Document()
    with open(DATA, encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    return doc


def test_dimension_tool_picks_a_control_point_of_the_spline():
    from omacad.ui.viewport.dimension_overlay_mixin import DimensionOverlayMixin
    doc = _report_doc()
    view = SimpleNamespace(doc=doc, _entity_tolerance=lambda: 1.0)
    pick = DimensionOverlayMixin._dim_pick(view, 95.3, 54.8)
    assert pick[0] == "pt" and pick[1].entity_id == "spline_1" and pick[2] == "pt2"


def test_distances_from_the_origin_hold_a_spline_point_and_undo_restores_it():
    doc = _report_doc()
    sid = doc.active_sketch.sketch_id
    doc.add_dimension_constraint(sid, "HORIZ_DIST", "line_4", 100.0, refs=["spline_1"], pts=["p1", "pt2"], offset=5)
    doc.add_dimension_constraint(sid, "VERT_DIST", "line_4", 60.0, refs=["spline_1"], pts=["p1", "pt2"], offset=5)
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    assert spline.points[2] == pytest.approx((100.0, 60.0))
    assert spline.points[1] == pytest.approx((55.0, 20.0))          # the other points stay where they were
    assert sk.dof == 0

    assert doc.update_dimension(sid, sk.dimensions[-1].dim_id, 70.0)  # editing the value moves the point again
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    assert spline.points[2] == pytest.approx((100.0, 70.0))

    again = Sketch.from_dict(sk.to_dict())
    assert [d.pts for d in again.dimensions[-2:]] == [["p1", "pt2"], ["p1", "pt2"]]
    doc.undo()
    doc.undo()
    doc.undo()
    assert doc.active_sketch.get_entity("spline_1").points[2] == pytest.approx((95.0, 55.0))


def test_only_dimensioned_spline_points_enter_the_solver():
    from omacad.model.sketch_solver import _solver_entities
    doc = _report_doc()
    sk = doc.active_sketch
    assert not {"spline_1", "spline_3"} & set(_solver_entities(sk))   # a spline without dimensions adds no DOF
    doc.add_dimension_constraint(sk.sketch_id, "HORIZ_DIST", "line_4", 100.0, refs=["spline_1"], pts=["p1", "pt2"])
    assert doc.active_sketch.dof == 1          # was fully defined; one coordinate of the point is still free


@pytest.mark.parametrize("distance", [3.0, -3.0, 10.0])
def test_offset_of_a_control_point_spline_is_a_control_point_spline_with_as_many_points(distance):
    sk = _report_doc().active_sketch
    for eid in ("spline_1", "spline_3"):
        src = sk.get_entity(eid)
        new = sk.offset_entities([eid], distance)
        assert len(new) == 1 and isinstance(new[0], SketchSpline)
        assert new[0].control_points and len(new[0].points) == len(src.points)
        original = LineString(src.get_points(64))
        fitted = LineString(new[0].get_points(64))
        assert fitted.hausdorff_distance(original.offset_curve(distance)) < 0.05
        for p in new[0].get_points(64):
            assert original.distance(Point(p)) == pytest.approx(abs(distance), abs=0.05)


def test_offset_past_the_curvature_radius_stays_control_point_splines_without_loops():
    """Where the distance is larger than a bend's radius the offset gets a corner (its loop is trimmed): the
    stretches between corners become control point splines of their own, none crossing itself."""
    sk = Sketch.from_dict(_report_doc().active_sketch.to_dict())
    wavy = sk.add_spline([(0, 0), (20, 25), (40, -25), (60, 25), (80, -25), (100, 0)], control_points=True)
    for distance in (5.0, 12.0, -12.0):
        new = sk.offset_entities([wavy.entity_id], distance)
        exact = LineString(wavy.get_points(64)).offset_curve(distance)
        assert new and all(isinstance(e, SketchSpline) and e.control_points for e in new)
        assert all(LineString(e.get_points(64)).is_simple for e in new)
        joined = [p for e in new for p in e.get_points(64)]
        assert max(exact.distance(Point(p)) for p in joined) < max(0.1, 0.05 * abs(distance))
        assert sum(len(e.points) for e in new) <= len(wavy.points) + 24 * len(new)


def test_add_control_point_goes_where_the_cursor_is_and_dimensions_keep_their_point():
    doc = _report_doc()
    sid = doc.active_sketch.sketch_id
    doc.add_dimension_constraint(sid, "HORIZ_DIST", "line_4", 100.0, refs=["spline_1"], pts=["p1", "pt2"])
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    # between (55, 20) and (100, 55): the shortest detour of the control polygon
    assert sk.insert_spline_point("spline_1", (80.0, 30.0)) == 2
    assert spline.control_points and spline.points[2] == (80.0, 30.0) and len(spline.points) == 5
    assert sk.dimensions[-1].pts == ["p1", "pt3"]
    assert spline.points[3] == pytest.approx((100.0, 55.0))
    # near the far end: after the last but one point
    assert sk.insert_spline_point("spline_1", (118.0, 100.0)) == 4


def test_add_control_point_from_the_fan_menu_after_the_click_event_is_gone():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QSurfaceFormat
    from PySide6.QtWidgets import QApplication
    from omacad.ui.viewport.viewport import Viewport3D
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    doc = _report_doc()
    vp = Viewport3D(doc)
    vp.resize(800, 600)
    vp.align_to_plane(doc.active_sketch.plane)
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    scr = vp.world_to_screen(sk.plane.uv_to_world(80.0, 30.0))
    at = QPointF(scr[0], scr[1])
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, at, vp.mapToGlobal(at), Qt.MouseButton.RightButton,
                        Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)
    vp._show_element_menu(event, spline)
    import shiboken6
    shiboken6.delete(event)                      # Qt deletes it before the fan menu runs the item
    items = {i.id: i for c in vp._ensure_fan_menu().categories for i in (c.children or [])}
    items["el_insert_point"].callback()
    spline = doc.active_sketch.get_entity("spline_1")
    assert len(spline.points) == 5
    assert spline.points[2] == pytest.approx((80.0, 30.0), abs=0.5)


@pytest.mark.parametrize("distance", [2.0, -2.0, 5.0])
def test_closed_control_point_spline_offsets_to_a_closed_one_with_as_many_points(distance):
    from shapely.geometry import Polygon
    sk = Sketch.from_dict(_report_doc().active_sketch.to_dict())
    loop = sk.add_spline([(0, 0), (20, -5), (30, 20), (5, 30), (-10, 15), (0, 0)], control_points=True)
    new = sk.offset_entities([loop.entity_id], distance)
    assert len(new) == 1 and new[0].control_points and len(new[0].points) == len(loop.points)
    assert new[0].points[0] == pytest.approx(new[0].points[-1])
    # positive = outward; the seam's kink stays a kink (mitred), as in the original
    exact = Polygon(loop.get_points(64)).buffer(distance, join_style="mitre", mitre_limit=10.0).exterior
    assert max(exact.distance(Point(p)) for p in new[0].get_points(64)) < max(0.1, 0.05 * abs(distance))
