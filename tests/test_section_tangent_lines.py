"""Section view must not invent tangent edges on curved walls sliced by the cut plane."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.viewport.viewport import Viewport3D


class _StubViewport(Viewport3D):
    def __init__(self, doc):
        self.doc = doc
        self.section = None
        self.display_solids = None
        self.display_override = None
        self.set_preview_plane = lambda _p: None
        self.update = lambda: None


def test_section_cut_cylinder_has_no_false_tangent_lines():
    doc = Document()
    doc.add_cylinder(radius=20.0, height=40.0, name="Cyl")
    body = next(iter(doc.bodies.values()))
    assert len(body.render_mesh.tangent_lines()) == 0

    vp = _StubViewport(doc)
    vp.set_section((0.0, 0.0, 0.0), (0.0, -1.0, 0.0), 0.5, flip=False, show_plane=False)
    sec_mesh = vp.section["meshes"][body.body_id]
    assert len(sec_mesh.tangent_lines()) == 0


def test_section_cut_preserves_and_clips_real_tangent_edges():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "tangent_edges_walls_and_arcs.omacad"))
    body = next(iter(doc.bodies.values()))
    assert len(body.render_mesh.tangent_lines().reshape(-1, 2, 3)) == 6

    vp = _StubViewport(doc)
    vp.set_section((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 25.0, flip=False, show_plane=False)
    seg = vp.section["meshes"][body.body_id].tangent_lines().reshape(-1, 2, 3)
    assert len(seg) == 6
    assert np.allclose(np.abs(seg[:, 1, 2] - seg[:, 0, 2]), 25.0, atol=1e-4)
    assert np.all(seg[:, :, 2] <= 25.0 + 1e-4)
