"""Zooming out must reach a whole large model (a 1 m+ tube Christmas tree): the wheel stopped at distance 2000 mm
and the far clipping plane was fixed at 5000 mm behind the eye's target. Now the limit is MAX_DISTANCE and the far
plane follows the zoom, so a model several times the visible height is never clipped away."""
import math

import numpy as np
import pytest

from omacad.ui.math3d import MAX_DISTANCE, MIN_DISTANCE, camera_matrices, clamp_distance


def test_zoom_limits():
    assert clamp_distance(1e9) == MAX_DISTANCE and clamp_distance(0.1) == MIN_DISTANCE
    assert MAX_DISTANCE >= 50000.0
    assert clamp_distance(2000.0 * 1.1) > 2000.0        # past the old stop


@pytest.mark.parametrize("ortho", [False, True])
@pytest.mark.parametrize("distance", [3000.0, 20000.0, MAX_DISTANCE])
def test_far_side_of_a_big_model_stays_inside_the_clip_volume(distance, ortho):
    proj, view = camera_matrices(np.zeros(3), distance, 30.0, 25.0, 1.5, ortho_view=ortho)
    size = distance * math.tan(math.radians(22.5))     # a box as tall as the view, seen from any side
    for corner in np.array(np.meshgrid(*[[-size, size]] * 3)).T.reshape(-1, 3):
        clip = proj @ view @ np.append(corner, 1.0)
        assert -clip[3] <= clip[2] <= clip[3]
