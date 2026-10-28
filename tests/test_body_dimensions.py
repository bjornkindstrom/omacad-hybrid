"""Björn #106: a selected body shows its length, width and height as dimension arrows beside it."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace

import numpy as np
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui.viewport.body_dims import box_corners, dimension_edges, draw_body_dimensions


class _Recorder(QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.texts = []

    def drawText(self, *args):
        self.texts.append(args[-1])
        return super().drawText(*args)


def _view(doc):
    """An isometric-ish projection seen from +x, -y, above: the floor corner nearest the viewer is (hi x, lo y)."""
    def project(pts):
        p = np.asarray(pts, float)
        x = 200 + (p[:, 0] + p[:, 1]) * 2.0
        y = 300 + (p[:, 0] - p[:, 1]) * 1.0 - p[:, 2] * 2.0
        return np.c_[x, y], np.ones(len(p), bool)
    return SimpleNamespace(doc=doc, project_points=project)


def test_edges_are_the_front_floor_edges_and_one_upright():
    lo, hi = (0, 0, 0), (43, 47, 20)
    screen, _ = _view(None).project_points(box_corners(lo, hi))
    edges = dimension_edges(screen, lo, hi)
    assert sorted(round(v, 6) for _a, _b, v in edges) == [20, 43, 47]
    front = edges[0][0]
    assert tuple(box_corners(lo, hi)[front]) == (43, 0, 0)
    upright = edges[2]
    assert box_corners(lo, hi)[upright[1]][2] == 20 and box_corners(lo, hi)[upright[0]][2] == 0


def test_selected_body_draws_its_three_sizes_and_nothing_without_selection():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(43, 47, 20)
    image = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = _Recorder(image)
    draw_body_dimensions(_view(doc), painter)
    assert painter.texts == []
    doc.selected_body_ids = list(doc.bodies)
    draw_body_dimensions(_view(doc), painter)
    painter.end()
    assert sorted(painter.texts) == ["20.00", "43.00", "47.00"]
