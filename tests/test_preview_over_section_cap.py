"""Request #36: under a section view the preview of a cut was hidden behind the opaque cut face. The preview is now
drawn after the cap, so it shows through the cross-section. Needs the real display (GL); skipped offscreen."""
import time

import manifold3d as m3d
import numpy as np
import pytest
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication


def _red_pixels(img) -> int:
    from PySide6.QtGui import QImage
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    a = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())[:, :img.width() * 3]
    a = a.reshape(img.height(), img.width(), 3).astype(int)
    return int(((a[..., 0] > 150) & (a[..., 1] < 140) & (a[..., 2] < 140)).sum())      # the cut preview's red


def test_cut_preview_shows_through_the_cut_face():
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    win.showFullScreen()
    win.doc.add_box(40, 40, 20)
    t = time.time()
    while time.time() - t < 1.5:
        app.processEvents()
    vp = win.viewport
    vp.azimuth, vp.elevation, vp.distance = 180.0, 0.0, 90.0          # straight at the cut face
    vp.target = np.array([0.0, 0.0, 10.0], dtype=np.float32)
    vp.set_section((0, 0, 0), (0, -1, 0), 0.0, flip=True)
    hole = m3d.Manifold.cylinder(20, 6, 6, 32).rotate([90, 0, 0]).translate([0, 10, 10])     # inside the kept half
    results = {}
    for name, preview in (("none", None), ("cut", hole)):
        vp.set_preview(preview, "cut")
        for _ in range(20):
            app.processEvents()
        vp.update()
        for _ in range(10):
            app.processEvents()
        img = vp.grabFramebuffer()
        if img.isNull():
            pytest.skip("no GL picture")
        results[name] = _red_pixels(img)
    win.close()
    assert results["cut"] > results["none"] + 20000, results     # before the fix only ~13500 more red pixels showed
