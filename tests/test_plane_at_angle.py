"""Björn #51: planes can be turned (Fusion's Plane at Angle) - about the start plane's X/Y direction or an edge."""
import math

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.document import Document


def test_plane_turned_about_x_then_offset():
    doc = Document()
    pid = doc.add_construction_plane(doc.origin_planes["XY"], 5.0, origin=(0, 0, 0), angle=30.0, axis_dir=(1, 0, 0))
    c = doc.construction_planes[pid]
    want_n = np.array([0.0, -math.sin(math.radians(30)), math.cos(math.radians(30))])
    assert np.allclose(c["normal"], want_n, atol=1e-9)
    assert np.allclose(c["origin"], want_n * 5.0, atol=1e-9)
    sk = doc.start_sketch_on_plane(doc.construction_plane(pid))      # a sketch can go on it
    assert np.allclose(sk.plane.normal, want_n, atol=1e-6)


def test_plane_turned_about_a_box_edge_contains_the_edge(tmp_path):
    doc = Document()
    box = doc.add_box(20, 10, 6)
    top = box.manifold.bounding_box()[5]
    edge = next(e for e in box.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - top) < 1e-9 and abs(e.p1[2] - top) < 1e-9 and abs(e.p0[1] - e.p1[1]) < 1e-9)
    mid, d = (edge.p0 + edge.p1) / 2, edge.p1 - edge.p0
    top_plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], top, origin=(0, 0, 0)))
    pid = doc.add_construction_plane(top_plane, 0.0, origin=mid, angle=45.0, axis_point=mid, axis_dir=d)
    c = doc.construction_planes[pid]
    n = np.asarray(c["normal"])
    for p in (edge.p0, edge.p1):                     # the edge lies in the new plane
        assert abs(float((p - np.asarray(c["origin"])) @ n)) < 1e-9
    assert abs(abs(float(n[2])) - math.cos(math.radians(45))) < 1e-9
    path = tmp_path / "p.omacad"
    Exporter.save_project(doc, str(path))
    assert np.allclose(Exporter.load_project(str(path)).construction_planes[pid]["normal"], n)


def test_angle_zero_is_a_plain_offset():
    o, n = Document.angled_plane((0, 0, 1), (1, 2, 3), 4.0, 0.0, None, (1, 0, 0))
    assert np.allclose(o, (1, 2, 7)) and np.allclose(n, (0, 0, 1))


def test_offset_plane_panel_turns_the_preview_and_the_plane():
    import pytest
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    from omacad.ui.dialogs.sketch_plane_dlg import OffsetPlaneDialog
    QApplication.instance() or QApplication([])
    w = MainWindow()
    seen = {}

    def drive():
        dlgs = w.findChildren(OffsetPlaneDialog)
        if not dlgs:
            QTimer.singleShot(20, drive)
            return
        dlg = dlgs[-1]
        try:
            dlg.spn_dist.setValue(0.0)
            dlg.cmb_axis.setCurrentIndex(1)          # the plane's Y direction
            dlg.spn_angle.setValue(90.0)
            QApplication.processEvents()
            seen["preview"] = np.asarray(w.viewport.preview_plane.normal, dtype=float)
        finally:
            dlg.accept()

    QTimer.singleShot(0, drive)
    w.on_offset_base_picked(w.doc.origin_planes["XY"])
    c = next(iter(w.doc.construction_planes.values()))
    assert np.allclose(np.abs(c["normal"]), (1, 0, 0), atol=1e-6)        # XY turned 90° about Y: a YZ-like plane
    assert np.allclose(np.abs(seen["preview"]), (1, 0, 0), atol=1e-6)
    w.close()
