"""Under a section view the live preview is cut like the bodies; before, a tool preview (e.g. Offset Face on a thread)
showed the whole solid and covered the thread you were looking at."""
import manifold3d as m3d
import numpy as np

from omacad.ui.viewport.viewport import Viewport3D


class _Stub(Viewport3D):
    def __init__(self):   # no GL context needed
        self.section = None
        self.update = lambda: None


def test_preview_is_cut_by_the_section():
    vp = _Stub()
    box = m3d.Manifold.cube((10, 10, 10), True)
    vp.set_preview(box)
    full = vp.preview_mesh
    vp.section = {"origin": np.zeros(3), "normal": np.array([0.0, 1.0, 0.0]), "offset": 0.0, "flip": False}
    vp.set_preview(box)
    ys = np.asarray(vp.preview_mesh.vertices, dtype=float).reshape(-1, 3)[:, 1]
    assert ys.max() <= 1e-6 and np.asarray(full.vertices).reshape(-1, 3)[:, 1].max() > 4.9
