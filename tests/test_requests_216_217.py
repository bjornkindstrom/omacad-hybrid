"""Linked hole sizes and selection order when driving sketch distances."""
import math
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchCircle
from omacad.model.sketch_pattern import circular_copies, corner_copies, rectangular_copies
from omacad.ui import settings as settings_mod

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def view(tmp_path, monkeypatch):
    from omacad.ui.viewport import Viewport3D
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "settings.json"))
    vp = Viewport3D(Document())
    vp.resize(800, 600)
    yield vp
    vp.close()
    vp.deleteLater()
    _app.processEvents()


@pytest.mark.parametrize("kind", ["corners", "rectangular", "circular"])
@pytest.mark.parametrize("linked", [True, False])
def test_master_diameter_drives_holes_after_save_and_undo(kind, linked, tmp_path):
    doc = Document()
    sk = doc.start_sketch("XY")
    master = sk.add_circle((-40., 20.), 5.)
    if kind == "corners":
        copies = corner_copies(sk, [master], (-50., -30., 50., 30.), linked=linked)
    elif kind == "rectangular":
        copies = rectangular_copies(sk, [master], 2, 80., 2, -40., linked=linked)
    else:
        copies = circular_copies(sk, [master], 4, (0., 0.), linked=linked)
    positions = {c.entity_id: tuple(c.center) for c in copies}
    diameter = next(d for d in sk.dimensions if d.target_entity_id == master.entity_id)
    assert doc.update_dimension(sk.sketch_id, diameter.dim_id, 16.)
    for eid, position in positions.items():
        assert sk.get_entity(eid).radius == pytest.approx(8. if linked else 5.)
        assert sk.get_entity(eid).center == pytest.approx(position)
    doc.undo()
    assert all(e.radius == pytest.approx(5.) for e in sk.entities)
    doc.redo()
    path = tmp_path / "holes.omacad"
    doc.finish_sketch()
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    restored = loaded.sketches[sk.sketch_id]
    assert loaded.update_dimension(sk.sketch_id, diameter.dim_id, 12.)
    assert restored.get_entity(master.entity_id).radius == pytest.approx(6.)
    for eid in positions:
        assert restored.get_entity(eid).radius == pytest.approx(6. if linked else 5.)


def test_pattern_panel_link_option_preview_cancel_and_undo(view):
    doc = view.doc
    sk = doc.start_sketch("XY")
    sk.add_rect((-50., -30.), (50., 30.))
    master = sk.add_circle((-40., 20.), 5.)
    before = sk.to_dict()
    view.selected_entities = {master.entity_id}
    view.set_sketch_tool("PATTERN")
    panel = view.pattern_panel
    panel.kind.setCurrentIndex(panel.kind.findData("corners"))
    assert panel.linked.isChecked()
    assert len([c for c in sk.constraints if c.ctype == "EQUAL"]) == 3
    view._pattern_preview()
    assert len([c for c in sk.constraints if c.ctype == "EQUAL"]) == 3
    panel.linked.setChecked(False)
    assert not any(c.ctype == "EQUAL" for c in sk.constraints)
    panel.linked.setChecked(True)
    panel.cancel.click()
    assert sk.to_dict() == before
    view.selected_entities = {master.entity_id}
    view.set_sketch_tool("PATTERN")
    panel.ok.click()
    assert len([e for e in sk.entities if isinstance(e, SketchCircle)]) == 4
    doc.undo()
    assert sk.to_dict() == before
    doc.redo()
    assert len([c for c in sk.constraints if c.ctype == "EQUAL"]) == 3


def test_linked_hole_keeps_its_edge_clearance_when_master_diameter_changes():
    doc = Document()
    sk = doc.start_sketch("XY")
    line = sk.add_line((-50., 30.), (50., 30.))
    master = sk.add_circle((-20., 10.), 5.)
    copy, = rectangular_copies(sk, [master], 2, 40.)
    assert doc.add_constraints(sk.sketch_id, [("FIX", [line.entity_id], [])])
    assert doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", copy.entity_id, 15.,
                                        refs=[line.entity_id], pts=["edge_near"],
                                        moving_entity_id=copy.entity_id)
    diameter = next(d for d in sk.dimensions if d.target_entity_id == master.entity_id)
    assert doc.update_dimension(sk.sketch_id, diameter.dim_id, 16.)
    assert copy.radius == pytest.approx(8.)
    assert abs(line.p1[1] - copy.center[1]) - copy.radius == pytest.approx(15.)


@pytest.mark.parametrize("slope", [0., 0.2])
def test_parallel_lines_move_the_first_selection(view, monkeypatch, slope):
    sk = view.doc.start_sketch("XY")
    first = sk.add_line((-30., 0.), (30., 0.))
    second = sk.add_line((-30., 20.), (30., 20. + slope))
    before = second.to_dict()
    undo_count = len(view.doc.undo_stack)
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda *_, **kw: (12., None))
    view.handle_dimension_tool_click(0., 0.)
    view.handle_dimension_tool_click(0., 20. + slope / 2)
    assert second.to_dict() == before
    from omacad.model.dim_layout import line_distance
    assert line_distance(first, second) == pytest.approx(12.)
    assert len(view.doc.undo_stack) == undo_count + 1
    view.doc.undo()
    assert not any(c.ctype == "PARALLEL" for c in sk.constraints)


def test_angle_moves_first_arm(view, monkeypatch):
    sk = view.doc.start_sketch("XY")
    first = sk.add_line((0., 0.), (30., 0.))
    second = sk.add_line((0., 0.), (0., 30.))
    before = second.to_dict()
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda *_, **kw: (60., None))
    view._dim_angle(first, second)
    assert second.to_dict() == before
    assert first.p2 != pytest.approx((30., 0.))


@pytest.mark.parametrize("circle_first", [True, False])
@pytest.mark.parametrize("rim", [True, False])
def test_circle_line_click_order_survives_edit_save_and_undo(view, monkeypatch, circle_first, rim, tmp_path):
    doc = view.doc
    sk = doc.start_sketch("XY")
    line = sk.add_line((-30., 30.), (30., 30.))
    circle = sk.add_circle((0., 10.), 5.)
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    picks = [("ent", circle) if rim else ("pt", circle, "center"), ("ent", line)]
    if not circle_first:
        picks.reverse()
    pick_iter = iter(picks)
    monkeypatch.setattr(type(view), "_dim_pick", lambda *_: next(pick_iter))
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda *_, **kw: (10., None))
    stationary = line if circle_first else circle
    stationary_before = stationary.to_dict()
    assert view.handle_dimension_tool_click(0., 15.)
    assert view.handle_dimension_tool_click(0., 15.)
    dim = next(d for d in sk.dimensions if d.dim_type == "PT_LINE_DIST")
    assert dim.moving_entity_id == (circle.entity_id if circle_first else line.entity_id)
    assert sk.get_entity(stationary.entity_id).to_dict() == stationary_before
    distance = abs(sk.get_entity(circle.entity_id).center[1] - sk.get_entity(line.entity_id).p1[1])
    assert distance == pytest.approx(15. if rim else 10.)
    doc.undo()
    assert sk.get_entity(circle.entity_id).center == pytest.approx((0., 10.))
    assert sk.get_entity(line.entity_id).p1 == pytest.approx((-30., 30.))
    doc.redo()
    path = tmp_path / "distance.omacad"
    doc.finish_sketch()
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    assert loaded.update_dimension(sk.sketch_id, dim.dim_id, 12.)
    restored = loaded.sketches[sk.sketch_id]
    assert restored.get_entity(stationary.entity_id).to_dict() == stationary_before
    distance = abs(restored.get_entity(circle.entity_id).center[1] - restored.get_entity(line.entity_id).p1[1])
    assert distance == pytest.approx(17. if rim else 12.)


@pytest.mark.parametrize("kind", ["DISTANCE", "HORIZ_DIST", "VERT_DIST"])
def test_point_distance_moves_first_circle_only(kind):
    doc = Document()
    sk = doc.start_sketch("XY")
    first = sk.add_circle((0., 0.), 2.)
    second = sk.add_circle((30., 40.), 3.)
    before = second.to_dict()
    assert doc.add_dimension_constraint(sk.sketch_id, kind, first.entity_id, 20.,
                                        refs=[second.entity_id], pts=["center", "center"],
                                        moving_entity_id=first.entity_id)
    assert second.to_dict() == before
    x, y = first.center
    value = math.hypot(x - 30., y - 40.) if kind == "DISTANCE" else abs((x - 30.) if kind == "HORIZ_DIST" else (y - 40.))
    assert value == pytest.approx(20.)


def test_fixed_first_selection_rejects_distance_instead_of_moving_target():
    doc = Document()
    sk = doc.start_sketch("XY")
    first = sk.add_circle((0., 0.), 2.)
    second = sk.add_circle((30., 0.), 3.)
    assert doc.add_constraints(sk.sketch_id, [("FIX", [first.entity_id], [])])
    before = sk.to_dict()
    assert not doc.add_dimension_constraint(sk.sketch_id, "HORIZ_DIST", first.entity_id, 20.,
                                            refs=[second.entity_id], pts=["center", "center"],
                                        moving_entity_id=first.entity_id)
    assert sk.to_dict() == before


def test_legacy_dimensions_load_without_selection_metadata():
    sk = Sketch("legacy")
    first = sk.add_circle((0., 0.), 2.)
    data = sk.to_dict()
    for dim in data["dimensions"]:
        dim.pop("moving_entity_id", None)
    restored = Sketch.from_dict(data)
    assert restored.get_entity(first.entity_id).radius == 2.


def report_sketch(doc):
    data = json.loads((Path(__file__).parent / "data" / "hole_pattern_master_216.json").read_text())
    sk = Sketch.from_dict(data)
    doc.sketches[sk.sketch_id] = sk
    doc.active_sketch = sk
    return sk


def test_report_holes_recreated_as_a_linked_corner_pattern():
    doc = Document()
    sk = report_sketch(doc)
    master = sk.get_entity("circle_9")
    sk.entities = [e for e in sk.entities if not isinstance(e, SketchCircle) or e is master]
    from omacad.model.sketch_pattern import corner_bounds
    copies = corner_copies(sk, [master], corner_bounds(sk, [master]))
    assert len(copies) == 3
    assert doc.update_dimension(sk.sketch_id, "d3", 14.)
    assert all(e.radius == pytest.approx(7.) for e in sk.entities if isinstance(e, SketchCircle))


@pytest.mark.parametrize("circle_first", [True, False])
def test_report_rectangle_and_hole_follow_click_order(view, monkeypatch, circle_first):
    sk = report_sketch(view.doc)
    line, hole = sk.get_entity("line_3"), sk.get_entity("circle_8")
    before = (line if circle_first else hole).to_dict()
    picks = [("ent", hole), ("ent", line)]
    if not circle_first:
        picks.reverse()
    pick_iter = iter(picks)
    monkeypatch.setattr(type(view), "_dim_pick", lambda *_: next(pick_iter))
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda *_, **kw: (15., None))
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    view.handle_dimension_tool_click(80., 45.)
    view.handle_dimension_tool_click(80., 45.)
    assert len(sk.dimensions) == 6, view.doc.last_message
    assert (line if circle_first else hole).to_dict() == before
    assert abs(line.p1[1] - hole.center[1]) - hole.radius == pytest.approx(15.)
