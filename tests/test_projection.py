import numpy as np
import pytest

from omacad.ui.math3d import camera_matrices, ray_from_screen

TARGET = np.array([5.0, -3.0, 2.0])


def ndc(proj, view, p):
    c = proj @ view @ np.array([*p, 1.0])
    return c[:3] / c[3]


@pytest.mark.parametrize("fov,ortho_view", [(15, False), (30, False), (60, False), (30, True)])
def test_target_is_centred(fov, ortho_view):
    proj, view = camera_matrices(TARGET, 140.0, 45.0, 30.0, 1.5, fov, ortho_view)
    assert np.allclose(ndc(proj, view, TARGET)[:2], 0.0, atol=1e-5)


def test_zoom_independent_of_fov():
    """Two points 10 mm apart at the target keep the same screen distance whatever the field of view."""
    spans = []
    for fov, ortho_view in [(15, False), (30, False), (60, False), (45, False), (30, True)]:
        proj, view = camera_matrices(TARGET, 140.0, 45.0, 30.0, 1.0, fov, ortho_view)
        up = view[1, :3]   # screen-up in world space: moving along it keeps the depth
        a = ndc(proj, view, TARGET + up * 10.0)
        b = ndc(proj, view, TARGET - up * 10.0)
        spans.append(abs(a[1] - b[1]))
    assert np.allclose(spans, spans[0], rtol=1e-3)


def test_lower_fov_is_flatter():
    """Ratio of a near edge to a far edge (same length) approaches 1 as the field of view drops."""
    def ratio(fov):
        proj, view = camera_matrices(TARGET, 140.0, 0.0, 0.0, 1.0, fov, False)
        # looking along +Y; edges parallel to Z, one 40 mm nearer, one 40 mm farther
        near = ndc(proj, view, TARGET + [0, -40, 5]) - ndc(proj, view, TARGET + [0, -40, -5])
        far = ndc(proj, view, TARGET + [0, 40, 5]) - ndc(proj, view, TARGET + [0, 40, -5])
        return near[1] / far[1]
    assert ratio(60) > ratio(30) > ratio(15) > 1.0


def test_orthographic_rays_are_parallel():
    proj, view = camera_matrices(TARGET, 140.0, 45.0, 30.0, 1.0, 30, True)
    o1, d1 = ray_from_screen(10, 20, 400, 400, view, proj)
    o2, d2 = ray_from_screen(300, 350, 400, 400, view, proj)
    assert np.allclose(d1, d2, atol=1e-4)
    oc, dc = ray_from_screen(200, 200, 400, 400, view, proj)
    # the centre ray passes through the target
    t = np.dot(TARGET - oc, dc)
    assert np.allclose(oc + dc * t, TARGET, atol=1e-2)


def test_perspective_centre_ray_hits_target():
    proj, view = camera_matrices(TARGET, 140.0, 45.0, 30.0, 1.0, 30, False)
    oc, dc = ray_from_screen(200, 200, 400, 400, view, proj)
    t = np.dot(TARGET - oc, dc)
    assert np.allclose(oc + dc * t, TARGET, atol=1e-2)
