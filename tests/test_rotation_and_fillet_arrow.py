import pytest
import numpy as np
from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchLine, SketchCircle, SketchRect, rotate_entity, rotate_point


def test_rotate_point():
    p = (10.0, 0.0)
    # Rotate 90 deg around origin
    p_rot = rotate_point(p, 90.0, (0.0, 0.0))
    assert abs(p_rot[0] - 0.0) < 1e-6
    assert abs(p_rot[1] - 10.0) < 1e-6

    # Rotate 180 deg around (5.0, 0.0)
    p_rot180 = rotate_point(p, 180.0, (5.0, 0.0))
    assert abs(p_rot180[0] - 0.0) < 1e-6
    assert abs(p_rot180[1] - 0.0) < 1e-6


def test_rotate_sketch_entities():
    line = SketchLine("l1", (0.0, 0.0), (10.0, 0.0))
    rotate_entity(line, 90.0, (0.0, 0.0))
    assert abs(line.p1[0]) < 1e-6 and abs(line.p1[1]) < 1e-6
    assert abs(line.p2[0]) < 1e-6 and abs(line.p2[1] - 10.0) < 1e-6

    circle = SketchCircle("c1", (10.0, 0.0), 5.0)
    rotate_entity(circle, 90.0, (0.0, 0.0))
    assert abs(circle.center[0]) < 1e-6
    assert abs(circle.center[1] - 10.0) < 1e-6
    assert circle.radius == 5.0


def test_fillet_chamfer_arrow_direction():
    doc = Document()
    body = doc.add_box(10.0, 10.0, 10.0)
    
    # Convex edges should have an inward-pointing bisector (d1 + d2)
    convex_edges = [e for e in body.edges if hasattr(e, "p0") and getattr(e, "convex", True)]
    assert len(convex_edges) > 0
    for e in convex_edges:
        axis = e.d1 + e.d2
        assert np.linalg.norm(axis) > 1e-6
        # Pointing into material: dot product with outward face normals should be <= 0
        assert (axis @ e.n1) <= 1e-6
        assert (axis @ e.n2) <= 1e-6


def test_fillet_arrow_vertical_along_wall_for_horizontal_edge():
    """Report 20261031-072053: user requested that the draggable fillet arrow moves vertically (up/down)
    rather than diagonally from the side when adjusting an edge on top of an extrusion."""
    from omacad.ui.main_window import MainWindow
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    body = win.doc.add_box(30.0, 20.0, 10.0)
    win.prompt_round_edges("fillet")
    top_edges = [e for e in body.edges if hasattr(e, "p0") and abs(e.p0[2] - 10.0) < 1e-6 and abs(e.p1[2] - 10.0) < 1e-6]
    assert len(top_edges) > 0
    win.viewport.selected_edges = [top_edges[0]]
    win.viewport.edges_selection_changed.emit()

    handle = win.viewport.extrude_handle
    assert handle is not None
    # For a top edge on the box, the arrow must point straight down along Z [0, 0, -1]
    assert np.allclose(handle["axis"], [0.0, 0.0, -1.0])

    # For a bottom edge, the arrow must point straight up along Z [0, 0, 1]
    bottom_edges = [e for e in body.edges if hasattr(e, "p0") and abs(e.p0[2]) < 1e-6 and abs(e.p1[2]) < 1e-6]
    assert len(bottom_edges) > 0
    win.viewport.selected_edges = [bottom_edges[0]]
    win.viewport.edges_selection_changed.emit()
    handle_bottom = win.viewport.extrude_handle
    assert handle_bottom is not None
    assert np.allclose(handle_bottom["axis"], [0.0, 0.0, 1.0])

