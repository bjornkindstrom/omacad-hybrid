"""Offset Face under a section view: a click reaches the cut thread, not the half of the body that is cut away."""
from types import SimpleNamespace

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.kernel import CadKernel
from omacad.ui.viewport import picker_mixin
from omacad.ui.viewport.viewport import Viewport3D

REPORT = "tests/data/offset_face_section_thread.omacad"


class _Stub(Viewport3D):
    def __init__(self):
        pass


def test_pick_goes_through_the_cut_away_half(monkeypatch):
    doc = Exporter.load_project(REPORT)
    nut = doc.bodies["body_cylinder_2"]
    vp = _Stub()
    vp.doc, vp.plane_pick_purpose, vp.shell_target_body_id = doc, "offset_face", nut.body_id
    vp.get_matrices = lambda: (None, None, None)
    vp.width = vp.height = lambda: 100
    # section along XZ, the y > 0 half is cut away (viewer looks from +y towards -y)
    p, keep = np.zeros(3), np.array([0.0, -1.0, 0.0])
    vp.section = {"origin": p, "normal": np.array([0.0, 1.0, 0.0]), "offset": 0.0, "flip": False,
                  "meshes": {nut.body_id: CadKernel.extract_render_mesh(nut.manifold.trim_by_plane(tuple(keep), 0.0))}}
    monkeypatch.setattr(picker_mixin, "ray_from_screen", lambda *a: (np.array([0.0, 100.0, 20.0]), np.array([0.0, -1.0, 0.0])))
    hit = vp._pick_surface(0, 0)
    assert hit is not None
    assert hit["point"][1] < 0 and abs(hit["point"][1]) < 23      # the inner thread (r ~ 20), not the outer wall at y = +27
    assert not vp._section_keeps([0.0, 5.0, 0.0]) and vp._section_keeps([0.0, -5.0, 0.0])
