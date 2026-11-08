"""Regression test for Request #232: Lustig skuggning.
Loft bodies must not get inverted vertex normals on thin shelled walls,
and side quads on 2D-tessellated curved walls must retain smooth shading
instead of being flattened into bands by strip normals.
"""
from pathlib import Path
import numpy as np
from omacad.io.exporter import Exporter

DATA = Path(__file__).parent / "data"


def test_232_loft_no_inverted_normals_and_retains_smooth_shading():
    doc = Exporter.load_project(str(DATA / "request_232_loft_shading.omacad"))
    body = list(doc.bodies.values())[0]
    rm = body.render_mesh

    V = rm.vertices.reshape(-1, 3, 3)
    N = rm.normals.reshape(-1, 3, 3)

    fn = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)

    dots = (N * fn[:, None, :]).sum(axis=2)

    # No vertex normals pointing backwards relative to face normal
    assert dots.min() >= -1e-6, f"Found inverted vertex normals: min dot {dots.min()}"

    # Loft side walls retain smooth shading (not flattened by strip normals)
    mid = (V[:, :, 2].mean(axis=1) > 100) & (V[:, :, 2].mean(axis=1) < 400)
    diffs = np.linalg.norm(N[mid, 1] - N[mid, 0], axis=1) + np.linalg.norm(N[mid, 2] - N[mid, 0], axis=1)
    smooth_count = int((diffs > 0.01).sum())
    total_mid = int(mid.sum())
    assert smooth_count > 0.8 * total_mid, f"Expected >80% smooth triangles in mid section, got {smooth_count}/{total_mid}"
