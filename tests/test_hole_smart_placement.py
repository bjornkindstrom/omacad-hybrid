import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QImage

from omacad.ui.main_window import MainWindow
from omacad.model.sketch import SketchPlane


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1000, 800)
    w.viewport.resize(800, 600)
    yield w
    w.close()


def test_hole_placement_smart_circle_measuring_guides(win):
    """When placing a hole on a plane or face, measuring guides to the nearest straight edges
    are computed and drawn like Smart Circle."""
    body = win.doc.add_box(40.0, 30.0, 20.0)
    vp = win.viewport

    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    vp.begin_hole_place(plane)

    assert vp.hole_place_mode is True
    assert len(vp.hole_place_segments) >= 4  # The 4 edges of the top face of the box

    # Hover near center
    vp.hole_place_hover = np.array([10.0, 10.0, 20.0])

    # Render overlay onto an image buffer
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    vp.draw_painter_overlays(painter)
    painter.end()

    # Press to place a point
    assert vp._hole_place_press(400, 300)
    assert len(vp.hole_place_points) == 1

    # End placement
    vp.end_hole_place()
    assert vp.hole_place_mode is False
    assert len(vp.hole_place_segments) == 0


def test_hole_placement_typing_and_browser_editing(win):
    """Typing dimensions during hole placement sets exact offsets, and these are editable in the object browser."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent, Qt

    body = win.doc.add_box(40.0, 30.0, 20.0)
    vp = win.viewport

    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    vp.begin_hole_place(plane)

    # Hover cursor over top face near (10, 10, 20)
    vp.hole_place_hover = np.array([10.0, 10.0, 20.0])

    # Type "15" into distance 1
    for ch in "15":
        evt = QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch)
        vp.keyPressEvent(evt)
    assert vp.hole_dyn_texts[0] == "15"

    # Tab to switch to distance 2
    evt_tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    vp.keyPressEvent(evt_tab)
    assert vp.hole_dyn_focus == 1

    # Type "12" into distance 2
    for ch in "12":
        evt = QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch)
        vp.keyPressEvent(evt)
    assert vp.hole_dyn_texts[1] == "12"

    # Resolve point with typed distances
    pt_data = vp._hole_place_resolve_point()
    assert pt_data is not None
    assert len(pt_data["refs"]) == 2
    assert pt_data["refs"][0]["dist"] == 15.0
    assert pt_data["refs"][1]["dist"] == 12.0

    # Add hole to document with this point
    feat = win.doc.add_hole([pt_data], diameter=6.0, depth=10.0)
    assert len(feat.points) == 1
    assert len(feat.points[0]["refs"]) == 2

    # Refresh object browser and check tree items
    win.browser.refresh_tree()

    # Find the hole feature item in the browser
    hole_item = None
    for item, _ in win.browser._walk():
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "feature" and data[1] == feat.feature_id:
            hole_item = item
            break

    assert hole_item is not None
    # Check that distance child rows exist
    hole_dim_rows = []
    for k in range(hole_item.childCount()):
        row = hole_item.child(k)
        data = row.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "hole_dim":
            hole_dim_rows.append((row, data))

    assert len(hole_dim_rows) == 2
    assert "Distance to edge 1: 15 mm" in hole_dim_rows[0][0].text(0)
    assert "Distance to edge 2: 12 mm" in hole_dim_rows[1][0].text(0)

    # Edit distance 1 in document via edit_hole_dimension
    assert win.doc.edit_hole_dimension(feat.feature_id, 0, 0, "20.0")
    assert feat.points[0]["refs"][0]["dist"] == 20.0

    # Also test via apply_dimension (used by history delegate when user edits inline)
    from omacad.ui.history_delegate import apply_dimension
    assert apply_dimension(win.doc, "hole_dim", (feat.feature_id, 0, 1), "18.0")
    assert feat.points[0]["refs"][1]["dist"] == 18.0

    win.browser.refresh_tree()
    # Find row again and verify updated text
    found_20 = False
    found_18 = False
    for item, _ in win.browser._walk():
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "feature" and data[1] == feat.feature_id:
            for k in range(item.childCount()):
                row = item.child(k)
                if "Distance to edge 1: 20 mm" in row.text(0):
                    found_20 = True
                if "Distance to edge 2: 18 mm" in row.text(0):
                    found_18 = True
    assert found_20 is True
    assert found_18 is True

    # Test undo
    win.doc.undo()
    current_feat = next(f for f in win.doc.timeline.features if f.feature_id == feat.feature_id)
    assert current_feat.points[0]["refs"][1]["dist"] == 12.0
    win.doc.undo()
    current_feat = next(f for f in win.doc.timeline.features if f.feature_id == feat.feature_id)
    assert current_feat.points[0]["refs"][0]["dist"] == 15.0
