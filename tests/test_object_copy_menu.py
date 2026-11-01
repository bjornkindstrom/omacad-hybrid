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


def test_a_primitive_just_made_can_be_copied_from_its_row_and_its_step(monkeypatch):
    """A primitive is built on its own, without the full rebuild that records step states, so both menus left out
    the copy entries until something else rebuilt the document."""
    from omacad.model.document import Document
    from omacad.ui.object_browser import FEATURE_ROLE
    QApplication.instance() or QApplication([])
    doc = Document()
    box = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    oid = doc.object_history.owners[fid]
    assert not doc.step_states                                  # no rebuild has happened yet
    browser = BrowserTree(doc)
    actions, order = _object_menu(monkeypatch, browser, oid)
    assert order[:2] == ["New linked object", "Independent copy"]
    actions["New linked object"].trigger()
    assert len(doc.bodies) == 2
    for bid in doc.bodies:
        assert doc.bodies[bid].manifold.volume() == pytest.approx(1000)

    cyl = doc.add_cylinder(3, 5)
    cfid = doc.timeline.last_added.feature_id
    step = next(item for item, _ in browser._walk() if item.data(0, FEATURE_ROLE) == cfid)
    shown = []

    class Recorded(QMenu):
        def exec(self, *args):
            shown.append(self)

    monkeypatch.setattr(browser_module, "QMenu", Recorded)
    monkeypatch.setattr(browser.tree, "itemAt", lambda pos: step)
    browser.show_context_menu(QPoint(0, 0))
    texts = [a.text() for a in shown[-1].actions()]
    assert "Independent copy of " + cyl.body_id in texts
    assert box.body_id in doc.bodies


def test_a_linked_copy_is_named_linked_copy_and_shown_in_italic():
    from omacad.model.document import Document
    QApplication.instance() or QApplication([])
    doc = Document()
    box = doc.add_box(10, 10, 10)
    linked = doc.branch_object("box_1", box.body_id)
    copy = doc.branch_object("box_1", box.body_id, linked=False)
    assert linked.name == "Box 1 Linked copy" and copy.name == "Box 1 Copy"
    browser = BrowserTree(doc)
    lid = linked.body_id.removeprefix("body_")
    oid = doc.object_history.owners[lid]
    mine = {("object", oid), ("feature", lid), ("body", linked.body_id)}
    items = [item for item, _ in browser._walk()]
    italic = {item.data(0, ROLE) for item in items if item.font(0).italic()}
    assert italic == mine                       # the link's object, step and body; nothing else
    assert any(item.text(0) == "Box 1 Linked copy" for item in items)


def test_links_named_branch_in_older_files_read_linked_copy():
    doc = Exporter.load_project("tests/data/linked_copy_of_primitive_step.omacad")
    assert doc.bodies["body_branch_4"].name == "Box 1 Linked copy"
