"""The Dimension tool shows a small value box in the 3D view once two points are picked; the sketch banner is gone."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402


@pytest.fixture
def view(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    v = Viewport3D(Document())
    v.resize(800, 600)
    return v


def two_points(view):
    sk = view.doc.start_sketch("XY")
    a = sk.add_line((0, 0), (0, 10))
    b = sk.add_line((40, 0), (40, 10))
    view.align_to_plane(sk.plane)
    view.set_sketch_tool("DIMENSION")
    assert view.handle_dimension_tool_click(0.0, 0.0)          # end point of the first line
    assert view.handle_dimension_tool_click(40.0, 0.0)         # end point of the second line
    return sk, a, b


def dist_dims(sk):
    return [d for d in sk.dimensions if d.dim_type in ("DISTANCE", "HORIZ_DIST", "VERT_DIST")]


def test_box_appears_with_the_measure(view):
    two_points(view)
    box = view._dim_box
    assert box is not None and not box.isHidden()
    assert box.spin.value() == pytest.approx(40.0)


def test_box_follows_the_cursor_until_you_type(view):
    sk, *_ = two_points(view)
    view._dim_hover_uv = None
    _k, measured, label = view._dim_points_kind(view._dim_place, 20.0, 15.0)    # above the points: horizontal
    view._dim_box.set_measure(label, measured)
    assert "Horizontal" in view._dim_box.lbl.text() and view._dim_box.spin.value() == pytest.approx(40.0)
    view._dim_box.edited = True
    view._dim_box.spin.setValue(33.0)
    view._dim_box.set_measure("x", 99.0)
    assert view._dim_box.spin.value() == pytest.approx(33.0)


def test_typed_value_and_placement_click(view):
    sk, *_ = two_points(view)
    view._dim_box.edited = True
    view._dim_box.spin.setValue(30.0)
    assert view.handle_dimension_tool_click(20.0, 18.0)                         # placement click above = horizontal
    dims = dist_dims(sk)
    assert [d.dim_type for d in dims] == ["HORIZ_DIST"] and dims[0].value == pytest.approx(30.0)
    assert view._dim_box is None


def test_click_without_typing_keeps_the_measured_value(view):
    sk, *_ = two_points(view)
    assert view.handle_dimension_tool_click(20.0, 18.0)
    dims = dist_dims(sk)
    assert len(dims) == 1 and dims[0].value == pytest.approx(40.0)


def test_enter_in_the_box_places_it(view):
    sk, *_ = two_points(view)
    view._dim_box.edited = True
    view._dim_box.spin.setValue(25.0)
    view._dim_box.committed.emit()
    dims = dist_dims(sk)
    assert len(dims) == 1 and dims[0].value == pytest.approx(25.0) and view._dim_box is None


def test_escape_in_the_box_cancels(view):
    sk, *_ = two_points(view)
    view._dim_box.cancelled.emit()
    assert view._dim_box is None and view._dim_place is None and not dist_dims(sk)


def test_status_bar_shows_the_sketch_status_instead_of_a_banner():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow()
    assert w.lbl_sketch_status.text() == ""
    w.doc.start_sketch("XY")
    assert w.lbl_sketch_status.text().startswith("✏️ Sketch 1 (XY)")
    w.doc.active_sketch = None
    w.doc.notify_changed()
    assert w.lbl_sketch_status.text() == ""


def test_editing_box_takes_the_value_when_you_click_elsewhere(view):
    """#77: the box for an existing dimension only listened for Enter/Esc; after a click outside it stayed forever."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLineEdit
    from omacad.ui.inline_value import InlineValueBox
    elsewhere = QLineEdit()

    def type_and_leave():
        box = view.findChild(InlineValueBox)
        box.spin.lineEdit().setText("12")
        QApplication.instance().focusChanged.emit(box.spin, elsewhere)

    QTimer.singleShot(0, type_and_leave)
    value, _expr = view.prompt_dimension_inline("d1", 5.0, 0.1, 1000.0, " mm")
    assert value == 12.0
    assert view.findChild(InlineValueBox) is None or not view.findChild(InlineValueBox).isVisible()
