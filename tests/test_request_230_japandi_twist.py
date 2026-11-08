"""Regression test for Request #230: Japandi med twist ser lite knasig ut i viewporten.
Twisted ribs on a revolved surface with tilted profile normals must not poke past
the wall's end planes or slice jagged artifacts into the top rim.
"""
from pathlib import Path
import numpy as np
from omacad.io.exporter import Exporter

DATA = Path(__file__).parent / "data"


def test_230_japandi_twist_does_not_protrude_past_rim():
    doc = Exporter.load_project(str(DATA / "request_230_japandi_twist.omacad"))
    body = list(doc.bodies.values())[0]
    rm = body.render_mesh

    v = rm.vertices.reshape(-1, 3)
    z_max = v[:, 2].max()

    # The top rim plane of the vase is at 101.5865; ribs must not overshoot it
    assert z_max <= 101.5865 + 1e-3, f"Ribs overshoot rim: z_max={z_max}"

    lines = rm.sharp_lines.reshape(-1, 2, 3)
    # No sharp lines should exceed the rim plane
    assert lines[:, :, 2].max() <= 101.5865 + 1e-3, "Sharp lines overshoot the rim"

    # Lines on the rim plane itself
    on_rim = (np.abs(lines[:, :, 2] - z_max) < 1e-3).all(axis=1)
    assert on_rim.any(), "No lines found on top rim"
    top_lines = lines[on_rim]

    # The annular rim surface between the inner wall (~18.2 mm) and outer ribs (>21.6 mm)
    # must be clean: no sharp lines slicing across the rim
    r0 = np.hypot(top_lines[:, 0, 0], top_lines[:, 0, 1])
    r1 = np.hypot(top_lines[:, 1, 0], top_lines[:, 1, 1])
    crossing = ((r0 < 19.0) & (r1 > 20.0)) | ((r0 > 20.0) & (r1 < 19.0))
    assert not crossing.any(), "Lines cross diagonally across top rim face"

    r_mid = np.hypot(top_lines.mean(axis=1)[:, 0], top_lines.mean(axis=1)[:, 1])
    in_between = (r_mid > 18.5) & (r_mid < 21.5)
    assert not in_between.any(), f"Found {in_between.sum()} ragged line segments on top rim face"
