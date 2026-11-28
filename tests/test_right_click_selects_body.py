"""A right-click on a body that is not selected makes it the selection, so the menu's commands act on it."""
from omacad.model.document import Document


def _view_with_two_boxes():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    doc.add_box(20, 20, 20)
    doc.add_box(20, 20, 20)
    doc.move_body(list(doc.bodies)[1], dx=60.0)
    a, b = list(doc.bodies)
    vp = Viewport3D(doc)
    vp.resize(800, 600)
    vp.set_view("iso")
    vp.zoom_fit()
    return doc, vp, a, b


def _screen_centre(vp, doc, bid):
    m = doc.bodies[bid].manifold.bounding_box()
    centre = [(m[i] + m[i + 3]) / 2 for i in range(3)]
    return vp.world_to_screen(centre)


def test_right_click_on_an_unselected_body_selects_it_and_keeps_a_selected_one():
    doc, vp, a, b = _view_with_two_boxes()
    doc.select_body(a)
    x, y = _screen_centre(vp, doc, b)
    assert vp.pick_body(x, y) == b
    vp._select_right_clicked_body(x, y)
    assert doc.selected_body_ids == [b]                      # Shell, Fillet, Move ... now get the clicked body
    doc.select_body(a, multi=True)
    vp._select_right_clicked_body(x, y)
    assert sorted(doc.selected_body_ids) == sorted([a, b])   # clicking inside the selection keeps all of it
    vp.deleteLater()


def test_nothing_changes_while_a_tool_is_open():
    doc, vp, a, b = _view_with_two_boxes()
    doc.select_body(a)
    vp.active_tool_title = lambda: "Shell"
    vp._select_right_clicked_body(*_screen_centre(vp, doc, b))
    assert doc.selected_body_ids == [a]
    vp.deleteLater()
