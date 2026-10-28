"""Clicking a face in Fillet/Chamfer takes all its edges, closed loops and straight edges together
(problem report 20261024-082418: a honeycomb box side has both, and only the loops were taken)."""
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from omacad.io.exporter import Exporter
from omacad.ui.viewport.picker_mixin import PickerMixin


def _outline_length(face) -> float:
    """Length of the face's outline (outer boundary + holes), from its own triangles."""
    n = np.asarray(face.normal, dtype=float)
    u = np.cross(n, [0.0, 0.0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0.0, 0.0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    region = unary_union([Polygon([(p @ u, p @ v) for p in t]).buffer(1e-6) for t in face.tris])
    return region.boundary.length


def test_honeycomb_box_side_selects_every_cell_outline():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "honeycomb_box_face_edges.omacad"))
    body = next(iter(doc.bodies.values()))
    side = max((f for f in body.faces if f.index >= 0 and abs(f.normal[1] + 1) < 1e-3), key=lambda f: f.area)
    edges = PickerMixin._edges_of_face(None, side, body)
    kinds = {e.kind for e in edges}
    assert "line" in kinds and kinds <= {"loop", "line"}
    total = sum(float(np.linalg.norm(np.diff(e.polyline(), axis=0), axis=1).sum()) for e in edges)
    assert abs(total - _outline_length(side)) < 1e-2 * _outline_length(side)
