"""Tests for Omacad Fan / Radial Menu (two-arc right-click fan menu)."""

import pytest
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtWidgets import QApplication

from omacad.ui.fan_menu import FanMenuOverlay, FanItem
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    return w


class _Ev:
    def __init__(self, x=100.0, y=100.0):
        self._pos = QPointF(x, y)

    def position(self):
        return self._pos

    def globalPosition(self):
        return self._pos


def test_fan_categories_solid_mode(win):
    vp = win.viewport
    cats = vp._build_workspace_fan_categories(sketch=False)
    cat_ids = [c.id for c in cats]
    assert "cat_create" in cat_ids
    assert "cat_modify" in cat_ids
    assert "cat_inspect" in cat_ids
    assert "cat_view" in cat_ids
    assert "cat_history" in cat_ids

    create_cat = next(c for c in cats if c.id == "cat_create")
    tool_ids = [t.id for t in create_cat.children]
    assert "extrude" in tool_ids
    assert "revolve" in tool_ids
    assert "primitives" in tool_ids
    assert "patterns" in tool_ids

    # Sub-fan
    prims = next(t for t in create_cat.children if t.id == "primitives")
    assert any(p.id == "box" for p in prims.children)
    assert any(p.id == "cylinder" for p in prims.children)


def test_fan_categories_sketch_mode(win):
    vp = win.viewport
    cats = vp._build_workspace_fan_categories(sketch=True)
    cat_ids = [c.id for c in cats]
    assert "cat_create" in cat_ids
    assert "cat_modify" in cat_ids
    assert "cat_constraints" in cat_ids

    create_cat = next(c for c in cats if c.id == "cat_create")
    tool_ids = [t.id.lower() for t in create_cat.children]
    assert "line" in tool_ids
    assert "rectangles" in tool_ids
    assert "circle" in tool_ids

    const_cat = next(c for c in cats if c.id == "cat_constraints")
    assert len(const_cat.children) >= 10


def test_fan_menu_overlay_hit_test_and_popup(win):
    win.show()
    vp = win.viewport
    overlay = vp._ensure_fan_menu()

    cats = vp._build_workspace_fan_categories(sketch=False)
    overlay.popup(
        center=QPoint(300, 300),
        categories=cats,
        default_category_idx=0
    )
    assert not overlay.isHidden()
    assert len(overlay.inner_sectors) == len(cats)
    assert len(overlay.outer_sectors) > 0

    # Test hub hover
    overlay.update_cursor_pos(QPointF(300, 300))
    assert overlay.hovered_hub == "hub_center"

    # Test outer sector hover
    # Mid-angle for first outer sector
    sec0 = overlay.outer_sectors[0]
    import math
    mid_rad = math.radians(sec0.start_angle + sec0.span_angle / 2.0)
    r = (sec0.r_inner + sec0.r_outer) * 0.5
    ox = overlay.center_pos.x() + r * math.cos(mid_rad)
    oy = overlay.center_pos.y() - r * math.sin(mid_rad)
    overlay.update_cursor_pos(QPointF(ox, oy))
    assert overlay.hovered_outer_idx == 0

    # Triggering hovered item
    triggered = []
    overlay.action_triggered.connect(triggered.append)
    overlay.finish_gesture()
    assert overlay.isHidden()
    assert len(triggered) == 1
    assert triggered[0].id == sec0.item.id


def test_fan_menu_context_face(win):
    win.show()
    win.doc.add_box(10, 10, 10)
    vp = win.viewport
    overlay = vp._ensure_fan_menu()

    # Right-click general menu
    vp._show_general_menu(_Ev(200, 200))
    assert not overlay.isHidden()
    assert any(c.id == "cat_context" for c in overlay.categories)
    assert overlay.categories[0].id == "cat_context"
    overlay.dismiss()


def test_fan_menu_rendering_and_mouse_events(win):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    win.resize(900, 700)
    win.show()
    vp = win.viewport
    vp.resize(800, 600)
    overlay = vp._ensure_fan_menu()
    cats = vp._build_workspace_fan_categories(sketch=False)

    # Open with split hub (OK / Cancel)
    overlay.popup(
        center=QPointF(400, 300),
        categories=cats,
        hub_ok=FanItem(id="tool_ok", label="Finish"),
        hub_cancel=FanItem(id="tool_cancel", label="Cancel"),
        default_category_idx=0,
    )
    assert overlay.is_open

    # Hover an outer sector that has sub-sectors (e.g., primitives)
    prim_idx = next(i for i, s in enumerate(overlay.outer_sectors) if s.item.id == "primitives")
    sec_prim = overlay.outer_sectors[prim_idx]
    import math
    mid_rad = math.radians(sec_prim.start_angle + sec_prim.span_angle / 2.0)
    r = (sec_prim.r_inner + sec_prim.r_outer) * 0.5
    ox = overlay.center_pos.x() + r * math.cos(mid_rad)
    oy = overlay.center_pos.y() - r * math.sin(mid_rad)
    overlay.handle_mouse_move(ox, oy)
    assert overlay.hovered_outer_idx == prim_idx
    assert len(overlay.sub_sectors) > 0

    # Render onto a QImage to verify draw() completes without error
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = QPainter(img)
    try:
        overlay.draw(painter, 800, 600)
    finally:
        painter.end()

    # Clicking on a parent outer sector ("primitives") in click mode expands its children into outer_sectors!
    class _BtnEv(_Ev):
        def __init__(self, x, y, btn=Qt.MouseButton.LeftButton):
            super().__init__(x, y)
            self._btn = btn
        def button(self):
            return self._btn
        def modifiers(self):
            return Qt.KeyboardModifier.NoModifier

    vp.mousePressEvent(_BtnEv(ox, oy, Qt.MouseButton.LeftButton))
    assert not vp.is_orbiting
    assert not vp.is_panning
    vp.mouseReleaseEvent(_BtnEv(ox, oy, Qt.MouseButton.LeftButton))
    assert overlay.is_open
    assert overlay.expanded_group_item is not None
    assert overlay.expanded_group_item.id == "primitives"
    assert any(s.item.id == "box" for s in overlay.outer_sectors)

    # Clicking "box" in the expanded outer ring opens BoxDialog and closes the fan menu
    box_sec = next(s for s in overlay.outer_sectors if s.item.id == "box")
    b_rad = math.radians(box_sec.start_angle + box_sec.span_angle / 2.0)
    b_r = (box_sec.r_inner + box_sec.r_outer) * 0.5
    bx = overlay.center_pos.x() + b_r * math.cos(b_rad)
    by = overlay.center_pos.y() - b_r * math.sin(b_rad)
    vp.mousePressEvent(_BtnEv(bx, by, Qt.MouseButton.LeftButton))
    vp.mouseReleaseEvent(_BtnEv(bx, by, Qt.MouseButton.LeftButton))
    assert not overlay.is_open
    assert win.inspector.current_tool_dlg is not None
    win.inspector.current_tool_dlg.reject()

    # Re-open and test clicking outside dismisses without orbiting
    overlay.popup(center=QPointF(400, 300), categories=cats, default_category_idx=0)
    vp.mousePressEvent(_BtnEv(10, 10, Qt.MouseButton.LeftButton))
    assert not vp.is_orbiting
    vp.mouseReleaseEvent(_BtnEv(10, 10, Qt.MouseButton.LeftButton))
    assert not overlay.is_open

    # 1. Fast right-click (< 180ms) opens fan menu and keeps it open
    vp.mousePressEvent(_BtnEv(400, 300, Qt.MouseButton.RightButton))
    vp.mouseReleaseEvent(_BtnEv(400, 300, Qt.MouseButton.RightButton))
    assert overlay.is_open
    overlay.dismiss()

    # 2. Slow right-click (>= 180ms, timeout fires before release at same spot) ALSO keeps fan menu open!
    vp.mousePressEvent(_BtnEv(400, 300, Qt.MouseButton.RightButton))
    vp._on_rfan_timeout()
    assert overlay.is_open
    vp.mouseReleaseEvent(_BtnEv(400, 300, Qt.MouseButton.RightButton))
    assert overlay.is_open
    assert not overlay.gesture_mode
    overlay.dismiss()

    # 3. Hold right-click (>= 180ms) + drag to outer leaf sector + release triggers tool and closes
    vp.mousePressEvent(_BtnEv(520, 220, Qt.MouseButton.RightButton))
    vp._on_rfan_timeout()
    assert overlay.is_open
    # Pick "box" from Primitives category or expand primitives
    prim_cat_idx = next(i for i, c in enumerate(overlay.categories) if c.id == "cat_primitives")
    overlay.active_category_idx = prim_cat_idx
    overlay._rebuild_geometry()
    box_sec = next(s for s in overlay.outer_sectors if s.item.id == "box")
    mid_rad = math.radians(box_sec.start_angle + box_sec.span_angle / 2.0)
    r_leaf = (box_sec.r_inner + box_sec.r_outer) * 0.5
    lx = overlay.center_pos.x() + r_leaf * math.cos(mid_rad)
    ly = overlay.center_pos.y() - r_leaf * math.sin(mid_rad)
    vp.mouseMoveEvent(_BtnEv(lx, ly, Qt.MouseButton.RightButton))
    vp.mouseReleaseEvent(_BtnEv(lx, ly, Qt.MouseButton.RightButton))
    assert not overlay.is_open
    # Verify the BoxDialog opened with placement_offset matching the right-clicked 3D point!
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None
    assert hasattr(dlg, "placement_offset")
    assert tuple(dlg.placement_offset) == tuple(vp._fan_click_world)
    assert (dlg.placement_offset[0] != 0.0) or (dlg.placement_offset[1] != 0.0)
    dlg.reject()


def test_fan_menu_sketch_text_and_tools(win):
    """Verify sketch tools (especially Text) triggered from the fan menu invoke MainWindow prompts."""
    win.show()
    vp = win.viewport
    win.start_sketch_on_plane("XY")
    assert win.doc.active_sketch is not None

    cats = vp._build_workspace_fan_categories(sketch=True)
    create_cat = next(c for c in cats if c.id == "cat_create")

    # Find TEXT item in create_cat
    text_item = next(it for it in create_cat.children if it.id == "TEXT")
    assert text_item is not None

    # Trigger TEXT callback
    text_item.callback()

    # Verify TextDialog opened via prompt_text() and text session initialized
    assert win._text_session is not None
    assert win._text_session.dlg is not None
    assert vp.sketch_tool == "TEXT"

    # Close text dialog
    win._text_session.dlg.reject()
    assert win._text_session is None

    # Test LINE item
    line_item = next(it for it in create_cat.children if it.id == "line")
    line_item.callback()
    assert vp.sketch_tool == "LINE"
    assert win.ribbon.btn_line.isChecked()





