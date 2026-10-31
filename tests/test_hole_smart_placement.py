import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QImage

from omacad.ui.main_window import MainWindow
from omacad.model.sketch import SketchPlane


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1000, 800)
    w.viewport.resize(800, 600)
    yield w
    w.close()


def test_hole_placement_smart_circle_measuring_guides(win):
    """When placing a hole on a plane or face, measuring guides to the nearest straight edges
    are computed and drawn like Smart Circle."""
    body = win.doc.add_box(40.0, 30.0, 20.0)
    vp = win.viewport

    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    vp.begin_hole_place(plane)

    assert vp.hole_place_mode is True
    assert len(vp.hole_place_segments) >= 4  # The 4 edges of the top face of the box

    # Hover near center
    vp.hole_place_hover = np.array([10.0, 10.0, 20.0])

    # Render overlay onto an image buffer
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    vp.draw_painter_overlays(painter)
    painter.end()

    # Press to place a point
    assert vp._hole_place_press(400, 300)
    assert len(vp.hole_place_points) == 1

    # End placement
    vp.end_hole_place()
    assert vp.hole_place_mode is False
    assert len(vp.hole_place_segments) == 0
