"""Request #87: the ground grid is background, including when viewed from below."""
import numpy as np
import pytest
from PySide6.QtGui import QImage, QSurfaceFormat
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from omacad.model.document import Document
from omacad.ui.viewport.viewport import Viewport3D


def _pixels(view):
    img = view.grabFramebuffer().convertToFormat(QImage.Format.Format_RGB888)
    assert not img.isNull()
    return np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 3].reshape(img.height(), img.width(), 3).copy()


@pytest.mark.parametrize('elevation', [-30, 30])
def test_ground_grid_does_not_cover_the_body(elevation):
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    if app.platformName() in ('offscreen', 'minimal'):
        pytest.skip('needs the real display (GL)')
    doc = Document()
    doc.add_box(50, 40, 30)
    vp = Viewport3D(doc)
    vp.resize(800, 700)
    vp.show()
    try:
        QTest.qWait(1500)
        vp.azimuth, vp.elevation, vp.distance = 210., float(elevation), 240.
        vp.target = np.array([25., 20., 15.])
        vp.render_origin_axes = lambda mvp: None
        vp.draw_painter_overlays = lambda painter: None
        vp.show_grid = False
        plain = _pixels(vp)
        # Obtain the solid's screen footprint independently of its colour or theme.
        body = next(iter(doc.bodies.values()))
        body.visible = False
        empty = _pixels(vp)
        body.visible = True
        footprint = np.any(plain != empty, axis=2)
        # Stay clear of antialiased silhouette pixels.
        inside = footprint.copy()
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                inside &= np.roll(footprint, (dy, dx), axis=(0, 1))
        assert inside.sum() > 1000
        vp.show_grid = True
        grid = _pixels(vp)
        assert np.array_equal(grid[inside], plain[inside])
        assert np.any(grid[~footprint] != plain[~footprint])  # still visible around the body
    finally:
        vp.close()
