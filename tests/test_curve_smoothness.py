"""The curve smoothness setting decides how many flat pieces a circle gets."""
import math

import pytest

from omacad.model import quality
from omacad.model.document import Document


@pytest.fixture(autouse=True)
def restore():
    before = quality.circle_segments()
    yield
    quality.set_circle_segments(before)


@pytest.mark.parametrize("n", [32, 96, 192])
def test_cylinder_and_circle_profile_follow_the_setting(n):
    quality.set_circle_segments(n)
    d = Document()
    d.add_cylinder(10, 5)
    body = next(iter(d.bodies.values()))
    expected = 0.5 * n * 100 * math.sin(2 * math.pi / n) * 5
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    sk = d.start_sketch("XY")
    sk.add_circle((0, 0), 10)
    sk.solve_profiles()
    assert len(sk.profiles[0].exterior_pts) == n


def test_smoother_means_closer_to_a_true_circle():
    vols = []
    for n in (32, 96, 360):
        quality.set_circle_segments(n)
        d = Document()
        d.add_cylinder(10, 1)
        vols.append(next(iter(d.bodies.values())).manifold.volume())
    assert vols[0] < vols[1] < vols[2] < math.pi * 100
