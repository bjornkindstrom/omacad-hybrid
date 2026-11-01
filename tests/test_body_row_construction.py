"""Requests 144, 146, 147: a step-named body reads "Body of <object>", a body can become a construction body
(dull, see-through, never picked), and a click on an object row selects its bodies in the view."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.ui.browser import BrowserTree
from omacad.ui.object_browser import ROLE

DOC = "tests/data/body_of_body.omacad"
OID = "object_feat_sketch_2"
BID = "body_extrude_4"


def _rows(browser):
    return [item.text(0).replace("🧊 ", "") for item, _ in browser._walk()]


def test_body_row_is_named_after_its_object():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    browser = BrowserTree(doc)
    assert "Body of Body 2" in _rows(browser)
    doc.rename_object(OID, "Bänk")
    browser.refresh_tree()
    assert "Body of Bänk" in _rows(browser)
    doc.rename_item("body", BID, "Lock")          # a name the user gave the body stays
    browser.refresh_tree()
    assert "Lock" in _rows(browser)


def test_construction_body_is_saved_and_never_picked(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    body = doc.bodies[BID]
    assert body.pickable
    doc.set_body_construction(BID, True)
    assert doc.bodies[BID].construction and not doc.bodies[BID].pickable
    path = str(tmp_path / "c.omacad")
    Exporter.save_project(doc, path)
    again = Exporter.load_project(path)
    assert again.bodies[BID].construction
    doc.undo()
    assert not doc.bodies[BID].construction
    doc.redo()
    assert doc.bodies[BID].construction


def test_click_on_object_row_selects_its_bodies():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    browser = BrowserTree(doc)
    item = next(i for i, _ in browser._walk() if i.data(0, ROLE) == ("object", OID))
    browser.on_item_clicked(item, 0)
    assert doc.bodies[BID].selected
    assert doc.selected_body_ids == [BID]
