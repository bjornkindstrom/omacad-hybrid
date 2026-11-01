"""Requests #149, #150: Object grouping in the browser and group selection / coloring."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.ui.browser import BrowserTree
from omacad.ui.object_browser import ROLE

DOC = "tests/data/body_of_body.omacad"


def _rows(browser):
    return [item.text(0) for item, _ in browser._walk()]


def test_object_group_create_and_browser_hierarchy():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    oids = list(doc.object_history.objects.keys())
    assert len(oids) >= 2

    # Create a group with the first object
    gid = doc.create_object_group("My Group", [oids[0]])
    assert doc.object_group_of(oids[0]) == gid
    assert doc.object_group_of(oids[1]) is None

    browser = BrowserTree(doc)
    rows = _rows(browser)
    assert "My Group" in rows

    # Renaming group
    assert doc.rename_object_group(gid, "Renamed Group")
    browser.refresh_tree()
    assert "Renamed Group" in _rows(browser)

    # Adding second object to group
    assert doc.add_to_object_group(gid, oids[1])
    assert doc.object_group_of(oids[1]) == gid

    # Removing first object from group (ungroup individual)
    assert doc.remove_from_object_group(oids[0])
    assert doc.object_group_of(oids[0]) is None

    # Deleting group (ungroups all)
    assert doc.remove_object_group(gid)
    assert doc.object_group_of(oids[1]) is None
    browser.refresh_tree()
    assert "Renamed Group" not in _rows(browser)


def test_object_group_selection_selects_all_bodies():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    oids = list(doc.object_history.objects.keys())
    gid = doc.create_object_group("Boxar", oids[:2])

    doc.select_object_group(gid)
    # Check that bodies belonging to these objects are selected
    expected_bodies = set()
    for oid in oids[:2]:
        obj = doc.object_history.objects[oid]
        expected_bodies.update(b for b in obj.body_ids if b in doc.bodies and doc.bodies[b].pickable)

    for bid, body in doc.bodies.items():
        if bid in expected_bodies:
            assert body.selected is True
        else:
            assert body.selected is False


def test_object_group_save_and_restore(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(DOC)
    oids = list(doc.object_history.objects.keys())
    gid = doc.create_object_group("Saved Group", [oids[0]])

    path = str(tmp_path / "grouped.omacad")
    Exporter.save_project(doc, path)

    loaded = Exporter.load_project(path)
    assert len(loaded.object_groups) == 1
    assert loaded.object_groups[0]["name"] == "Saved Group"
    assert loaded.object_groups[0]["objects"] == [oids[0]]
