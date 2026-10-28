"""Help & Commands (F1) replaces the picture guides: every function grouped as in the ribbon with help text, a
keyword search, and Enter runs the selected function."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.ui import commands
from omacad.ui.help_topics import search, topics
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()


def test_every_ribbon_command_has_help():
    titled = {t.cid for t in topics() if t.cid}
    in_ribbon = set()
    for _tab, groups in (("S", commands.SOLID_GROUPS), ("K", commands.SKETCH_GROUPS)):
        for _g, items in groups:
            for item in items:
                in_ribbon |= set(item[4]) if isinstance(item, tuple) else {item}
    in_ribbon |= set(commands.PATTERNS)
    missing = {c for c in in_ribbon if c in commands.COMMANDS and c != "settings"} - titled
    assert not missing
    assert all(t.text for t in topics())


def test_search_finds_by_other_words():
    assert search("hole")[0].title == "Hole"
    assert "Fillet" in [t.title for t in search("round radius")]
    assert [t.title for t in search("boolean")] == ["Combine"]
    assert search("print")                                       # export to a slicer
    assert search("zzzz-nothing") == []


def test_f1_opens_help_and_enter_runs_the_function(win):
    act = next(a for a in win.findChildren(QAction) if "Commands" in a.text())
    assert act.shortcut().toString() == "F1"
    assert not any(a.text() == "Guides" for a in win.findChildren(QAction))
    win.show_help()
    hw = win._help_window
    hw.edt_search.setText("box")
    assert hw.selected().cid == "box"
    QTest.keyClick(hw.edt_search, Qt.Key.Key_Return)
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and "Box" in dlg.windowTitle() and not hw.isVisible()
    dlg.reject()


def test_a_sketch_tool_needs_a_sketch(win):
    win.show_help()
    hw = win._help_window
    hw.edt_search.setText("trim")
    hw.run_selected()
    assert "sketch tool" in win.status_label.text() and win.doc.active_sketch is None


def test_menus_show_help_on_hover(win):
    menus = {a.text(): a.menu() for a in win.menuBar().actions()}
    assert all(menus[m].toolTipsVisible() for m in ("Create", "Modify", "Inspect"))


def test_best_match_is_selected(win):
    win.show_help()
    hw = win._help_window
    hw.edt_search.setText("round")
    assert hw.selected().title == "Fillet"            # its search words say round; Emboss only mentions it


def test_close_button_closes_the_help(win):
    win.show_help()
    hw = win._help_window
    assert hw.isVisible()
    hw.btn_close.click()
    assert not hw.isVisible()
