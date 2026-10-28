"""View cube projection, 26 navigation targets and pointer capture."""
import math
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from omacad.ui.viewcube import ViewCube
from omacad.ui.viewport.overlay_mixin import OverlayMixin


@pytest.fixture
def cube():
    app = QApplication.instance() or QApplication([])
    cube = ViewCube()
    cube._app = app
    return cube


def draw(cube, az=45, el=30):
    image = QImage(400, 200, QImage.Format.Format_ARGB32)
    image.fill(0xffffffff)
    painter = QPainter(image)
    cube.draw(painter, 400, 200, az, el)
    painter.end()
    return image


def center(poly):
    return sum(p.x() for p in poly) / 4, sum(p.y() for p in poly) / 4


def test_front_right_projection_matches_camera(cube):
    draw(cube)
    faces = {name: center(poly) for name, poly, _ in cube.rendered_faces}
    assert faces["RIGHT"][0] > faces["FRONT"][0]
    assert faces["TOP"][1] < faces["FRONT"][1]


def test_all_26_targets_and_exact_camera_angles(cube):
    seen = set()
    for az in (45, 135, 225, 315):
        for el in (-35, 35):
            draw(cube, az, el)
            for name, poly in cube.hit_regions:
                seen.add(name)
                assert cube.target_at(*center(poly), 400) == name
                view = SimpleNamespace(update=lambda: None)
                OverlayMixin.set_view(view, name)
                a, e = math.radians(view.azimuth), math.radians(view.elevation)
                actual = np.array([math.cos(e)*math.sin(a), -math.cos(e)*math.cos(a), math.sin(e)])
                expected = sum((n for label, n, _ in cube.FACES if label in name.split("_")), np.zeros(3))
                expected /= np.linalg.norm(expected)
                assert np.allclose(actual, expected, atol=0.002)
    assert len(seen) == 26


def test_click_uses_position_without_hover_and_home_matches_drawing(cube):
    draw(cube, 0, 89.9)
    clicked = []
    cube.on_face_clicked = clicked.append
    poly = next(p for name, p in cube.hit_regions if name == "TOP")
    assert cube.handle_mouse_press(*center(poly), 400)
    assert cube.handle_mouse_release()
    assert clicked == ["TOP"]
    assert not cube.handle_mouse_press(5, 180, 400)
    rect = cube.home_rect(400)
    assert cube.handle_mouse_press(rect.center().x(), rect.bottom()-1, 400)
    cube.handle_mouse_release()
    assert clicked == ["TOP", "HOME"]


def test_drag_captures_outside_cube_and_does_not_snap(cube):
    draw(cube)
    clicked, moves = [], []
    cube.on_face_clicked = clicked.append
    cube.on_orbit = lambda dx, dy: moves.append((dx, dy))
    x, y = center(cube.hit_regions[4][1])
    assert cube.handle_mouse_press(x, y, 400)
    assert cube.handle_mouse_move(x + 100, y + 30, 400)
    assert cube.handle_mouse_release()
    assert moves == [(100, 30)]
    assert clicked == []
    assert not cube.handle_mouse_release()


def test_drag_matches_viewport_orbit_and_clamps_poles():
    view = SimpleNamespace(azimuth=5., elevation=80., update=lambda: None)
    OverlayMixin._orbit_viewcube(view, 20, 40)
    assert view.azimuth == 355.
    assert view.elevation == 89.9
    OverlayMixin._orbit_viewcube(view, 0, -400)
    assert view.elevation == -89.9
