"""Looks at the result: the jar's inner thread is rendered in the real viewport (needs the real display) and the
picture must stay as clean as before the offset. Hairy ("fnas") walls show up as many vertical light/dark stripes:
the ratio of horizontal to vertical brightness change in the thread picture jumps from ~0.19 to ~0.46."""
import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QImage, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.ui.main_window import MainWindow

DOC = str(Path(__file__).parent / "data" / "offset_face_coil_stuck.omacad")


def _picture(win, app, doc):
    win.attach_document(doc)
    win.showFullScreen()            # the same picture size on every run (a tiling window manager resizes others)
    t = time.time()
    while time.time() - t < 1.5:
        app.processEvents()
    vp = win.viewport
    vp.azimuth, vp.elevation, vp.distance = 193.3, 22.0, 16.0
    vp.target = np.array([0.0, 0.0, 15.0])
    doc.bodies["body_cylinder_1"].visible = False
    for sid in doc.sections:
        doc.set_section_active(sid, True)
    for _ in range(40):
        app.processEvents()
    vp.update()
    for _ in range(20):
        app.processEvents()
    img = vp.grabFramebuffer()
    if img.isNull():                  # no GL context (CI, offscreen)
        return None
    img = img.convertToFormat(QImage.Format.Format_Grayscale8)
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[:, :w].astype(float)
    return a[int(h * 0.1):int(h * 0.5), int(w * 0.3):int(w * 0.7)]      # the inside of the thread


def _stripes(c) -> float:
    return float(np.abs(np.diff(c, axis=1)).mean() / max(np.abs(np.diff(c, axis=0)).mean(), 1e-9))


def _doc(mode):
    doc = Exporter.load_project(DOC)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    if mode == "thread":
        doc.add_offset_face("body_split_2", last.faces, -0.2)
    elif mode == "mesh":             # the old way, deforming the finished mesh
        last.suppressed = False
        doc.timeline.recompute(doc)
    return doc


def test_thread_offset_looks_as_clean_as_the_original():
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication.instance() or QApplication([])
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    ratios = {}
    for mode in ("orig", "thread", "mesh"):
        win = MainWindow()
        pic = _picture(win, app, _doc(mode))
        win.close()
        if pic is None or pic.std() < 1.0:
            pytest.skip("no GL picture (offscreen)")
        ratios[mode] = _stripes(pic)
    assert ratios["thread"] < ratios["orig"] * 1.2, ratios      # as clean as the thread was before
    assert ratios["mesh"] > ratios["thread"] * 1.3, ratios      # and the measure does see the hairy mesh result
