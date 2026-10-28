"""An extruded cut tangent to a shell wall must not leave narrow mesh strips."""
from pathlib import Path

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model import quality
from omacad.model.kernel import CadKernel


DATA = Path(__file__).parent / "data"


def test_extrude_cut_through_threaded_shell_resolves_coincident_wall():
    doc = Exporter.load_project(str(DATA / "extrude_cut_thread_fuzz.omacad"))
    body_id = "body_cylinder_1"
    before = doc.step_states[9][body_id]
    cutter = doc.timeline.features[9].build_solid(doc)
    expected = before - CadKernel.grown(cutter, 1e-6)

    body = doc.bodies[body_id]
    mesh = body.manifold.to_mesh()
    assert body.manifold.volume() == pytest.approx(expected.volume(), abs=1e-6)
    # The plain cut creates 7,206 triangles, including narrow fragments along
    # the near-coincident inner wall. The tolerance-expanded tool resolves them.
    assert len(mesh.tri_verts) < 6_000


def _wall_area(solid, r0, r1, z0, z1):
    """Area of the faces between radius r0..r1 and height z0..z1 (thin leftover walls show up here)."""
    mesh = solid.to_mesh()
    p = np.asarray(mesh.vert_properties)[:, :3][np.asarray(mesh.tri_verts)]
    c = p.mean(axis=1)
    r = np.hypot(c[:, 0], c[:, 1])
    area = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1) / 2
    return float(area[(r > r0) & (r < r1) & (c[:, 2] > z0) & (c[:, 2] < z1)].sum())


def test_extrude_cut_of_lid_plug_at_360_segments_leaves_no_strips():
    # F9 report: at 360 curve segments the profile (drawn on the can's inner wall, r 14) and the
    # lid's plug wall differ by up to 0.5 um, so a 1 nm clearance left double-sided strips in the lid.
    old = quality.circle_segments()
    quality.set_circle_segments(360)
    try:
        doc = Exporter.load_project(str(DATA / "extrude_cut_lid_plug_360.omacad"))
    finally:
        quality.set_circle_segments(old)
    lid = doc.bodies["body_cylinder_7"].manifold
    assert _wall_area(doc.step_states[9]["body_cylinder_7"], 13.9, 14.05, 40.05, 45.95) > 500   # the plug was there
    assert _wall_area(lid, 13.9, 14.05, 40.05, 45.95) == 0.0
    assert lid.volume() == pytest.approx(7528.5044, abs=1e-3)
