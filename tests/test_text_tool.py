"""The sketch Text tool end to end: dialog options, click to place, Text On Path by clicking a circle, edit later, one
undo step, cancel removes the text."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane, SketchText
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    return w


def _texts(w):
    return [e for e in w.doc.active_sketch.entities if isinstance(e, SketchText)]


def test_text_button_exists_and_starts_the_tool(win):
    assert win.ribbon.btn_text.text().strip() == "Text"
    win.ribbon.btn_text.click()
    assert win.viewport.sketch_tool == "TEXT" and win._text_session is not None
    assert win.inspector.current_tool_dlg is win._text_session.dlg
    assert win.viewport.text_draft is not None                       # the ghost that follows the cursor
    win._text_session.dlg.reject()


def test_click_places_the_text_and_ok_is_one_undo_step(win):
    win.prompt_text()
    dlg = win._text_session.dlg
    dlg.edt_text.setPlainText("OMACAD")
    dlg.spn_height.setValue(8.0)
    win.viewport.text_place_requested.emit((12.0, 5.0), None)
    t = _texts(win)[0]
    assert t.text == "OMACAD" and t.anchor == (12.0, 5.0) and t.height == 8.0
    dlg.edt_text.setPlainText("OMA")                                  # still editable live before OK
    dlg.cmb_h.setCurrentIndex(1)
    assert t.text == "OMA" and t.h_align == "center"
    assert len(win.doc.active_sketch.profiles) >= 3                  # the letters are profiles already
    dlg.accept()
    assert win._text_session is None and win.inspector.current_tool_dlg is None
    assert len(_texts(win)) == 1
    win.doc.undo()                                                   # placing + editing was one step
    assert _texts(win) == []


def test_cancel_removes_a_placed_text(win):
    win.prompt_text()
    win.viewport.text_place_requested.emit((0.0, 0.0), None)
    assert len(_texts(win)) == 1
    win._text_session.dlg.reject()
    assert _texts(win) == [] and win._text_session is None


def test_text_on_path_picks_a_circle(win):
    sk = win.doc.active_sketch
    circle = sk.add_circle((0.0, 0.0), 25.0)
    win.prompt_text()
    dlg = win._text_session.dlg
    dlg.cmb_type.setCurrentIndex(1)                                  # Text On Path
    assert win.viewport.text_wants_path
    win.viewport.text_place_requested.emit(None, None)               # a click that hit no curve does nothing
    assert _texts(win) == []
    dlg.edt_text.setPlainText("AROUND THE CIRCLE")
    win.viewport.text_place_requested.emit(None, circle.entity_id)
    t = _texts(win)[0]
    assert t.path_id == circle.entity_id and t.polygons()
    dlg.cmb_place.setCurrentIndex(1)                                 # Below
    assert t.placement == "below"
    dlg.accept()
    assert _texts(win)[0].path_id == circle.entity_id


def test_edit_existing_text_and_cancel_restores_it(win):
    sk = win.doc.active_sketch
    t = sk.add_text("Hello", (3.0, 4.0), height=6.0)
    win.prompt_text_edit(t.entity_id)
    dlg = win._text_session.dlg
    assert dlg.edt_text.toPlainText() == "Hello" and dlg.spn_height.value() == 6.0
    dlg.edt_text.setPlainText("Changed")
    dlg.spn_height.setValue(12.0)
    assert _texts(win)[0].text == "Changed"
    dlg.reject()
    again = _texts(win)[0]
    assert again.text == "Hello" and again.height == 6.0              # back to what it was


def test_edit_then_ok_is_one_undo_step(win):
    sk = win.doc.active_sketch
    t = sk.add_text("Hello", (3.0, 4.0), height=6.0)
    win.prompt_text_edit(t.entity_id)
    win._text_session.dlg.edt_text.setPlainText("World")
    win._text_session.dlg.accept()
    assert _texts(win)[0].text == "World"
    win.doc.undo()
    assert _texts(win)[0].text == "Hello"


def test_leaving_the_tool_before_placing_cancels(win):
    win.prompt_text()
    win.viewport.set_sketch_tool("LINE")
    assert win._text_session is None


def test_right_click_menu_offers_edit_text():
    import inspect
    from omacad.ui.viewport.viewport import Viewport3D
    src = inspect.getsource(Viewport3D._show_element_menu)
    assert "edit_text" in src and "Edit Text" in src


def test_dialog_shows_the_rows_that_fit_the_type():
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs import TextDialog
    dlg = TextDialog()
    dlg.show()
    assert dlg.cmb_v.isVisible() and dlg.flip_box.isVisible() and not dlg.cmb_place.isVisible()
    assert dlg.layout_label(dlg.flip_box).isVisible()
    dlg.cmb_type.setCurrentIndex(1)
    assert not dlg.cmb_v.isVisible() and not dlg.flip_box.isVisible() and dlg.cmb_place.isVisible() and dlg.chk_fit.isVisible()
    assert not dlg.layout_label(dlg.flip_box).isVisible()               # no "Flip:" label left behind


def test_the_font_list_is_themed_not_black(win):
    from omacad.ui.dialogs.text_dlg import ThemedFontComboBox
    win.prompt_text()
    dlg = win._text_session.dlg                                      # docked in the side panel, as in the app
    assert isinstance(dlg.cmb_font, ThemedFontComboBox)
    dlg.cmb_font.showPopup()
    css = dlg.cmb_font.view().styleSheet()
    dlg.cmb_font.hidePopup()
    assert "background-color" in css and "#000000" not in css.lower() and "rgb(0, 0, 0)" not in css
    dlg.reject()


def test_the_font_list_follows_a_light_theme_and_a_dark_one():
    from PySide6.QtGui import QColor
    from omacad.ui import theme
    from omacad.ui.dialogs.text_dlg import ThemedFontComboBox

    def background() -> float:
        value = theme.themeify(ThemedFontComboBox.POPUP_CSS).split("background-color:")[1].split(";")[0].strip()
        return QColor(value).lightnessF()                              # themeify gives #rrggbb or rgb(r, g, b)

    try:
        theme.set_fixed_theme("catppuccin-latte")
        light = background()
        theme.set_fixed_theme("tokyo-night")
        dark = background()
    finally:
        theme.set_fixed_theme(None)
        theme._palette = theme.load_palette()
    assert light > 0.7 and dark < 0.35                                 # a light theme gives a light list, a dark one a dark list


def test_cancel_keeps_other_sketch_work_done_while_the_panel_was_open(win):
    sk = win.doc.active_sketch
    win.prompt_text()
    win.viewport.text_place_requested.emit((0.0, 0.0), None)
    line = sk.add_line((50.0, 0.0), (60.0, 0.0))                     # drawn while the text panel is open
    win._text_session.dlg.reject()
    assert _texts(win) == [] and any(e.entity_id == line.entity_id for e in sk.entities)


def test_cancel_of_an_edit_resets_only_the_text(win):
    sk = win.doc.active_sketch
    t = sk.add_text("ABC", (0.0, 0.0))
    win.prompt_text_edit(t.entity_id)
    win._text_session.dlg.edt_text.setPlainText("XYZ")
    line = sk.add_line((50.0, 0.0), (60.0, 0.0))
    win._text_session.dlg.reject()
    assert t.text == "ABC" and any(e.entity_id == line.entity_id for e in sk.entities)


def test_another_tool_keeps_the_placed_text_as_its_own_undo_step(win):
    win.prompt_text()
    win._text_session.dlg.edt_text.setPlainText("HI")
    win.viewport.text_place_requested.emit((0.0, 0.0), None)
    win.viewport.set_sketch_tool("LINE")
    assert win._text_session is None and len(_texts(win)) == 1
    before = win.doc.active_sketch.to_dict()
    line = win.doc.active_sketch.add_line((50.0, 0.0), (60.0, 0.0))
    win.doc.record_sketch_change(win.doc.active_sketch, before)
    win.doc.undo()                                                    # the line goes, the text stays
    assert len(_texts(win)) == 1
    assert not any(e.entity_id == line.entity_id for e in win.doc.active_sketch.entities)
    win.doc.undo()                                                    # then the text
    assert _texts(win) == []


class _LeftClick:
    def button(self):
        from PySide6.QtCore import Qt
        return Qt.MouseButton.LeftButton


def test_text_in_box_fills_and_centres_and_refits_on_a_new_font(win):
    import pytest as _pytest
    from PySide6.QtGui import QFont
    win.prompt_text()
    dlg = win._text_session.dlg
    dlg.cmb_type.setCurrentIndex(dlg.cmb_type.findData("box"))
    dlg.edt_text.setPlainText("OMACAD")
    vp = win.viewport
    vp.set_sketch_tool("TEXT")
    for uv in ((10.0, 0.0), (70.0, 20.0)):            # two corners: a 60 x 20 box centred on (40, 10)
        vp.sketch_current_uv = uv
        vp._text_press(_LeftClick(), 0, 0)
    t = _texts(win)[0]
    x0, y0, x1, y1 = t.bbox()
    assert t.box == (60.0, 20.0)
    assert (x0 >= 10 - 1e-6 and x1 <= 70 + 1e-6 and y0 >= -1e-6 and y1 <= 20 + 1e-6)          # inside the box
    assert max(x1 - x0 - 60, y1 - y0 - 20) == _pytest.approx(0.0, abs=1e-6)                   # touches two sides
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == _pytest.approx((40.0, 10.0))                     # centred
    h_before = t.fitted_height()
    dlg.cmb_font.setCurrentFont(QFont("DejaVu Serif"))
    x0, y0, x1, y1 = t.bbox()
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == _pytest.approx((40.0, 10.0))                     # still centred
    assert max(x1 - x0 - 60, y1 - y0 - 20) == _pytest.approx(0.0, abs=1e-6)
    assert dlg.spn_height.isReadOnly() and dlg.spn_height.value() == _pytest.approx(t.fitted_height(), abs=0.01)
    assert t.fitted_height() != _pytest.approx(h_before)
    dlg.accept()
    from omacad.io.exporter import Exporter
    data = Exporter.document_to_dict(win.doc)
    again = next(e for s in data["sketches"] for e in s["entities"] if e["entity_type"] == "text")
    assert again["box"] == [60.0, 20.0] or tuple(again["box"]) == (60.0, 20.0)


def test_text_in_box_margin_keeps_room_on_every_side(win):
    """Björn #109: a margin inside the box makes the text a little smaller, still centred."""
    import pytest as _pytest
    win.prompt_text()
    dlg = win._text_session.dlg
    assert not dlg.spn_margin.isVisibleTo(dlg)
    dlg.cmb_type.setCurrentIndex(dlg.cmb_type.findData("box"))
    assert dlg.spn_margin.isVisibleTo(dlg)
    dlg.edt_text.setPlainText("OMACAD")
    vp = win.viewport
    vp.set_sketch_tool("TEXT")
    for uv in ((10.0, 0.0), (70.0, 20.0)):
        vp.sketch_current_uv = uv
        vp._text_press(_LeftClick(), 0, 0)
    t = _texts(win)[0]
    h_full = t.fitted_height()
    dlg.spn_margin.setValue(2.0)
    assert t.margin == 2.0
    x0, y0, x1, y1 = t.bbox()
    assert x0 >= 12 - 1e-6 and x1 <= 68 + 1e-6 and y0 >= 2 - 1e-6 and y1 <= 18 + 1e-6
    assert max(x1 - x0 - 56, y1 - y0 - 16) == _pytest.approx(0.0, abs=1e-6)                   # touches the margin
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == _pytest.approx((40.0, 10.0))
    assert t.fitted_height() < h_full and dlg.spn_height.value() == _pytest.approx(t.fitted_height(), abs=0.01)
    dlg.accept()
    again = SketchText.from_dict(t.to_dict())
    assert again.margin == 2.0 and again.bbox() == _pytest.approx(t.bbox())
