"""Björn's requests #91-#99: readable value boxes, lines ending on a circle close a face, browser dimension
picks, 45°/90° line snaps and hidden bodies left alone by Extrude."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from omacad.model.document import Document
from omacad.model.sketch import SketchCircle, SketchLine
from omacad.model.sketch_snap import SketchSnapper


def test_value_box_text_differs_from_its_box_in_every_role_theme():
    from omacad.ui import theme
    try:
        for name in theme.ROLE_THEMES:
            theme.set_fixed_theme(name)
            box, text = theme.qcolor(37, 40, 44), theme.qcolor(224, 227, 231)
            assert abs(box.lightness() - text.lightness()) > 100, name
    finally:
        theme.set_fixed_theme(theme.DEFAULT_ROLE_THEME)


def test_lines_ending_on_a_circle_close_the_region_between_them():
    sk = Document().start_sketch("XY")
    sk.entities = [SketchCircle("c", (0, 0), 42.720018726587654),
                   SketchLine("a", (-29.681941525473725, 30.69996180908213), (-90.0, 105.0)),
                   SketchLine("b", (-90.0, 105.0), (135.0, 85.0)),
                   SketchLine("d", (135.0, 85.0), (38.67300662964384, 18.103164264522604))]
    assert len(sk.solve_profiles()) == 2


def test_line_snaps_to_45_degrees_and_square_to_the_previous_line():
    sk = Document().start_sketch("XY")
    r = SketchSnapper.snap((20.3, 19.6), sk, start_uv=(0.0, 0.0), snap_distance=1.0, enable_grid_snap=False)
    assert r.snap_type == "ANGLE" and r.label == "45°" and r.uv[0] == pytest.approx(r.uv[1])
    sk.entities = [SketchLine("l", (-30.0, 10.0), (0.0, 0.0))]
    r = SketchSnapper.snap((10.4, 29.5), sk, start_uv=(0.0, 0.0), snap_distance=1.0, enable_grid_snap=False)
    assert r.snap_type == "ANGLE" and r.label == "90°"
    assert r.uv[0] * -30.0 + r.uv[1] * 10.0 == pytest.approx(0.0, abs=1e-9)


def test_hidden_body_is_not_cut_or_joined():
    doc = Document()
    doc.add_box(20, 20, 10)
    bid = next(iter(doc.bodies))
    volume = doc.bodies[bid].manifold.volume()
    doc.bodies[bid].visible = False
    sk = doc.start_sketch("XY")
    sk.add_circle((0, 0), 3)
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5, operation="cut")
    assert doc.bodies[bid].manifold.volume() == pytest.approx(volume)
    doc.extrude_profile(sk.sketch_id, 0, 5, operation="auto")
    assert doc.timeline.features[-1].operation == "new_body"
    assert doc.bodies[bid].manifold.volume() == pytest.approx(volume)


def test_dimension_row_in_browser_reports_what_it_measures():
    from omacad.ui.browser import BrowserTree
    app = QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((0, 0), 5)
    doc.finish_sketch()
    sk.dimensions.clear()
    from omacad.model.sketch_types import SketchDimension
    sk.dimensions.append(SketchDimension("d1", "d1", "DIAMETER", sk.entities[0].entity_id, 10.0))
    widget = BrowserTree(doc)
    widget.tree.expandAll()
    seen = []
    widget.dimension_selected.connect(lambda s, d: seen.append((s, d)))
    row = next(item for item, _ in widget._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ('dimension', (sk.sketch_id, 'd1')))
    widget.on_item_clicked(row, 0)
    assert seen[-1] == (sk.sketch_id, 'd1')
    other = next(item for item, _ in widget._walk() if (item.data(0, Qt.ItemDataRole.UserRole) or ('',))[0] == 'sketch')
    widget.on_item_clicked(other, 0)
    assert seen[-1] == ("", "")
    widget.deleteLater()
    app.processEvents()
