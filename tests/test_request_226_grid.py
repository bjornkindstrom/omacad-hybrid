"""#226: the grid follows Settings > grid step and is visible on the sketch plane / in front views."""
import numpy as np


def _win():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    return MainWindow()


def test_grid_uses_settings_step_and_coarsens_when_zoomed_out(monkeypatch):
    from omacad.ui import settings
    win = _win()
    v = win.viewport
    monkeypatch.setitem(settings.get_settings()._data, "grid_step", 2.0)
    v.distance = 60.0
    _frame, minor, major = v.grid_lines()
    ys = sorted({round(a[1], 6) for a, b in minor + major if abs(a[1] - b[1]) < 1e-9})
    gaps = np.diff(ys)
    step = float(gaps.min())
    assert step >= 2.0 - 1e-9 and abs(step / 2.0 - round(step / 2.0)) < 1e-9
    v.distance = 5000.0
    _frame, minor_far, _ = v.grid_lines()
    ys_far = sorted({round(a[1], 6) for a, b in minor_far if abs(a[1] - b[1]) < 1e-9})
    assert float(np.diff(ys_far).min()) > step
    win.close()


def test_grid_faces_the_camera_in_front_view_and_lies_on_sketch_plane():
    from omacad.model.sketch_entities import SketchPlane
    win = _win()
    v = win.viewport
    v.azimuth, v.elevation = 0.0, 60.0
    _o, _u, _v, n = v._grid_frame()
    assert abs(n[2]) == 1.0                       # XY from above
    v.azimuth, v.elevation = 0.0, 0.0
    _o, _u, _v, n = v._grid_frame()
    assert abs(n[2]) < 1e-9                       # front view: a vertical origin plane, not the edge-on XY
    xz = SketchPlane.create_named("XZ")
    _o, u, vv, n = v._grid_frame(xz)
    assert np.allclose(n, xz.normal) and np.allclose(u, xz.u_axis)
    win.close()
