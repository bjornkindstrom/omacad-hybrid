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
