"""#227: the cursor locks onto the origin axes (visible before the first click), like Fusion."""
from omacad.model.sketch import Sketch
from omacad.model.sketch_entities import SketchPlane
from omacad.model.sketch_snap import SketchSnapper


def _sketch(name="XZ"):
    return Sketch("s", "Sketch", SketchPlane.create_named(name))


def test_hover_near_axis_locks_onto_it_before_first_click():
    sk = _sketch("XZ")
    r = SketchSnapper.snap((12.3, 0.6), sk, None, snap_distance=1.0, grid_step=0.0,
                           enable_grid_snap=False, infer=True)
    assert r.snap_type == "AXIS" and r.uv == (12.3, 0.0) and r.label == "On X axis"
    r = SketchSnapper.snap((-0.7, 8.0), sk, None, snap_distance=1.0, grid_step=0.0,
                           enable_grid_snap=False, infer=True)
    assert r.snap_type == "AXIS" and r.uv == (0.0, 8.0) and r.label == "On Z axis"


def test_far_from_axes_and_face_planes_do_not_lock():
    sk = _sketch("XY")
    r = SketchSnapper.snap((12.3, 5.0), sk, None, snap_distance=1.0, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type == "NONE"
    face = Sketch("f", "Face", SketchPlane.from_face([0, 0, 1], [0, 0, 5]))
    r = SketchSnapper.snap((12.3, 0.5), face, None, snap_distance=1.0, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type != "AXIS"


def test_vertical_line_end_lands_on_horizontal_axis():
    sk = _sketch("XY")
    r = SketchSnapper.snap((10.2, 0.4), sk, (10.0, 20.0), snap_distance=1.0, grid_step=0.0,
                           enable_grid_snap=False)
    assert r.snap_type == "ORTHO_V" and r.uv == (10.0, 0.0)
