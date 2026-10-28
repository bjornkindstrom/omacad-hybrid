"""F9 report: on a shelled jar with a thread and a circular pattern of debossed slots, the inner edges of the
shoulder (z 38, r 18 and r 14) could not be picked for a chamfer. The booleans left zero-area triangles along the
seam, so each circle came out as a dozen short arcs with gaps. Faces and edges are now read from the mesh with those
collapsed (Manifold.simplify, 1e-6 mm), which gives back each whole circle."""
import pytest
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import compute_planar_edges


def _shoulder_circles(edges, r):
    out = []
    for e in edges:
        p = np.asarray(e.polyline(), dtype=float).reshape(-1, 3)
        if np.allclose(p[:, 2], 38.0, atol=1e-3) and np.allclose(np.hypot(p[:, 0], p[:, 1]), r, atol=0.05):
            out.append(e)
    return out


def test_shoulder_edges_of_patterned_jar_are_whole_circles():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "shoulder_edge_slivers.omacad"))
    body = doc.bodies["body_cylinder_1"]
    for edges in (body.edges, compute_planar_edges(body.manifold)):
        for r in (18.0, 14.0):
            found = _shoulder_circles(edges, r)
            assert len(found) == 1, f"r {r}: {len(found)} pieces"
            assert found[0].kind == "circle" and abs(found[0].radius - r) < 0.05
            assert found[0].sweep > 2 * np.pi - 1e-6


def test_inner_shoulder_edge_takes_a_chamfer():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "shoulder_edge_slivers.omacad"))
    edge = _shoulder_circles(doc.bodies["body_cylinder_1"].edges, 18.0)[0]
    before = doc.bodies["body_cylinder_1"].manifold.volume()
    doc.add_fillet([edge.ref()], 1.0, "chamfer")
    added = doc.bodies["body_cylinder_1"].manifold.volume() - before
    # an inside corner gets filled: the 1 x 1 triangle (0.5 mm^2) swept round its centroid at r 18 - 1/3 (Pappus)
    assert abs(added - 0.5 * 2 * np.pi * (18.0 - 1.0 / 3.0)) < 0.01 * added
