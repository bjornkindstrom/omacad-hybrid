"""
Omacad - 3D ViewCube Navigation Widget
Renders an orientation cube with face, edge and corner targets and drag rotation.
"""

import math
from typing import Optional, Callable
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QPolygonF, QFont, QTransform
from omacad.ui.theme import qcolor


class ViewCube:
    """Renders a responsive 3D orientation cube overlay using QPainter."""

    FACES = [
        ("TOP", np.array([0, 0, 1]), [(0,0,1), (1,0,1), (1,1,1), (0,1,1)]),
        ("BOTTOM", np.array([0, 0, -1]), [(0,0,0), (0,1,0), (1,1,0), (1,0,0)]),
        ("FRONT", np.array([0, -1, 0]), [(0,0,0), (1,0,0), (1,0,1), (0,0,1)]),
        ("BACK", np.array([0, 1, 0]), [(0,1,0), (0,1,1), (1,1,1), (1,1,0)]),
        ("RIGHT", np.array([1, 0, 0]), [(1,0,0), (1,1,0), (1,1,1), (1,0,1)]),
        ("LEFT", np.array([-1, 0, 0]), [(0,0,0), (0,0,1), (0,1,1), (0,1,0)]),
    ]

    def __init__(self, size: int = 110, on_face_clicked: Optional[Callable[[str], None]] = None,
                 on_orbit=None):
        self.size = size
        self.on_orbit = on_orbit
        self._press = None
        self._dragged = False
        self.hit_regions = []
        self.right_margin = 25
        self.on_face_clicked = on_face_clicked
        self.hovered_face: Optional[str] = None
        self.cube_center = (0, 0)
        self.rendered_faces = []  # List of (face_name, QPolygonF, z_depth)
        self.home_hovered = False

    def home_rect(self, viewport_w):
        return QRectF(viewport_w - self.size - self.right_margin - 12, 23, 22, 22)

    def target_at(self, x, y, viewport_w):
        if self.home_rect(viewport_w).contains(x, y):
            return "HOME"
        pt = QPointF(x, y)
        for name, poly in reversed(self.hit_regions):
            if poly.containsPoint(pt, Qt.FillRule.OddEvenFill):
                return name
        return None

    def handle_mouse_move(self, local_x: int, local_y: int, viewport_w: int) -> bool:
        if self._press is not None:
            x, y, target = self._press
            dx, dy = local_x - x, local_y - y
            if self._dragged or abs(dx) + abs(dy) >= 4:
                self._dragged = True
                if self.on_orbit:
                    self.on_orbit(dx, dy)
                self._press = (local_x, local_y, target)
            return True
        target = self.target_at(local_x, local_y, viewport_w)
        changed = self.hovered_face != target or self.home_hovered != (target == "HOME")
        self.hovered_face = target
        self.home_hovered = target == "HOME"
        return changed

    def handle_mouse_press(self, local_x: int, local_y: int, viewport_w: int) -> bool:
        target = self.target_at(local_x, local_y, viewport_w)
        if target is None:
            return False
        self._press = (local_x, local_y, target)
        self._dragged = False
        return True

    def handle_mouse_release(self) -> bool:
        if self._press is None:
            return False
        _, _, target = self._press
        self._press = None
        if not self._dragged and self.on_face_clicked:
            self.on_face_clicked(target)
        self._dragged = False
        return True

    def draw(self, painter: QPainter, viewport_w: int, viewport_h: int, azimuth: float, elevation: float):
        """Draws the 3D cube rotated according to camera azimuth and elevation."""
        cube_x = viewport_w - self.size - self.right_margin
        cube_y = 35
        center_x = cube_x + self.size / 2.0
        center_y = cube_y + self.size / 2.0
        self.cube_center = (center_x, center_y)

        # 1. Draw Home Button
        home_rect = self.home_rect(viewport_w)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(qcolor(95, 105, 120), 1.2))
        painter.setBrush(QBrush(qcolor(226, 109, 40) if self.home_hovered else qcolor(45, 50, 58, 220)))
        painter.drawRoundedRect(home_rect, 4, 4)

        # Draw home house icon
        painter.setPen(QPen(qcolor(255, 255, 255) if self.home_hovered else qcolor(224, 227, 231), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        hx, hy = home_rect.center().x(), home_rect.center().y()
        house_poly = QPolygonF([
            QPointF(hx, hy - 5),
            QPointF(hx - 5, hy),
            QPointF(hx - 5, hy + 5),
            QPointF(hx + 5, hy + 5),
            QPointF(hx + 5, hy),
        ])
        painter.drawPolyline(house_poly)

        # 2. Compute View Matrix for Cube
        rad_az = math.radians(azimuth)
        rad_el = math.radians(elevation)

        # Direction from center to eye
        eye = np.array([
            math.cos(rad_el) * math.sin(rad_az),
            -math.cos(rad_el) * math.cos(rad_az),
            math.sin(rad_el)
        ], dtype=float)

        # Up and right vectors
        up = np.array([0.0, 0.0, 1.0], dtype=float)
        right = np.cross(-eye, up)
        norm_r = np.linalg.norm(right)
        if norm_r < 1e-4:
            right = np.array([1.0, 0.0, 0.0], dtype=float)
        else:
            right /= norm_r
        cam_up = np.cross(eye, right)

        # Project a unit cube centered at origin [-0.5..0.5]
        scale = self.size * 0.64

        def project(pt):
            # Center cube
            v = np.array(pt, dtype=float) - 0.5
            px = np.dot(v, right) * scale + center_x
            py = -np.dot(v, cam_up) * scale + center_y
            depth = -np.dot(v, eye)
            return px, py, depth

        # Collect faces and sort back-to-front
        faces_to_render = []
        for name, normal, corners in self.FACES:
            # Face normal dot eye gives visibility (positive means facing camera)
            vis = float(np.dot(normal, eye))
            if vis > 0.05:  # Facing camera (cull back faces)
                pts_2d = [project(c) for c in corners]
                avg_depth = sum(p[2] for p in pts_2d) / 4.0
                poly = QPolygonF([QPointF(p[0], p[1]) for p in pts_2d])
                faces_to_render.append((name, poly, avg_depth, vis, corners))

        # Sort back to front (largest depth first)
        faces_to_render.sort(key=lambda x: x[2], reverse=True)
        self.rendered_faces = []
        self.hit_regions = []

        font = QFont("sans-serif", 9, QFont.Weight.Bold)
        painter.setFont(font)

        for name, poly, depth, vis, corners in faces_to_render:
            self.rendered_faces.append((name, poly, depth))

            # Split each face into centre, edge and corner targets. Coordinates
            # remain world directions, shared by neighbouring faces.
            corners = np.asarray(corners, dtype=float)
            cuts = (0.0, 0.22, 0.78, 1.0)
            for i in range(3):
                for j in range(3):
                    def world(u, v):
                        return corners[0] + u * (corners[1] - corners[0]) + v * (corners[3] - corners[0])
                    region = QPolygonF([
                        QPointF(*project(world(u, v))[:2])
                        for u, v in [(cuts[i], cuts[j]), (cuts[i+1], cuts[j]),
                                     (cuts[i+1], cuts[j+1]), (cuts[i], cuts[j+1])]
                    ])
                    direction = np.rint(2 * world(i / 2, j / 2) - 1).astype(int)
                    labels = [label for label, normal, _ in self.FACES if np.dot(normal, direction) > 0]
                    target = "_".join(labels)
                    self.hit_regions.append((target, region))
                    hovered = self.hovered_face == target
                    shade = int(160 + 65 * vis)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(qcolor(70, 155, 220) if hovered else qcolor(shade, shade + 3, min(255, shade + 8)))
                    painter.drawPolygon(region)
            painter.setPen(QPen(qcolor(95, 105, 120), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)

            # Map label axes onto the face rather than drawing floating text.
            if vis >= 0.28:
                normal = next(n for label, n, _ in self.FACES if label == name)
                horizontal = np.cross([0, 0, 1], normal).astype(float)
                if np.linalg.norm(horizontal) == 0:
                    horizontal = np.array([1., 0., 0.])
                vertical = np.cross(normal, horizontal)
                center = corners.mean(axis=0)
                c = project(center)
                a = project(center + horizontal)
                b = project(center - vertical)
                painter.save()
                painter.setTransform(QTransform(
                    (a[0]-c[0])/70, (a[1]-c[1])/70,
                    (b[0]-c[0])/70, (b[1]-c[1])/70, c[0], c[1]), True)
                painter.setPen(qcolor(35, 45, 60))
                painter.drawText(QRectF(-35, -12, 70, 24), Qt.AlignmentFlag.AlignCenter, name)
                painter.restore()
