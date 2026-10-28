"""Report 20261016-210524: Offset Face -0.2 on a thread flank folded the flat end caps (hair-thin triangles) over."""
from pathlib import Path

import numpy as np

import omacad.model.features.offset_face as of
from omacad.io.exporter import Exporter


def _normals(manifold):
    mesh = manifold.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    t = np.asarray(mesh.tri_verts)
    return np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])


def test_thread_flank_offset_folds_no_triangle():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "offset_face_thread_folds.omacad"))
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    before = doc.bodies[last.target_body_id].manifold
    cap = {}
    orig = of.m3d.Mesh

    class Capture(orig):                      # the Manifold constructor reorders vertices; compare before that
        def __init__(self, **kw):
            cap.update(kw)
            super().__init__(**kw)

    of.m3d.Mesh = Capture
    try:
        after = of.offset_surfaces(before, last.faces, last.distance)
    finally:
        of.m3d.Mesh = orig
    assert after is not None and after.volume() < before.volume()
    mesh = before.to_mesh()
    t = np.asarray(mesh.tri_verts)
    v = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
    n0 = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    w = np.asarray(cap["vert_properties"], dtype=np.float64)[:, :3]
    n1 = np.cross(w[t[:, 1]] - w[t[:, 0]], w[t[:, 2]] - w[t[:, 0]])
    real = np.linalg.norm(n0, axis=1) > 2e-4          # micro triangles may flip by float32 rounding alone
    assert ((np.einsum("ij,ij->i", n0, n1) < 0) & real).sum() == 0
