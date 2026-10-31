"""Regression test for problem report 20261031-083336:
Pattern / mirror of a thread cut creates cleanly cut threads without vertical cylinder-facet seam lines.
"""

from pathlib import Path
import numpy as np

from omacad.io.exporter import Exporter


def test_pattern_thread_no_ugly_vertical_facet_lines():
    doc_path = Path("/home/kindstrom/Work/omacad-hybrid/.state/data/feedback/20261031-083336/document.omacad")
    doc = Exporter.load_project(str(doc_path))
    doc.timeline.recompute(doc)
    body = doc.bodies["body_split_5"]
    mesh = body.render_mesh
    lines = np.asarray(mesh.sharp_lines).reshape(-1, 2, 3)

    holes = [
        ("original (-15, -15)", -15, -15),
        ("mirror X (15, -15)", 15, -15),
        ("mirror Y (-15, 15)", -15, 15),
        ("mirror XY (15, 15)", 15, 15),
    ]

    for name, x, y in holes:
        mid = 0.5 * (lines[:, 0, :] + lines[:, 1, :])
        dist = np.hypot(mid[:, 0] - x, mid[:, 1] - y)
        hl = lines[dist < 5.0]
        dz = np.abs(hl[:, 1, 2] - hl[:, 0, 2])
        vertical_count = int(np.sum(dz > 0.05))
        assert vertical_count == 0, f"{name} had {vertical_count} vertical facet lines"
