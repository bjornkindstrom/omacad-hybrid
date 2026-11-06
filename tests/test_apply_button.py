"""Green ✓ apply button in the viewport for sketch and 3D tools that wait for Enter after picking."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from omacad.model.features.offset_face import plane_face_ref
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    yield w
    if w.inspector.current_tool_dlg is not None:
        w.inspector.current_tool_dlg.reject()
    w.close()


def _visible_apply_buttons(vp):
    return [b for b in vp.findChildren(QToolButton) if b.text() == "✓" and b.isVisible()]


def test_sketch_tools_show_and_click_green_check_button(win):
    vp = win.viewport
    sk = win.doc.start_sketch("XY")
    sk.add_rect((0.0, 0.0), (20.0, 15.0))
    win.doc.notify_changed()
    vp.zoom_fit()

    # 1. Sketch Move (pick phase -> base phase on clicking green ✓)
    vp.selected_entities = set()
    vp.set_sketch_tool("MOVE")
    assert vp._move_phase == "pick"
    vp._sketch_apply_place()
    assert not vp._sketch_apply_btn.isVisible()
    vp.selected_entities = {sk.entities[0].entity_id}
    vp._sketch_apply_place()
    assert vp._sketch_apply_btn.isVisible()
    vp._sketch_apply_btn.click()
    assert vp._move_phase == "base"

    # 2. Sketch Mirror (pick phase -> axis phase on clicking green ✓)
    vp.selected_entities = set()
    vp.set_sketch_tool("MIRROR")
    assert vp._mirror_phase == "pick"
    vp.selected_entities = {sk.entities[0].entity_id}
    vp._sketch_apply_place()
    assert vp._sketch_apply_btn.isVisible()
    vp._sketch_apply_btn.click()
    assert vp._mirror_phase == "axis"

    # 3. Sketch Spline (2+ points -> finishes spline on clicking green ✓)
    vp.set_sketch_tool("SPLINE")
    vp._spline_points = [(0.0, 0.0), (10.0, 5.0), (20.0, 0.0)]
    vp.sketch_start_uv = (20.0, 0.0)
    vp._sketch_apply_place()
    assert vp._sketch_apply_btn.isVisible()
    n_before = len(sk.entities)
    vp._sketch_apply_btn.click()
    assert len(sk.entities) == n_before + 1

    # 4. Sketch Rotate, Scale & Pattern
    vp.selected_entities = {sk.entities[0].entity_id}
    vp.set_sketch_tool("ROTATE")
    vp._sketch_apply_place()
    assert vp._sketch_apply_btn.isVisible()
    vp._sketch_apply_btn.click()
    assert vp.sketch_tool == "NONE"

    vp.selected_entities = {sk.entities[0].entity_id}
    vp.set_sketch_tool("SCALE")
    vp._sketch_apply_place()
    assert vp._sketch_apply_btn.isVisible()
    vp._sketch_apply_btn.click()
    assert vp.sketch_tool == "NONE"

    vp.selected_entities = {sk.entities[0].entity_id}
    vp.set_sketch_tool("PATTERN")
    vp._sketch_apply_place()
    assert vp._sketch_apply_btn.isVisible()
    vp._sketch_apply_btn.click()
    assert vp.sketch_tool == "NONE"

    win.on_finish_sketch()


def test_3d_pick_tools_show_and_click_green_check_button(win):
    vp = win.viewport
    sk = win.doc.start_sketch("XY")
    sk.add_rect((0.0, 0.0), (20.0, 15.0))
    win.doc.finish_sketch()
    vp.zoom_fit()

    # 1. Extrude
    win.prompt_extrude(10.0)
    QTest.qWait(80)
    btns = _visible_apply_buttons(vp)
    assert btns
    btns[0].click()
    QApplication.processEvents()
    assert len(win.doc.bodies) == 1

    # 2. Offset Face
    body = next(iter(win.doc.bodies.values()))
    face = max(body.faces, key=lambda f: f.normal[2])
    win.prompt_offset_face(face=face)
    QTest.qWait(100)
    btns = _visible_apply_buttons(vp)
    assert btns
    btns[0].click()
    QApplication.processEvents()
    assert win.doc.timeline.features[-1].feature_type == "offset_face"

    # 3. Shell
    win.prompt_shell(body.body_id)
    QTest.qWait(100)
    btns = _visible_apply_buttons(vp)
    assert btns
    btns[0].click()
    QApplication.processEvents()
    assert win.doc.timeline.features[-1].feature_type == "shell"
