"""Settings > Show tangent edges (rapport 20261025-124359): a line where a flat wall runs smoothly into a tangent
arc, like Fusion. Off by default; worked out lazily from the render mesh."""
from pathlib import Path

import manifold3d as m3d
import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.kernel import CadKernel
from omacad.ui.settings import DEFAULT_SETTINGS

DOC = str(Path(__file__).parent / "data" / "tangent_edges_walls_and_arcs.omacad")


def _segments(manifold):
    return CadKernel.extract_render_mesh(manifold).tangent_lines().reshape(-1, 2, 3)


def test_wall_and_arc_seams_of_the_reported_extrude_are_tangent_edges():
    doc = Exporter.load_project(DOC)
    body = next(iter(doc.bodies.values()))
    seg = body.render_mesh.tangent_lines().reshape(-1, 2, 3)
    # six places where a straight side of the sketch runs into an arc, each one the full 50 mm height
    assert len(seg) == 6
    assert np.allclose(np.abs(seg[:, 1, 2] - seg[:, 0, 2]), 50.0)
    assert np.allclose(seg[:, 0, :2], seg[:, 1, :2])          # vertical
    feet = sorted(map(tuple, np.round(seg[:, 0, :2], 1)))
    assert feet == [(-40.0, 55.0), (-20.0, 0.0), (50.0, 105.0), (60.0, 5.0), (105.0, 75.0), (109.0, 33.4)]


def test_rounded_rectangle_has_eight_tangent_edges_box_and_cylinder_none():
    rounded = m3d.Manifold.extrude(m3d.CrossSection.square([40, 20]).offset(5, m3d.JoinType.Round,
                                                                           circular_segments=96), 10)
    seg = _segments(rounded)
    assert len(seg) == 8 and np.allclose(np.abs(seg[:, 1, 2] - seg[:, 0, 2]), 10.0)
    assert len(_segments(m3d.Manifold.cube([10, 10, 10]))) == 0
    assert len(_segments(m3d.Manifold.cylinder(10, 5, circular_segments=96))) == 0


def test_tangent_edges_are_off_by_default():
    assert DEFAULT_SETTINGS["show_tangent_edges"] is False
