"""Björn #110: starred values gather under ⭐ Favorites in the browser, in named groups, and can be changed there:
the text of each hook, or a step's size."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QMenu

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.browser import BrowserTree
from omacad.ui.history_delegate import apply_dimension
from omacad.ui.object_browser import ROLE

DOC = "tests/data/favorites_hooks.omacad"


@pytest.fixture
def doc():
    QApplication.instance() or QApplication([])
    return Exporter.load_project(DOC)


def _rows(browser):
    return {item.data(0, ROLE): item.text(0) for item, _ in browser._walk() if item.data(0, ROLE)}


def test_star_values_into_groups_and_change_them_from_the_browser(doc):
    browser = BrowserTree(doc)
    assert ("favorites", "") not in _rows(browser)
    for sid, group in (("sketch_2", "Krok Noah"), ("sketch_4", "Krok Milo"), ("sketch_6", "Krok Björn")):
        assert doc.add_favorite(["text", sid, "text_9"], group)
    doc.add_favorite(["parameter", "extrude_2", "distance"], "Krok Noah")
    browser.refresh_tree()
    rows = _rows(browser)
    assert [g["name"] for g in doc.favorites] == ["Krok Noah", "Krok Milo", "Krok Björn"]
    assert rows[("fav", ("text", "sketch_4", "text_9"))] == "Sketch 2 (copy) · Text: M"
    assert rows[("fav", ("parameter", "extrude_2", "distance"))] == "Extrude 1 · Distance: 20 mm"
    assert ("fav_group", "Krok Noah") in rows

    volume = doc.bodies["body_extrude_8"].manifold.volume()
    apply_dimension(doc, "text", ("sketch_4", "text_9"), "W")            # what the row editor commits
    assert doc.sketches["sketch_4"].get_entity("text_9").text == "W"
    assert doc.bodies["body_extrude_8"].manifold.volume() != pytest.approx(volume)
    assert doc.sketches["sketch_2"].get_entity("text_9").text == "N"
    doc.undo()
    assert doc.sketches["sketch_4"].get_entity("text_9").text == "M"
    assert doc.bodies["body_extrude_8"].manifold.volume() == pytest.approx(volume)

    apply_dimension(doc, "parameter", ("extrude_2", "distance"), "25")
    assert doc.bodies["body_extrude_2"].manifold.bounding_box()[5] == pytest.approx(25)


def test_favorites_are_saved_undone_renamed_and_removed(doc, tmp_path):
    doc.add_favorite(["text", "sketch_2", "text_9"], "Krok Noah")
    doc.add_favorite(["dimension", "sketch_1", "d1"], "Krok Noah")
    doc.add_favorite(["dimension", "sketch_1", "d1"], "Sizes")              # one group per value: it moves
    assert doc.favorites == [{"name": "Krok Noah", "items": [["text", "sketch_2", "text_9"]]},
                             {"name": "Sizes", "items": [["dimension", "sketch_1", "d1"]]}]
    path = tmp_path / "fav.omacad"
    Exporter.save_project(doc, str(path))
    assert Exporter.load_project(str(path)).favorites == doc.favorites
    assert doc.rename_favorite_group("Sizes", "Mått")
    assert not doc.rename_favorite_group("Mått", "Krok Noah")              # names stay unique
    doc.undo()
    assert [g["name"] for g in doc.favorites] == ["Krok Noah", "Sizes"]
    assert doc.remove_favorite(["text", "sketch_2", "text_9"])
    assert [g["name"] for g in doc.favorites] == ["Sizes"]                # an empty group goes
    assert doc.remove_favorite_group("Sizes") and doc.favorites == []
    assert Document().favorites == []


def test_context_menu_offers_groups_and_new_group(doc):
    browser = BrowserTree(doc)
    doc.add_favorite(["text", "sketch_2", "text_9"], "Krok Noah")
    menu = QMenu()
    browser._favorite_menu(menu, ["text", "sketch_4", "text_9"])
    sub = next(a.menu() for a in menu.actions() if a.menu())
    assert [a.text() for a in sub.actions() if a.text()] == ["Krok Noah", "New group…"]
    assert browser._owner_name(["text", "sketch_4", "text_9"]) == "Krok Milo"
    assert browser._owner_name(["parameter", "extrude_2", "distance"]) == "Krok Noah"
    menu = QMenu()
    browser._favorite_menu(menu, ["text", "sketch_2", "text_9"])
    assert any(a.text() == "Remove from favorites" for a in menu.actions())
