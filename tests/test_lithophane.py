"""Lithophane: picture walls, flat, round and as a globe."""
import io
import json

import manifold3d as m3d
import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.lithophane import MAX_CELLS, LithophaneFeature, encode_picture


def picture(left=0, right=255, size=(80, 60)):
    img = Image.new("L", size, left)
    img.paste(right, (size[0] // 2, 0, *size))
    out = io.BytesIO()
    img.save(out, "PNG")
    return encode_picture(out.getvalue())


def build(**kw):
    return LithophaneFeature("f", "f", **{"image_data": picture(), "detail": 1.0, **kw}).build_solid()


@pytest.mark.parametrize("kw", [
    {}, {"upright": False}, {"frame": 0.0}, {"fit": "crop", "height": 40.0}, {"fit": "stretch", "height": 150.0},
    {"shape": "cylinder", "arc": 120.0}, {"shape": "cylinder", "arc": 360.0}, {"shape": "cylinder", "arc": 355.0},
    {"shape": "sphere"}, {"shape": "sphere", "opening": 0.0}, {"shape": "sphere", "arc": 360.0, "lat_span": 180.0},
])
def test_every_shape_is_one_closed_solid(kw):
    solid = build(**kw)
    assert solid.status() == m3d.Error.NoError and solid.volume() > 0
    # a closed globe has its hollow as a second skin
    assert len(solid.decompose()) == (2 if kw.get("opening") == 0.0 else 1)


def test_dark_is_thick_and_left_stays_left():
    v = np.asarray(build(frame=0.0).to_mesh().vert_properties)[:, :3]
    depth = -v[:, 1]
    assert depth[v[:, 0] < -5].max() == pytest.approx(3.0, abs=0.01)     # black half
    assert depth[v[:, 0] > 5].max() == pytest.approx(0.8, abs=0.05)      # white half
    v = np.asarray(build(frame=0.0, mirror=True).to_mesh().vert_properties)[:, :3]
    assert -v[v[:, 0] < -5, 1].min() == pytest.approx(0.8, abs=0.05)


def test_top_of_the_picture_is_up():
    img = Image.new("L", (40, 40), 255)
    img.paste(0, (0, 0, 40, 20))
    out = io.BytesIO()
    img.save(out, "PNG")
    data = encode_picture(out.getvalue())
    for kw in ({}, {"shape": "cylinder"}):
        v = np.asarray(build(image_data=data, frame=0.0, **kw).to_mesh().vert_properties)[:, :3]
        depth = -v[:, 1] if not kw else np.hypot(v[:, 0], v[:, 1])
        mid = v[:, 2].max() / 2
        assert depth[v[:, 2] > mid + 5].max() > depth[v[:, 2] < mid - 5].max() + 1.5


def test_proportions_and_round_sizes():
    w, _, z0, w1, _, z1 = build(frame=0.0).bounding_box()
    assert (w1 - w, z1 - z0) == pytest.approx((100.0, 75.0), abs=1e-3)
    b = build(shape="sphere", image_data=picture(0, 0), arc=360.0).bounding_box()
    assert b[3] - b[0] == pytest.approx(80.0, abs=0.2)
    assert b[2] == pytest.approx(0.0, abs=1e-4)


def test_wall_thickness_on_a_tube():
    solid = build(shape="cylinder", arc=360.0, frame=0.0, image_data=picture(128, 128))
    v = np.asarray(solid.to_mesh().vert_properties)[:, :3]
    r = np.hypot(v[:, 0], v[:, 1])
    t = 3.0 - 2.2 * 128 / 255
    assert r.min() == pytest.approx(37.0, abs=1e-3) and r.max() == pytest.approx(37.0 + t, abs=1e-3)


def test_huge_sizes_stay_within_the_point_limit():
    f = LithophaneFeature("f", "f", image_data=picture(), width=600.0, detail=0.1)
    assert f.effective_detail() > 0.1
    assert f.build_solid().num_tri() < 4.4 * MAX_CELLS


@pytest.mark.parametrize("kw", [{"image_data": ""}, {"min_thickness": 4.0}, {"frame": 60.0},
                                {"shape": "cylinder", "radius": 2.0}, {"shape": "sphere", "opening": 79.0}])
def test_impossible_values_say_why(kw):
    with pytest.raises(ValueError):
        build(**kw)


def test_save_load_edit_and_undo():
    doc = Document()
    body = doc.add_lithophane(image_data=picture(), detail=1.0, translation=[10, 0, 0])
    assert body.faces and not body.edges or body.manifold.num_tri() <= 5000
    vol = body.manifold.volume()
    data = json.loads(json.dumps(Exporter.document_to_dict(doc)))
    other = Document()
    Exporter.apply_dict(other, data)
    assert next(iter(other.bodies.values())).manifold.volume() == pytest.approx(vol)
    assert doc.edit_feature(0, shape="cylinder")
    assert next(iter(doc.bodies.values())).manifold.volume() != pytest.approx(vol)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(vol)


def test_bad_values_leave_no_step():
    doc = Document()
    with pytest.raises(ValueError):
        doc.add_lithophane()
    assert not doc.timeline.features and not doc.bodies


def test_panel(tmp_path):
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs.lithophane_dlg import LithophaneDialog
    d = LithophaneDialog()
    assert d.build_preview() is None and "picture" in d.lbl_problem.text()
    bad = tmp_path / "x.png"
    bad.write_text("no")
    assert not d.load_image(bad)
    good = tmp_path / "ok.png"
    Image.new("RGBA", (30, 20), (0, 0, 0, 0)).save(good)
    assert d.load_image(good)
    for i, shape in enumerate(("flat", "cylinder", "sphere")):
        d.cmb_shape.setCurrentIndex(i)
        assert d.get_params()["shape"] == shape
        assert d.build_preview() is not None
    assert d.spins["radius"].isVisibleTo(d) and not d.spins["width"].isVisibleTo(d)
    e = LithophaneDialog()
    e.set_params(d.get_params())
    assert e.get_params() == d.get_params()


def test_prompt_creates_a_body(tmp_path):
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs.lithophane_dlg import LithophaneDialog
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    try:
        win.prompt_lithophane()
        dlg = win.findChildren(LithophaneDialog)[-1]
        dlg.set_params({"image_data": picture(), "detail": 1.0})
        dlg.accept()
        assert [f.feature_type for f in win.doc.timeline.features] == ["lithophane"]
    finally:
        win.doc.modified = False
        win.deleteLater()


def test_edit_from_the_timeline(monkeypatch):
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs.lithophane_dlg import LithophaneDialog
    from omacad.ui.feature_edit import edit_feature
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    try:
        win.doc.add_lithophane(image_data=picture(), detail=1.0)

        def use_cylinder(dlg):
            assert dlg.image_data
            dlg.cmb_shape.setCurrentIndex(1)
            return 1
        monkeypatch.setattr(LithophaneDialog, "exec", use_cylinder)
        assert edit_feature(win, win.doc, 0)
        assert win.doc.timeline.features[0].shape == "cylinder"
    finally:
        win.doc.modified = False
        win.deleteLater()


# ---- tone curve, picture clean-up, outlines, stand and the lit preview (0.9.9.80.225)

def _gray(level, size=(40, 30)):
    out = io.BytesIO()
    Image.new("L", size, level).save(out, "PNG")
    return encode_picture(out.getvalue())


def test_light_tone_makes_the_light_through_the_wall_follow_the_picture():
    feat = LithophaneFeature("f", "f", image_data=_gray(128), tone="light", min_thickness=0.8, max_thickness=3.0)
    lum = np.linspace(0, 1, 11)
    lit = feat.transmitted(feat.thickness_for(lum), feat.min_thickness)
    dark = feat.transmitted(np.array([3.0]), 0.8)[0]
    assert np.allclose(lit, dark + (1 - dark) * lum)                 # linear in the light, not in the plastic
    assert np.isclose(feat.thickness_for(np.array([0.0]))[0], 3.0) and np.isclose(feat.thickness_for(np.array([1.0]))[0], 0.8)
    linear = LithophaneFeature("f", "f", image_data=_gray(128))      # older projects: thickness straight from lightness
    assert np.allclose(linear.thickness_for(lum), 3.0 - 2.2 * lum)


def test_older_projects_build_exactly_as_before():
    old = LithophaneFeature("f", "f", image_data=picture(), detail=1.0)
    explicit = LithophaneFeature("f", "f", image_data=picture(), detail=1.0, tone="linear", auto_levels=False,
                                 sharpen=0.0, denoise=0.0, outline="rect", corner_radius=0.0, stand=0.0)
    a, b = old.build_solid().to_mesh(), explicit.build_solid().to_mesh()
    assert np.array_equal(a.vert_properties, b.vert_properties) and np.array_equal(a.tri_verts, b.tri_verts)


def test_auto_levels_spreads_a_flat_picture_over_the_whole_range():
    img = Image.new("L", (40, 30), 110)
    img.paste(150, (20, 0, 40, 30))
    out = io.BytesIO()
    img.save(out, "PNG")
    feat = LithophaneFeature("f", "f", image_data=encode_picture(out.getvalue()), auto_levels=True)
    t = feat._thickness(40, 30, 40 / 30)
    assert np.isclose(t.max(), feat.max_thickness) and np.isclose(t.min(), feat.min_thickness)


def test_sharpen_adds_and_denoise_removes_detail():
    rng = np.random.default_rng(3)
    out = io.BytesIO()
    Image.fromarray(rng.integers(60, 200, (60, 80)).astype(np.uint8), "L").save(out, "PNG")
    data = encode_picture(out.getvalue())
    spread = lambda **kw: LithophaneFeature("f", "f", image_data=data, **kw)._thickness(80, 60, 80 / 60).std()
    plain = spread()
    assert spread(sharpen=100.0) > plain > spread(denoise=2.0)


@pytest.mark.parametrize("outline", ["rounded", "circle", "heart"])
def test_shaped_plates_are_one_closed_solid_inside_their_box(outline):
    plain = build(frame=3.0)
    solid = build(frame=3.0, outline=outline, corner_radius=8.0)
    assert solid.status() == m3d.Error.NoError and len(solid.decompose()) == 1
    assert 0 < solid.volume() < plain.volume()
    assert np.allclose(solid.bounding_box(), plain.bounding_box(), atol=0.05)   # the outline fills the same box


def test_frame_follows_a_round_outline():
    feat = LithophaneFeature("f", "f", image_data=_gray(255), outline="circle", frame=4.0, width=60.0,
                             fit="stretch", height=60.0, detail=0.5)
    u = v = np.linspace(0, 60, 121)
    t, _ = feat._shaped_thickness(u, v, 60, 60)
    assert np.isclose(t[60, 60], feat.min_thickness)            # white middle: thinnest
    assert np.isclose(t[60, 2], feat.max_thickness)             # 1 mm inside the circle's edge: frame
    assert np.isclose(t[60, 12], feat.min_thickness)            # 6 mm in: picture again


def test_stand_holds_the_upright_plate_and_rests_on_the_floor():
    plain = build(frame=3.0)
    for outline in ("rect", "heart"):
        solid = build(frame=3.0, outline=outline, stand=20.0)
        lo, hi = np.array(solid.bounding_box()[:3]), np.array(solid.bounding_box()[3:])
        assert len(solid.decompose()) == 1 and abs(lo[2]) < 1e-6
        assert hi[1] - lo[1] >= 20.0 - 1e-6                     # the foot is as deep as asked
        assert hi[2] > plain.bounding_box()[5]                  # the plate stands on top of it


def test_backlit_preview_matches_the_body_thickness():
    feat = LithophaneFeature("f", "f", image_data=picture(), tone="light", detail=1.0)
    lit, inside = feat.backlit(120)
    assert lit.shape == inside.shape and lit.shape[1] == 120 and inside.all()
    assert lit.max() <= 1.0 + 1e-9 and lit.min() >= feat.transmitted(np.array([feat.max_thickness]), feat.min_thickness)[0] - 1e-9
    assert lit[lit.shape[0] // 2, 10] < lit[lit.shape[0] // 2, -10]    # black left half is dark, white right is lit
    heart, inside = LithophaneFeature("f", "f", image_data=picture(), outline="heart").backlit(80)
    assert not inside.all() and inside[inside.shape[0] // 2].any()


def test_panel_new_options_lit_preview_and_old_steps_kept(tmp_path):
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs.lithophane_dlg import LithophaneDialog
    d = LithophaneDialog()
    assert d.get_params()["tone"] == "light" and d.get_params()["sharpen"] == 40.0     # a new one starts better
    d.set_image(picture())
    d.spins["detail"].setValue(1.0)
    assert d.build_preview() is not None and d.lbl_lit.pixmap() is not None and not d.lbl_lit.pixmap().isNull()
    d.cmb_outline.setCurrentIndex(d.cmb_outline.findData("rounded"))
    assert d.spins["corner_radius"].isVisibleTo(d) and d.spins["stand"].isVisibleTo(d)
    d.spins["stand"].setValue(15.0)
    d.spins["corner_radius"].setValue(6.0)
    assert d.build_preview() is not None
    p = d.get_params()
    assert p["outline"] == "rounded" and p["stand"] == 15.0 and p["corner_radius"] == 6.0
    d.checks["upright"].setChecked(False)
    assert not d.spins["stand"].isVisibleTo(d) and d.get_params()["stand"] == 0.0      # no foot when lying
    d.cmb_shape.setCurrentIndex(1)
    assert not d.cmb_outline.isVisibleTo(d) and d.get_params()["outline"] == "rect"
    old = LithophaneFeature("f", "f", image_data=picture()).to_dict()
    old.pop("tone")                                         # a step saved before tones existed
    e = LithophaneDialog()
    e.set_params(old)
    assert e.get_params()["tone"] == "linear" and e.get_params()["sharpen"] == 0.0


def test_a_sphere_step_can_be_edited_from_the_timeline(monkeypatch):
    """The sphere editor called two helpers that did not exist (NameError as soon as it opened)."""
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs.primitives_dlg import SphereDialog
    from omacad.ui.feature_edit import edit_feature
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    try:
        win.doc.add_sphere(10.0)

        def bigger(dlg):
            assert dlg.cmb_placement.currentData() == "center"
            dlg.spn_radius.setValue(12.0)
            return 1
        monkeypatch.setattr(SphereDialog, "exec", bigger)
        assert edit_feature(win, win.doc, 0)
        assert win.doc.timeline.features[0].radius == pytest.approx(12.0)
    finally:
        win.doc.modified = False
        win.deleteLater()
