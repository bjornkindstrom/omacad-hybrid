"""The browser tree is built like Fusion 360's: Document Settings, Named Views, Origin, Analysis, Bodies, Sketches."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(10, 10, 10)
    sk = w.doc.start_sketch("XY")
    sk.add_rect((0, 0), (5, 5))
    w.doc.finish_sketch() if hasattr(w.doc, "finish_sketch") else None
    return w


def top_labels(w):
    root = w.browser.tree.topLevelItem(0)
    return [root.child(i).text(0) for i in range(root.childCount())]


def find(w, kind, name=""):
    stack = [w.browser.tree.topLevelItem(0)]
    while stack:
        it = stack.pop()
        if it.data(0, Qt.ItemDataRole.UserRole) == (kind, name):
            return it
        stack += [it.child(i) for i in range(it.childCount())]


def test_structure_follows_fusion(win):
    assert win.browser.tree.topLevelItem(0).text(0).endswith("(Unsaved)")
    assert top_labels(win) == ["Document Settings", "Named Views", "Origin", "Analysis", "Objects"]
    views = find(win, "view", "HOME").parent()
    assert [views.child(i).text(0) for i in range(views.childCount())] == ["Home", "Top", "Front", "Right", "Back", "Left", "Bottom"]


def test_sketches_and_bodies_have_object_parents(win):
    sid = next(iter(win.doc.sketches))
    bid = next(iter(win.doc.bodies))
    sketch = find(win, "sketch", sid)
    body = find(win, "body", bid)
    assert sketch.parent().data(0, Qt.ItemDataRole.UserRole)[0] == "object"
    assert body.parent().data(0, Qt.ItemDataRole.UserRole)[0] == "object"
    assert sketch.parent() is not body.parent()


def test_group_eye_hides_and_shows_everything_in_it(win):
    win.doc.add_cylinder(2, 5)
    assert all(b.visible for b in win.doc.bodies.values())
    win.browser.on_item_clicked(find(win, "group", "objects"), 1)
    assert not any(b.visible for b in win.doc.bodies.values())
    win.browser.on_item_clicked(find(win, "group", "objects"), 1)
    assert all(b.visible for b in win.doc.bodies.values())


def test_v_toggles_the_selected_item_and_named_view_click_emits(win):
    seen = []
    win.browser.named_view_requested.connect(seen.append)
    body_id = next(iter(win.doc.bodies))
    item = find(win, "body", body_id)
    win.browser.tree.setCurrentItem(item)
    win.browser.toggle_selected_visibility()
    assert not win.doc.bodies[body_id].visible
    win.browser.on_item_clicked(find(win, "view", "TOP"), 0)
    assert seen == ["TOP"]


def test_find_helpers(win):
    sk_id = next(iter(win.doc.sketches))
    assert win.doc.feature_index_for("sketch", sk_id) is not None
    body_id = next(iter(win.doc.bodies))
    assert win.doc.feature_index_for("body", body_id) is not None
    win.find_in_window("body", body_id)
    win.find_in_timeline("body", body_id)
    assert win.doc.feature_index_for("sketch", "nope") is None


def test_expansion_is_kept_with_the_new_tree(win):
    named = find(win, "view", "HOME").parent()
    named.setExpanded(True)
    win.doc.add_cylinder(2, 5)
    assert find(win, "view", "HOME").parent().isExpanded()


def test_right_click_on_a_sketch_line_offers_edit_sketch():
    """In the 3D view (not in sketch mode) a right-click on a sketch's lines finds the sketch."""
    import numpy as np
    QApplication.instance() or QApplication([])
    from omacad.model.document import Document
    from omacad.ui.viewport import Viewport3D
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_line((0, 0), (40, 0))
    d.finish_sketch() if hasattr(d, "finish_sketch") else setattr(d, "active_sketch", None)
    v = Viewport3D(d)
    v.resize(800, 600)
    v.azimuth, v.elevation = 0.0, 89.9
    on_line = v.world_to_screen(sk.plane.uv_to_world(20.0, 0.0))
    away = v.world_to_screen(sk.plane.uv_to_world(20.0, 30.0))
    assert v._sketch_line_at(*on_line) == sk.sketch_id
    assert v._sketch_line_at(*away) is None
    sk.visible = False
    assert v._sketch_line_at(*on_line) is None            # hidden sketches are not picked


def test_browser_is_only_as_tall_as_its_rows_and_grows_when_a_branch_opens(win):
    """The browser leaves the drawing area below it free; it fills the height (and scrolls) only when it must."""
    b = win.browser
    root = b.tree.topLevelItem(0)
    for i in range(root.childCount()):
        root.child(i).setExpanded(False)
    short = b.preferred_height(2000)
    assert short < 2000
    root.child(0).setExpanded(True)                     # Document Settings opens: two more rows
    assert b.preferred_height(2000) > short
    assert b.preferred_height(150) == 150               # no more room: the tree scrolls inside the cap
