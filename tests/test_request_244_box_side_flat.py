"""Request #244: "Fast view" smoothing bent the flat side of a Box in a Row box (rounded corners) out of its face,
so the hover highlight showed only in blotches."""
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model import quality

DATA = Path(__file__).parent / "data"


def test_box_side_stays_in_its_face_and_matches_the_hover_patch():
    quality.set_fast_view(True, 72)
    doc = Exporter.load_project(str(DATA / "box_row_side_244.omacad"))
    body = next(b for b in doc.bodies.values() if b.name == "Box 1")
    mesh = body.render_mesh
    side = next(f for f in body.faces if f.normal[0] < -0.99 and np.ptp(f.tris[:, :, 1]) > 30)
    x = float(side.tris[0, 0, 0])
    lo = side.tris.reshape(-1, 3).min(axis=0) + 0.05
    hi = side.tris.reshape(-1, 3).max(axis=0) - 0.05
    for tangent in (False, True):
        mesh._display = None
        drawn = mesh.display_arrays(mesh.drawn_edges(tangent))[0].reshape(-1, 3)
        over = (drawn[:, 1] > lo[1]) & (drawn[:, 1] < hi[1]) & (drawn[:, 2] > lo[2]) & (drawn[:, 2] < hi[2])
        front = over & (drawn[:, 0] < x + 1.0)
        assert front.sum() > 6
        assert np.abs(drawn[front, 0] - x).max() < 1e-4       # was 0.25 mm out of the face
    patch = np.asarray(mesh.display_patch_arrays(side.tris, np.zeros((0, 3), np.float32))[0]).reshape(-1, 3)
    assert np.abs(patch[:, 0] - x).max() < 1e-4
