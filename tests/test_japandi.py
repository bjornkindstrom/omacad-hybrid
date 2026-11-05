"""Japandi ribs (requests #179-#182): volumes against formulas, the twist against a turned section, a bore left alone,
a curved wall, refused faces, the model's history and the panel."""
import math
import os
from types import SimpleNamespace
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import manifold3d as m3d
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from shapely import affinity
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces_hit_tests import _normal_axis, detect_cylinder_surface
from omacad.model.features.japandi import PROFILE_SAG, SAG, apply_japandi, rib_count, rib_period
from omacad.model.features.offset_face import cylinder_face_ref
from omacad.ui.dialogs.surface_texture_dlg import SurfaceTextureDialog
from omacad.ui.feature_edit import can_edit

R, H = 30.0, 50.0
PIN = m3d.Manifold.cylinder(H, R, R, 720)
REF = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": R, "length": H, "internal": False}
ROUND = dict(shape="half-round", direction="outward", radius=1.5, width=2.0, depth=2.0, spacing=0.0, twist=0.0, margin=0.0)
RECT = {**ROUND, "shape": "rectangular", "spacing": 2.0}
_app = QApplication.instance() or QApplication([])


def apply(solid=PIN, ref=REF, **params):
    result, ribs, notes = apply_japandi(solid, [ref], {**ROUND, **params})
    assert not notes
    return result, ribs


def section(solid, z):
    """The solid's outline at height z, holes taken out."""
    rings = [np.asarray(r) for r in solid.slice(z).to_polygons()]
    rings.sort(key=lambda r: -Polygon(r).area)
    return Polygon(rings[0], rings[1:])


def off_circle(radius, width=2.0, spacing=2.0, height=H):
    """The most volume straight pieces can differ by, lying up to SAG off the circle on the ribs' share of the wall."""
    return width / (width + spacing) * 2.0 * math.pi * radius * height * SAG


def rectangular_volume(ribs, height, width=2.0, depth=2.0, spacing=2.0):
    """Ribs whose share of the circle stays width / (width + spacing), between R and R + depth."""
    return ribs * (2.0 * math.pi / ribs) * width / (width + spacing) / 2.0 * ((R + depth) ** 2 - R ** 2) * height


def test_rectangular_ribs_add_the_volume_of_their_sectors():
    result, ribs = apply(**RECT)
    assert ribs == rib_count(R, RECT) == 47
    assert result.status() == m3d.Error.NoError and result.genus() == 0
    assert result.volume() - PIN.volume() == pytest.approx(rectangular_volume(ribs, H), abs=off_circle(R + 2.0))


def test_rectangular_grooves_cut_the_volume_of_their_sectors():
    result, ribs = apply(**{**RECT, "direction": "inward"})
    removed = ribs * (2.0 * math.pi / ribs) * 0.5 / 2.0 * (R ** 2 - (R - 2.0) ** 2) * H
    assert PIN.volume() - result.volume() == pytest.approx(removed, abs=off_circle(R - 2.0))
    assert result.bounding_box()[5] == pytest.approx(H) and result.genus() == 0


def test_width_depth_and_spacing_all_count():
    wide, ribs = apply(**{**RECT, "width": 3.0, "depth": 1.0, "spacing": 1.0})
    assert ribs == rib_count(R, {**RECT, "width": 3.0, "spacing": 1.0}) == 47
    assert wide.volume() - PIN.volume() == pytest.approx(rectangular_volume(ribs, H, 3.0, 1.0, 1.0), abs=off_circle(R + 1.0, 3.0, 1.0))
    assert wide.bounding_box()[3] == pytest.approx(R + 1.0, abs=0.01)


@pytest.mark.parametrize("spacing", [0.0, 1.0])
def test_half_round_ribs_add_half_discs_of_the_asked_radius(spacing):
    result, ribs = apply(spacing=spacing)
    assert ribs == rib_count(R, {**ROUND, "spacing": spacing})
    widened = (2.0 * math.pi * R / ribs) / rib_period({**ROUND, "spacing": spacing})   # whole ribs fit: a little wider
    half_disc = math.pi * 1.5 ** 2 / 2.0 * widened
    assert result.volume() - PIN.volume() == pytest.approx(ribs * half_disc * H, rel=0.02)
    assert result.bounding_box()[3] == pytest.approx(R + 1.5, abs=0.03)
    assert result.genus() == 0


def test_half_round_grooves_go_in_by_the_radius():
    result, ribs = apply(direction="inward", spacing=1.0)
    assert result.volume() < PIN.volume()
    radii = np.hypot(*np.asarray(section(result, H / 2).exterior.coords).T)
    assert radii.min() == pytest.approx(R - 1.5, abs=0.02) and radii.max() == pytest.approx(R, abs=0.05)
    assert result.bounding_box()[5] == pytest.approx(H)


@pytest.mark.parametrize("params", [ROUND, {**RECT, "direction": "inward"}])
def test_twist_turns_each_section_in_proportion_to_its_height(params):
    twist = 90.0
    result, _ = apply(**{**params, "twist": twist})
    start = section(result, 0.5)
    for z in (H / 4, H / 2, H - 0.5):
        turned = affinity.rotate(start, twist * (z - 0.5) / H, origin=(0, 0))
        assert section(result, z).symmetric_difference(turned).area < 0.03 * start.area
    assert result.status() == m3d.Error.NoError and result.genus() == 0


def test_twist_can_turn_the_other_way():
    right, _ = apply(twist=60.0)
    left, _ = apply(twist=-60.0)
    assert section(left, H / 2).symmetric_difference(section(right, H / 2)).area > 10.0
    mirrored = affinity.scale(section(right, 10.0), -1.0, 1.0, origin=(0, 0))
    assert left.volume() == pytest.approx(right.volume(), rel=1e-3) and mirrored.is_valid


def test_margin_leaves_plain_ends():
    margin = 5.0
    result, ribs = apply(margin=margin)
    plain = PIN.volume() / H
    assert section(result, margin / 2).area == pytest.approx(plain, rel=1e-4)
    assert section(result, H - margin / 2).area == pytest.approx(plain, rel=1e-4)
    assert section(result, H / 2).area > plain + 100.0
    assert result.volume() - PIN.volume() == pytest.approx((apply()[0].volume() - PIN.volume()) * (H - 2 * margin) / H, rel=1e-3)


@pytest.mark.parametrize("params", [ROUND, {**RECT, "direction": "inward"}])
def test_the_inside_of_a_pot_is_not_touched(params):
    bore_r = R - 4.0
    pot = PIN - m3d.Manifold.cylinder(H, bore_r, bore_r, 720).translate((0, 0, 3))
    result, _ = apply(solid=pot, **params)
    bore = Polygon(section(result, H / 2).interiors[0])
    assert bore.area == pytest.approx(Polygon(section(pot, H / 2).interiors[0]).area, rel=1e-6)
    assert section(result, 1.5).area > section(pot, H / 2).area and result.genus() == 0


def _vase():
    zs = np.linspace(0.0, 80.0, 81)
    radii = 22.0 + 12.0 * np.sin(zs / 80.0 * math.pi * 1.3)
    outline = [(0.0, 0.0)] + list(zip(radii, zs)) + [(0.0, 80.0)]
    ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": float(radii.mean()), "length": 80.0, "internal": False}
    return m3d.Manifold.revolve(m3d.CrossSection([np.array(outline)]), 240), ref, lambda z: 22.0 + 12.0 * math.sin(z / 80.0 * math.pi * 1.3)


def _peaks(polygon):
    """Ribs in an outline: stretches beyond a radius halfway up the rib."""
    coords = np.asarray(polygon.exterior.coords)[:-1]
    radii = np.hypot(coords[:, 0], coords[:, 1])
    high = radii > (radii.min() + radii.max()) / 2.0
    return int(np.sum(high & ~np.roll(high, 1)))


def test_ribs_follow_a_curved_wall_and_narrow_with_it():
    vase, ref, wall = _vase()
    result, ribs = apply(solid=vase, ref=ref)
    assert result.status() == m3d.Error.NoError and result.genus() == 0
    largest = max(wall(z) for z in np.linspace(0, 80, 321))
    for z in (5.0, 40.0, 75.0):
        outline = section(result, z)
        assert _peaks(outline) == ribs
        radii = np.hypot(*np.asarray(outline.exterior.coords).T)
        # a half-round rib scales with the wall. It stands along the normal, so a leaning wall shows it longer across the radius
        slope = (wall(z + 0.01) - wall(z - 0.01)) / 0.02
        assert radii.max() - wall(z) == pytest.approx(1.5 * wall(z) / largest * math.hypot(1.0, slope), abs=PROFILE_SAG + 0.02)


def test_twist_on_a_curved_wall_is_one_whole_body_and_stays_light():
    vase, ref, _ = _vase()
    result, ribs = apply(solid=vase, ref=ref, twist=120.0)
    assert result.status() == m3d.Error.NoError and result.genus() == 0
    assert result.num_tri() < 400_000
    assert section(result, 40.0).symmetric_difference(section(apply(solid=vase, ref=ref)[0], 40.0)).area > 10.0


@pytest.mark.parametrize("params", [ROUND, {**RECT, "direction": "inward", "depth": 0.8, "twist": 90.0}])
def test_a_face_as_it_is_picked_in_the_view(params):
    """The reference comes from the same detection as a click on the wall, not from known values."""
    vase, _, _ = _vase()
    mesh = vase.to_mesh()
    tris = np.asarray(mesh.vert_properties)[:, :3][np.asarray(mesh.tri_verts)]
    middle = tris.mean(axis=1)
    clicked = int(np.argmin(np.abs(middle[:, 2] - 40.0) - np.hypot(middle[:, 0], middle[:, 1])))
    ref = cylinder_face_ref(detect_cylinder_surface(SimpleNamespace(vertices=tris.reshape(-1, 3)), clicked))
    result, ribs, notes = apply_japandi(vase, [ref], params)
    assert not notes and ribs >= 3
    assert result.status() == m3d.Error.NoError and result.genus() == 0
    assert (result.volume() > vase.volume()) == (params["direction"] == "outward")


def test_fine_round_mesh_still_finds_its_axis():
    """The full SVD built an N x N matrix: 100 000 normals ran out of memory, and the wall was no longer seen as round."""
    angle = np.linspace(0.0, 2.0 * math.pi, 100_000)
    axis = _normal_axis(np.column_stack((np.cos(angle), np.sin(angle), np.zeros(len(angle)))))
    assert axis is not None and abs(axis[2]) == pytest.approx(1.0)


@pytest.mark.parametrize("ref, params, why", [
    ({**REF, "internal": True}, ROUND, "outer round"),
    ({"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, H]}, ROUND, "outer round"),
    (REF, {**ROUND, "margin": 30.0}, "margin"),
    (REF, {**RECT, "direction": "inward", "depth": 40.0}, "fit"),
    (REF, {**RECT, "spacing": 0.0}, "above zero"),
    (REF, {**ROUND, "radius": 0.05, "twist": 3600.0}, "too many"),
])
def test_faces_and_values_that_cant_work_say_why(ref, params, why):
    result, ribs, notes = apply_japandi(PIN, [ref], params)
    assert ribs == 0 and result is PIN and why in notes[0]


def test_a_face_that_stops_part_way_round_is_refused():
    half = PIN - m3d.Manifold.cube((2 * R, 4 * R, 2 * H), True).translate((-R, 0, H / 2))
    _, ribs, notes = apply_japandi(half, [REF], ROUND)
    assert ribs == 0 and "all the way round" in notes[0]


def test_step_saves_rebuilds_and_undoes(tmp_path):
    doc = Document()
    body = doc.add_cylinder(R, H)
    before = body.manifold.volume()
    faces = [dict(REF)]
    feat = doc.add_japandi(body.body_id, faces, shape="rectangular", direction="inward", width=2.5, depth=1.5, spacing=2.0, twist=45.0, margin=2.0)
    assert feat.name == "Japandi 1" and feat.ribs > 0 and can_edit(feat)
    made = doc.bodies[body.body_id].manifold.volume()
    assert made < before

    doc.timeline.recompute(doc)
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(made, rel=1e-6)

    path = str(tmp_path / "japandi.omacad")
    Exporter.save_project(doc, path)
    copy = Exporter.load_project(path)
    again = next(f for f in copy.timeline.features if f.feature_type == "japandi")
    assert again.params() == feat.params() and again.faces == feat.faces
    assert copy.bodies[body.body_id].manifold.volume() == pytest.approx(made, rel=1e-6)

    doc.undo()
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(before)
    assert not [f for f in doc.timeline.features if f.feature_type == "japandi"]


def test_a_refused_step_adds_nothing():
    doc = Document()
    body = doc.add_cylinder(R, H)
    with pytest.raises(ValueError, match="margin"):
        doc.add_japandi(body.body_id, [dict(REF)], margin=30.0)
    assert not [f for f in doc.timeline.features if f.feature_type == "japandi"]


def test_panel_shows_the_settings_of_the_shape_and_edits_a_step():
    doc = Document()
    body = doc.add_cylinder(R, H)
    feat = doc.add_japandi(body.body_id, [dict(REF)], shape="rectangular", direction="inward", width=3.0, depth=1.0, spacing=2.0, twist=30.0)
    dlg = SurfaceTextureDialog(doc, feature=feat)
    page = dlg.page
    assert dlg.kind() == "japandi" and not dlg.cmb_kind.isEnabled() and dlg.faces == feat.faces
    assert dlg.params() == feat.params()
    assert page.spins["width"].isVisibleTo(page) and page.spins["depth"].isVisibleTo(page) and not page.spins["radius"].isVisibleTo(page)
    page.cmb_shape.setCurrentText("Half-round")
    assert page.spins["radius"].isVisibleTo(page) and not page.spins["width"].isVisibleTo(page) and not page.spins["depth"].isVisibleTo(page)
    assert dlg.params()["shape"] == "half-round" and page.spins["spacing"].isVisibleTo(page) and page.spins["twist"].isVisibleTo(page)
    dlg.deleteLater()


def test_panel_makes_a_step_with_a_live_preview_and_keeps_only_outer_round_faces():
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    body = win.doc.add_cylinder(R, H)
    volume = body.manifold.volume()
    win.prompt_surface_texture()
    dlg = win.inspector.current_tool_dlg
    plane = {"kind": "plane", "normal": [0, 0, 1], "origin": [0, 0, H]}
    win.viewport.offset_face_picked.emit(plane, body.body_id)
    dlg.cmb_kind.setCurrentText("Japandi")
    assert win.viewport.plane_pick_mode and dlg.faces == []
    win.viewport.offset_face_picked.emit(plane, body.body_id)
    assert dlg.faces == [] and "outer round" in win.status_label.text()
    win.viewport.offset_face_picked.emit(dict(REF), body.body_id)
    assert len(dlg.faces) == 1
    page = dlg.page
    assert page.spins["radius"].isVisible() and not page.spins["width"].isVisible()   # docked, each field sits in a slider widget
    page.cmb_shape.setCurrentText("Rectangular")
    assert page.spins["width"].isVisible() and page.spins["depth"].isVisible() and not page.spins["radius"].isVisible()
    page.cmb_shape.setCurrentText("Half-round")
    dlg.accept()
    _app.processEvents()
    assert win.doc.timeline.features[-1].feature_type == "japandi"
    assert win.doc.bodies[body.body_id].visible and win.viewport.preview_mesh is None
    assert win.doc.bodies[body.body_id].manifold.volume() > volume
    assert "ribs per turn" in win.status_label.text()
    win.close()
