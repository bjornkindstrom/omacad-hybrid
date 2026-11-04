"""Wavy Slices: layer heights, wave size and alignment against exact values, plus undo, edit, save and reload."""

import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
import manifold3d as m3d
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.wavy_slices import MAX_LAYERS, layer_bounds, slice_body, wave_ring


def circle(radius, count=720):
    a = np.arange(count) * 2 * math.pi / count
    return np.column_stack((radius * np.cos(a), radius * np.sin(a)))


def box_doc(x=40.0, y=40.0, z=20.0):
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(x, y, z)
    return doc, next(iter(doc.bodies))


def radii(solid, z):
    points = np.vstack([np.asarray(r) for r in solid.slice(z).to_polygons()])
    return np.hypot(points[:, 0], points[:, 1])


def test_layers_keep_the_exact_height_of_the_body():
    assert layer_bounds(0.0, 10.0, 2.0) == [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 8.0), (8.0, 10.0)]
    assert layer_bounds(0.0, 5.0, 2.0)[-1] == (4.0, 5.0)        # a shorter top layer
    assert layer_bounds(0.0, 6.1, 2.0)[-1] == (4.0, 6.1)        # a sliver joins the layer below
    assert layer_bounds(0.0, 1.0, 5.0) == [(0.0, 1.0)]


def test_too_many_layers_and_a_bad_height_are_refused():
    with pytest.raises(ValueError, match="too many"):
        layer_bounds(0.0, MAX_LAYERS + 1.0, 1.0)
    with pytest.raises(ValueError, match="above zero"):
        layer_bounds(0.0, 1.0, 0.0)


def test_amplitude_is_peak_to_peak_and_gives_the_requested_number_of_waves():
    ring = wave_ring(circle(20.0), 8, 3.0, 0.0)
    r = np.hypot(ring[:, 0], ring[:, 1])
    assert r.max() == pytest.approx(21.5, abs=0.01)
    assert r.min() == pytest.approx(18.5, abs=0.01)
    peaks = (r > np.roll(r, 1)) & (r >= np.roll(r, -1))
    assert np.count_nonzero(peaks) == 8


def test_zero_amplitude_keeps_sharp_corners_exactly():
    doc, bid = box_doc(40.0, 30.0, 20.0)
    source = doc.bodies[bid].manifold
    solid = slice_body(source, 12, 3.0, 0.0)
    assert solid.volume() == pytest.approx(40.0 * 30.0 * 20.0, rel=1e-9)
    assert solid.bounding_box() == pytest.approx(source.bounding_box())


def test_waves_line_up_up_the_stack_wherever_the_outline_starts():
    """The slice returns rings from any start vertex; the wave must not depend on it."""
    ring = circle(20.0)
    a = wave_ring(ring, 6, 2.0, 0.0)
    b = wave_ring(np.roll(ring, 137, axis=0), 6, 2.0, 0.0)
    a, b = a[np.lexsort(a.T)], b[np.lexsort(b.T)]
    assert a == pytest.approx(b, abs=1e-6)


def test_phase_shift_moves_the_wave_by_that_angle_per_layer():
    cylinder = m3d.Manifold.cylinder(20.0, 20.0, 20.0, 720)
    solid = slice_body(cylinder, 6, 5.0, 4.0, 90.0)     # the seam reads sin(0), sin(90), sin(180), sin(270) up the stack

    def edge_at_seam(z):
        """Where the outline crosses the +X ray from the centre: the wave's value at the seam."""
        points = np.vstack([np.asarray(r) for r in solid.slice(z).to_polygons()])
        points = points[points[:, 0] > 0]
        return points[np.argmin(np.abs(points[:, 1])), 0]

    assert [edge_at_seam(z) for z in (2.5, 7.5, 12.5, 17.5)] == pytest.approx([20.0, 22.0, 20.0, 18.0], abs=0.02)


def test_volume_is_kept_by_a_symmetric_wave_on_a_cylinder():
    """Averaged round the ring a sine adds and removes the same area; the second-order term is π·(a/2)²/2."""
    cylinder = m3d.Manifold.cylinder(20.0, 20.0, 20.0, 720)
    solid = slice_body(cylinder, 10, 2.0, 2.0, 15.0)
    expected = (cylinder.slice(1.0).area() + math.pi * 1.0 ** 2 / 2.0) * 20.0
    assert solid.volume() == pytest.approx(expected, rel=2e-3)
    assert solid.status() == m3d.Error.NoError
    assert len(solid.decompose()) == 1


def test_offset_moves_the_outline_out_and_in():
    cylinder = m3d.Manifold.cylinder(10.0, 20.0, 20.0, 720)
    assert radii(slice_body(cylinder, 8, 2.0, 0.0, 0.0, 1.5), 5.0).max() == pytest.approx(21.5, abs=0.02)
    assert radii(slice_body(cylinder, 8, 2.0, 0.0, 0.0, -1.5), 5.0).max() == pytest.approx(18.5, abs=0.02)


def test_an_inward_offset_that_eats_the_body_is_refused_and_adds_no_step():
    doc, bid = box_doc(10.0, 10.0, 10.0)
    steps, volume = len(doc.timeline.features), doc.bodies[bid].manifold.volume()
    with pytest.raises(ValueError, match="Nothing is left"):
        doc.add_wavy_slices(bid, offset=-6.0)
    assert len(doc.timeline.features) == steps
    assert doc.bodies[bid].manifold.volume() == pytest.approx(volume)


def test_a_hollow_body_keeps_its_hole_and_an_even_wall():
    outer = m3d.Manifold.cylinder(20.0, 25.0, 25.0, 720)
    hollow = outer - m3d.Manifold.cylinder(40.0, 20.0, 20.0, 720).translate((0.0, 0.0, -10.0))
    solid = slice_body(hollow, 10, 2.0, 2.0, 0.0)
    assert solid.slice(5.0).num_contour() == 2
    rings = sorted((np.asarray(r) for r in solid.slice(5.0).to_polygons()), key=lambda r: -abs(r[:, 0]).max())
    out_r, in_r = np.hypot(*rings[0].T), np.hypot(*rings[1].T)
    assert out_r.max() - in_r.max() == pytest.approx(5.0, abs=0.05)
    assert out_r.min() - in_r.min() == pytest.approx(5.0, abs=0.05)
    assert solid.volume() == pytest.approx(hollow.volume(), rel=5e-3)


def test_undo_edit_and_save_reload_rebuild_the_same_body():
    doc, bid = box_doc()
    before = doc.bodies[bid].manifold.volume()
    feat = doc.add_wavy_slices(bid, waves=8, slice_height=4.0, amplitude=1.5, phase_shift=30.0, offset=0.5)
    made = doc.bodies[bid].manifold.volume()
    assert made != pytest.approx(before)

    data = Exporter.document_to_dict(doc)
    copy = Document()
    Exporter.apply_dict(copy, data)
    copy.timeline.recompute(copy)
    again = next(f for f in copy.timeline.features if f.feature_type == "wavy_slices")
    assert (again.waves, again.slice_height, again.amplitude, again.phase_shift, again.offset) == (8, 4.0, 1.5, 30.0, 0.5)
    assert copy.bodies[bid].manifold.volume() == pytest.approx(made)

    assert doc.edit_feature(doc.timeline.features.index(feat), amplitude=0.0, offset=0.0)
    assert doc.bodies[bid].manifold.volume() == pytest.approx(before, rel=1e-9)

    doc.undo()      # the edit
    assert doc.bodies[bid].manifold.volume() == pytest.approx(made)
    doc.undo()      # the step
    assert not [f for f in doc.timeline.features if f.feature_type == "wavy_slices"]
    assert doc.bodies[bid].manifold.volume() == pytest.approx(before)


def test_panel_opens_and_reads_its_values():
    from omacad.ui.dialogs import SurfaceTextureDialog
    doc, bid = box_doc()
    dlg = SurfaceTextureDialog(doc, kind="wavy_slices", body_id=bid)
    assert dlg.target_body_id() == bid
    dlg.page.spins["waves"].setValue(7)
    dlg.page.spins["slice_height"].setValue(1.5)
    assert dlg.params() == {"waves": 7, "slice_height": 1.5, "amplitude": 2.0, "phase_shift": 15.0, "offset": 0.0}
    feat = doc.add_wavy_slices(bid, waves=5, amplitude=1.0)
    dlg.page.load(feat)
    assert dlg.params()["waves"] == 5 and dlg.params()["amplitude"] == 1.0


def test_the_real_tool_previews_in_the_bodys_place_and_ok_makes_one_undoable_step():
    from omacad.ui.dialogs import SurfaceTextureDialog
    from omacad.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    body = win.doc.add_box(40.0, 40.0, 20.0)
    volume = body.manifold.volume()

    win.browser.surface_texture_requested.emit(body.body_id)
    dlg = next(w for w in app.allWidgets() if isinstance(w, SurfaceTextureDialog) and w.window() is win)
    assert win.viewport.preview_mesh is not None and not win.doc.bodies[body.body_id].visible

    dlg.page.spins["offset"].setValue(-30.0)     # nothing is left: the tool says so instead of failing
    dlg.changed.emit()
    QTest.qWait(150)
    assert "Nothing is left" in dlg.lbl_info.text()
    dlg.page.spins["offset"].setValue(0.0)
    dlg.accept()
    app.processEvents()

    assert win.viewport.preview_mesh is None and win.doc.bodies[body.body_id].visible
    assert [f.feature_type for f in win.doc.timeline.features][-1] == "wavy_slices"
    assert win.doc.bodies[body.body_id].manifold.volume() != pytest.approx(volume)
    win.doc.undo()
    assert win.doc.bodies[body.body_id].manifold.volume() == pytest.approx(volume)
    win.close()
