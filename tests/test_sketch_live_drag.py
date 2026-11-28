"""Sketch plan step 6: dragging a point solves the sketch live, so what is joined to it follows, and the release
solves once more (before, the joined lines stayed behind until the next solve)."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document


def test_dragging_a_rectangle_corner_carries_its_neighbours_along():
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    sk.add_rect((0.0, 0.0), (20.0, 10.0))
    sk = doc.active_sketch
    from omacad.model.sketch_solver import solve_sketch
    sk.dimensions = [d for d in sk.dimensions if d.dim_type != "LENGTH"]      # free size: the corner may move
    assert solve_sketch(sk).ok
    corner_line = next(l for l in sk.entities if l.entity_type == "line" and l.p2 == pytest.approx((20.0, 10.0)))
    vp._endpoint_drag = {"sketch_id": sk.sketch_id, "entity_id": corner_line.entity_id, "point_name": "p2",
                         "moved": False, "before": sk.to_dict()}
    target = (26.0, 14.0)
    vp.get_sketch_plane_uv = lambda x, y: target
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt, QEvent
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(5, 5), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    vp._endpoint_drag_move(ev)
    sk = doc.active_sketch
    at_corner = [l for l in sk.entities if l.entity_type == "line"
                 and any(p == pytest.approx(target, abs=1e-6) for p in (l.p1, l.p2))]
    assert len(at_corner) == 2                                     # the neighbouring side followed live
    vp._endpoint_drag_release()
    sk = doc.active_sketch
    assert len([l for l in sk.entities if l.entity_type == "line"
                and any(p == pytest.approx(target, abs=1e-6) for p in (l.p1, l.p2))]) == 2
    vp.deleteLater()
