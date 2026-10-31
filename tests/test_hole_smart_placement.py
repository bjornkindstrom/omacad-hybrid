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

    # Click on the pencil (column 1) to edit distance
    item_row, item_data = hole_dim_rows[0]
    win.browser.on_item_clicked(item_row, 1)

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


def test_hole_preview_moves_with_typed_dimensions_and_badge_focus(win):
    """As the user types into smart boxes, the preview coordinates update dynamically,
    and clicking on dimension badges selects that dimension box."""
    from PySide6.QtGui import QKeyEvent, QMouseEvent
    from PySide6.QtCore import QEvent, Qt, QPointF

    body = win.doc.add_box(40.0, 30.0, 20.0)
    vp = win.viewport

    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    vp.begin_hole_place(plane)

    # Hover cursor over top face near (10, 10, 20)
    vp.hole_place_hover = np.array([10.0, 10.0, 20.0])

    # Render overlays to compute badges and effective position
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    vp.draw_painter_overlays(painter)
    painter.end()

    # Initial effective position matches hover
    orig_eff = getattr(vp, "_hole_last_effective_world", None)
    assert orig_eff is not None
    assert np.allclose(orig_eff, [10.0, 10.0, 20.0])

    # Now type "5" into box 0
    evt = QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, "5")
    vp.keyPressEvent(evt)
    assert vp.hole_dyn_texts[0] == "5"

    # Render again - effective point should now have shifted to 5 mm from edge 1
    painter = QPainter(img)
    vp.draw_painter_overlays(painter)
    painter.end()

    new_eff = getattr(vp, "_hole_last_effective_world", None)
    assert new_eff is not None
    # Position shifted
    assert not np.allclose(orig_eff, new_eff)

    # Check that badge rects are registered
    assert hasattr(vp, "_hole_badge_rects")
    assert len(vp._hole_badge_rects) >= 1

    # Simulate mouse click on badge 1 (orange / edge 2)
    idx, rect = vp._hole_badge_rects[1] if len(vp._hole_badge_rects) > 1 else vp._hole_badge_rects[0]
    click_pos = rect.center()
    mouse_evt = QMouseEvent(QEvent.Type.MouseButtonPress, click_pos, Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    vp.mousePressEvent(mouse_evt)

    # Focus should have shifted to that badge index
    assert vp.hole_dyn_focus == idx


def test_hole_prompt_does_not_create_sketch(win):
    """Picking a face for Hole must not enter sketch mode (no Finish Sketch required)."""
    body = win.doc.add_box(40.0, 30.0, 20.0)
    win.prompt_hole()

    # There should be an active hole dialog and viewport should be picking hole_plane
    assert win.viewport.plane_pick_mode is True
    assert win.viewport.plane_pick_purpose == "hole_plane"
    assert win.doc.active_sketch is None

    # Simulate picking the top face
    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    win.viewport.hole_plane_picked.emit(plane)

    # We must NOT be in sketch mode!
    assert win.doc.active_sketch is None
    assert win.viewport.hole_place_mode is True


def test_hole_in_all_corners_with_chamfer(win):
    """Clicking 'Holes in all corners' places matching holes in all 4 corners with chamfer enabled."""
    body = win.doc.add_box(40.0, 30.0, 20.0)
    win.prompt_hole()

    # Pick top face
    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    win.viewport.hole_plane_picked.emit(plane)

    # Get active dialog from inspector
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None
    assert dlg.btn_all_corners.isEnabled() is True

    # Click the button
    dlg.btn_all_corners.click()

    # 4 points should now be placed
    assert len(dlg.points) == 4
    # Chamfer depth should be set (>= 1.0)
    assert dlg.spn_chamfer_depth.value() >= 1.0

    # Points should correspond to the 4 corners with offsets
    xs = [p["origin"][0] for p in dlg.points]
    ys = [p["origin"][1] for p in dlg.points]
    assert min(xs) == pytest.approx(5.0)
    assert max(xs) == pytest.approx(35.0)
    assert min(ys) == pytest.approx(5.0)
    assert max(ys) == pytest.approx(25.0)


def test_hole_in_all_corners_preserves_custom_offsets_from_placed_hole(win):
    """If user placed a hole with custom offsets (e.g. 8 mm and 12 mm), 'Holes in all corners' uses those offsets."""
    body = win.doc.add_box(60.0, 40.0, 20.0)
    win.prompt_hole()

    plane = SketchPlane.from_face([0.0, 0.0, 1.0], [0.0, 0.0, 20.0])
    win.viewport.hole_plane_picked.emit(plane)
    dlg = win.inspector.current_tool_dlg

    # Place a hole with custom offsets (8.0 mm from one edge, 12.0 mm from another)
    pt_custom = {
        "origin": [8.0, 12.0, 20.0],
        "normal": [0.0, 0.0, 1.0],
        "refs": [
            {"p1": [0.0, 0.0], "p2": [60.0, 0.0], "dist": 12.0, "expr": None},
            {"p1": [0.0, 0.0], "p2": [0.0, 40.0], "dist": 8.0, "expr": None},
        ],
    }
    win.viewport.hole_point_picked.emit(pt_custom)

    assert len(dlg.points) == 1
    # Click Holes in all corners
    dlg.btn_all_corners.click()

    assert len(dlg.points) == 4
    xs = [p["origin"][0] for p in dlg.points]
    ys = [p["origin"][1] for p in dlg.points]
    assert min(xs) == pytest.approx(8.0)
    assert max(xs) == pytest.approx(52.0)
    assert min(ys) == pytest.approx(12.0)
    assert max(ys) == pytest.approx(28.0)

