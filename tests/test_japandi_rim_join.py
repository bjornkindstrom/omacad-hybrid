"""Report 20261107-093936: smooth end rims meet the rib crests at both ends."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

import numpy as np
import manifold3d as m3d
import pytest
from shapely.geometry import Polygon
from PySide6.QtWidgets import QApplication
from omacad.io.exporter import Exporter
from omacad.model.features.japandi import apply_japandi

_app = QApplication.instance() or QApplication([])

REPORT = Path(__file__).parent / "data" / "japandi_rim_join.omacad"


def outline(body, z):
    return Polygon(max(body.slice(z).to_polygons(), key=lambda p: Polygon(p).area))


@pytest.mark.parametrize("rim", ["chamfer", "round"])
@pytest.mark.parametrize("shape", ["rectangular", "half-round"])
@pytest.mark.parametrize("twist", [0., 35.])
@pytest.mark.parametrize("height_profile", ["even", "arch"])
def test_report_smooth_rim_meets_rib_crests(rim, shape, twist, height_profile):
    doc = Exporter.load_project(str(REPORT))
    feature = doc.timeline.features[-1]
    old = doc.bodies[feature.target_body_id].manifold
    assert outline(old, 2.999).hausdorff_distance(outline(old, 3.001)) > 0.8
    doc.timeline.marker_index = 1
    doc.timeline.recompute(doc)
    base = doc.bodies[feature.target_body_id].manifold
    result, ribs, notes = apply_japandi(base, feature.faces,
        {**feature.params(), "rim_follow": True, "rim": rim, "shape": shape, "twist": twist, "height_profile": height_profile})
    assert ribs > 0 and not notes
    assert result.status() == m3d.Error.NoError and len(result.decompose()) == 1
    for edge, sign in ((3., -1.), (37., 1.)):
        band = np.asarray(outline(result, edge + sign * 0.001).exterior.coords)
        rib = np.asarray(outline(result, edge - sign * 0.001).exterior.coords)
        band_r, rib_r = np.linalg.norm(band, axis=1), np.linalg.norm(rib, axis=1)
        assert np.ptp(band_r) < 0.03
        assert band_r.max() == pytest.approx(rib_r.max(), abs=0.03)
    # Following the ends must leave the middle ribs and the bore unchanged.
    ordinary, _, _ = apply_japandi(base, feature.faces,
        {**feature.params(), "rim": rim, "shape": shape, "twist": twist, "height_profile": height_profile})
    assert result.slice(20.).area() == pytest.approx(ordinary.slice(20.).area(), abs=1e-5)


def test_follow_setting_history_file_and_panel(tmp_path):
    doc = Exporter.load_project(str(REPORT))
    feature = doc.timeline.features[-1]
    assert feature.rim_follow is False
    from omacad.ui.dialogs.surface_texture_dlg import _JapandiPage
    app = QApplication.instance() or QApplication([])
    page = _JapandiPage()
    page.load(feature)
    page.chk_rim_follow.setChecked(True)
    assert page.params()["rim_follow"] is True
    assert doc.edit_feature(1, rim_follow=True)
    assert doc.timeline.features[-1].rim_follow
    doc.undo()
    assert not doc.timeline.features[-1].rim_follow
    doc.redo()
    assert doc.timeline.features[-1].rim_follow
    path = tmp_path / "follow.omacad"
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    assert loaded.timeline.features[-1].rim_follow is True
    page.load(loaded.timeline.features[-1])
    assert page.chk_rim_follow.isChecked()
    page.close()


@pytest.mark.parametrize("rim", ["chamfer", "round"])
def test_follow_rim_on_closed_curved_wall(rim):
    from shapely.geometry import box
    from omacad.model.features.base import region_cross_section
    outline_shape = box(-10., -5., 10., 5.).buffer(4., quad_segs=24)
    solid = m3d.Manifold.extrude(region_cross_section(outline_shape), 20.)
    ref = {"kind": "surface", "point": [14., 0., 10.], "normal": [1., 0., 0.]}
    doc = Exporter.load_project(str(REPORT))
    params = {**doc.timeline.features[-1].params(), "rim": rim, "rim_follow": True,
              "path": "straight", "height_profile": "even", "depth": 1., "twist": 0.}
    result, ribs, notes = apply_japandi(solid, [ref], params)
    assert ribs > 0 and not notes
    assert result.status() == m3d.Error.NoError and len(result.decompose()) == 1
    straight, _, _ = apply_japandi(solid, [ref], {**params, "twist": 45.})
    for z in (1.5, 18.5):
        assert outline(result, z).hausdorff_distance(outline(straight, z)) < 1e-6


@pytest.mark.parametrize("rim", ["chamfer", "round"])
def test_094826_no_flutes_in_end_band(rim):
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "japandi_smooth_rim.omacad"))
    feature = doc.timeline.features[-1]
    assert feature.rim_follow
    doc.timeline.marker_index = 1
    doc.timeline.recompute(doc)
    base = doc.bodies[feature.target_body_id].manifold
    result, ribs, notes = apply_japandi(base, feature.faces, {**feature.params(), "rim": rim})
    assert ribs == 103 and not notes
    assert result.status() == m3d.Error.NoError and len(result.decompose()) == 1
    for z in (0.75, 1.5, 2.999, 37.001, 38.5, 39.25):
        points = np.asarray(outline(result, z).exterior.coords)
        assert np.ptp(np.linalg.norm(points, axis=1)) < 0.03
    for z in (2.999, 37.001):
        points = np.asarray(outline(result, z).exterior.coords)
        assert np.linalg.norm(points, axis=1).max() == pytest.approx(50.5, abs=0.03)
