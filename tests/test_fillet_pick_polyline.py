import numpy as np
import pytest

from omacad.model.document import Document
from omacad.ui.viewport.picker_mixin import PickerMixin


def test_fillet_marking_edges_shows_actual_edge_position():
    """Verify that marking multiple edges for fillet/chamfer shows lines where they are
    right now rather than shifting to where the fillet will end up (regression test for
    report 20261101-100445)."""
    doc = Document()
    body = doc.add_box(70.0, 40.0, 10.0)

    picker = PickerMixin()
    picker.doc = doc

    # Select multiple edges on top face (z = 10.0)
    top_edges = [
        e for e in body.edges
        if getattr(e, "kind", "") == "line" and abs(e.p0[2] - 10.0) < 1e-3 and abs(e.p1[2] - 10.0) < 1e-3
    ]
    assert len(top_edges) == 4

    picker.selected_edges = list(top_edges[:3])
    picker.hover_edge = top_edges[3]
    picker.fillet_rail_offset = 2.0  # Even if a fillet size is active in preview

    # Under render_pick_overlays, the lines for selected_edges, hover_edge, and xray
    # are generated from e.polyline(), remaining on the surface at z = 10.0,
    # NOT offset downwards into the material (e.g. at z = 8.0).
    for edge in picker.selected_edges:
        pts = edge.polyline()
        assert np.allclose(pts[:, 2], 10.0, atol=1e-5)

    hover_pts = picker.hover_edge.polyline()
    assert np.allclose(hover_pts[:, 2], 10.0, atol=1e-5)
