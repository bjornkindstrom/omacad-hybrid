"""Björn #48: a sketch started on a face centres that face and zooms so it fills most of the view."""
import math

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow
from omacad.model.sketch import SketchPlane


@pytest.mark.parametrize("size", [8.0, 300.0])
def test_sketch_on_face_frames_the_face(size):
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.doc.add_box(size, size, 10)
    body = next(iter(w.doc.bodies.values()))
    face = max(body.faces, key=lambda f: float(np.asarray(f.normal) @ [0, 0, 1]) * 1e6 + float(np.asarray(f.origin)[2]))
    plane = SketchPlane.from_face(face.normal, face.origin)
    plane.face = face
    w.viewport.distance, w.viewport.target = 900.0, np.array([500.0, 500.0, 0.0], dtype=np.float32)
    w.on_plane_picked(plane)
    v = w.viewport
    pts = np.asarray(face.tris, dtype=float).reshape(-1, 3)
    assert np.allclose(v.target[:2], (pts.min(axis=0)[:2] + pts.max(axis=0)[:2]) / 2, atol=1e-3)
    seen = 2.0 * v.distance * math.tan(math.radians(v.fovy) / 2.0) * min(1.0, v.width() / max(1, v.height()))
    assert 0.6 < size / seen < 0.95                      # fills the view, with a margin
    w.close()
