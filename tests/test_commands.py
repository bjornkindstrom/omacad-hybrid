"""One list of commands (omacad.ui.commands) drives the ribbon and the menu bar: every shortcut is unique where it is
live, every command reaches a Ribbon signal, and a command has the same name in the ribbon and the menu."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui import commands
from omacad.ui.main_window import MainWindow
from omacad.ui.ribbon import Ribbon, RibbonButton
from omacad.ui.viewport.events_mixin import SKETCH_KEYS


@pytest.fixture(scope="module")
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def test_shortcuts_are_unique_per_mode():
    for mode in ("model", "sketch"):
        keys = [k for c in commands.COMMANDS.values() if mode in c.modes for k in (c.shortcut, *c.extra_shortcuts) if k]
        assert len(keys) == len(set(keys)), mode


def test_single_letter_sketch_keys_are_the_viewport_keys():
    from PySide6.QtGui import QKeySequence
    letters = {c.shortcut for c in commands.COMMANDS.values() if "sketch" in c.modes and len(c.shortcut) == 1}
    assert {QKeySequence(k)[0].key() for k in letters} <= SKETCH_KEYS


def test_every_command_signal_exists_on_the_ribbon():
    for c in commands.COMMANDS.values():
        assert hasattr(Ribbon, c.signal), c.cid


def test_menu_and_ribbon_use_the_registry_names(win):
    for cid, act in win.command_actions.items():
        assert act.text() == commands.label(cid)
    for btn in win.ribbon.findChildren(RibbonButton):
        cid = btn.property("command")
        if cid in commands.COMMANDS:
            assert btn.text().replace("\n", " ").startswith(commands.label(cid).split()[0])


def test_solid_tab_groups_in_fusion_order(win):
    from PySide6.QtWidgets import QWidget
    names = [w.objectName() for w in win.ribbon.solid_tab.findChildren(QWidget) if w.objectName().startswith("RibbonGroup_")]
    assert names == ["RibbonGroup_CREATE", "RibbonGroup_MODIFY", "RibbonGroup_INSPECT"]
    menus = [a.text() for a in win.menuBar().actions()]
    assert menus == ["File", "Edit", "Create", "Modify", "Inspect", "View", "Help"]


def test_menu_entry_opens_the_tool(win):
    win.doc.add_box(10, 10, 10)
    win.command_actions["box"].trigger()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and "Box" in dlg.windowTitle()
    dlg.reject()
    assert "statistics" in win.command_actions        # Document Statistics: reachable again (Inspect menu)
