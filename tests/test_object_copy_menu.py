"""Report 20261101-131319: the object row (the one with the thumbnail) offers a linked or an independent
copy of the object as it stands now, at the top of its menu; before, only each step's own menu had them."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMenu

from omacad.io.exporter import Exporter
from omacad.ui import browser as browser_module
from omacad.ui.browser import BrowserTree
from omacad.ui.object_browser import ROLE

DOC = "tests/data/object_copy_menu.omacad"
OID = "object_feat_sketch_1"


def _object_menu(monkeypatch, browser, oid):
    shown = []

    class Recorded(QMenu):
        def exec(self, *args):
            shown.append(self)

    monkeypatch.setattr(browser_module, "QMenu", Recorded)
    item = next(item for item, _ in browser._walk() if item.data(0, ROLE) == ("object", oid))
    monkeypatch.setattr(browser.tree, "itemAt", lambda pos: item)
    browser.show_context_menu(QPoint(0, 0))
    return {a.text(): a for a in shown[0].actions() if a.text()}, [a.text() for a in shown[0].actions()]


def test_object_row_copies_the_finished_object(monkeypatch):
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    assert doc.object_history.copy_sources(doc, OID) == [("move_8", "body_extrude_2")]
    browser = BrowserTree(doc)
    actions, order = _object_menu(monkeypatch, browser, OID)
    assert order[:2] == ["New linked object", "Independent copy"]
    volume = doc.bodies["body_extrude_2"].manifold.volume()
    before = set(doc.bodies)

    actions["New linked object"].trigger()
    (linked,) = set(doc.bodies) - before
    actions["Independent copy"].trigger()
    (frozen,) = set(doc.bodies) - before - {linked}
    for bid in (linked, frozen):
        assert doc.bodies[bid].manifold.volume() == pytest.approx(volume)
    assert doc.object_history.owners[linked.removeprefix("body_")] != OID

    doc.edit_feature_dimension("extrude_2", "distance", "30")      # the linked copy follows, the other stays
    assert doc.bodies[linked].manifold.volume() == pytest.approx(doc.bodies["body_extrude_2"].manifold.volume())
    assert doc.bodies[frozen].manifold.volume() == pytest.approx(volume)


def test_object_stepped_back_is_copied_as_shown():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    doc.object_step_to(OID, "shell_3")
    assert doc.object_history.copy_sources(doc, OID) == [("shell_3", "body_extrude_2")]
