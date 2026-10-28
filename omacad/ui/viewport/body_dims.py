"""Length, width and height of the selected bodies, drawn as dimension arrows beside them (Björn #106)."""

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QFont, QPolygonF
from omacad.ui import theme

GAP = 26.0      # px from the box edge out to the dimension line


def box_corners(lo, hi) -> np.ndarray:
    """The 8 corners of an axis-aligned box; corner i has x = hi when bit 0 is set, y bit 1, z bit 2."""
    return np.array([[(lo, hi)[i & 1][0], (lo, hi)[(i >> 1) & 1][1], (lo, hi)[(i >> 2) & 1][2]] for i in range(8)], float)


def dimension_edges(screen: np.ndarray, lo, hi):
    """Which box edges to dimension, as (corner a, corner b, value): the two floor edges at the floor corner lowest on
    screen (nearest the viewer) and the upright edge at the end of those two that lies furthest right."""
    size = np.asarray(hi, float) - np.asarray(lo, float)
    front = max(range(4), key=lambda i: screen[i][1])
    edges = [(front, front ^ 1, size[0]), (front, front ^ 2, size[1])]
    side = max((front ^ 1, front ^ 2), key=lambda i: screen[i][0])
    edges.append((side, side | 4, size[2]))
    return [(a, b, v) for a, b, v in edges if v > 1e-6]


def draw_body_dimensions(vp, painter: QPainter) -> None:
    doc = vp.doc
    if doc.active_sketch is not None:
        return
    bodies = [doc.bodies[b] for b in doc.selected_body_ids
              if b in doc.bodies and doc.bodies[b].visible and doc.bodies[b].render_mesh is not None
              and len(doc.bodies[b].render_mesh.vertices) > 0]
    if not bodies:
        return
    lo = np.min([b.render_mesh.bounds_min for b in bodies], axis=0).astype(float)
    hi = np.max([b.render_mesh.bounds_max for b in bodies], axis=0).astype(float)
    screen, front = vp.project_points(box_corners(lo, hi))
    if not front.all():
        return
    centre = screen.mean(axis=0)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    font = QFont(painter.font())
    font.setPixelSize(13)
    painter.setFont(font)
    for a, b, value in dimension_edges(screen, lo, hi):
        _draw_dimension(painter, screen[a], screen[b], centre, f"{value:.2f}")
    painter.restore()


def _draw_dimension(painter: QPainter, a, b, centre, label: str) -> None:
    d = b - a
    length = float(np.hypot(*d))
    if length < 12:
        return
    u = d / length
    n = np.array([-u[1], u[0]])
    if np.dot(n, (a + b) / 2 - centre) < 0:      # outwards, away from the body
        n = -n
    p, q = a + n * GAP, b + n * GAP
    line = theme.qcolor(224, 227, 231, 220)
    painter.setPen(QPen(line, 1.2))
    for s, t in ((a, p), (b, q)):                 # extension lines from the corners
        painter.drawLine(QPointF(*(s + n * 4)), QPointF(*(t + n * 6)))
    painter.drawLine(QPointF(*p), QPointF(*q))
    painter.setBrush(line)
    for tip, back in ((p, u), (q, -u)):
        base = tip + back * 9
        painter.drawPolygon(QPolygonF([QPointF(*tip), QPointF(*(base + n * 3.5)), QPointF(*(base - n * 3.5))]))
    fm = painter.fontMetrics()
    w, h = fm.horizontalAdvance(label) + 16, fm.height() + 8
    mid = (p + q) / 2
    rect = QRectF(mid[0] - w / 2, mid[1] - h / 2, w, h)
    painter.setPen(QPen(theme.qcolor(90, 96, 104), 1))
    painter.setBrush(theme.qcolor(37, 40, 44, 240))
    painter.drawRoundedRect(rect, 4, 4)
    painter.setPen(theme.qcolor(224, 227, 231))
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
