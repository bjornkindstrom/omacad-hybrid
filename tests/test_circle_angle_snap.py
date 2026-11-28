"""Circle 45-degree snapping and point-to-point dimensions between circle angle points."""
import math
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchPlane, point_of
from omacad.model.sketch_snap import SketchSnapper
from omacad.model.sketch_solver import solve_sketch
from omacad.ui import settings as settings_mod


def test_snap_circle_45_degree_points():
    sk = Sketch("sk", SketchPlane())
    sk.add_circle((10.0, 20.0), 10.0)

    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        ex, ey = 10.0 + 10.0 * math.cos(rad), 20.0 + 10.0 * math.sin(rad)
        res = SketchSnapper.snap(
            raw_uv=(ex + 0.15, ey - 0.15),
            sketch=sk,
            start_uv=None,
            snap_distance=0.5,
            reference_segments=None,
            grid_step=1.0,
            enable_grid_snap=False,
            enable_geom_snap=True,
            infer=False,
        )
        assert res.snap_type == "ENDPOINT"
        assert res.uv == pytest.approx((ex, ey), abs=1e-6)

    # Away from 45-degree multiples, snapping falls back to EDGE on the circle perimeter
    rad20 = math.radians(20)
    res_edge = SketchSnapper.snap(
        raw_uv=(10.0 + 10.2 * math.cos(rad20), 20.0 + 10.2 * math.sin(rad20)),
        sketch=sk,
        start_uv=None,
        snap_distance=0.5,
        reference_segments=None,
        grid_step=1.0,
        enable_grid_snap=False,
        enable_geom_snap=True,
        infer=False,
    )
    assert res_edge.snap_type == "EDGE"


@pytest.mark.parametrize(
    "dim_type, pt_a, pt_b, target_val, check",
    [
        ("HORIZ_DIST", "deg0", "deg180", 12.0, lambda a, b: abs(b[0] - a[0])),
        ("VERT_DIST", "deg90", "deg270", 15.0, lambda a, b: abs(b[1] - a[1])),
        ("DISTANCE", "deg45", "deg225", 20.0, lambda a, b: math.dist(a, b)),
    ],
)
def test_dimension_between_circle_angle_points(dim_type, pt_a, pt_b, target_val, check):
    doc = Document()
    sk = doc.start_sketch("XY")
    c1 = sk.add_circle((0.0, 0.0), 5.0)
    c2 = sk.add_circle((30.0, 20.0), 4.0)
    doc.add_constraints(sk.sketch_id, [("FIX", [c1.entity_id], [])])
    sk.add_dimension("DIAMETER", c2.entity_id, 8.0)
    sk.add_dimension(dim_type, c1.entity_id, target_val, refs=[c2.entity_id], pts=[pt_a, pt_b])

    res = solve_sketch(sk)
    assert res.ok, res.message
    pa, pb = point_of(c1, pt_a), point_of(c2, pt_b)
    assert check(pa, pb) == pytest.approx(target_val, abs=1e-4)


def test_dimension_tool_picks_circle_angle_points(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from omacad.ui.viewport import Viewport3D

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))

    doc = Document()
    sk = doc.start_sketch("XY")
    c1 = sk.add_circle((0.0, 0.0), 10.0)
    c2 = sk.add_circle((40.0, 0.0), 10.0)
    doc.add_constraints(sk.sketch_id, [("FIX", [c1.entity_id], [])])

    view = Viewport3D(doc)
    view.resize(800, 600)
    view.set_sketch_tool("DIMENSION")

    p1 = point_of(c1, "deg45")
    p2 = point_of(c2, "deg135")
    assert view._dim_pick(*p1) == ("pt", c1, "deg45")
    assert view._dim_pick(*p2) == ("pt", c2, "deg135")

    assert view.handle_dimension_tool_click(*p1)
    assert view.handle_dimension_tool_click(*p2)
    assert view._dim_place is not None
    assert view._dim_place["a"] == ("pt", c1, "deg45")
    assert view._dim_place["b"] == ("pt", c2, "deg135")

    # Place horizontally above the two points
    view._dim_finish_points(20.0, 25.0)
    view._hide_dim_box()
    dims = [d for d in sk.dimensions if d.dim_type == "HORIZ_DIST"]
    assert len(dims) == 1
    assert dims[0].pts == ["deg45", "deg135"]
