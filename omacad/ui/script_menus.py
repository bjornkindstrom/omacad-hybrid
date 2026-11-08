"""Submenus of the built-in tools that have script versions (Jar with Lid, Star Brackets, Box in a Row): the tool
itself, its script and every changed copy, and "Modify with AI…". Shared by the ribbon dropdowns, the tool's own
ribbon button and the Create menu, and filled each time it opens so new copies show up at once."""
from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMenu

# command id of the built-in tool -> its scripts' FAMILY value
FAMILIES = {"jar": "jar", "star_brackets": "star_brackets", "box_row": "box_row"}


class ScriptRightClick(QObject):
    """Right-click on a script in a menu: Rename…, Modify with AI…, Delete… (the action's data is the script's path).
    `manage(what, path)` gets "rename", "modify" or "delete" after the menus have closed."""

    def __init__(self, menu: QMenu, manage: Callable[[str, str], None]):
        super().__init__(menu)
        self.menu, self.manage = menu, manage
        menu.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease) \
                and event.button() == Qt.MouseButton.RightButton:
            act = self.menu.actionAt(event.position().toPoint())
            path = act.data() if act is not None else None
            if not path:
                return False
            if event.type() == QEvent.Type.MouseButtonRelease:
                self.show_for(str(path), event.globalPosition().toPoint())
            return True                          # never runs the script
        if event.type() == QEvent.Type.ContextMenu:
            act = self.menu.actionAt(event.pos())
            if act is not None and act.data():
                return True
        return False

    def show_for(self, path: str, at) -> Optional[str]:
        from omacad.scripting.folder import is_own
        from omacad.ui import theme
        ctx = QMenu(self.menu)
        theme.style_menu(ctx)
        ctx.setToolTipsVisible(True)
        run_easy = ctx.addAction("Run in Easy mode")
        easy = ctx.addAction("Easy mode settings…")
        rename = ctx.addAction("Rename…")
        rename.setToolTip("Change the name shown in the menus (the file stays)")
        modify = ctx.addAction(theme.command_icon("new_script_ai", "🤖", 18), "Modify with AI…")
        modify.setToolTip("An AI makes a changed copy of this script")
        ctx.addSeparator()
        delete = ctx.addAction("Delete…")
        own = is_own(path)
        delete.setEnabled(own)
        delete.setToolTip("Moves your script to the trash" if own else "Omacad's own scripts can't be deleted")
        chosen = ctx.exec(at)
        what = {run_easy: "run_easy", easy: "easy", rename: "rename", modify: "modify", delete: "delete"}.get(chosen)
        if what:
            close_popups()
            QTimer.singleShot(0, lambda: self.manage(what, path))
        return what


def close_popups() -> None:
    """Closes every open menu (the dropdown and the submenus it came from)."""
    for _ in range(10):
        popup = QApplication.activePopupWidget()
        if popup is None:
            break
        popup.close()


def fill_family_menu(menu: QMenu, cid: str, run_tool: Callable[[], None], scripts: Callable[[str], List],
                     run_script: Callable[[str], None], modify: Callable[[str], None],
                     manage: Optional[Callable[[str, str], None]] = None) -> None:
    """Fills `menu` (cleared first) for the tool `cid`. `scripts(family)` gives ScriptInfo objects."""
    from omacad.ui import commands, theme
    family = FAMILIES[cid]
    menu.clear()
    c = commands.get(cid)
    act = menu.addAction(theme.command_icon(cid, c.icon, 18), f"{c.label} (built-in)")
    act.setToolTip(c.tip)
    act.triggered.connect(lambda _=False: run_tool())
    found = []
    try:
        found = scripts(family) or []
    except Exception as e:          # an unreadable folder must not break the menu
        from omacad import applog
        applog.log("scripts", f"family menu {family}: {e}")
    if found:
        menu.addSeparator()
        for info in found:
            a = menu.addAction(theme.command_icon("scripts", "📜", 18), info.name)
            a.setToolTip((info.description or info.path.name) + ("\nRight-click: rename, modify or delete"
                                                                 if manage is not None else ""))
            a.setData(str(info.path))
            a.setEnabled(not info.error)
            a.triggered.connect(lambda _=False, p=str(info.path): run_script(p))
    menu.addSeparator()
    m = menu.addAction(theme.command_icon("new_script_ai", "🤖", 18), "Modify with AI…")
    m.setToolTip("Describe a change; an AI makes a changed copy of the script (the original stays as it is)")
    m.triggered.connect(lambda _=False: modify(family))


def family_menu(parent, cid: str, run_tool, scripts, run_script, modify, manage=None) -> QMenu:
    """A menu for `cid` that fills itself each time it is shown."""
    from omacad.ui import commands, theme
    menu = QMenu(commands.label(cid), parent)
    theme.style_menu(menu)
    menu.setToolTipsVisible(True)
    menu.setIcon(theme.command_icon(cid, commands.get(cid).icon, 18))
    menu.aboutToShow.connect(lambda: fill_family_menu(menu, cid, run_tool, scripts, run_script, modify, manage))
    fill_family_menu(menu, cid, run_tool, scripts, run_script, modify, manage)
    if manage is not None:
        menu._script_right_click = ScriptRightClick(menu, manage)
    return menu
