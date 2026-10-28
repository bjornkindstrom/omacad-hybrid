"""Report 20261016-212334: Offset Face -0.2 on a thread/bore left ~460 vertices of the wall almost unmoved (0.2/4096):
micro triangles flipping by float rounding made the fold guard halve their step the maximum number of times."""
from pathlib import Path

import numpy as np

import omacad.model.features.offset_face as of
from omacad.io.exporter import Exporter


def test_micro_triangles_do_not_freeze_vertices():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "offset_face_coil_stuck.omacad"))
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    before = doc.bodies[last.target_body_id].manifold
    cap = {}
    orig = of.m3d.Mesh

    class Capture(orig):
        def __init__(self, **kw):
            cap.update(kw)
            super().__init__(**kw)

    of.m3d.Mesh = Capture
    try:
        after = of.offset_surfaces(before, last.faces, last.distance)
    finally:
        of.m3d.Mesh = orig
    assert after is not None and after.volume() < before.volume()
    v = np.asarray(before.to_mesh().vert_properties, dtype=np.float64)[:, :3]
    w = np.asarray(cap["vert_properties"], dtype=np.float64)[:, :3]
    d = np.linalg.norm(w - v, axis=1)
    stuck = int(((d > 0) & (d < 1e-3)).sum())
    assert stuck < 20, stuck
