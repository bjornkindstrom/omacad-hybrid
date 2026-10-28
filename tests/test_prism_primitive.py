"""Hexagon / regular prism primitive: sized across flats, with every Cylinder option measured square to the flats."""
import math

import pytest

from omacad.model.document import Document
from omacad.model.features.primitives import PrismFeature


def _area(apothem, sides=6):
    return sides * apothem**2 * math.tan(math.pi / sides)


def test_hexagon_is_sized_across_flats_with_a_flat_facing_x():
    solid = PrismFeature("p", "p", 20.0, 10.0).build_solid()
    assert solid.volume() == pytest.approx(_area(10) * 10, rel=1e-9)
    x0, y0, z0, x1, y1, z1 = solid.bounding_box()
    assert (x0, x1) == pytest.approx((-10, 10))                       # flats on ±X
    assert y1 == pytest.approx(10 / math.cos(math.pi / 6))            # corners on ±Y
    assert (z0, z1) == pytest.approx((0, 10))


@pytest.mark.parametrize("sides", [3, 5, 8])
def test_other_side_counts(sides):
    solid = PrismFeature("p", "p", 30.0, 4.0, sides=sides).build_solid()
    assert solid.volume() == pytest.approx(_area(15, sides) * 4, rel=1e-9)
    assert solid.bounding_box()[3] == pytest.approx(15)


def test_shell_wall_is_square_to_the_flats():
    solid = PrismFeature("p", "p", 20.0, 10.0, wall_thickness=2.0).build_solid()
    assert solid.volume() == pytest.approx(_area(10) * 10 - _area(8) * 8, rel=1e-9)


def test_chamfer_runs_along_every_flat():
    a, h, c = 10.0, 10.0, 1.0
    solid = PrismFeature("p", "p", 2 * a, h, outer_round=c, outer_round_kind="chamfer").build_solid()
    k = _area(1.0)
    expected = k * a**2 * (h - 2 * c) + 2 * k * (a**3 - (a - c)**3) / 3
    assert solid.volume() == pytest.approx(expected, rel=1e-9)


def test_taper_narrows_the_flats():
    a, h, angle = 10.0, 10.0, 10.0
    solid = PrismFeature("p", "p", 2 * a, h, taper_angle=angle).build_solid()
    top = a - h * math.tan(math.radians(angle))
    a0, a1 = _area(a), _area(top)
    assert solid.volume() == pytest.approx(h / 3 * (a0 + a1 + math.sqrt(a0 * a1)), rel=1e-6)


def test_tapered_shelled_rounded_hexagon_builds():
    solid = PrismFeature("p", "p", 30.0, 20.0, taper_angle=5.0, wall_thickness=2.0, outer_round=2.0,
                         inner_round=1.0).build_solid()
    assert solid.genus() == 0 and 0 < solid.volume() < _area(15) * 20


def test_document_add_edit_save_load_and_undo(tmp_path):
    from omacad.io.exporter import Exporter
    doc = Document()
    body = doc.add_prism(20.0, 10.0, wall_thickness=1.0)
    feat = doc.timeline.features[-1]
    assert body.name == "Hexagon 1" and feat.feature_type == "prism"
    assert doc.edit_feature(0, across_flats=30.0, sides=8)
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(_area(15, 8) * 10 - _area(14, 8) * 9, rel=1e-9)
    path = tmp_path / "hex.omacad"
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    again = loaded.timeline.features[0]
    assert (again.feature_type, again.sides, again.across_flats, again.wall_thickness) == ("prism", 8, 30.0, 1.0)
    doc.undo()
    assert doc.timeline.features[0].across_flats == 20.0 and doc.timeline.features[0].sides == 6


def test_dialog_reports_across_flats_and_sides():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.dialogs import PrismDialog
    QApplication.instance() or QApplication([])
    dlg = PrismDialog()
    dlg.spn_radius.setValue(24.0)
    dlg.spn_sides.setValue(5)
    assert dlg.get_values()[:2] == (24.0, 40.0) and dlg.sides() == 5
    assert dlg.form.labelForField(dlg.spn_radius).text() == "Across flats:"


@pytest.mark.parametrize("grouped", [True, False])
def test_hexagon_command_previews_creates_and_undoes(grouped):
    from PySide6.QtWidgets import QApplication, QMenu, QToolButton
    from omacad.ui.main_window import MainWindow
    from omacad.ui.settings import get_settings
    QApplication.instance() or QApplication([])
    get_settings().set("group_primitives", grouped)
    w = MainWindow()
    if grouped:
        menu = next(m for m in w.ribbon.findChildren(QMenu) if any(a.text() == "Prism" for a in m.actions()))
        next(a for a in menu.actions() if a.text() == "Prism").trigger()
    else:
        next(b for b in w.ribbon.findChildren(QToolButton) if b.text() == "Prism").click()
    handles = w.viewport.primitive_handles
    dlg = handles.dialog
    assert handles.kind == "prism" and dlg.windowTitle() == "Create Prism"
    assert w.viewport.preview_mesh is not None and not w.doc.bodies
    assert [label for *_, label in handles.specs()] == ["Across flats", "Height"]
    dlg.spn_wall.setValue(2.0)
    dlg.accept()
    body = next(iter(w.doc.bodies.values()))
    assert body.name == "Hexagon 1"
    assert body.manifold.volume() == pytest.approx(_area(10) * 40 - _area(8) * 38, rel=1e-9)
    w.doc.undo()
    assert not w.doc.bodies
    w.close()
