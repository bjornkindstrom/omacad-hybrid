"""Primitive dimensions track direct dragging while creation remains undoable."""
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from omacad.ui.dialogs import BoxDialog, CylinderDialog, SphereDialog
from omacad.ui.primitive_handles import PrimitiveHandles
from omacad.ui.main_window import MainWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("kind,cls", [("box", BoxDialog), ("cylinder", CylinderDialog), ("sphere", SphereDialog)])
def test_drag_fields_and_clamp(app, kind, cls):
    d = cls()
    vp = SimpleNamespace(plane_pick_mode=None, preview_mesh=None, setCursor=lambda *_: None, update=lambda: None,
                         world_to_screen=lambda p: (200 + 3*p[0] - 2*p[1], 200 + p[0] + p[1] - 3*p[2]))
    handles = PrimitiveHandles(vp, d, kind)
    for index in range(len(handles.geometry())):
        field, tip, tangent, _ = handles.geometry()[index]
        old = field.value()
        assert handles.press(*tip)
        handles.move(*(tip + tangent*10))
        assert field.value() == pytest.approx(old+10)
        assert handles.release()
    field, tip, tangent, _ = handles.geometry()[0]
    assert handles.press(*tip)
    handles.move(*(tip - tangent*100000))
    assert field.value() == 1
    handles.release()
    assert not handles.press(-10000, -10000)
    d.close()


def test_box_handles_follow_placement_and_picked_plane(app):
    d = BoxDialog()
    vp = SimpleNamespace()
    h = PrimitiveHandles(vp, d, "box")
    d.cmb_placement.setCurrentIndex(d.cmb_placement.findData("corner"))
    specs = h.specs()
    assert np.allclose(specs[0][1], [50, 25, 12.5])
    assert np.allclose(specs[0][2], [1, 0, 0])
    plane = SimpleNamespace(origin=[10, 20, 30], normal=[0, -1, 0],
                            u_axis=[1, 0, 0], v_axis=[0, 0, 1], name="XZ")
    d.set_target_plane(plane)
    height = h.specs()[2]
    assert np.allclose(height[1], [10, -5, 30])
    assert np.allclose(height[2], [0, -1, 0])
    d.close()


def test_primitive_placement_drag_stays_in_world_xy_plane(app):
    d = BoxDialog()
    origin = np.array([0., 0., 100.])
    direction = np.array([0., 0., -1.])
    vp = SimpleNamespace(
        plane_pick_mode=False,
        preview_mesh=SimpleNamespace(vertices=[1]),
        get_matrices=lambda: (np.eye(4), np.eye(4), None),
        width=lambda: 100,
        height=lambda: 100,
        setCursor=lambda *_: None,
        world_to_screen=lambda p: (0., 0.),
        update=lambda: None,
    )
    h = PrimitiveHandles(vp, d, "box")
    h._ray = lambda *_: (origin, direction)
    h._preview_hit = lambda *_: (np.array([1., 2., 3.]), direction)
    h.hit = lambda *_: None
    assert h.press(10, 10)
    h._ray = lambda *_: (np.array([5., 8., 100.]), direction)
    h.move(20, 20)
    assert d.placement_offset == pytest.approx([4., 6., 0.])
    h.release()
    d.close()


def mouse(vp, kind, point, button, buttons):
    e = QMouseEvent(kind, QPointF(*point), QPointF(*point), button, buttons, Qt.KeyboardModifier.NoModifier)
    {QEvent.Type.MouseButtonPress: vp.mousePressEvent,
     QEvent.Type.MouseMove: vp.mouseMoveEvent,
     QEvent.Type.MouseButtonRelease: vp.mouseReleaseEvent}[kind](e)


@pytest.mark.parametrize("kind", ["box", "cylinder", "sphere"])
def test_create_preview_drag_accept_undo_and_cancel(app, kind):
    w = MainWindow()
    vp = w.viewport
    vp.resize(1000, 800)
    getattr(w, "prompt_"+kind)()
    h = vp.primitive_handles
    assert h is not None
    field, tip, tangent, _ = h.geometry()[0]
    initial = field.value()
    mouse(vp, QEvent.Type.MouseButtonPress, tip, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    mouse(vp, QEvent.Type.MouseMove, tip+tangent*10, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    QTest.qWait(80)
    span = vp.preview_mesh.bounds_max[0] - vp.preview_mesh.bounds_min[0]
    assert span == pytest.approx((initial+10) * (1 if kind == "box" else 2), abs=.01)
    mouse(vp, QEvent.Type.MouseButtonRelease, tip+tangent*10, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    assert field.value() == pytest.approx(initial+10)
    assert not w.doc.bodies
    h.dialog.accept()
    assert vp.primitive_handles is None
    assert len(w.doc.bodies) == 1
    feat = w.doc.timeline.features[-1]
    if kind == "box":
        assert next(iter(w.doc.bodies.values())).manifold.volume() == pytest.approx(60*50*25)
    else:
        assert feat.radius == pytest.approx(initial+10)
    w.doc.undo()
    assert not w.doc.bodies
    getattr(w, "prompt_"+kind)()
    vp.primitive_handles.dialog.reject()
    QTest.qWait(80)
    assert vp.primitive_handles is None
    assert not w.doc.bodies
    assert vp.preview_mesh is None
    w.close()


def test_cancel_drag_restores_formula(app):
    d = BoxDialog()
    d.spn_length.set_expression("2*(20+5)")
    vp = SimpleNamespace(plane_pick_mode=None, preview_mesh=None, setCursor=lambda *_: None, update=lambda: None,
                         world_to_screen=lambda p: (200 + 3*p[0] - 2*p[1], 200 + p[0] + p[1] - 3*p[2]))
    handles = PrimitiveHandles(vp, d, "box")
    field, tip, tangent, _ = handles.geometry()[0]
    assert handles.press(*tip)
    handles.move(*(tip+tangent*10))
    assert field.value() == 60
    handles.cancel_drag()
    assert field.value() == 50
    assert field.expression() == "2*(20+5)"
    assert handles.drag is None
    d.close()


@pytest.mark.parametrize("kind,cls,count", [("box", BoxDialog, 3), ("cylinder", CylinderDialog, 2), ("sphere", SphereDialog, 1)])
def test_one_handle_per_dimension(app, kind, cls, count):
    d = cls()
    specs = PrimitiveHandles(SimpleNamespace(), d, kind).specs()
    assert len(specs) == count
    assert len({id(field) for field, *_ in specs}) == count
    d.close()


@pytest.mark.parametrize("decimals,expected", [(0, 51), (1, 51.3), (2, 51.26)])
def test_drag_precision_setting(app, decimals, expected):
    from omacad.ui.settings import get_settings
    get_settings().set("primitive_drag_decimals", decimals)
    d = BoxDialog()
    vp = SimpleNamespace(plane_pick_mode=None, preview_mesh=None, setCursor=lambda *_: None, update=lambda: None,
                         world_to_screen=lambda p: (200 + 3*p[0] - 2*p[1], 200 + p[0] + p[1] - 3*p[2]))
    handles = PrimitiveHandles(vp, d, "box")
    field, tip, tangent, _ = handles.geometry()[0]
    assert handles.press(*tip)
    handles.move(*(tip+tangent*1.256))
    assert field.value() == pytest.approx(expected)
    handles.cancel_drag()
    assert field.value() == 50
    d.close()
