"""Knurl: grooves against exact cross-sections, refused faces, a bore left alone, the model's history and the tool."""
import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import manifold3d as m3d
import numpy as np
import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from shapely import affinity
from shapely.geometry import Point, Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.knurl import apply_knurl, kept_solid, star_outline, tooth_count, twist_degrees

R, H = 15.0, 40.0
PIN = m3d.Manifold.cylinder(H, R, R, 720)
REF = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": R, "length": H, "internal": False}
P = dict(pattern="straight", pitch=1.5, depth=0.6, angle=30.0, margin=0.0)
DISC = Polygon(np.asarray(PIN.slice(H / 2).to_polygons()[0]))


def star(turn=0.0):
    """The star in the world: the face's frame (omacad _frame) puts its local +X, the first crest, on world +Y."""
    return affinity.rotate(Polygon(star_outline(R, 0.6, tooth_count(R, 1.5))), 90.0 + turn, origin=(0, 0))


def section(solid, z):
    return solid.slice(z).area()


def test_teeth_fit_whole_round_the_circumference():
    assert tooth_count(R, 1.5) == 63    # 2π·15 / 1.5 = 62.8
    assert tooth_count(1.0, 50.0) == 3
    outline = star_outline(10.0, 1.0, 8)
    assert len(outline) == 16
    radii = np.hypot(*outline.T)
    assert radii[0::2] == pytest.approx([10.0] * 8) and radii[1::2] == pytest.approx([9.0] * 8)


def test_straight_grooves_cut_exactly_the_star_along_the_whole_face():
    solid, teeth, notes = apply_knurl(PIN, [REF], P)
    assert (teeth, notes) == (63, [])
    area = DISC.intersection(star()).area
    assert section(solid, 20.0) == pytest.approx(area, rel=1e-7)
    assert solid.volume() == pytest.approx(area * H, rel=1e-6)
    bb = solid.bounding_box()
    assert (bb[2], bb[5]) == pytest.approx((0.0, H))    # the height is kept


def test_right_and_left_turn_opposite_ways_by_the_helix_angle():
    z = 20.0 + 1e-3
    twist = twist_degrees(R, H + 2e-3, 30.0)
    turned = twist * (z + 1e-3) / (H + 2e-3)
    for pattern, sign in (("right", 1.0), ("left", -1.0)):
        solid, _, _ = apply_knurl(PIN, [REF], dict(P, pattern=pattern))
        got = Polygon(max((np.asarray(r) for r in solid.slice(z).to_polygons()), key=len))
        want = DISC.intersection(star(sign * turned))
        groove = DISC.area - want.area
    assert got.symmetric_difference(want).area < 0.03 * groove, pattern


def test_twist_follows_the_angle():
    assert twist_degrees(10.0, 10.0, 45.0) == pytest.approx(math.degrees(1.0))


def test_diamond_is_both_directions_at_once():
    solid, teeth, _ = apply_knurl(PIN, [REF], dict(P, pattern="diamond"))
    assert teeth == 63
    z = 20.0
    turned = twist_degrees(R, H + 2e-3, 30.0) * (z + 1e-3) / (H + 2e-3)
    want = DISC.intersection(star(turned)).intersection(star(-turned))
    assert section(solid, z) == pytest.approx(want.area, rel=1e-3)
    single, _, _ = apply_knurl(PIN, [REF], dict(P, pattern="right"))
    assert solid.volume() < single.volume() < PIN.volume()
    assert solid.status() == m3d.Error.NoError
    assert len(solid.decompose()) == 1


def test_margin_leaves_plain_ends():
    solid, _, _ = apply_knurl(PIN, [REF], dict(P, margin=5.0))
    plain, cut = DISC.area, DISC.intersection(star()).area
    assert section(solid, 2.0) == pytest.approx(plain, rel=1e-9)
    assert section(solid, 38.0) == pytest.approx(plain, rel=1e-9)
    assert section(solid, 20.0) == pytest.approx(cut, rel=1e-7)
    assert solid.volume() == pytest.approx(plain * 10.0 + cut * 30.0, rel=1e-6)


def test_a_bore_inside_the_face_is_not_touched():
    bore = m3d.Manifold.cylinder(H + 20.0, 5.0, 5.0, 96).translate((0, 0, -10.0))
    tube = PIN - bore
    solid, _, _ = apply_knurl(tube, [REF], dict(P, pattern="diamond"))
    rings = sorted((np.asarray(r) for r in solid.slice(20.0).to_polygons()), key=len)
    radii = np.hypot(*rings[0].T)                      # a 96-sided bore: corners on 5, chord midpoints on 5·cos(π/96)
    assert radii.max() == pytest.approx(5.0, abs=1e-6)
    assert radii.min() == pytest.approx(5.0 * math.cos(math.pi / 96.0), abs=1e-6)
    assert solid.genus() == tube.genus()


def test_a_step_above_the_face_keeps_its_own_size():
    head = m3d.Manifold.cylinder(10.0, 25.0, 25.0, 720).translate((0, 0, H))
    bolt = PIN + head
    solid, _, _ = apply_knurl(bolt, [REF], P)
    assert section(solid, H + 5.0) == pytest.approx(section(bolt, H + 5.0), rel=1e-6)


@pytest.mark.parametrize("ref, params, why", [
    (dict(REF, internal=True), P, "outer round"),
    ({"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, H]}, P, "outer round"),
    (REF, dict(P, depth=20.0), "doesn't fit"),
    (REF, dict(P, margin=25.0), "no room"),
])
def test_faces_that_cant_take_a_knurl_say_why_and_leave_the_body(ref, params, why):
    solid, teeth, notes = apply_knurl(PIN, [ref], params)
    assert teeth == 0 and why in notes[0]
    assert solid.volume() == pytest.approx(PIN.volume())


def test_a_part_of_a_round_is_refused():
    half = PIN - m3d.Manifold.cube((40.0, 40.0, H + 2.0)).translate((-20.0, 0.0, -1.0))
    solid, teeth, notes = apply_knurl(half, [REF], P)
    assert teeth == 0 and "all the way round" in notes[0]
    assert solid.volume() == pytest.approx(half.volume())


def test_too_fine_a_pitch_is_refused_before_it_takes_minutes():
    with pytest.raises(ValueError, match="too fine"):
        kept_solid(100.0, 300.0, "diamond", 0.1, 0.05, 45.0)


def doc_with_pin():
    QApplication.instance() or QApplication([])
    doc = Document()
    body = doc.add_cylinder(R, H)
    return doc, body.body_id


def test_add_knurl_refuses_without_adding_a_step():
    doc, bid = doc_with_pin()
    steps = len(doc.timeline.features)
    with pytest.raises(ValueError, match="doesn't fit"):
        doc.add_knurl(bid, [REF], pattern="straight", depth=20.0)
    assert len(doc.timeline.features) == steps


def test_save_edit_undo_and_a_taller_cylinder_rebuild_it():
    doc, bid = doc_with_pin()
    before = doc.bodies[bid].manifold.volume()
    feat = doc.add_knurl(bid, [REF], pattern="straight", pitch=2.0, depth=0.5)
    made = doc.bodies[bid].manifold.volume()
    assert feat.teeth == tooth_count(R, 2.0) and made < before

    copy = Document()
    Exporter.apply_dict(copy, Exporter.document_to_dict(doc))
    copy.timeline.recompute(copy)
    again = next(f for f in copy.timeline.features if f.feature_type == "knurl")
    assert (again.pattern, again.pitch, again.depth) == ("straight", 2.0, 0.5)
    assert copy.bodies[bid].manifold.volume() == pytest.approx(made)

    index = doc.timeline.features.index(feat)
    assert doc.edit_feature(index, depth=1.0)
    assert doc.bodies[bid].manifold.volume() < made
    doc.undo()
    assert doc.bodies[bid].manifold.volume() == pytest.approx(made)

    assert doc.edit_feature(0, height=H * 2)             # the cylinder grows: the knurl follows the whole face
    grown = doc.bodies[bid].manifold
    assert feat.notes == [] and grown.slice(H * 1.5).area() < grown.slice(H * 0.5).area() * 1.001
    assert grown.slice(H * 1.5).area() == pytest.approx(grown.slice(H * 0.5).area(), rel=1e-3)
    assert grown.slice(H * 1.5).area() < math.pi * R * R * 0.99


def test_the_real_tool_picks_previews_and_makes_one_undoable_step():
    from omacad.ui.dialogs import SurfaceTextureDialog
    from omacad.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    body = win.doc.add_cylinder(R, H)
    volume = body.manifold.volume()

    win.ribbon.surface_texture_clicked.emit()
    dlg = next(w for w in app.allWidgets() if isinstance(w, SurfaceTextureDialog) and w.window() is win)
    dlg.cmb_kind.setCurrentText("Knurl")
    win.viewport.offset_face_picked.emit({"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, H]}, body.body_id)
    assert not dlg.faces and "outer round" in win.status_label.text()
    win.viewport.offset_face_picked.emit(dict(REF), body.body_id)
    assert dlg.faces
    for _ in range(100):
        if win.viewport.preview_mesh is not None:
            break
        QTest.qWait(50)
    assert win.viewport.preview_mesh is not None and "teeth per turn" in dlg.lbl_info.text()
    assert not win.doc.bodies[body.body_id].visible
    dlg.page.cmb_pattern.setCurrentText("Straight")
    assert not dlg.page.spins["angle"].isEnabled()
    dlg.accept()
    app.processEvents()

    assert win.viewport.preview_mesh is None and win.doc.bodies[body.body_id].visible
    assert win.doc.timeline.features[-1].feature_type == "knurl"
    assert win.doc.bodies[body.body_id].manifold.volume() < volume
    win.doc.undo()
    assert win.doc.bodies[body.body_id].manifold.volume() == pytest.approx(volume)
    win.close()
