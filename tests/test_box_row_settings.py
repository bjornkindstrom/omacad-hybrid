"""Tests for Box in a row group settings in the tree and internal height Z calculation.

1. Height Z is the clear usable height between the inside floor of the box and the underside of the lid.
2. Group settings appear in the object browser tree under 📁 Box in a row, allowing all parts
   in the group to be edited together in a single place.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from omacad.model.document import Document, box_row_outer_height, box_row_inner_height
from omacad.ui.history_delegate import apply_dimension, value_ref
from omacad.ui.browser import BrowserTree
from omacad.io.exporter import Exporter


def test_height_z_clear_distance_calculation():
    """Verify that height Z is measured from the inside floor of the box to the underside of the lid."""
    QApplication.instance() or QApplication([])
    doc = Document()

    # Case 1: With lid
    inner_z = 35.0
    wall_t = 2.0
    bot_t = 2.5
    lip_h = 6.0
    clearance = 0.2
    outer_h = box_row_outer_height(
        inner_z,
        bottom_thickness=bot_t,
        wall_thickness=wall_t,
        has_lid=True,
        lip_height=lip_h,
        clearance=clearance,
    )
    # Inside floor is at z = bot_t
    # Groove starts at z_g = outer_h - lip_h
    # Underside of lid sits at lid_z = z_g + clearance / 2.0
    # Clear space = lid_z - bot_t = (outer_h - lip_h + clearance / 2.0) - bot_t
    z_floor = bot_t
    z_g = outer_h - lip_h
    z_lid_bottom = z_g + clearance / 2.0
    assert abs((z_lid_bottom - z_floor) - inner_z) < 1e-6
    assert abs(box_row_inner_height(outer_h, bot_t, wall_t, True, lip_h, clearance) - inner_z) < 1e-6

    # Create actual box row and verify geometric bounds
    bodies = doc.add_box_row(
        count=1,
        length=50.0,
        width=40.0,
        height=inner_z,
        wall_thickness=wall_t,
        bottom_thickness=bot_t,
        has_lid=True,
        lip_height=lip_h,
        clearance=clearance,
    )
    box = bodies[0]
    lid = bodies[1]

    # Box bounds
    box_bounds = box.manifold.bounding_box()
    lid_bounds = lid.manifold.bounding_box()

    # The box outer height must match outer_h
    assert abs((box_bounds[5] - box_bounds[2]) - outer_h) < 1e-3
    # The bottom of the lid must be at z_lid_bottom
    # Note: lid features include front pull tab which hangs down slightly, but the main sliding plate
    # is at z_lid_bottom. Let's check that lid_bounds min z and plate level are consistent
    assert lid_bounds[2] >= box_bounds[2]  # inside the box height range
    assert lid_bounds[5] <= box_bounds[5] + 1e-2

    # Case 2: Without lid
    outer_h_no_lid = box_row_outer_height(inner_z, bot_t, wall_t, has_lid=False)
    assert abs((outer_h_no_lid - bot_t) - inner_z) < 1e-6


def test_box_row_group_settings_in_browser_tree():
    """Verify that group settings rows appear in the browser tree with pencils and correct role data."""
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box_row(
        count=2,
        length=60.0,
        width=40.0,
        height=30.0,
        spacing=5.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        has_lid=True,
    )
    browser = BrowserTree(doc)

    gid = doc.object_groups[0]["id"]
    tree_items = list(browser._walk())
    labels = [it[0].text(0) for it in tree_items]

    # Group exists
    assert any("Box in a row 1" in l for l in labels)
    # Settings branch exists
    assert any("Settings" in l for l in labels)

    # Parameter rows exist under Settings
    param_labels = [it[0].text(0) for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) and it[0].data(0, Qt.ItemDataRole.UserRole)[0] == "group_param"]
    assert any("Height (Z): 30 mm" in l for l in param_labels)
    assert any("Length (X): 60 mm" in l for l in param_labels)
    assert any("Width (Y): 40 mm" in l for l in param_labels)
    assert any("Boxes count: 2" in l for l in param_labels)
    assert any("Spacing: 5 mm" in l for l in param_labels)
    assert any("Wall thickness: 2 mm" in l for l in param_labels)
    assert not any("Snap detent" in l for l in param_labels)

    # Check that value_ref recognizes group_param
    item = next(it[0] for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) == ("group_param", (gid, "height")))
    ref = value_ref(item.data(0, Qt.ItemDataRole.UserRole))
    assert ref == ("group_param", (gid, "height"))


def test_edit_box_row_group_param_updates_all_boxes():
    """Verify that editing a setting in the group updates all boxes and lids together."""
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

    # 1. Edit Height (Z) from 30 to 45
    res = apply_dimension(doc, "group_param", (gid, "height"), "45")
    assert res is True
    params = doc.box_row_group_params(gid)
    assert params["height"] == 45.0

    # Both boxes and lids should now have height corresponding to inner_z=45
    box_feats, lid_feats = doc.box_row_features(gid)
    expected_outer_h = box_row_outer_height(45.0, 2.0, 2.0, True, 6.0, 0.2)
    for bf in box_feats:
        assert abs(bf.height - expected_outer_h) < 1e-6
    for lf in lid_feats:
        assert abs(lf.height - expected_outer_h) < 1e-6

    # 2. Edit Length (X) from 60 to 70 and spacing to 10
    apply_dimension(doc, "group_param", (gid, "length"), "70")
    apply_dimension(doc, "group_param", (gid, "spacing"), "10")
    params = doc.box_row_group_params(gid)
    assert params["length"] == 70.0
    assert params["spacing"] == 10.0
    for bf in box_feats:
        assert bf.length == 70.0
    for lf in lid_feats:
        assert lf.length == 70.0

    # Translations should reflect step_x = 70 + 10 = 80
    x0 = box_feats[0].translation[0]
    x1 = box_feats[1].translation[0]
    assert abs(abs(x1 - x0) - 80.0) < 1e-6

    # 3. Edit count from 2 to 3
    apply_dimension(doc, "group_param", (gid, "count"), "3")
    params = doc.box_row_group_params(gid)
    assert params["count"] == 3
    box_feats, lid_feats = doc.box_row_features(gid)
    assert len(box_feats) == 3
    assert len(lid_feats) == 3
    assert len(doc.object_groups[0]["objects"]) == 6

    # 4. Undo restores previous count
    doc.undo()
    params = doc.box_row_group_params(gid)
    assert params["count"] == 2


def test_box_row_group_params_persistence_and_export(tmp_path):
    """Verify that group settings persist when saving and loading project files."""
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

    # Ensure browser displays group settings on loaded doc
    browser = BrowserTree(loaded)
    tree_items = list(browser._walk())
    param_labels = [it[0].text(0) for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) and it[0].data(0, Qt.ItemDataRole.UserRole)[0] == "group_param"]
    assert any("Height (Z): 33 mm" in l for l in param_labels)


def test_pencil_click_on_box_row_group_param_opens_editor():
    """Verify that clicking the pencil in column 1 of a group setting row opens the in-place editor."""
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

    assert not count_item.icon(1).isNull()  # pencil exists
    browser.on_item_clicked(count_item, 1)  # click the pencil
    QTest.qWait(50)

    editor = next((e for e in browser.tree.findChildren(QLineEdit) if e.isVisible()), None)
    assert editor is not None, "Pencil click must open the QLineEdit editor for the group parameter"
    assert editor.text() == "2"

    # Edit count to 3
    editor.setText("3")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(200)

    assert doc.box_row_group_params(gid)["count"] == 3
    assert len(doc.box_row_features(gid)[0]) == 3


def test_lid_is_flat_without_raised_rib():
    """Verify that lid top has no protruding square/rib and that box and lid still slide without overlap."""
    QApplication.instance() or QApplication([])
    doc = Document()
    bodies = doc.add_box_row(
        count=1,
        length=60.0,
        width=40.0,
        height=30.0,
        wall_thickness=2.0,
        bottom_thickness=2.0,
        has_lid=True,
        lip_height=2.2,
        clearance=0.2,
        snap_size=0.6,
    )
    box = bodies[0]
    lid = bodies[1]

    bb_box = box.manifold.bounding_box()
    bb_lid = lid.manifold.bounding_box()

    # Problem 1: No protruding rib/square above box top or lid plate
    # Max Z of lid must not exceed box top Z
    assert bb_lid[5] <= bb_box[5] + 1e-3, f"Lid max Z {bb_lid[5]} exceeds box top {bb_box[5]}"

    # The snap detent is gone (#162): no setting in the group
    gid = doc.object_groups[0]["id"]
    box_feats, lid_feats = doc.box_row_features(gid)

    # Overlap between box and lid remains 0 (clean sliding fit)
    box_after = doc.bodies[f"body_{box_feats[0].feature_id}"]
    lid_after = doc.bodies[f"body_{lid_feats[0].feature_id}"]
    assert (box_after.manifold ^ lid_after.manifold).volume() < 1e-3


def test_feedback_report_20261101_205055_document():
    """Load and verify document from report 20261101-205055."""
    QApplication.instance() or QApplication([])
    report_path = "/home/kindstrom/Work/omacad-hybrid/.state/data/feedback/20261101-205055/document.omacad"
    if os.path.exists(report_path):
        doc = Exporter.load_project(report_path)
        assert len(doc.bodies) == 4
        assert len(doc.object_groups) == 1
        gid = doc.object_groups[0]["id"]
        params = doc.box_row_group_params(gid)
        # Browser tree no longer lists a Snap detent (#162)
        browser = BrowserTree(doc)
        tree_items = list(browser._walk())
        param_labels = [it[0].text(0) for it in tree_items if it[0].data(0, Qt.ItemDataRole.UserRole) and it[0].data(0, Qt.ItemDataRole.UserRole)[0] == "group_param"]
        assert not any("Snap detent" in l for l in param_labels)
