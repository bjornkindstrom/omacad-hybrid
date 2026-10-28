"""Draft angle geometry, shell thickness, persistence and safe validation."""
import math

import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.features.primitives import BoxFeature, CylinderFeature
from omacad.model import quality
from omacad.io.exporter import Exporter
from omacad.ui.main_window import MainWindow
from omacad.ui.numeric_slider import NumericSlider


def box_volume(l, w, h, k):
    return l*w*h - (l+w)*k*h*h + 4*k*k*h**3/3


def cylinder_volume(r, h, k):
    n = quality.circle_segments()
    return n/2*math.sin(2*math.pi/n) * (r*r*h-r*k*h*h+k*k*h**3/3)


@pytest.mark.parametrize("angle", [-12, 0, 12])
@pytest.mark.parametrize("kind", ["box", "cylinder"])
@pytest.mark.parametrize("wall", [0., 2.])
def test_tapered_volume_and_constant_normal_shell(kind, angle, wall):
    doc = Document()
    k = math.tan(math.radians(angle))
    h = 20.
    if kind == "box":
        body = doc.add_box(50, 40, h, taper_angle=angle, wall_thickness=wall, center="bottom_center")
        expected = box_volume(50, 40, h, k)
    else:
        body = doc.add_cylinder(25, h, taper_angle=angle, wall_thickness=wall)
        expected = cylinder_volume(25, h, k)
    if wall:
        offset = wall/math.cos(math.radians(angle))
        if kind == "box":
            expected -= box_volume(50-2*k*wall-2*offset, 40-2*k*wall-2*offset, h-wall, k)
        else:
            expected -= cylinder_volume(25-k*wall-offset, h-wall, k)
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    saved = Exporter.document_to_dict(doc)
    copy = Document()
    Exporter.apply_dict(copy, saved)
    assert copy.timeline.features[0].taper_angle == angle
    assert next(iter(copy.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    doc.undo()
    assert not doc.bodies
    doc.redo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("cls,args", [(BoxFeature, (50, 40, 20)), (CylinderFeature, (25, 20))])
def test_taper_rounding_and_placement(cls, args):
    feature = cls("a", "A", *args, taper_angle=8, wall_thickness=2,
                  outer_round=1, inner_round=.5, center=True,
                  plane_origin=[10, 20, 30], plane_normal=[0, -1, 0],
                  plane_u=[1, 0, 0], plane_v=[0, 0, 1])
    solid = feature.build_solid()
    assert not solid.is_empty()
    assert solid.status().name == "NoError"
    assert 0 < solid.volume() < cls("b", "B", *args).build_solid().volume()


@pytest.mark.parametrize("kind,args", [("box", (10, 10, 50)), ("cylinder", (5, 50))])
def test_invalid_taper_leaves_document_unchanged(kind, args):
    doc = Document()
    before = doc.snapshot()
    with pytest.raises(ValueError, match="closes the top"):
        getattr(doc, "add_"+kind)(*args, taper_angle=45)
    assert doc.snapshot() == before


@pytest.mark.parametrize("kind", ["box", "cylinder"])
def test_dialog_taper_slider_validation_and_edit(kind):
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    getattr(w, "prompt_"+kind)()
    dlg = w.viewport.primitive_handles.dialog
    assert isinstance(dlg.spn_taper.parentWidget(), NumericSlider)
    dlg.spn_taper.setValue(85)
    dlg.accept()
    assert not w.doc.bodies
    assert dlg.lbl_problem.text()
    dlg.spn_taper.setValue(10)
    dlg.accept()
    assert w.doc.timeline.features[-1].taper_angle == 10
    assert w.doc.edit_feature(0, taper_angle=-5)
    assert w.doc.timeline.features[0].taper_angle == -5
    w.doc.undo()
    assert w.doc.timeline.features[0].taper_angle == 10
    w.close()

