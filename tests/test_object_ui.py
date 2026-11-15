"""Real in-tree editors and responsive browser layout."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QInputDialog
from PySide6.QtTest import QTest
from omacad.model.document import Document
from omacad.ui.browser import BrowserTree


@pytest.fixture
def browser():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 10)
    widget = BrowserTree(doc)
    widget.resize(500, 700)
    widget.show()
    widget.tree.expandAll()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def row(browser, key):
    return next(item for item, _ in browser._walk()
                if item.data(0, Qt.ItemDataRole.UserRole) == ('parameter', (browser.doc.timeline.features[0].feature_id, key)))


def wait_for(condition, timeout_ms=5000):
    """Pump the event loop until condition() holds (PySide6 has no QTest.qWaitFor)."""
    waited = 0
    while not condition() and waited < timeout_ms:
        QTest.qWait(10)
        waited += 10


def test_value_edited_inside_tree_enter_commits_and_escape_cancels(browser, monkeypatch):
    def no_dialog(*args, **kwargs):
        pytest.fail('Numeric editing opened a modal dialog')
    monkeypatch.setattr(QInputDialog, 'getText', no_dialog)
    item = row(browser, 'height')
    browser.tree.scrollToItem(item)
    QApplication.processEvents()
    QTest.mouseClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=browser.tree.visualItemRect(item).center())
    QTest.mouseDClick(browser.tree.viewport(), Qt.MouseButton.LeftButton, pos=browser.tree.visualItemRect(item).center())
    QTest.qWait(20)                                   # the editor opens once the double-click has finished
    editor = browser.tree.findChild(QLineEdit)
    assert editor is not None and editor.isVisible()
    editor.setText('2*8')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    wait_for(lambda: browser.doc.timeline.features[0].height == 16, 5000)   # applied on a deferred tick; slow CI needs more than a fixed 20 ms
    assert browser.doc.timeline.features[0].height == 16
    assert browser.doc.timeline.features[0].exprs['height'] == '2*8'
    browser.on_item_double_clicked(row(browser, 'height'), 0)
    QTest.qWait(20)
    editor = next(e for e in browser.tree.findChildren(QLineEdit) if e.isVisible())
    editor.setText('99')
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    QTest.qWait(20)
    assert browser.doc.timeline.features[0].height == 16
    browser.doc.undo()
    assert browser.doc.timeline.features[0].height == 10


def test_pencil_opens_the_value_editor_with_one_click_and_a_rebuild_does_not_close_it(browser):
    item = row(browser, 'height')
    assert not item.icon(1).isNull()                  # the pencil
    browser.on_item_clicked(item, 1)
    QTest.qWait(20)
    editor = next(e for e in browser.tree.findChildren(QLineEdit) if e.isVisible())
    browser.refresh_tree()                            # a document change while typing waits for the editor
    assert editor.isVisible()
    editor.setText('12')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(300)
    assert browser.doc.timeline.features[0].height == 12
    assert 'Height: 12' in row(browser, 'height').text(0)


def test_invalid_expression_is_reported_in_browser_without_changing_model(browser):
    browser.tree.itemDelegate().apply_value('parameter',
        (browser.doc.timeline.features[0].feature_id, 'height'), 'missing_parameter')
    assert browser.doc.timeline.features[0].height == 10
    assert browser.parameter_error is not None
    assert 'missing_parameter' in row(browser, 'height').text(0)


def test_width_grows_with_expanded_text_and_respects_small_window(browser):
    width = browser.preferred_width(1600)
    item = row(browser, 'height')
    item.setText(0, 'Height: wall_thickness * 12 + base_height + top_clearance')
    larger = browser.preferred_width(1600)
    assert larger > width
    assert larger <= 1600 * .48
    assert browser.preferred_width(500) <= 280


def test_live_preview_does_not_modify_document_or_undo_stack(browser):
    delegate = browser.tree.itemDelegate()
    original = browser.doc.snapshot()
    undo_count = len(browser.doc.undo_stack)
    seen = []
    browser.preview_changed.connect(seen.append)
    delegate.preview_value = ('parameter', (browser.doc.timeline.features[0].feature_id, 'height'), '2 cm')
    delegate.update_preview()
    assert seen[-1] is not None
    assert next(iter(seen[-1].values())).volume() == pytest.approx(2000)
    assert browser.doc.snapshot() == original
    assert len(browser.doc.undo_stack) == undo_count
    delegate.clear_preview()
    assert seen[-1] is None


def test_value_editor_is_tall_enough_to_show_what_is_typed(browser):
    """Björn: the editor sat inside the stylesheet's item padding (17 px) and cut the text off."""
    item = row(browser, 'height')
    browser.on_item_double_clicked(item, 0)
    QApplication.processEvents()
    editor = next(e for e in browser.tree.findChildren(QLineEdit) if e.isVisible())
    assert editor.height() >= editor.sizeHint().height()
    assert editor.height() >= browser.tree.visualItemRect(item).height()
    QTest.keyClick(editor, Qt.Key.Key_Escape)


def test_jar_tool_objects_hang_under_their_combine_in_the_tree():
    from omacad.model.jar import JarSpec
    doc = Document()
    doc.add_jar(JarSpec())
    widget = BrowserTree(doc)
    objects = next(item for item, _ in widget._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ('group', 'objects'))
    trunk = [objects.child(i).text(0) for i in range(objects.childCount())]
    assert trunk == ['Jar', 'Lid']
    neck = next(item for item, _ in widget._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ('object', 'object_cylinder_2'))
    assert neck.parent().data(0, Qt.ItemDataRole.UserRole) == ('feature', 'combine_3')
    widget.deleteLater()


def test_row_editor_keeps_label_in_sight_and_suggests_parameters(browser):
    """Björn: parameters can be typed in the browser, and the value's name stays visible next to the number."""
    from omacad.model.document import Parameter
    from omacad.ui.expr_spin import ExprLineEdit
    browser.doc.set_parameters([Parameter('wall', '3'), Parameter('width', '20')])
    browser.refresh_tree()
    browser.tree.expandAll()
    QApplication.processEvents()
    item = row(browser, 'height')
    browser.on_item_double_clicked(item, 0)
    QApplication.processEvents()
    editor = next(e for e in browser.tree.findChildren(ExprLineEdit) if e.isVisible())
    label = browser.tree.fontMetrics().horizontalAdvance('Height: ')
    assert editor.geometry().left() >= browser.tree.visualItemRect(item).left() + label - 2
    editor.selectAll()
    QTest.keyClicks(editor, 'w')
    assert editor.suggestions_visible() and editor._list.choices == 2      # wall, width
    QTest.keyClick(editor, Qt.Key.Key_Down)
    QTest.keyClick(editor, Qt.Key.Key_Return)                            # picks the name, does not commit
    assert editor.isVisible() and editor.text() == 'width'
    QTest.keyClicks(editor, '/2')
    assert editor._list.isVisible() and editor._list.item(0).text() == '= 10'
    QTest.keyClick(editor, Qt.Key.Key_Return)
    wait_for(lambda: browser.doc.timeline.features[0].exprs.get('height') == 'width/2', 5000)
    feature = browser.doc.timeline.features[0]
    assert feature.height == 10 and feature.exprs['height'] == 'width/2'


def test_eye_on_object_row_hides_and_shows_the_whole_object():
    """Report 20261025-115036: the top of each object's chain gets its own eye."""
    from omacad.model.jar import JarSpec
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_jar(JarSpec())
    widget = BrowserTree(doc)
    role = Qt.ItemDataRole.UserRole
    jar = next(item for item, _ in widget._walk() if item.data(0, role) == ('object', 'object_cylinder_1'))
    lid = next(oid for oid, o in doc.object_history.objects.items() if o.name == 'Lid')
    jar_bodies = list(doc.object_history.objects['object_cylinder_1'].body_ids)
    assert jar_bodies and not jar.icon(1).isNull()
    widget.on_item_clicked(jar, 1)
    assert not any(doc.bodies[b].visible for b in jar_bodies)
    assert all(doc.bodies[b].visible for b in doc.object_history.objects[lid].body_ids)
    assert not doc.object_visible('object_cylinder_1') and doc.object_visible(lid)
    jar = next(item for item, _ in widget._walk() if item.data(0, role) == ('object', 'object_cylinder_1'))
    widget.on_item_clicked(jar, 1)
    assert all(doc.bodies[b].visible for b in jar_bodies)
    widget.deleteLater()
    app.processEvents()


# =========================================================================
# Object Groups in Browser
# =========================================================================

def _rows(browser):
    return [item.text(0) for item, _ in browser._walk()]


def test_object_group_create_and_browser_hierarchy(tmp_path):
    from omacad.io.exporter import Exporter
    app = QApplication.instance() or QApplication([])
    doc = Exporter.load_project("tests/data/body_of_body.omacad")
    oids = list(doc.object_history.objects.keys())
    assert len(oids) >= 2

    gid = doc.create_object_group("My Group", [oids[0]])
    assert doc.object_group_of(oids[0]) == gid
    assert doc.object_group_of(oids[1]) is None

    browser = BrowserTree(doc)
    rows = _rows(browser)
    assert "My Group" in rows

    assert doc.rename_object_group(gid, "Renamed Group")
    browser.refresh_tree()
    assert "Renamed Group" in _rows(browser)

    assert doc.add_to_object_group(gid, oids[1])
    assert doc.object_group_of(oids[1]) == gid

    assert doc.remove_from_object_group(oids[0])
    assert doc.object_group_of(oids[0]) is None

    assert doc.remove_object_group(gid)
    assert doc.object_group_of(oids[1]) is None
    browser.refresh_tree()
    assert "Renamed Group" not in _rows(browser)

    # Save and restore
    gid2 = doc.create_object_group("Saved Group", [oids[0]])
    path = str(tmp_path / "grouped.omacad")
    Exporter.save_project(doc, path)
    loaded = Exporter.load_project(path)
    assert len(loaded.object_groups) == 1
    assert loaded.object_groups[0]["name"] == "Saved Group"
    assert loaded.object_groups[0]["objects"] == [oids[0]]
    browser.deleteLater()
    app.processEvents()


def test_object_group_selection_selects_all_bodies():
    from omacad.io.exporter import Exporter
    app = QApplication.instance() or QApplication([])
    doc = Exporter.load_project("tests/data/body_of_body.omacad")
    oids = list(doc.object_history.objects.keys())
    gid = doc.create_object_group("Boxar", oids[:2])

    doc.select_object_group(gid)
    expected_bodies = set()
    for oid in oids[:2]:
        obj = doc.object_history.objects[oid]
        expected_bodies.update(b for b in obj.body_ids if b in doc.bodies and doc.bodies[b].pickable)

    for bid, body in doc.bodies.items():
        if bid in expected_bodies:
            assert body.selected is True
        else:
            assert body.selected is False
    app.processEvents()


# =========================================================================
# Object Row Copy Menu Actions
# =========================================================================

def _object_menu(monkeypatch, browser, oid):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu
    from omacad.ui import browser as browser_module
    from omacad.ui.object_browser import ROLE
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
    from omacad.io.exporter import Exporter
    app = QApplication.instance() or QApplication([])
    doc = Exporter.load_project("tests/data/object_copy_menu.omacad")
    oid = "object_feat_sketch_1"
    assert doc.object_history.copy_sources(doc, oid) == [("move_8", "body_extrude_2")]
    browser = BrowserTree(doc)
    actions, order = _object_menu(monkeypatch, browser, oid)
    assert order[:2] == ["New linked object", "Independent copy"]
    volume = doc.bodies["body_extrude_2"].manifold.volume()
    before = set(doc.bodies)

    actions["New linked object"].trigger()
    (linked,) = set(doc.bodies) - before
    actions["Independent copy"].trigger()
    (frozen,) = set(doc.bodies) - before - {linked}
    for bid in (linked, frozen):
        assert doc.bodies[bid].manifold.volume() == pytest.approx(volume)
    assert doc.object_history.owners[linked.removeprefix("body_")] != oid

    doc.edit_feature_dimension("extrude_2", "distance", "30")
    assert doc.bodies[linked].manifold.volume() == pytest.approx(doc.bodies["body_extrude_2"].manifold.volume())
    assert doc.bodies[frozen].manifold.volume() == pytest.approx(volume)
    browser.deleteLater()
    app.processEvents()


def test_object_stepped_back_is_copied_as_shown():
    from omacad.io.exporter import Exporter
    app = QApplication.instance() or QApplication([])
    doc = Exporter.load_project("tests/data/object_copy_menu.omacad")
    oid = "object_feat_sketch_1"
    doc.object_step_to(oid, "shell_3")
    assert doc.object_history.copy_sources(doc, oid) == [("shell_3", "body_extrude_2")]


def test_a_primitive_just_made_can_be_copied_from_its_row_and_its_step(monkeypatch):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu
    from omacad.ui import browser as browser_module
    from omacad.ui.object_browser import FEATURE_ROLE
    app = QApplication.instance() or QApplication([])
    doc = Document()
    box = doc.add_box(10, 10, 10)
    fid = doc.timeline.last_added.feature_id
    oid = doc.object_history.owners[fid]
    assert not doc.step_states
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
    browser.deleteLater()
    app.processEvents()


def test_a_linked_copy_is_named_linked_copy_and_shown_in_italic():
    from omacad.ui.object_browser import ROLE
    app = QApplication.instance() or QApplication([])
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
    assert italic == mine
    assert any(item.text(0) == "Box 1 Linked copy" for item in items)
    browser.deleteLater()
    app.processEvents()


def test_links_named_branch_in_older_files_read_linked_copy():
    from omacad.io.exporter import Exporter
    doc = Exporter.load_project("tests/data/linked_copy_of_primitive_step.omacad")
    assert doc.bodies["body_branch_4"].name == "Box 1 Linked copy"
