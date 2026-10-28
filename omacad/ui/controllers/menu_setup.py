"""Main window menu bar construction."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMenu
from omacad.ui import theme
from omacad.ui.theme import style


class MenuSetupMixin:
    """Build the main application menu bar."""

    def setup_menu_bar(self):
        menubar = self.menuBar()

        # File Menu
        menu_file = menubar.addMenu("File")

        act_new = QAction("New Design", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self.on_file_new)
        menu_file.addAction(act_new)

        act_open = QAction("Open Project (.omacad)…", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.on_file_open)
        menu_file.addAction(act_open)
        self.menu_recent = menu_file.addMenu("Open Recent")
        self.rebuild_recent_menu()

        act_save = QAction("Save Project (.omacad)", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.on_file_save)
        menu_file.addAction(act_save)

        act_save_as = QAction("Save Project As…", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self.on_file_save_as)
        menu_file.addAction(act_save_as)

        menu_file.addSeparator()

        act_import_3mf = QAction("Import 3MF…", self)
        act_import_3mf.triggered.connect(self.on_import_3mf)
        menu_file.addAction(act_import_3mf)

        menu_file.addSeparator()

        act_export_stl = QAction("Export All as STL…", self)
        act_export_stl.triggered.connect(self.on_export_all_stl)
        menu_file.addAction(act_export_stl)

        act_export_step = QAction("Export All as STEP…", self)
        act_export_step.triggered.connect(self.on_export_all_step)
        menu_file.addAction(act_export_step)

        menu_file.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # Edit Menu
        menu_edit = menubar.addMenu("Edit")
        act_undo = self.act_undo = QAction("Undo", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.triggered.connect(self.on_undo)
        menu_edit.addAction(act_undo)
        act_redo = self.act_redo = QAction("Redo", self)
        act_redo.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        act_redo.triggered.connect(self.on_redo)
        menu_edit.addAction(act_redo)
        self.doc.history_listeners.append(self._update_undo_actions)
        self._update_undo_actions()
        menu_edit.addSeparator()
        act_settings = QAction("Settings…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self.on_open_settings)
        menu_edit.addAction(act_settings)

        # Create / Modify / Inspect: the same commands, names and keys as the ribbon (omacad.ui.commands)
        from omacad.ui import commands
        self.command_actions = {}
        for title, cids in commands.MENUS:
            menu = menubar.addMenu(title)
            for cid in cids:
                if cid is None:
                    menu.addSeparator()
                    continue
                c = commands.get(cid)
                act = QAction(theme.named_icon(theme.COMMAND_ICONS[cid], c.icon, 24) if cid in theme.COMMAND_ICONS
                              else theme.emoji_icon(c.icon, 24) if c.icon != "dimension" else theme.tool_icon(c.icon, 24),
                              c.label, menu)
                keys = [k for k in (c.shortcut, *c.extra_shortcuts) if k]
                if keys:
                    act.setShortcuts([QKeySequence(k) for k in keys])
                act.setToolTip(c.tip)
                act.triggered.connect(lambda _=False, cid=cid: self.ribbon._emit_command(cid))
                menu.addAction(act)
                self.command_actions[cid] = act
            menu.setToolTipsVisible(True)       # hovering an entry shows what it does

        # View Menu
        menu_view = menubar.addMenu("View")
        act_fit = menu_view.addAction("Fit View", self.viewport.zoom_fit)
        act_fit.setShortcuts([QKeySequence("F"), QKeySequence("Home")])
        menu_view.addAction("Toggle Ground Grid", self.toggle_grid)
        menu_view.addAction("Toggle Feature Edges", self.toggle_edges)
        self._origin_actions = {}
        menu_origin = menu_view.addMenu("Origin")
        for kind, name, label in (("all", "", "Show Origin"), ("axis", "X", "X Axis"), ("axis", "Y", "Y Axis"),
                                  ("axis", "Z", "Z Axis"), ("plane", "XY", "XY Plane"), ("plane", "XZ", "XZ Plane"),
                                  ("plane", "YZ", "YZ Plane")):
            if kind == "axis" and name == "X":
                menu_origin.addSeparator()
            if kind == "plane" and name == "XY":
                menu_origin.addSeparator()
            act = menu_origin.addAction(label)
            act.setCheckable(True)
            act.toggled.connect(lambda on, k=kind, n=name: self.doc.set_origin_visibility(k, n, on))
            self._origin_actions[(kind, name)] = act
        self.doc.add_change_listener(self.sync_origin_actions)
        self.sync_origin_actions()

        # Help Menu
        menu_help = menubar.addMenu("Help")
        act_report = QAction("Report problem…", self)
        act_report.setShortcut(QKeySequence("F10"))      # F9 belongs to Omarchy
        act_report.setToolTip("Describe what is wrong; the AI gets a screenshot, the model and the log, and fixes it")
        act_report.triggered.connect(self.on_report_problem)
        menu_help.addAction(act_report)
        act_request = QAction("Request a change…", self)
        act_request.setShortcut(QKeySequence("F8"))
        act_request.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        act_request.setToolTip("Ask for a change or a new feature: your text, a screenshot, the model and the log are sent to the owner on GitHub")
        act_request.triggered.connect(self.on_request_change)
        menu_help.addAction(act_request)
        act_help = QAction(theme.emoji_icon("❓", 24), "Help && Commands…", menu_help)
        act_help.setShortcut(QKeySequence("F1"))
        act_help.setToolTip("Every function, grouped as in the ribbon, with help text and a search: Enter runs it")
        act_help.triggered.connect(self.show_help)
        menu_help.insertAction(menu_help.actions()[0] if menu_help.actions() else None, act_help)
        menu_help.addAction("Changelog…", self.on_changelog)
        menu_help.addAction("About Omacad", self.on_about)

        # Icons for the other menu entries (the commands have theirs); drawn from emoji at a size the menu font can't give
        icons = {
            "New Design": "📄", "Open Project": "📂", "Save Project As": "💾", "Save Project": "💾", "Export All as STL": "📤",
            "Import 3MF": "📥", "Exit": "🚪", "Undo": "↩️", "Redo": "↪️", "Fit View": "🔲", "Toggle Ground Grid": "📐",
            "Toggle Feature Edges": "🔳", "About": "ℹ️", "Settings": "⚙️",
        }
        studio_names = {"Fit View": "fit", "Toggle Ground Grid": "grid"}   # their emoji means something else in Studio
        for menu in menubar.findChildren(QMenu):
            for act in menu.actions():
                if not act.icon().isNull():
                    continue
                for label, emoji in icons.items():
                    if act.text().startswith(label):
                        act.setIcon(theme.named_icon(studio_names.get(label, ""), emoji, 24))
                        break

        # Document / File Name display at the top (Fusion style)
        self.lbl_doc_title = QLabel()
        self.lbl_doc_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        style(self.lbl_doc_title, "font-size: 12px; font-weight: bold; color: #9AA0A6; padding: 2px 14px; background: transparent;")
        menubar.setCornerWidget(self.lbl_doc_title, Qt.Corner.TopRightCorner)
        self.update_window_title()
