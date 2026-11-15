"""Spline UI tests: handle picking, badges, dimensions, and fan menu interactions."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QPainter, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import Sketch, SketchSpline
from omacad.model.sketch_entities import SketchSpline
from omacad.ui.viewport.dimension_overlay_mixin import DimensionOverlayMixin
from omacad.ui.viewport.viewport import Viewport3D

DATA_DIR = Path(__file__).parent / "data"
REPORT_DATA = DATA_DIR / "control_spline_dimension.json"
BADGE_DATA = DATA_DIR / "spline_constraint_badges.json"


def _report_doc():
    doc = Document()
    with open(REPORT_DATA, encoding="utf-8") as f:
        Exporter.apply_dict(doc, json.load(f))
    return doc


@pytest.fixture
def viewport():
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    doc = Document()
    vp = Viewport3D(doc)
    vp.paintGL = lambda: None
    vp.initializeGL = lambda: None
    vp.resize(800, 600)
    return vp


def test_spline_handle_picking_and_insert(viewport):
    doc = viewport.doc
    sk = doc.start_sketch("XY")
    sp = sk.add_spline([(0, 0), (10, 20), (30, 0)])
    viewport.selected_entities = {sp.entity_id}

    plane = sk.plane
    fit_scr = viewport.world_to_screen(plane.uv_to_world(10, 20))
    assert fit_scr is not None
    handle = viewport._pick_spline_handle(fit_scr[0], fit_scr[1])
    assert handle is not None
    assert handle["entity"].entity_id == sp.entity_id

    uv = (5.0, 10.0)
    idx = sk.insert_spline_point(sp.entity_id, uv)
    assert len(sp.points) == 4


def test_offset_badge_symbol_visible_in_sketch_mode():
    if QApplication.instance() is None:
        QApplication([])
    doc = Document()
    sk = doc.start_sketch("XY")
    src = sk.add_spline([(0, 0), (25, 30), (50, -20), (75, 40), (100, 0)], control_points=True)
    copy = sk.offset_entities([src.entity_id], 4.0)[0]

    view = Viewport3D(doc)
    view.paintGL = lambda: None
    view.initializeGL = lambda: None
    view.resize(800, 600)
    view.align_to_plane(sk.plane)
    view.sketch_palette.chk_show_constraints.setChecked(False)

    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    try:
        view.draw_constraint_badges(p)
    finally:
        p.end()
        view.close()

    offset_c = next(c for c in sk.constraints if c.ctype == "OFFSET")
    assert any(cid == offset_c.cid for _, cid in view.constraint_badges)
    assert Viewport3D.CONSTRAINT_GLYPHS["OFFSET"] == "⧉"


def test_saved_spline_coincident_constraints_do_not_interrupt_dimension_painting():
    if QApplication.instance() is None:
        QApplication([])
    with open(BADGE_DATA, encoding="utf-8") as f:
        sketch = Sketch.from_dict(json.load(f))
    constraints = {c.cid: c for c in sketch.constraints}
    assert constraints["c_4"].pts == ["pt0", "p2"]
    assert constraints["c_5"].pts == ["pt3", "p2"]
    doc = Document()
    doc.sketches[sketch.sketch_id] = sketch
    doc.active_sketch = sketch
    view = Viewport3D(doc)
    view.paintGL = lambda: None
    view.initializeGL = lambda: None
    view.resize(800, 600)
    view.align_to_plane(sketch.plane)
    view.sketch_palette.chk_show_constraints.setChecked(True)
    view.sketch_palette.chk_show_dims.setChecked(True)
    image = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        view.draw_constraint_badges(painter)
        view.draw_dimensions(painter)
    finally:
        painter.end()
        view.close()
    assert {cid for _, cid in view.constraint_badges} >= {"c_4", "c_5"}
    assert {"d5", "d6"} <= set(view.dim_badges)
    assert doc.update_dimension(sketch.sketch_id, "d5", 4.5)
    assert sketch.get_entity("spline_1").points[1][1] == pytest.approx(4.5)


def test_dimension_tool_picks_a_control_point_of_the_spline():
    doc = _report_doc()
    view = SimpleNamespace(doc=doc, _entity_tolerance=lambda: 1.0)
    pick = DimensionOverlayMixin._dim_pick(view, 95.3, 54.8)
    assert pick[0] == "pt" and pick[1].entity_id == "spline_1" and pick[2] == "pt2"


def test_add_control_point_from_the_fan_menu_after_the_click_event_is_gone():
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    doc = _report_doc()
    vp = Viewport3D(doc)
    vp.paintGL = lambda: None
    vp.initializeGL = lambda: None
    vp.resize(800, 600)
    vp.align_to_plane(doc.active_sketch.plane)
    sk = doc.active_sketch
    spline = sk.get_entity("spline_1")
    scr = vp.world_to_screen(sk.plane.uv_to_world(80.0, 30.0))
    at = QPointF(scr[0], scr[1])
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, at, vp.mapToGlobal(at), Qt.MouseButton.RightButton,
                        Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)
    vp._show_element_menu(event, spline)
    import shiboken6
    shiboken6.delete(event)
    items = {i.id: i for c in vp._ensure_fan_menu().categories for i in (c.children or [])}
    items["el_insert_point"].callback()
    spline = doc.active_sketch.get_entity("spline_1")
    assert len(spline.points) == 5
    assert spline.points[2] == pytest.approx((80.0, 30.0), abs=0.5)
