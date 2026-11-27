"""SolidWorks-style Smart Dimension on a line: one click, then where you click places it and picks its kind."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402


@pytest.fixture
def view(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    v = Viewport3D(Document())
    v.resize(800, 600)
    return v


def slanted(view):
    sk = view.doc.start_sketch("XY")
    line = sk.add_line((0.0, 0.0), (30.0, 40.0))
    sk.dimensions.clear()                      # add_line already gives a length dimension
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    assert view.handle_dimension_tool_click(15.0, 20.0)       # the middle of the line
    assert view._dim_place and view._dim_place["line"] is line
    return sk, line


def test_beside_the_line_gives_its_length(view):
    sk, line = slanted(view)
    view.handle_dimension_tool_click(5.0, 30.0)               # off to the side, diagonal zone
    assert [(d.dim_type, d.target_entity_id) for d in sk.dimensions] == [("LENGTH", line.entity_id)]
    assert sk.dimensions[0].value == pytest.approx(50.0)


def test_above_gives_the_horizontal_extent(view):
    sk, line = slanted(view)
    view.handle_dimension_tool_click(15.0, 60.0)              # above, within the line's x range
    d, = sk.dimensions
    assert (d.dim_type, d.refs, d.pts) == ("HORIZ_DIST", [line.entity_id], ["p1", "p2"])
    assert d.value == pytest.approx(30.0)


def test_beside_gives_the_vertical_extent(view):
    sk, line = slanted(view)
    view.handle_dimension_tool_click(60.0, 20.0)              # right of it, within the line's y range
    d, = sk.dimensions
    assert d.dim_type == "VERT_DIST" and d.value == pytest.approx(40.0)


def test_clicking_another_line_while_placing_gives_an_angle(view):
    sk, line = slanted(view)
    other = sk.add_line((0.0, 0.0), (40.0, 0.0))
    sk.dimensions.clear()
    view.prompt_dimension_value = lambda *a, **k: (53.13, None)
    view.handle_dimension_tool_click(20.0, 0.0)
    assert not view._dim_place
    assert [d.dim_type for d in sk.dimensions] == ["ANGLE"]


def _arc_and_wall(view):
    sk = view.doc.start_sketch("XY")
    arc = sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    wall = sk.add_line((-30.0, -20.0), (30.0, -20.0))
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    assert view.handle_dimension_tool_click(7.07, 7.07)       # on the arc: it waits like a circle
    assert view._dim_pending and view._dim_pending[0][1] is arc
    return sk, arc, wall


def test_arc_then_a_line_gives_the_distance_from_its_centre(view, monkeypatch):
    monkeypatch.setattr(type(view), "prompt_dimension_value", lambda self, *a, **k: (25.0, None))
    sk, arc, wall = _arc_and_wall(view)
    view.handle_dimension_tool_click(20.0, -20.0)              # on the wall
    sk = view.doc.active_sketch
    d = sk.dimensions[-1]
    assert (d.dim_type, d.target_entity_id, d.refs, d.pts) == ("PT_LINE_DIST", arc.entity_id, [wall.entity_id], ["center"])
    arc, wall = sk.get_entity(arc.entity_id), sk.get_entity(wall.entity_id)
    centre = arc.get_circle_params()[0]
    dist = abs(centre[1] - wall.p1[1]) if abs(wall.p1[1] - wall.p2[1]) < 1e-9 else None
    assert dist is None or dist == pytest.approx(25.0, abs=1e-6)


def test_arc_then_empty_space_edits_its_radius(view, monkeypatch):
    seen = []
    monkeypatch.setattr(type(view), "prompt_edit_dimension", lambda self, sid, did, value: seen.append(value))
    sk, arc, wall = _arc_and_wall(view)
    view.handle_dimension_tool_click(40.0, 40.0)               # away from everything
    assert seen == [pytest.approx(10.0)]                       # the arc's own radius dimension
