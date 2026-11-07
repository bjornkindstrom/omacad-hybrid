"""Continuous Japandi rims and unclipped paired controls (requests 188, 189 and 191)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QWidget, QComboBox
from omacad.model.document import Document
from omacad.ui import theme
from omacad.ui.side_panel import InspectorPanel
from omacad.ui.dialogs.boolean_dlg import SplitBodyDialog


def test_split_body_paired_controls_fit_after_docking(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(theme, "FIXED_THEME", "studio")
    doc = Document()
    doc.add_box(10, 10, 10)
    plane = doc.add_construction_plane(doc.origin_planes["XY"], 4.)
    host = QWidget()
    host.resize(2048, 1122)
    panel = InspectorPanel(doc, host)
    dlg = SplitBodyDialog(doc, host, preselected_plane_id=plane)
    panel.dock_tool(dlg)
    host.show()
    for _ in range(6):
        app.processEvents()
    panel.set_max_height(1000)
    for _ in range(3):
        app.processEvents()
    try:
        for field in (dlg.cmb_target, dlg.cmb_plane):
            assert field.height() >= field.minimumSizeHint().height()
            assert field.parentWidget().rect().contains(field.geometry()), (field.geometry(), field.parentWidget().rect())
        assert panel.scroll.verticalScrollBar().maximum() == 0
    finally:
        dlg.reject()
        host.close()


import math
import numpy as np
import manifold3d as m3d
from shapely.geometry import Polygon, box
from omacad.model.features.base import region_cross_section
from omacad.model.features.japandi import JapandiFeature, apply_japandi

RADIUS, HEIGHT = 20., 30.
CYLINDER = m3d.Manifold.cylinder(HEIGHT, RADIUS, RADIUS, 360)
FACE = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1],
        "radius": RADIUS, "length": HEIGHT, "internal": False}
PARAMS = dict(shape="rectangular", direction="outward", radius=1.5, width=2., depth=2.,
              spacing=2., twist=0., margin=4., rim_depth=3.)


@pytest.mark.parametrize("kind", ["straight", "chamfer", "round"])
def test_rim_follows_whole_circumference_at_both_ends(kind):
    result, ribs, notes = apply_japandi(CYLINDER, [FACE], {**PARAMS, "rim": kind})
    assert not notes and ribs > 0 and result.status() == m3d.Error.NoError
    assert len(result.decompose()) == 1
    for distance in (0.5, 2., 3.5):
        u = distance / PARAMS["margin"]
        relief = 3. * ({"straight": 1., "chamfer": 1.-u, "round": math.sin(math.pi*u)}[kind])
        for z in (distance, HEIGHT-distance):
            points = np.asarray(result.slice(z).to_polygons()[0])
            radii = np.linalg.norm(points, axis=1)
            assert radii.min() == pytest.approx(RADIUS+relief, abs=0.04)
            assert radii.max() == pytest.approx(RADIUS+relief, abs=0.04)


def test_round_rim_can_extend_inside_hollow_body():
    hollow = CYLINDER - m3d.Manifold.cylinder(HEIGHT+2., 17., 17., 360).translate([0,0,-1])
    outer, _, notes = apply_japandi(hollow, [FACE], {**PARAMS, "rim": "round"})
    both, _, more = apply_japandi(hollow, [FACE], {**PARAMS, "rim": "round", "rim_inside": True})
    assert not notes and not more
    assert both.status() == m3d.Error.NoError and len(both.decompose()) == 1
    assert both.volume() > outer.volume()
    for z in (2., HEIGHT-2.):
        contours = both.slice(z).to_polygons()
        assert len(contours) == 2
        smallest = min(float(np.linalg.norm(np.asarray(p), axis=1).min()) for p in contours)
        assert smallest == pytest.approx(14., abs=0.04)
    assert both.slice(HEIGHT/2).area() == pytest.approx(outer.slice(HEIGHT/2).area())


@pytest.mark.parametrize("kind", ["straight", "chamfer", "round"])
def test_rim_follows_closed_rounded_rectangle_including_seam(kind):
    outline = box(-20., -8., 20., 8.).buffer(5., quad_segs=24)
    solid = m3d.Manifold.extrude(region_cross_section(outline), HEIGHT)
    ref = {"kind": "surface", "point": [25., 0., 15.], "normal": [1.,0.,0.]}
    result, ribs, notes = apply_japandi(solid, [ref], {**PARAMS, "rim": kind})
    assert not notes and ribs > 0
    assert result.status() == m3d.Error.NoError and len(result.decompose()) == 1
    for z in (2., HEIGHT-2.):
        polygons = result.slice(z).to_polygons()
        assert len(polygons) == 1
        cross = Polygon(polygons[0])
        added = 1.5 if kind == "chamfer" else 3.
        expected = outline.buffer(added)
        assert cross.hausdorff_distance(expected) < 0.1


def test_rim_settings_survive_history_and_save(tmp_path):
    from omacad.io.exporter import Exporter
    doc = Document()
    body = doc.add_cylinder(RADIUS, HEIGHT)
    feature = doc.add_japandi(body.body_id, [FACE], **PARAMS, rim="round", rim_inside=True)
    assert feature.rim == "round"
    target = tmp_path / "rim.omacad"
    Exporter.save_project(doc, str(target))
    loaded = Exporter.load_project(str(target))
    restored = next(f for f in loaded.timeline.features if isinstance(f, JapandiFeature))
    assert restored.rim == "round" and restored.rim_inside
    assert restored.rim_depth == 3.
    from omacad.ui.dialogs.surface_texture_dlg import _JapandiPage
    app = QApplication.instance() or QApplication([])
    page = _JapandiPage()
    page.load(restored)
    assert page.params()["rim"] == "round"
    assert page.params()["rim_inside"] is True
    assert page.params()["rim_depth"] == 3.
    page.close()



def test_end_rims_cap_open_curved_wall_without_joining_its_ends():
    half = CYLINDER.trim_by_plane((1.,0.,0.), 0.)
    face = {"kind": "surface", "point": [RADIUS,0.,15.], "normal": [1.,0.,0.]}
    result, ribs, notes = apply_japandi(half, [face], {**PARAMS, "rim": "straight"})
    assert not notes and ribs > 0
    assert result.status() == m3d.Error.NoError and len(result.decompose()) == 1
    assert result.bounding_box()[0] > -0.1
    assert result.bounding_box()[3] == pytest.approx(RADIUS+3., abs=0.04)
