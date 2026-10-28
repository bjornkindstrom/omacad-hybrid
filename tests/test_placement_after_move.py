"""Björn: what belongs to a step of an object that was moved later (its sketch, what the step added, the edges a
Fillet rounds) is shown where the body is now, not where it was when the step was made."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.main_window import MainWindow

DOC = "tests/data/favorites_hooks.omacad"      # three hooks, each with sketches, fillets and moves


def _corner_map(m, pts):
    return np.asarray(pts, float) @ m[:3, :3].T + m[:3, 3]


def test_placement_is_the_later_moves_of_the_same_object():
    doc = Document()
    doc.add_box(40, 20, 10)
    bid = next(iter(doc.bodies))
    box = doc.timeline.features[0].feature_id
    before = np.array(doc.bodies[bid].manifold.bounding_box()).reshape(2, 3)
    assert doc.placement_after(box) is None
    doc.move_body(bid, dx=5, dy=3, rz=30)
    doc.move_body(bid, dz=7, rx=90)
    m = doc.placement_after(box)
    corners = np.array([[x, y, z] for x in before[:, 0] for y in before[:, 1] for z in before[:, 2]])
    moved = _corner_map(m, corners)
    after = np.array(doc.bodies[bid].manifold.bounding_box()).reshape(2, 3)
    assert moved.min(axis=0) == pytest.approx(after[0], abs=1e-6)
    assert moved.max(axis=0) == pytest.approx(after[1], abs=1e-6)
    # a point on the body maps onto the body (the turn's direction is right, not only the box around it)
    probe = _corner_map(m, [[1.0, 1.0, 9.0]])[0]
    assert doc.bodies[bid].manifold.min_gap(
        __import__("manifold3d").Manifold.sphere(0.01).translate(list(probe)), 0.5) < 0.02
    # stepping back before the moves: nothing has moved yet
    doc.timeline.step_to(1, doc)
    assert doc.placement_after(box) is None


def test_a_moved_hooks_sketch_and_step_show_where_the_hook_is():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    sk_fid = next(f.feature_id for f in doc.timeline.features if f.feature_type == "sketch" and f.sketch.sketch_id == "sketch_1")
    doc.move_body("body_extrude_2", dy=16)
    m = doc.sketch_placement("sketch_1")
    assert m is not None and doc.placement_after(sk_fid) is not None
    lo, hi = np.array(doc.bodies["body_extrude_2"].manifold.bounding_box()).reshape(2, 3)
    sketch = doc.sketches["sketch_1"]
    pts = np.array([sketch.plane.uv_to_world(*p) for e in sketch.entities for seg in e.to_lines() for p in seg])
    shown = _corner_map(m, pts)
    assert shown[:, 1].min() >= lo[1] - 1e-6 and shown[:, 1].max() <= hi[1] + 1e-6     # on the hook, as it is now
    assert doc.sketch_placement("sketch_3") is None or not np.allclose(doc.sketch_placement("sketch_3"), m)

    w = MainWindow()
    Exporter.apply_dict(w.doc, Exporter.document_to_dict(doc))
    bar, doc = w.timeline_bar, w.doc
    chamfer = next(i for i, f in enumerate(doc.timeline.features) if f.feature_id == "fillet_4") + 1
    edges = bar._edges(chamfer)
    assert edges
    ys = np.concatenate([np.asarray(e.polyline())[:, 1] for e in edges])
    lo, hi = np.array(doc.bodies["body_extrude_2"].manifold.bounding_box()).reshape(2, 3)
    assert ys.min() >= lo[1] - 1e-3 and ys.max() <= hi[1] + 1e-3
    added, _removed = bar._changes(next(i for i, f in enumerate(doc.timeline.features) if f.feature_id == "extrude_2") + 1)
    assert added.bounding_box() == pytest.approx(doc.bodies["body_extrude_2"].manifold.bounding_box(), abs=0.6)
