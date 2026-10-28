"""Orbiting over the top must not make the view jump (it used to roll 90 degrees when passing 89 degrees elevation)."""
import numpy as np
import pytest

pytest.importorskip("PySide6")        # math3d lives in the ui package, which imports Qt

from omacad.ui.math3d import orbit_view  # noqa: E402


def screen_up(az, el):
    """World direction that points up on the screen (second row of the view matrix)."""
    return orbit_view(np.zeros(3), 140.0, az, el)[1, :3]


@pytest.mark.parametrize("az", [0.0, 37.0, 90.0, 200.0])
def test_no_roll_jump_across_89_degrees(az):
    below, above = screen_up(az, 88.9), screen_up(az, 89.1)
    assert np.dot(below, above) > 0.999


@pytest.mark.parametrize("az", [0.0, 90.0, 180.0])
def test_top_view_up_follows_azimuth(az):
    up = screen_up(az, 89.9)
    # looking down from the side the camera sits on, "up" on screen points away from it
    away = np.array([-np.sin(np.radians(az)), np.cos(np.radians(az)), 0.0])
    assert np.dot(up, away) > 0.999


def test_default_top_view_is_unchanged():
    """Plane alignment uses az 0, el 89.9: x to the right, y up on screen, as before."""
    view = orbit_view(np.zeros(3), 140.0, 0.0, 89.9)
    assert np.allclose(view[0, :3], [1, 0, 0], atol=1e-3) and np.allclose(view[1, :3], [0, 1, 0], atol=2e-3)
