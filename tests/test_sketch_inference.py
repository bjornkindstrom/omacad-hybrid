"""SolidWorks-style inference lines: line up with existing points while drawing."""
import pytest

from omacad.model.document import Document
from omacad.model.sketch_snap import SketchSnapper


def _sketch():
    sk = Document().start_sketch()
    sk.add_line((20.0, 30.0), (50.0, 30.0))
    return sk


def test_lines_up_vertically_with_an_existing_point():
    r = SketchSnapper.snap((20.6, 71.0), _sketch(), snap_distance=1.0, grid_step=5.0, infer=True)
    assert r.snap_type == "INFER"
    assert r.uv == pytest.approx((20.0, 70.0))          # u from the point, v from the grid
    assert r.inferences == (((20.0, 30.0), (20.0, 70.0)),)


def test_two_inferences_meet_at_their_crossing():
    sk = _sketch()
    sk.add_line((80.0, 60.0), (90.0, 60.0))
    r = SketchSnapper.snap((49.5, 60.4), sk, snap_distance=1.0, grid_step=0.0, enable_grid_snap=False, infer=True)
    assert r.uv == pytest.approx((50.0, 60.0))
    assert len(r.inferences) == 2


def test_horizontal_from_start_stops_under_another_point():
    r = SketchSnapper.snap((34.6, 0.3), _sketch(), start_uv=(0.0, 0.0), snap_distance=1.0, infer=True)
    assert r.snap_type == "ORTHO_H"
    assert r.uv == pytest.approx((35.0, 0.0))            # midpoint of the line above
    assert r.inferences == (((35.0, 30.0), (35.0, 0.0)),)


def test_off_without_the_flag():
    r = SketchSnapper.snap((20.6, 71.0), _sketch(), snap_distance=1.0, grid_step=5.0)
    assert r.snap_type == "GRID" and not r.inferences
