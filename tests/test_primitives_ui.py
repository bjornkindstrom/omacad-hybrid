"""UI tests for Primitives: dialogs, drag handles, shelled controls, taper validation, and ribbon integration."""
import math
from types import SimpleNamespace
import numpy as np
import pytest
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu, QToolButton
from PySide6.QtTest import QTest

from omacad.model import quality
from omacad.ui.dialogs import BoxDialog, CylinderDialog, SphereDialog, PrismDialog
from omacad.ui.main_window import MainWindow
from omacad.ui.numeric_slider import NumericSlider
from omacad.ui.primitive_handles import PrimitiveHandles
from omacad.ui.settings import get_settings


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


# =========================================================================
# 1. Direct handle dragging & viewport interaction
# =========================================================================

@pytest.mark.parametrize("kind,cls", [("box", BoxDialog), ("cylinder", CylinderDialog), ("sphere", SphereDialog)])
def test_drag_fields_and_clamp(app, kind, cls):
    d = cls()
    vp = SimpleNamespace(plane_pick_mode=None, preview_mesh=None, setCursor=lambda *_: None, update=lambda: None,
                         world_to_screen=lambda p: (200 + 3 * p[0] - 2 * p[1], 200 + p[0] + p[1] - 3 * p[2]))
    handles = PrimitiveHandles(vp, d, kind)
    for index in range(len(handles.geometry())):
        field, tip, tangent, _ = handles.geometry()[index]
        old = field.value()
        assert handles.press(*tip)
        handles.move(*(tip + tangent * 10))
        assert field.value() == pytest.approx(old + 10)
        assert handles.release()
    field, tip, tangent, _ = handles.geometry()[0]
    assert handles.press(*tip)
    handles.move(*(tip - tangent * 100000))
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
    origin = np.array([0.0, 0.0, 100.0])
    direction = np.array([0.0, 0.0, -1.0])
    vp = SimpleNamespace(
        plane_pick_mode=False,
        preview_mesh=SimpleNamespace(vertices=[1]),
        get_matrices=lambda: (np.eye(4), np.eye(4), None),
        width=lambda: 100,
        height=lambda: 100,
        setCursor=lambda *_: None,
        world_to_screen=lambda p: (0.0, 0.0),
        update=lambda: None,
    )
    h = PrimitiveHandles(vp, d, "box")
    h._ray = lambda *_: (origin, direction)
    h._preview_hit = lambda *_: (np.array([1.0, 2.0, 3.0]), direction)
    h.hit = lambda *_: None
    assert h.press(10, 10)
    h._ray = lambda *_: (np.array([5.0, 8.0, 100.0]), direction)
    h.move(20, 20)
    assert d.placement_offset == pytest.approx([4.0, 6.0, 0.0])
    h.release()
    d.close()


def _mouse_event(vp, kind, point, button, buttons):
    e = QMouseEvent(kind, QPointF(*point), QPointF(*point), button, buttons, Qt.KeyboardModifier.NoModifier)
    {QEvent.Type.MouseButtonPress: vp.mousePressEvent,
     QEvent.Type.MouseMove: vp.mouseMoveEvent,
     QEvent.Type.MouseButtonRelease: vp.mouseReleaseEvent}[kind](e)


@pytest.mark.parametrize("kind", ["box", "cylinder", "sphere"])
def test_create_preview_drag_accept_undo_and_cancel(app, kind):
    w = MainWindow()
    vp = w.viewport
    vp.resize(1000, 800)
    getattr(w, "prompt_" + kind)()
    h = vp.primitive_handles
    assert h is not None
    field, tip, tangent, _ = h.geometry()[0]
    initial = field.value()
    _mouse_event(vp, QEvent.Type.MouseButtonPress, tip, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    _mouse_event(vp, QEvent.Type.MouseMove, tip + tangent * 10, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    wanted = (initial + 10) * (1 if kind == "box" else 2)
    span = lambda: vp.preview_mesh.bounds_max[0] - vp.preview_mesh.bounds_min[0]
    for _ in range(500):
        if abs(span() - wanted) <= 0.01:
            break
        QTest.qWait(10)
    assert span() == pytest.approx(wanted, abs=0.01)
    _mouse_event(vp, QEvent.Type.MouseButtonRelease, tip + tangent * 10, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    assert field.value() == pytest.approx(initial + 10)
    assert not w.doc.bodies
    h.dialog.accept()
    assert vp.primitive_handles is None
    assert len(w.doc.bodies) == 1
    feat = w.doc.timeline.features[-1]
    if kind == "box":
        assert next(iter(w.doc.bodies.values())).manifold.volume() == pytest.approx(60 * 50 * 25)
    else:
        assert feat.radius == pytest.approx(initial + 10)
    w.doc.undo()
    assert not w.doc.bodies
    getattr(w, "prompt_" + kind)()
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
                         world_to_screen=lambda p: (200 + 3 * p[0] - 2 * p[1], 200 + p[0] + p[1] - 3 * p[2]))
    handles = PrimitiveHandles(vp, d, "box")
    field, tip, tangent, _ = handles.geometry()[0]
    assert handles.press(*tip)
    handles.move(*(tip + tangent * 10))
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
    get_settings().set("primitive_drag_decimals", decimals)
    d = BoxDialog()
    vp = SimpleNamespace(plane_pick_mode=None, preview_mesh=None, setCursor=lambda *_: None, update=lambda: None,
                         world_to_screen=lambda p: (200 + 3 * p[0] - 2 * p[1], 200 + p[0] + p[1] - 3 * p[2]))
    handles = PrimitiveHandles(vp, d, "box")
    field, tip, tangent, _ = handles.geometry()[0]
    assert handles.press(*tip)
    handles.move(*(tip + tangent * 1.256))
    assert field.value() == pytest.approx(expected)
    handles.cancel_drag()
    assert field.value() == 50
    d.close()


# =========================================================================
# 2. Shelled primitives & Ribbon layout
# =========================================================================

@pytest.mark.parametrize("kind", ["box", "cylinder"])
def test_shell_wall_in_the_panel_volume_and_undo(app, kind):
    w = MainWindow()
    getattr(w, "prompt_" + kind)()
    dlg = w.viewport.primitive_handles.dialog
    assert dlg.spn_wall.value() == 0
    assert w.viewport.preview_mesh is not None
    assert not w.doc.bodies
    dlg.spn_wall.setValue(4)
    dlg.accept()
    feat = w.doc.timeline.features[-1]
    assert feat.wall_thickness == 4
    body = next(iter(w.doc.bodies.values()))
    if kind == "box":
        expected = 50 * 50 * 25 - 42 * 42 * 21
    else:
        n = quality.circle_segments()
        expected = n / 2 * math.sin(2 * math.pi / n) * (20**2 * 40 - 16**2 * 36)
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    w.doc.undo()
    assert not w.doc.bodies
    w.doc.redo()
    assert next(iter(w.doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    w.close()


@pytest.mark.parametrize("grouped", [True, False])
def test_no_separate_shelled_commands_in_either_ribbon_layout(app, grouped):
    get_settings().set("group_primitives", grouped)
    w = MainWindow()
    texts = [a.text() for m in w.ribbon.findChildren(QMenu) for a in m.actions()]
    texts += [b.text() for b in w.ribbon.findChildren(QToolButton)]
    assert "Prism" in texts
    assert not [t for t in texts if t.startswith("Shelled")]
    w.close()


# =========================================================================
# 3. Dialog Taper validation & Prism dialog / command
# =========================================================================

@pytest.mark.parametrize("kind", ["box", "cylinder"])
def test_dialog_taper_slider_validation_and_edit(kind):
    w = MainWindow()
    getattr(w, "prompt_" + kind)()
    dlg = w.viewport.primitive_handles.dialog
    assert isinstance(dlg.spn_taper.parentWidget(), NumericSlider)
    dlg.spn_taper.setValue(85)
    dlg.accept()
    assert not w.doc.bodies
    assert dlg.lbl_problem.text()
    dlg.spn_taper.setValue(10)
    dlg.accept()
    assert w.doc.timeline.features[-1].taper_angle == 10
    assert w.doc.edit_feature(0, taper_angle=-5)
    assert w.doc.timeline.features[0].taper_angle == -5
    w.doc.undo()
    assert w.doc.timeline.features[0].taper_angle == 10
    w.close()


def test_dialog_reports_across_flats_and_sides(app):
    dlg = PrismDialog()
    dlg.spn_radius.setValue(24.0)
    dlg.spn_sides.setValue(5)
    assert dlg.get_values()[:2] == (24.0, 40.0) and dlg.sides() == 5
    assert dlg.form.labelForField(dlg.spn_radius).text() == "Across flats:"
    dlg.close()


@pytest.mark.parametrize("grouped", [True, False])
def test_hexagon_command_previews_creates_and_undoes(grouped):
    get_settings().set("group_primitives", grouped)
    w = MainWindow()
    if grouped:
        menu = next(m for m in w.ribbon.findChildren(QMenu) if any(a.text() == "Prism" for a in m.actions()))
        next(a for a in menu.actions() if a.text() == "Prism").trigger()
    else:
        next(b for b in w.ribbon.findChildren(QToolButton) if b.text() == "Prism").click()
    handles = w.viewport.primitive_handles
    dlg = handles.dialog
    assert handles.kind == "prism" and dlg.windowTitle() == "Create Prism"
    assert w.viewport.preview_mesh is not None and not w.doc.bodies
    assert [label for *_, label in handles.specs()] == ["Across flats", "Height"]
    dlg.spn_wall.setValue(2.0)
    dlg.accept()
    body = next(iter(w.doc.bodies.values()))
    assert body.name == "Hexagon 1"
    def _prism_area(apothem, sides=6):
        return sides * apothem**2 * math.tan(math.pi / sides)
    assert body.manifold.volume() == pytest.approx(_prism_area(10) * 40 - _prism_area(8) * 38, rel=1e-9)
    w.doc.undo()
    assert not w.doc.bodies
    w.close()


def test_cone_panel_makes_a_pointed_cone(app):
    from omacad.ui.dialogs.primitives_dlg import ConeDialog
    w = MainWindow()
    w.prompt_cone()
    QApplication.processEvents()
    d = w.findChildren(ConeDialog)[-1]
    d.spn_radius.setValue(10.0)
    d.spn_height.setValue(30.0)
    d.spn_top.setValue(0.0)
    d.accept()
    QApplication.processEvents()
    feat = w.doc.timeline.features[-1]
    assert feat.feature_type == "cone"
    vol = next(iter(w.doc.bodies.values())).manifold.volume()
    assert abs(vol - math.pi * 100 * 30 / 3) < 0.01 * math.pi * 1000
    w.close()


@pytest.mark.parametrize("grouped", [True, False])
def test_sphere_in_primitives_ribbon_triggers_dialog(app, grouped):
    get_settings().set("group_primitives", grouped)
    w = MainWindow()
    if grouped:
        menu = next(m for m in w.ribbon.findChildren(QMenu) if any(a.text() == "Sphere" for a in m.actions()))
        next(a for a in menu.actions() if a.text() == "Sphere").trigger()
    else:
        next(b for b in w.ribbon.findChildren(QToolButton) if b.text() == "Sphere").click()
    handles = w.viewport.primitive_handles
    assert handles is not None and handles.kind == "sphere"
    assert handles.dialog.windowTitle() == "Create Sphere"
    handles.dialog.reject()
    w.close()


def test_sphere_panel_placement_shell_wall_and_edit(app):
    from omacad.io.exporter import Exporter
    from omacad.model.document import Document
    from omacad.model.kernel import CadKernel

    w = MainWindow()
    w.prompt_sphere()
    dlg = w.viewport.primitive_handles.dialog
    dlg.spn_radius.setValue(20.0)
    dlg.cmb_placement.setCurrentIndex(dlg.cmb_placement.findData("bottom_center"))
    dlg.spn_wall.setValue(25.0)
    dlg.accept()
    assert not w.doc.bodies
    assert dlg.lbl_problem.text()

    dlg.spn_wall.setValue(2.0)
    dlg.accept()
    body = next(iter(w.doc.bodies.values()))
    expected = (CadKernel.create_sphere(20.0) - CadKernel.create_sphere(18.0)).volume()
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    assert body.manifold.bounding_box()[2] == pytest.approx(0.0, abs=1e-4)
    assert body.manifold.bounding_box()[5] == pytest.approx(40.0, abs=1e-4)

    assert w.doc.edit_feature(0, wall_thickness=3.0)
    expected_edited = (CadKernel.create_sphere(20.0) - CadKernel.create_sphere(17.0)).volume()
    assert next(iter(w.doc.bodies.values())).manifold.volume() == pytest.approx(expected_edited, rel=1e-6)

    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(w.doc))
    assert next(iter(loaded.bodies.values())).manifold.volume() == pytest.approx(expected_edited, rel=1e-6)
    w.close()
