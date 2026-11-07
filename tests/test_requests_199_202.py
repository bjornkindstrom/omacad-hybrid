"""Regression models and actual UI interactions from requests #199–#202."""
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model import quality
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.main_window import MainWindow
from omacad.ui.viewport.picker_mixin import patch_boundary_segments

_app = QApplication.instance() or QApplication([])
FIXTURE = Path(__file__).parent / "data" / "selection_loft_shell.omacad"


@pytest.fixture
def win():
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    yield window
    if window.inspector.current_tool_dlg is not None:
        window.inspector.current_tool_dlg.reject()
    window.viewport.set_sketch_tool("NONE")
    window.close()
    window.deleteLater()
    _app.processEvents()


@pytest.mark.parametrize("python_backend", [False, True])
def test_loft_shell_selection_has_only_the_two_true_rim_boundaries(monkeypatch, python_backend):
    if python_backend:
        from omacad import viewport_accel
        monkeypatch.setattr(viewport_accel, "_NATIVE", None)
    quality.set_fast_view(True, 72)
    body = next(iter(Exporter.load_project(str(FIXTURE)).bodies.values()))
    mesh = body.render_mesh
    triangles = np.asarray(mesh.vertices).reshape(-1, 3, 3)
    centres = triangles.mean(axis=1)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    inside = np.flatnonzero(((centres[:, :2] * normals[:, :2]).sum(axis=1) < -1.) & (np.abs(normals[:, 2]) < .9))
    mesh.curved_surface_with_normals(int(inside[len(inside) // 4]))
    labels, counts = np.unique(mesh._surface_ids[inside], return_counts=True)
    label = max((int(n), int(i)) for i, n in zip(labels, counts) if i >= 0)[1]
    seed = int(np.flatnonzero(mesh._surface_ids == label)[0])
    patch, _ = mesh.curved_surface_with_normals(seed)
    boundary = patch_boundary_segments(patch)
    assert len(boundary) > 100
    assert np.allclose(boundary[:, 0, 2], boundary[:, 1, 2], atol=1e-4)
    assert len(np.unique(np.round(boundary[:, :, 2], 3))) == 2
    drawn, _, lines = mesh.display_patch_arrays(patch, boundary.reshape(-1, 3))
    assert len(drawn) > patch.size // 3
    assert np.all(np.isfinite(drawn))
    # Every smoothed outline point must coincide with the solid's display geometry.
    base = np.ascontiguousarray(np.round(mesh.display_arrays(mesh.sharp_lines)[0], 4))
    outline = np.ascontiguousarray(np.round(lines, 4))
    dtype = np.dtype((np.void, 3 * base.dtype.itemsize))
    assert np.isin(outline.view(dtype).ravel(), base.view(dtype).ravel()).all()
    assert mesh.display_patch_arrays(patch, boundary.reshape(-1, 3))[0] is drawn


def test_suggestions_ignore_hidden_profiles_and_explain_valid_ones(win):
    doc = win.doc
    sk = doc.start_sketch("XY")
    sk.add_rect((0., 0.), (10., 10.))
    doc.finish_sketch()
    doc.selected_profile = (sk.sketch_id, 0)
    win.viewport.profile_picked.emit()
    button = win.ribbon.command_buttons["extrude"]
    assert button.property("suggested")
    assert "Suggested for the current selection" in button.toolTip()
    sk.visible = False
    doc.notify_changed()
    assert win.ribbon.selection_context() == ""
    assert not button.property("suggested")
    assert "Suggested for the current selection" not in button.toolTip()


def test_pattern_ribbon_click_expands_collapsed_settings_and_allows_corners(win):
    doc, vp = win.doc, win.viewport
    sk = doc.start_sketch("XY")
    sk.add_rect((-60., -45.), (60., 45.))
    circle = sk.add_circle((-45., 30.), 5.)
    vp.selected_entities = {circle.entity_id}
    vp.sketch_palette.toggle_collapsed()
    assert vp.sketch_palette.content_widget.isHidden()
    win.ribbon.command_buttons["pattern_sketch"].click()
    QTest.qWait(30)
    assert vp.pattern_panel.isVisible()
    assert vp.sketch_palette.btn_toggle.text() == "▼"
    vp.pattern_panel.kind.setCurrentIndex(vp.pattern_panel.kind.findData("corners"))
    assert len(vp._pattern["copies"]) == 3
    vp.pattern_panel.cancel.click()
    assert len(sk.entities) == 5


def test_shell_arrows_step_by_whole_mm_in_panel_and_viewport(win):
    body = win.doc.add_box(50., 50., 25.)
    win.prompt_shell(body.body_id)
    dlg = win.inspector.current_tool_dlg
    dlg.cmb_dir.setCurrentIndex(dlg.DIRS.index("both"))
    QTest.qWait(80)
    for field in (dlg.spn_thickness, dlg.spn_thickness2):
        overlay = next(e for e in win.viewport.findChildren(ExprDoubleSpinBox)
                       if getattr(e, "source_field", None) is field)
        assert field.singleStep() == overlay.singleStep() == 1.
        field.setValue(2.)
        overlay.stepUp()
        assert field.value() == overlay.value() == 3.
        field.stepDown()
        assert field.value() == overlay.value() == 2.
        overlay.set_expression("2.25")
        assert field.value() == 2.25  # typed precision remains available
