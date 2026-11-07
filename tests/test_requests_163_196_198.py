"""Corner sketch copies and direct viewport controls for Shell and Push / Pull."""
import numpy as np
import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.offset_face import plane_face_ref
from omacad.model.sketch import SketchCircle
from omacad.model.sketch_pattern import corner_bounds, corner_copies
from omacad.ui import feature_edit
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def win():
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    yield window
    if window.inspector.current_tool_dlg is not None:
        window.inspector.current_tool_dlg.reject()
    window.close()
    window.deleteLater()
    _app.processEvents()


def viewport_editor(vp, source):
    editors = [e for e in vp.findChildren(ExprDoubleSpinBox) if getattr(e, "source_field", None) is source]
    assert len(editors) == 1
    return editors[0]


@pytest.mark.parametrize("accept", [True, False])
def test_sketch_all_corners_preserves_inset_and_one_undo(win, accept, tmp_path):
    doc, vp = win.doc, win.viewport
    sk = doc.start_sketch("XY")
    sk.add_rect((-90., -50.), (90., 50.))
    circle = sk.add_circle((-85., 45.), 2.5)
    vp.selected_entities = {circle.entity_id}
    before_undo = len(doc.undo_stack)
    vp.set_sketch_tool("PATTERN")
    panel = vp.pattern_panel
    panel.kind.setCurrentIndex(panel.kind.findData("corners"))
    assert not any(label.isVisible() and label.text() in ("Count X", "Spacing X", "Count Y", "Spacing Y")
                   for label in panel.findChildren(QLabel))
    expected = [(-85., -45.), (-85., 45.), (85., -45.), (85., 45.)]
    assert sorted(tuple(e.center) for e in sk.entities if isinstance(e, SketchCircle)) == expected
    assert len({e.entity_id for e in sk.entities}) == len(sk.entities)
    # Preview changes do not accumulate additional copies.
    vp._pattern_preview()
    assert len([e for e in sk.entities if isinstance(e, SketchCircle)]) == 4
    (panel.ok if accept else panel.cancel).click()
    if accept:
        assert len(doc.undo_stack) == before_undo + 1
        doc.undo()
        assert len([e for e in doc.active_sketch.entities if isinstance(e, SketchCircle)]) == 1
        doc.redo()
        assert len([e for e in doc.active_sketch.entities if isinstance(e, SketchCircle)]) == 4
        doc.finish_sketch()
        path = tmp_path / "corners.omacad"
        Exporter.save_project(doc, str(path))
        loaded = Exporter.load_project(str(path))
        restored = next(iter(loaded.sketches.values()))
        assert sorted(tuple(e.center) for e in restored.entities if isinstance(e, SketchCircle)) == expected
    else:
        assert len(doc.undo_stack) == before_undo
        assert len([e for e in sk.entities if isinstance(e, SketchCircle)]) == 1


def test_corners_require_a_surrounding_outline_and_do_not_duplicate_centre():
    doc = Document()
    sk = doc.start_sketch("XY")
    circle = sk.add_circle((0., 0.), 1.)
    assert corner_bounds(sk, [circle]) is None
    sk.add_rect((-10., -5.), (10., 5.))
    bounds = corner_bounds(sk, [circle])
    assert bounds == (-10., -5., 10., 5.)
    assert not corner_copies(sk, [circle], bounds)


def test_shell_viewport_fields_sync_both_directions_and_cancel(win):
    body = win.doc.add_box(50., 50., 25.)
    win.prompt_shell(body.body_id)
    dlg = win.inspector.current_tool_dlg
    QTest.qWait(100)
    inside = viewport_editor(win.viewport, dlg.spn_thickness)
    outside = viewport_editor(win.viewport, dlg.spn_thickness2)
    assert inside.isVisible() and not outside.isVisible()
    inside.set_expression("1+2")
    assert dlg.spn_thickness.value() == 3.
    assert dlg.spn_thickness.expression() == "1+2"
    dlg.spn_thickness.setValue(4.)
    assert inside.value() == 4.
    dlg.cmb_dir.setCurrentIndex(dlg.DIRS.index("both"))
    QTest.qWait(100)
    assert outside.isVisible()
    outside.setValue(1.)
    assert dlg.spn_thickness2.value() == 1.
    host = inside.parentWidget()
    assert win.viewport.rect().contains(host.geometry())
    dlg.reject()
    assert not host.isVisible()
    assert not win.viewport.extrude_handle
    assert win.doc.bodies[body.body_id].manifold.volume() == pytest.approx(62500.)


def test_shell_edit_has_thickness_by_apply_button(win):
    body = win.doc.add_box(30., 30., 20.)
    win.doc.add_shell(body.body_id, 2., [])
    seen = []

    def finish():
        dlg = win.inspector.current_tool_dlg
        editor = viewport_editor(win.viewport, dlg.spn_thickness)
        seen.append(editor.value())
        editor.setValue(3.)
        dlg.accept()

    QTimer.singleShot(150, finish)
    assert feature_edit.edit_feature(win, win.doc, 1)
    assert seen == [2.]
    assert win.doc.timeline.features[1].thickness == 3.


@pytest.mark.parametrize("accept", [True, False])
def test_shell_viewport_keyboard_applies_or_cancels(win, accept):
    body = win.doc.add_box(30., 30., 20.)
    win.prompt_shell(body.body_id)
    dlg = win.inspector.current_tool_dlg
    QTest.qWait(100)
    editor = viewport_editor(win.viewport, dlg.spn_thickness)
    editor.setValue(3.)
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_Return if accept else Qt.Key.Key_Escape)
    _app.processEvents()
    assert win.inspector.current_tool_dlg is None
    assert win.doc.timeline.features[-1].feature_type == ("shell" if accept else "box")
    if accept:
        assert win.doc.timeline.features[-1].thickness == 3.


@pytest.mark.parametrize("distance", [-2., 3.])
def test_push_pull_drag_changes_face_and_undo_restores_body(win, distance, tmp_path):
    doc, vp = win.doc, win.viewport
    body = doc.add_box(20., 10., 5.)
    face = max(body.faces, key=lambda f: f.normal[2])
    win.prompt_offset_face(face)
    dlg = win.inspector.current_tool_dlg
    assert vp.extrude_handle is not None
    assert vp.extrude_handle["axis"] == pytest.approx([0., 0., 1.])
    vp.extrude_handle_dragged.emit(distance)
    assert dlg.distance() == distance
    assert vp.extrude_handle["dist"] == distance
    dlg.spn_dist.setValue(distance / 2)
    assert vp.extrude_handle["dist"] == distance / 2
    vp.extrude_handle_dragged.emit(distance)
    QTest.qWait(100)
    editor = viewport_editor(vp, dlg.spn_dist)
    assert editor.value() == distance
    dlg.accept()
    assert not vp.extrude_handle and not vp.plane_pick_mode
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(20 * 10 * (5 + distance))
    path = tmp_path / "push_pull.omacad"
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    assert loaded.bodies[body.body_id].manifold.volume() == pytest.approx(20 * 10 * (5 + distance))
    doc.undo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(1000.)


def test_push_pull_clear_cancel_and_cylinder_normal(win):
    body = win.doc.add_cylinder(10., 15., wall_thickness=2.)
    ref = dict(kind="cylinder", origin=[0., 0., 0.], axis=[0., 0., 1.],
               radius=8., length=15., internal=True, body_id=body.body_id)
    win.prompt_offset_face(ref)
    dlg = win.inspector.current_tool_dlg
    point, normal = dlg.drag_frame(body)
    assert np.dot(point[:2], normal[:2]) < 0  # positive adds material into the bore
    dlg.clear()
    assert not win.viewport.extrude_handle
    dlg.reject()
    assert not win.viewport.extrude_handle and body.visible
