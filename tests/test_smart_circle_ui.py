"""The Smart Circle tool end to end in the viewport: numbers and Enter place a dimensioned circle."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402
from omacad.model.sketch import SketchCircle  # noqa: E402


@pytest.fixture
def view():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport import Viewport3D
    return Viewport3D(Document())


def key(view, k, text=""):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier, text))


def typ(view, s):
    from PySide6.QtCore import Qt
    for ch in s:
        key(view, getattr(Qt.Key, f"Key_{ch}") if ch.isdigit() else Qt.Key.Key_Period, ch)
    key(view, Qt.Key.Key_Return)


def test_numbers_and_enter_place_a_circle_and_dimension_it(view):
    sk = view.doc.start_sketch("XY")
    sk.add_rect((0, 0), (60, 40))
    view.set_sketch_tool("SMART_CIRCLE")
    view._raw_mouse_uv = view.smart.mouse = (50, 30)
    view.smart.segments = view._smart_segments()
    typ(view, "8")          # diameter
    view.smart.mouse = (52, 20)
    typ(view, "10")         # 10 from the right wall
    view.smart.mouse = (30, 38)
    typ(view, "6")          # 6 from the top wall
    circles = [e for e in sk.entities if isinstance(e, SketchCircle)]
    assert len(circles) == 1
    c = circles[0]
    assert c.radius == pytest.approx(4.0)
    assert tuple(c.center) == pytest.approx((50.0, 34.0))
    kinds = sorted(d.dim_type for d in sk.dimensions if d.dim_type == "PT_LINE_DIST" and d.target_entity_id == c.entity_id)
    assert kinds == ["PT_LINE_DIST", "PT_LINE_DIST"]
    assert view.smart.stage == 0   # ready for the next circle

    # Editing a wall offset distance must move the circle, not the outer sketch
    dist_dim = next(d for d in sk.dimensions if d.dim_type == "PT_LINE_DIST" and d.value == pytest.approx(10.0))
    ok = view.doc.update_dimension(sk.sketch_id, dist_dim.dim_id, 20.0)
    assert ok
    lines = [e for e in sk.entities if hasattr(e, 'p1')]
    xs = [p[0] for l in lines for p in (l.p1, l.p2)]
    ys = [p[1] for l in lines for p in (l.p1, l.p2)]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(60.0)
    assert min(ys) == pytest.approx(0.0) and max(ys) == pytest.approx(40.0)
    assert tuple(c.center) == pytest.approx((40.0, 34.0))


def test_rounded_rect_asks_for_the_radius_after_width_and_height(view):
    from omacad.model.sketch import SketchLine
    sk = view.doc.start_sketch("XY")
    view.set_sketch_tool("ROUNDED_RECT")
    view.sketch_start_uv = (0.0, 0.0)
    view.sketch_current_uv = view._raw_mouse_uv = (30.0, 20.0)
    view._arm_dyn()
    typ(view, "40")
    typ(view, "25")
    assert view.dyn.names[view.dyn.focus] == "Radius"    # Enter after height moves on to the radius
    assert not [e for e in sk.entities if isinstance(e, SketchLine)]
    typ(view, "5")
    xs = [e.p1[0] for e in sk.entities if isinstance(e, SketchLine)] + [e.p2[0] for e in sk.entities if isinstance(e, SketchLine)]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(40.0)
    arcs = [e for e in sk.entities if getattr(e, "entity_type", "") == "arc"]
    assert len(arcs) == 4
    assert abs(40.0 - 2 * 5.0 - max(abs(e.p1[0] - e.p2[0]) for e in sk.entities if isinstance(e, SketchLine))) < 1e-6
