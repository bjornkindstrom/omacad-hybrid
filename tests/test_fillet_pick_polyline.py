import numpy as np
import pytest

from omacad.model.document import Document
from omacad.ui.viewport.picker_mixin import PickerMixin


def test_fillet_marking_edges_shows_actual_edge_position():
    """Verify that marking multiple edges for fillet/chamfer shows lines where they are
    right now for unselected and hovered edges, while the selected edges frame follows down
    with the fillet/chamfer rail (regression test for report 20261101-100445 and 20261103-203138)."""
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
    picker.fillet_rail_offset = 2.0  # Fillet size active in preview

    # Verify that the internal body edge picking cache _edge_segments(body) is intact and not shadowed
    edge_pick_cache = picker._edge_segments(body)
    assert len(edge_pick_cache) == 4
    assert len(edge_pick_cache[0]) == len(body.edges)

    # Hovering an edge while picking should show the line at the actual edge position (z = 10.0)
    hover_segs = np.array(picker._edge_render_lines([picker.hover_edge])).reshape(-1, 3)
    assert np.allclose(hover_segs[:, 2], 10.0, atol=1e-5)

    # The frame of selected edges follows down with the fillet/chamfer rail (z = 8.0)
    selected_segs = np.array(picker._edge_render_lines(picker.selected_edges, picker.fillet_rail_offset)).reshape(-1, 3)
    assert np.allclose(selected_segs[:, 2], 8.0, atol=1e-5)


def test_fillet_frame_follows_down_from_report_document():
    """Regression test for problem report 20261103-203138:
    Verify that the selected 4 top edges of Box 1 (z = 42.0) follow down with the
    fillet rail to z = 35.3 mm when radius is 6.7 mm."""
    from pathlib import Path
    from omacad.io.exporter import Exporter

    doc_path = Path(__file__).parent.parent / ".state" / "data" / "feedback" / "20261103-203138" / "document.omacad"
    if doc_path.exists():
        doc = Exporter.load_project(str(doc_path))
    else:
        doc = Document()
        doc.add_box(83.0, 98.0, 42.0)

    body = list(doc.bodies.values())[0]
    picker = PickerMixin()
    picker.doc = doc

    top_edges = [
        e for e in body.edges
        if getattr(e, "kind", "") == "line" and abs(e.p0[2] - 42.0) < 1e-3 and abs(e.p1[2] - 42.0) < 1e-3
    ]
    assert len(top_edges) == 4

    picker.selected_edges = list(top_edges)
    picker.fillet_rail_offset = 6.7

    frame_segs = np.array(picker._edge_render_lines(picker.selected_edges, picker.fillet_rail_offset)).reshape(-1, 3)
    assert np.allclose(frame_segs[:, 2], 42.0 - 6.7, atol=1e-5)
