"""Viewport ground grid tests: sizing, camera alignment, sketch planes, and occlusion."""
import numpy as np
import pytest
from PySide6.QtGui import QImage, QSurfaceFormat
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from omacad.model.document import Document
from omacad.model.sketch_entities import SketchPlane
from omacad.ui.main_window import MainWindow
from omacad.ui.viewport.viewport import Viewport3D


def _win():
    QApplication.instance() or QApplication([])
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
    win.deleteLater()


def test_grid_faces_the_camera_in_front_view_and_lies_on_sketch_plane():
    win = _win()
    v = win.viewport
    v.azimuth, v.elevation = 0.0, 60.0
    _o, _u, _v, n = v._grid_frame()
    assert abs(n[2]) == 1.0
    v.azimuth, v.elevation = 0.0, 0.0
    _o, _u, _v, n = v._grid_frame()
    assert abs(n[2]) < 1e-9
    xz = SketchPlane.create_named("XZ")
    _o, u, vv, n = v._grid_frame(xz)
    assert np.allclose(n, xz.normal) and np.allclose(u, xz.u_axis)
    win.close()
    win.deleteLater()


def _pixels(view):
    img = view.grabFramebuffer().convertToFormat(QImage.Format.Format_RGB888)
    assert not img.isNull()
    return np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 3].reshape(img.height(), img.width(), 3).copy()


@pytest.mark.desktop
@pytest.mark.parametrize("elevation", [-30, 30])
def test_ground_grid_does_not_cover_the_body(elevation):
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    doc = Document()
    doc.add_box(50, 40, 30)
    vp = Viewport3D(doc)
    vp.resize(800, 700)
    vp.show()
    try:
        QTest.qWait(1500)
        vp.azimuth, vp.elevation, vp.distance = 210.0, float(elevation), 240.0
        vp.target = np.array([25.0, 20.0, 15.0])
        vp.render_origin_axes = lambda mvp: None
        vp.draw_painter_overlays = lambda painter: None
        vp.show_grid = False
        plain = _pixels(vp)
        body = next(iter(doc.bodies.values()))
        body.visible = False
        empty = _pixels(vp)
        body.visible = True
        footprint = np.any(plain != empty, axis=2)
        inside = footprint.copy()
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                inside &= np.roll(footprint, (dy, dx), axis=(0, 1))
        assert inside.sum() > 1000
        vp.show_grid = True
        grid = _pixels(vp)
        assert np.array_equal(grid[inside], plain[inside])
        assert np.any(grid[~footprint] != plain[~footprint])
    finally:
        vp.close()
        vp.deleteLater()
