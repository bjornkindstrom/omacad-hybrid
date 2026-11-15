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


# =========================================================================
# Axis snapping & origin guides (Request #227)
# =========================================================================

def _named_sketch(name="XZ"):
    from omacad.model.sketch import Sketch
    from omacad.model.sketch_entities import SketchPlane
    return Sketch("s", "Sketch", SketchPlane.create_named(name))


def test_hover_near_axis_locks_onto_it_before_first_click():
    sk = _named_sketch("XZ")
    r = SketchSnapper.snap((12.3, 0.6), sk, None, snap_distance=1.0, grid_step=0.0,
                           enable_grid_snap=False, infer=True)
    assert r.snap_type == "AXIS" and r.uv == (12.3, 0.0) and r.label == "On X axis"
    r = SketchSnapper.snap((-0.7, 8.0), sk, None, snap_distance=1.0, grid_step=0.0,
                           enable_grid_snap=False, infer=True)
    assert r.snap_type == "AXIS" and r.uv == (0.0, 8.0) and r.label == "On Z axis"


def test_far_from_axes_and_face_planes_do_not_lock():
    from omacad.model.sketch import Sketch
    from omacad.model.sketch_entities import SketchPlane

    sk = _named_sketch("XY")
    r = SketchSnapper.snap((12.3, 5.0), sk, None, snap_distance=1.0, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type == "NONE"
    face = Sketch("f", "Face", SketchPlane.from_face([0, 0, 1], [0, 0, 5]))
    r = SketchSnapper.snap((12.3, 0.5), face, None, snap_distance=1.0, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type != "AXIS"


def test_vertical_line_end_lands_on_horizontal_axis():
    sk = _named_sketch("XY")
    r = SketchSnapper.snap((10.2, 0.4), sk, (10.0, 20.0), snap_distance=1.0, grid_step=0.0,
                           enable_grid_snap=False)
    assert r.snap_type == "ORTHO_V" and r.uv == (10.0, 0.0)


# =========================================================================
# Curve centres & snap points (Request #225)
# =========================================================================

def test_arc_centre_is_a_snap_point():
    from omacad.model.sketch import Sketch
    from omacad.model.sketch_entities import SketchPlane

    sk = Sketch("s", "Sketch", SketchPlane.create_named("XY"))
    sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    r = SketchSnapper.snap((0.3, 5.2), sk, None, snap_distance=0.5, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type != "ENDPOINT"
    sk2 = Sketch("s", "Sketch", SketchPlane.create_named("XY"))
    sk2.add_arc((30.0, 20.0), (20.0, 30.0), (10.0, 20.0))
    r = SketchSnapper.snap((20.2, 20.1), sk2, None, snap_distance=0.5, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type == "ENDPOINT" and abs(r.uv[0] - 20.0) < 1e-6 and abs(r.uv[1] - 20.0) < 1e-6


def test_overlay_draws_a_centre_dot_per_circle_and_arc():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.start_sketch_on_plane("XY")
    sk = win.doc.active_sketch
    sk.add_circle((5.0, 5.0), 3.0)
    sk.add_arc((30.0, 20.0), (20.0, 30.0), (10.0, 20.0))
    sk.add_line((0.0, 0.0), (10.0, 0.0))
    drawn = []

    class P:
        def __getattr__(self, name):
            return lambda *a, **k: drawn.append(a) if name == "drawEllipse" else None

    win.viewport.world_to_screen = lambda p: (float(p[0]), float(p[1]))
    win.viewport._draw_curve_centres(P(), sk)
    assert len(drawn) == 2
    win.close()
    win.deleteLater()


