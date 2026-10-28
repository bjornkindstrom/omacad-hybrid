"""The origin (axes and planes) can be hidden as a whole or piece by piece, and the choice is saved with the file."""
from omacad.io.exporter import Exporter
from omacad.model.document import Document


def test_defaults_axes_on_planes_off():
    d = Document()
    assert d.origin_visible("all")
    assert all(d.origin_visible("axis", n) for n in "XYZ")
    assert not any(d.origin_visible("plane", n) for n in ("XY", "XZ", "YZ"))


def test_master_switch_and_single_parts():
    d = Document()
    seen = []
    d.add_change_listener(lambda: seen.append(1))
    d.set_origin_visibility("axis", "Y", False)
    assert not d.origin_visible("axis", "Y") and d.origin_visible("axis", "X")
    d.set_origin_visibility("plane", "XZ", True)
    assert d.origin_visible("plane", "XZ")
    d.set_origin_visibility("all", "", False)
    assert not d.origin_visible("axis", "X") and not d.origin_visible("plane", "XZ")
    d.set_origin_visibility("axis", "Z", True)      # a single part switches the origin back on
    assert d.origin_visible("all") and d.origin_visible("axis", "Z")
    d.set_origin_visibility("axis", "Q", True)      # unknown name: ignored
    assert len(seen) == 4


def test_saved_and_restored():
    d = Document()
    d.set_origin_visibility("axis", "X", False)
    d.set_origin_visibility("plane", "YZ", True)
    data = Exporter.document_to_dict(d)
    d2 = Document()
    Exporter.apply_dict(d2, data)
    assert not d2.origin_visible("axis", "X") and d2.origin_visible("axis", "Y")
    assert d2.origin_visible("plane", "YZ")
    old = {k: v for k, v in data.items() if k != "origin_vis"}   # file from before this existed
    d3 = Document()
    d3.set_origin_visibility("axis", "X", False)
    Exporter.apply_dict(d3, old)
    assert d3.origin_visible("axis", "X")


def test_browser_eyes_and_view_menu_follow_the_document():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow()

    def item(kind, name):
        stack = [w.browser.tree.topLevelItem(i) for i in range(w.browser.tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            if it.data(0, 0x100) == (kind, name):
                return it
            stack += [it.child(i) for i in range(it.childCount())]

    w.browser.on_item_clicked(item("axis", "Y"), 1)
    assert not w.doc.origin_visible("axis", "Y")
    assert not w._origin_actions[("axis", "Y")].isChecked()
    w._origin_actions[("plane", "XY")].setChecked(True)
    assert w.doc.origin_visible("plane", "XY")
    w.browser.on_item_clicked(item("origin", "all"), 1)
    assert not w.doc.origin_visible("all") and not w._origin_actions[("all", "")].isChecked()


def test_tree_keeps_expanded_origin_when_toggling():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow()
    tree = w.browser.tree
    def origin_node():
        stack = [tree.topLevelItem(0)]
        while stack:
            it = stack.pop()
            if it.data(0, 0x100) == ("origin", "all"):
                return it
            stack += [it.child(i) for i in range(it.childCount())]
    origin_node().setExpanded(True)
    w.doc.set_origin_visibility("plane", "XY", True)
    assert origin_node().isExpanded()
    origin_node().setExpanded(False)
    w.doc.set_origin_visibility("plane", "XY", False)
    assert not origin_node().isExpanded()
