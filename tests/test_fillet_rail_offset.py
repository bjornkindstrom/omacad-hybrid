import numpy as np
import pytest
from omacad.model.faces_types import CircularEdge, PlanarEdge
from omacad.ui.viewport.picker_mixin import PickerMixin
from omacad.io.exporter import Exporter


def test_fillet_rail_offset_direction():
    """Verify that fillet rail guide lines shift downwards along the wall for both straight lines
    and circular arc corners (regression test for report 20261031-165820)."""
    picker = PickerMixin()

    # Top edge of an extruded block: flat face is top (axis = [0, 0, 1]),
    # cylinder wall extends downwards (s2 = -1.0).
    corner_arc = CircularEdge(
        center=np.array([47.0, 32.0, 25.0]),
        axis=np.array([0.0, 0.0, 1.0]),
        radius=3.0,
        s1=-1.0,
        s2=-1.0,
        convex=True,
    )

    offset_val = 2.0
    orig_pts = corner_arc.polyline()
    shifted_pts = picker._offset_edge_polyline(corner_arc, offset_val)

    # The shifted points should move downwards (Z should decrease by offset_val)
    # matching straight line wall offsets at the top of the body.
    assert np.allclose(orig_pts[:, 2] - offset_val, shifted_pts[:, 2], atol=1e-5)


def test_fillet_rail_offset_from_report_document():
    doc = Exporter.load_project("/home/kindstrom/Work/omacad-hybrid/.state/data/feedback/20261031-165820/document.omacad")
    doc.timeline.step_to(2, doc)
    body = list(doc.bodies.values())[0]

    picker = PickerMixin()
    top_lines = [e for e in body.edges if e.kind == "line" and abs(e.p0[2] - 25.0) < 1e-3 and abs(e.p1[2] - 25.0) < 1e-3]
    top_arcs = [e for e in body.edges if e.kind == "circle" and abs(e.center[2] - 25.0) < 1e-3]

    assert len(top_lines) > 0
    assert len(top_arcs) > 0

    offset_val = 3.0
    # Both lines and arc corners along the top contour must shift in the same direction (downwards in Z)
    for line in top_lines:
        orig = line.polyline()
        shifted = picker._offset_edge_polyline(line, offset_val)
        assert np.allclose(orig[:, 2] - offset_val, shifted[:, 2], atol=1e-5)

    for arc in top_arcs:
        orig = arc.polyline()
        shifted = picker._offset_edge_polyline(arc, offset_val)
        assert np.allclose(orig[:, 2] - offset_val, shifted[:, 2], atol=1e-5)
