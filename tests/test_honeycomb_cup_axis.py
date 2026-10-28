"""Honeycomb Through on a cup with a filleted rim (report 20261024-065939): the picked axis leaned 0.6 degrees,
cells on one side started inside the wall, measured Through across the hollow and cut ragged holes in the wall
opposite; others missed the inner face at their edges."""
import math
import os
from types import SimpleNamespace

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.faces_hit_tests import detect_cylinder_surface

DOC = os.path.join(os.path.dirname(__file__), "data", "honeycomb_filleted_cup.omacad")
HEX = math.sqrt(3) / 2 * 6.0 ** 2


def _cup():
    doc = Exporter.load_project(DOC)
    honey = doc.timeline.features[1]
    honey.suppressed = True
    doc.timeline.recompute(doc)
    return doc, honey


def test_the_wall_beside_a_fillet_is_picked_with_its_true_axis():
    doc, _ = _cup()
    mesh = doc.bodies["body_cylinder_1"].render_mesh
    tri = np.asarray(mesh.vertices, dtype=float).reshape(-1, 3, 3)
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1)[:, None]
    for deg in (0, 67, 200):
        d = np.array([math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0])
        i = int(np.flatnonzero((nrm @ d > 0.99) & (np.abs(nrm[:, 2]) < 1e-6))[0])
        cyl = detect_cylinder_surface(mesh, i)
        assert cyl["axis"] == pytest.approx([0, 0, 1], abs=1e-6)
        assert cyl["origin"] == pytest.approx([0, 0, 2], abs=1e-6)
        assert cyl["radius"] == pytest.approx(20.0, abs=1e-5)


def test_saved_leaning_axis_still_cuts_every_cell_through_the_wall_only():
    doc, honey = _cup()
    before = doc.bodies["body_cylinder_1"].manifold.volume()
    honey.suppressed = False                     # the face as saved by the report: axis 0.58 degrees off
    doc.timeline.recompute(doc)
    m = doc.bodies["body_cylinder_1"].manifold
    assert honey.cells == 64
    assert m.genus() == 64                       # every cell a hole, none into the opposite wall
    # each cell: hexagon (unrolled at r = 20) swept from r = 18 to 20, area scaling with rho / r
    assert before - m.volume() == pytest.approx(64 * HEX * (20 ** 2 - 18 ** 2) / (2 * 20), rel=2e-3)


def test_through_from_inside_the_material_stops_where_it_ends():
    import omacad.model.features.honeycomb as H
    doc, _ = _cup()
    rays = H._Rays(doc.bodies["body_cylinder_1"].manifold)
    # a point a little inside the outer wall: on to the inner face (r = 18), not across to the far wall
    d = H._depths([np.array([19.8, 0.0, 20.0])], [np.array([-1.0, 0.0, 0.0])], rays, None)[0]
    assert d == pytest.approx(1.8 + H.OVERSHOOT, abs=0.02)
