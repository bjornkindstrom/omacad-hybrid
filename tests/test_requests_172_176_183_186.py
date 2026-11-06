"""Lennart's requests: construction geometry (#183, #185, #186), deleted objects in the browser (#176), the clearance
step (#172) and textures on a shelled body with half-round ends (#184)."""
import manifold3d as m3d
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.model.features.honeycomb import HoneycombFeature
from omacad.model.features.japandi import JapandiFeature, apply_japandi
from omacad.model.features.knurl import apply_knurl
from omacad.ui.dialogs.surface_texture_dlg import outer_round
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    w = MainWindow()
    w.confirm_discard_changes = lambda: True
    yield w
    w.close()


def _press_x(win):
    win.viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier))


def _rows(win):
    win.browser.refresh_tree()
    return [item.text(0) for item, _ in win.browser._walk()]


@pytest.mark.parametrize("press", [_press_x, lambda win: win.ribbon.command_buttons["construction"].click()])
def test_selected_circle_switches_between_construction_and_normal(win, press):
    sketch = win.doc.start_sketch("XY")
    circle = sketch.add_circle((0, 0), 10, is_construction=True)
    win.doc.notify_changed()
    assert sketch.profiles == []
    win.viewport.selected_entities = {circle.entity_id}

    press(win)
    assert circle.is_construction is False and len(sketch.profiles) == 1
    assert not win.viewport.construction_mode and not win.ribbon.btn_construct.isChecked()

    press(win)
    assert circle.is_construction is True and sketch.profiles == []
    assert not win.viewport.construction_mode and not win.ribbon.btn_construct.isChecked()

    win.doc.undo()
    assert win.doc.active_sketch.entities[0].is_construction is False


def test_x_with_nothing_selected_still_toggles_the_mode(win):
    win.doc.start_sketch("XY")
    _press_x(win)
    assert win.viewport.construction_mode and win.ribbon.btn_construct.isChecked()
    win.ribbon.command_buttons["construction"].click()
    assert not win.viewport.construction_mode and not win.ribbon.btn_construct.isChecked()


def test_polygon_centre_circle_stays_construction(win):
    sketch = win.doc.start_sketch("XY")
    sketch.add_polygon((0, 0), (10, 0), 6)
    win.viewport.selected_entities = {e.entity_id for e in sketch.entities}
    _press_x(win)
    lines = [e for e in sketch.entities if e.entity_type == "line"]
    centre = next(e for e in sketch.entities if e.entity_type == "circle")
    assert all(e.is_construction for e in lines) and centre.is_construction
    _press_x(win)
    assert not any(e.is_construction for e in lines) and centre.is_construction


def test_ordinary_tool_after_construction_menu_draws_normally(win):
    win.doc.start_sketch("XY")
    win.start_construction_tool("CIRCLE")
    assert win.viewport.construction_mode and win.ribbon.btn_construct.isChecked()
    win.start_construction_tool("LINE")                     # the menu again: still construction
    assert win.viewport.construction_mode

    win.ribbon.command_buttons["circle"].click()
    assert not win.viewport.construction_mode and not win.ribbon.btn_construct.isChecked()
    assert win.viewport.sketch_tool == "CIRCLE"


def test_shortcut_after_construction_menu_draws_normally(win):
    win.doc.start_sketch("XY")
    win.start_construction_tool("LINE")
    win.viewport.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier))
    assert not win.viewport.construction_mode


def test_the_button_keeps_construction_on_through_tool_changes(win):
    win.doc.start_sketch("XY")
    win.ribbon.command_buttons["construction"].click()
    win.ribbon.command_buttons["circle"].click()
    assert win.viewport.construction_mode and win.ribbon.btn_construct.isChecked()


def test_new_design_starts_without_construction(win):
    win.doc.start_sketch("XY")
    win.start_construction_tool("LINE")
    win.on_file_new()
    assert not win.viewport.construction_mode and not win.ribbon.btn_construct.isChecked()

    win.doc.start_sketch("XY")                              # and the new document resets it too
    win.viewport.toggle_construction_mode()
    win.doc.finish_sketch()
    assert not win.viewport.construction_mode


def test_deleted_object_leaves_the_browser_until_undo(win):
    win.doc.add_box(10, 10, 10)
    kept = next(iter(win.doc.bodies))
    win.doc.add_box(20, 20, 20)
    gone = next(b for b in win.doc.bodies if b != kept)
    name = win.doc.bodies[gone].name
    assert any(name in row for row in _rows(win))

    win.doc.delete_body(gone)
    rows = _rows(win)
    assert not any("Delete" in row for row in rows)
    assert win.doc.bodies[kept].name in " ".join(rows)

    win.doc.undo()
    assert any(name in row for row in _rows(win))


def test_deleted_object_that_used_up_another_leaves_the_browser(win):
    win.doc.add_box(20, 20, 20)
    win.doc.add_box(10, 10, 30)
    first, second = list(win.doc.bodies)
    names = win.doc.bodies[first].name, win.doc.bodies[second].name
    win.doc.combine_bodies(first, second, "join")
    assert len(win.doc.bodies) == 1
    win.doc.delete_body(next(iter(win.doc.bodies)))
    rows = _rows(win)
    assert not any(name in row for row in rows for name in names)


def test_rolling_back_before_the_delete_shows_the_object(win):
    win.doc.add_box(20, 20, 20)
    body = next(iter(win.doc.bodies))
    name = win.doc.bodies[body].name
    win.doc.delete_body(body)
    assert not any(name in row for row in _rows(win))

    win.doc.toggle_suppress(len(win.doc.timeline.features) - 1)
    assert any(name in row for row in _rows(win))


def test_clearance_steps_in_tenths(win):
    from omacad.ui.dialogs.primitives_dlg import BoxInRowDialog
    spin = BoxInRowDialog().spn_clearance
    spin.stepUp()
    assert spin.value() == pytest.approx(0.3)
    spin.stepUp()
    assert spin.value() == pytest.approx(0.4)


def _stadium(margin=0.0):
    end = m3d.Manifold.cylinder(16.5, 15.0 - margin, 15.0 - margin, 96)
    return m3d.Manifold.batch_hull([end, end.translate((40.0, 0.0, 0.0))])


def test_textures_on_half_round_end_of_a_shelled_body():
    body = _stadium() - _stadium(1.5).translate((0.0, 0.0, 1.5))
    ref = {"kind": "surface", "point": [-15.0, 0.0, 8.0], "normal": [-1.0, 0.0, 0.0]}
    assert outer_round(ref)
    cells = dict(size=6.0, wall=1.5, margin=1.5, depth=1.0, through=True, angle=0.0, partial=False, randomness=100.0,
                 seed=1, style="even", fine_size=2.0, inner_wall=0.8, hotspots=1, rounding=0.0, opening=100.0,
                 opening_end=100.0, relaxation=0, hole="cell")
    for shape in ("hexagon", "voronoi"):
        result, count, _ = HoneycombFeature.compute(body, [ref], dict(cells, shape=shape))
        assert count > 5 and result.volume() < body.volume()

    knurled, teeth, notes = apply_knurl(body, [ref], dict(pattern="diamond", pitch=1.5, depth=0.6, angle=30.0, margin=0.0))
    assert teeth > 0 and not notes and knurled.volume() < body.volume()

    ribbed, ribs, notes = apply_japandi(body, [ref], _japandi_defaults())
    assert ribs > 0 and not notes and ribbed.volume() != body.volume()


def _japandi_defaults():
    import inspect
    signature = inspect.signature(JapandiFeature.__init__)
    return {name: signature.parameters[name].default for name in JapandiFeature.PARAMS}
