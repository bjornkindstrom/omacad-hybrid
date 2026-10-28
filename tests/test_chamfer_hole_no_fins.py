"""Chamfered holes and polygon contours must not leave zero-thickness fins in their walls (request 20261013-211700)."""
from collections import defaultdict
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter

DOC = Path(__file__).parent / "data" / "chamfer_hole_fins.omacad"


def fin_edges(m):
    mesh = m.to_mesh()
    V, T = np.array(mesh.vert_properties)[:, :3], np.array(mesh.tri_verts)
    N = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    L = np.linalg.norm(N, axis=1)
    N = N / np.maximum(L[:, None], 1e-12)
    edges = defaultdict(list)
    for i, t in enumerate(T):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((t[a], t[b])))].append(i)
    return sum(1 for ts in edges.values()
               if len(ts) == 2 and L[ts[0]] > 1e-3 and L[ts[1]] > 1e-3 and N[ts[0]] @ N[ts[1]] < -0.9)


def test_chamfered_hole_has_no_fins():
    doc = Exporter.load_project(str(DOC))
    doc.timeline.recompute(doc)
    m = next(iter(doc.bodies.values())).manifold
    assert fin_edges(m) == 0
    assert len(m.decompose()) == 1
