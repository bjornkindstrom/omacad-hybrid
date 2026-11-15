"""Box in a row UI, browser tree, settings editing, and lid toggle tests."""
import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtTest import QTest
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document, box_row_outer_height
from omacad.ui.browser import BrowserTree
from omacad.ui.history_delegate import apply_dimension


def test_lid_viewport_toggle():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(count=2, has_lid=True)

    assert doc.has_lids() is True
    assert doc.are_lids_visible() is True

    res = doc.toggle_lids_visibility()
    assert res is False
    assert doc.are_lids_visible() is False
    lids = [b for b in doc.bodies.values() if b.is_lid]
    for lid in lids:
        assert lid.visible is False

    res = doc.toggle_lids_visibility()
    assert res is True
    assert doc.are_lids_visible() is True
    for lid in lids:
        assert lid.visible is True


def test_box_row_group_settings_in_browser_tree():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(
        count=2,
        length=60.0,
        width=40.0,
        height=30.0,
        spacing=0.0,
        has_lid=True,
    )
    browser = BrowserTree(doc)
    tree_items = list(browser._walk())
    gid = doc.object_groups[0]["id"]

    roles = [it[0].data(0, Qt.ItemDataRole.UserRole) for it in tree_items]
    assert ("group_param", (gid, "count")) in roles
    assert ("group_param", (gid, "length")) in roles
    assert ("group_param", (gid, "width")) in roles
    assert ("group_param", (gid, "height")) in roles
    assert ("group_param", (gid, "spacing")) in roles
    assert ("group_param", (gid, "wall_thickness")) in roles
    assert ("group_param", (gid, "bottom_thickness")) in roles
    assert ("group_param", (gid, "outer_round")) in roles
    assert ("group_param", (gid, "inner_round")) in roles
    assert ("group_param", (gid, "honeycomb")) in roles


def test_edit_box_row_group_param_updates_all_boxes():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(
        count=2,
        length=60.0,
        width=40.0,
        height=30.0,
        spacing=0.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        has_lid=True,
    )
    gid = doc.object_groups[0]["id"]

    res = apply_dimension(doc, "group_param", (gid, "height"), "45")
    assert res is True
    params = doc.box_row_group_params(gid)
    assert params["height"] == 45.0

    box_feats, lid_feats = doc.box_row_features(gid)
    expected_outer_h = box_row_outer_height(45.0, 2.0, 2.0, True, 6.0, 0.2)
    for bf in box_feats:
        assert abs(bf.height - expected_outer_h) < 1e-6
    for lf in lid_feats:
        assert abs(lf.height - expected_outer_h) < 1e-6

    apply_dimension(doc, "group_param", (gid, "length"), "70")
    apply_dimension(doc, "group_param", (gid, "spacing"), "10")
    params = doc.box_row_group_params(gid)
    assert params["length"] == 70.0
    assert params["spacing"] == 10.0
    for bf in box_feats:
        assert bf.length == 70.0
    for lf in lid_feats:
        assert lf.length == 70.0

    x0 = box_feats[0].translation[0]
    x1 = box_feats[1].translation[0]
    assert abs(abs(x1 - x0) - 80.0) < 1e-6

    apply_dimension(doc, "group_param", (gid, "count"), "3")
    params = doc.box_row_group_params(gid)
    assert params["count"] == 3
    box_feats, lid_feats = doc.box_row_features(gid)
    assert len(box_feats) == 3
    assert len(lid_feats) == 3
    assert len(doc.object_groups[0]["objects"]) == 6

    doc.undo()
    params = doc.box_row_group_params(gid)
    assert params["count"] == 2


def test_box_row_group_params_persistence_and_export(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(
        count=2,
        length=55.0,
        width=35.0,
        height=28.0,
        wall_thickness=2.2,
        has_lid=True,
    )
    gid = doc.object_groups[0]["id"]
    apply_dimension(doc, "group_param", (gid, "height"), "33")

    file_path = str(tmp_path / "saved_group.omacad")
    Exporter.save_project(doc, file_path)

    loaded = Exporter.load_project(file_path)
    assert len(loaded.object_groups) == 1
    loaded_gid = loaded.object_groups[0]["id"]
    loaded_params = loaded.box_row_group_params(loaded_gid)
    assert loaded_params["height"] == 33.0
    assert loaded_params["length"] == 55.0

    browser = BrowserTree(loaded)
    tree_items = list(browser._walk())
    param_labels = [it[0].text(0) for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) and it[0].data(0, Qt.ItemDataRole.UserRole)[0] == "group_param"]
    assert any("Height (Z): 33 mm" in l for l in param_labels)


def test_pencil_click_on_box_row_group_param_opens_editor():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(count=2, length=60.0, width=40.0, height=30.0, has_lid=True)
    browser = BrowserTree(doc)
    browser.resize(500, 700)
    browser.show()
    browser.tree.expandAll()
    app.processEvents()
    gid = doc.object_groups[0]["id"]

    tree_items = list(browser._walk())
    count_item = next(it[0] for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) == ("group_param", (gid, "count")))

    assert not count_item.icon(1).isNull()
    browser.on_item_clicked(count_item, 1)
    QTest.qWait(50)

    editor = next((e for e in browser.tree.findChildren(QLineEdit) if e.isVisible()), None)
    assert editor is not None
    assert editor.text() == "2"

    editor.setText("3")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    for _ in range(500):
        if doc.box_row_group_params(gid)["count"] == 3:
            break
        QTest.qWait(10)

    assert doc.box_row_group_params(gid)["count"] == 3
    assert len(doc.box_row_features(gid)[0]) == 3
    browser.close()
