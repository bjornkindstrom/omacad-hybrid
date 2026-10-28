"""
Omacad - Left Browser Tree
Hierarchy tree for Document Settings, Origin geometry, Bodies, and Sketches.
"""

from typing import Optional, Dict
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QMenu, QHeaderView, QLabel, QHBoxLayout,
    QAbstractItemView, QToolButton
)
from PySide6.QtGui import QIcon, QAction, QBrush, QColor, QFont, QKeySequence, QShortcut
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.model.document import Document
from omacad.ui.theme import qcolor


class BrowserTree(QWidget):
    """Fusion 360 style left hierarchy browser."""

    preview_changed = Signal(object)
    content_width_changed = Signal()
    status_message = Signal(str)
    feature_selected = Signal(str)
    feature_edit_requested = Signal(str)
    feature_delete_requested = Signal(str)
    body_selected = Signal(str)
    sketch_selected = Signal(str)
    dimension_selected = Signal(str, str)              # sketch_id, dim_id; ("", "") = nothing
    start_sketch_on_plane = Signal(str)
    start_sketch_on_cplane = Signal(str)
    edit_section_requested = Signal(str)
    export_body_stl = Signal(str)
    export_body_step = Signal(str)
    edit_sketch_requested = Signal(str)
    edit_sketch_text_requested = Signal(str, str)     # sketch_id, entity_id
    split_body_requested = Signal(str, str)
    insert_canvas_requested = Signal(str)
    edit_canvas_requested = Signal(str)
    shell_body_requested = Signal(str)
    move_body_requested = Signal(str)
    named_view_requested = Signal(str)
    extrude_sketch_requested = Signal(str)
    offset_plane_requested = Signal(str, str)    # what was right-clicked: ("plane" | "cplane" | "sketch", id)
    find_in_window_requested = Signal(str, str)      # kind ("body"/"sketch"), id
    find_in_timeline_requested = Signal(str, str)
    delete_sketch_requested = Signal(str)
    body_color_requested = Signal(str)

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.doc = document
        self.parameter_error = None
        self._editor_width = 0
        self.doc.add_change_listener(self.refresh_tree)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header Bar (Fusion 360 floating card-style header)
        self.header = QWidget()
        style(self.header, "background-color: rgba(32, 34, 37, 0.75); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 3px 6px;",
              "QWidget { background: transparent; border: none; border-bottom: 1px solid @border; border-radius: 0; }"
              "QToolButton { border: none; color: @muted; } QToolButton:hover { background-color: @field; color: @text; }")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(6, 2, 4, 2)
        self.lbl_title = QLabel("BROWSER")
        style(self.lbl_title, "font-weight: bold; font-size: 11px; color: #8E95A0; letter-spacing: 0.8px; background: transparent;",
              "QLabel { color: @muted; font-size: 11px; font-weight: 600; letter-spacing: 1px; border: none; }")
        h_layout.addWidget(self.lbl_title)
        h_layout.addStretch()
        for label, action, tip in (
            ('⏮', 'start', 'Show the active object before its first step'),
            ('‹', 'back', 'Previous step of the active object'),
            ('›', 'next', 'Next step of the active object'),
            ('⏭', 'end', 'Show the complete active object'),
        ):
            button = QToolButton(self.header)
            theme.set_button_text(button, label, 16)
            button.setToolTip(tip)
            button.clicked.connect(lambda checked=False, a=action: self.navigate_history(a))
            h_layout.addWidget(button)

        layout.addWidget(self.header)

        # Tree Widget
        self.tree = QTreeWidget()
        from omacad.ui.history_delegate import HistoryDelegate
        self.tree.setItemDelegate(HistoryDelegate(self))
        self.tree.itemExpanded.connect(lambda item: self.content_width_changed.emit())
        self.tree.itemCollapsed.connect(lambda item: self.content_width_changed.emit())
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(22, 22))
        self.tree.setIndentation(18)
        self.tree.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        style(self.tree, """
            QTreeWidget {
                background: transparent;
                border: none;
                color: #D8DCE2;
                outline: none;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 5px 6px;
                border-radius: 4px;
                background: transparent;
            }
            QTreeWidget::item:hover {
                background-color: rgba(60, 68, 79, 0.4);
            }
            QTreeWidget::item:selected {
                background-color: rgba(6, 150, 215, 0.45);
                color: #FFFFFF;
            }
        """, """
            QTreeWidget { color: @text; font-size: 13px; }
            QTreeWidget::item { padding: 4px 6px; border-radius: 0; }
            QTreeWidget::item:hover { background-color: @field; }
            QTreeWidget::item:selected { background-color: @selection; color: @accent; }
        """)
        # Column 0 = name, column 1 = clickable visibility eye
        self.tree.setColumnCount(2)
        hdr = self.tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(1, 40)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        # F2 or a slow second click on a selected sketch/body renames it in place
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed
                                  | QAbstractItemView.EditTrigger.SelectedClicked)
        self.tree.itemChanged.connect(self.on_item_renamed)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.tree)
        # V shows/hides what is selected, as in Fusion
        sc = QShortcut(QKeySequence("V"), self.tree)
        sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc.activated.connect(self.toggle_selected_visibility)

        self.setObjectName("BrowserWidget")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        style(self, "QWidget#BrowserWidget { background: transparent; border: none; }",
              "QWidget#BrowserWidget { background-color: @surface; border: 1px solid @border; border-radius: 8px; }")
        self.refresh_tree()

    def refresh_tree(self):
        """Rebuilds the tree nodes based on the Document model. Not while a value is being typed: the rebuild would
        close the editor; it runs as soon as the editor is closed."""
        if self.tree.state() == self.tree.State.EditingState:
            if not getattr(self, "_refresh_pending", False):
                self._refresh_pending = True
                QTimer.singleShot(120, self._refresh_when_done)
            return
        self.tree.blockSignals(True)  # rebuilding must not look like a rename
        expanded = self._expanded_keys()
        selected = {self._item_key(item) for item in self.tree.selectedItems()}
        scroll = self.tree.verticalScrollBar().value()
        try:
            self._rebuild_tree()
            self._restore_expanded(expanded)
            for item, _ in self._walk():
                if self._item_key(item) in selected:
                    item.setSelected(True)
            self.tree.verticalScrollBar().setValue(scroll)
        finally:
            self.tree.blockSignals(False)
        if self.parameter_error:
            kind, ids, message = self.parameter_error
            for item, _ in self._walk():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == kind and tuple(data[1]) == ids:
                    item.setText(0, item.text(0) + " — " + message)
                    item.setForeground(0, QColor("#e06c75"))
                    item.setToolTip(0, message)
                    break
        self._editor_width = 0
        self.content_width_changed.emit()

    def preferred_width(self, available_width):
        """Fit visible rows while keeping usable space for the model on small windows."""
        content = 200
        metrics = self.tree.fontMetrics()
        for item, _ in self._walk():
            depth = 0
            parent = item.parent()
            visible = True
            while parent:
                depth += 1
                visible = visible and parent.isExpanded()
                parent = parent.parent()
            if visible:
                content = max(content, metrics.horizontalAdvance(item.text(0)) +
                              (depth + 1) * self.tree.indentation() + 48)
        content = max(content, self._editor_width)
        cap = max(160, min(int(available_width * 0.48), available_width - 220))
        width = min(max(260, content + 70), cap)
        self.tree.header().resizeSection(0, max(content, width - 70))
        return width

    def _refresh_when_done(self):
        if self.tree.state() == self.tree.State.EditingState:
            QTimer.singleShot(120, self._refresh_when_done)
            return
        self._refresh_pending = False
        self.refresh_tree()

    def preferred_height(self, available_height: int) -> int:
        """Just tall enough for the visible rows (header and margins included), so the drawing area below stays
        free; capped at the room available, where the tree scrolls as before."""
        tree = self.tree
        rows = 0
        index = tree.model().index(0, 0)
        while index.isValid():
            rows += max(tree.sizeHintForIndex(index).height(), 1)
            index = tree.indexBelow(index)
        m = self.layout().contentsMargins()
        chrome = (m.top() + m.bottom() + self.layout().spacing() + self.header.sizeHint().height()
                  + tree.frameWidth() * 2 + 2 * 4 + 16)      # tree padding + a little air under the last row
        if tree.horizontalScrollBar().isVisible():
            chrome += tree.horizontalScrollBar().height()
        return max(120, min(available_height, rows + chrome))

    def navigate_history(self, action):
        reason = getattr(self, 'busy_reason', lambda: '')()
        if reason:
            self.status_message.emit(reason)
            return
        history = self.doc.object_history
        obj = history.objects.get(history.active_id)
        if obj is None:
            return
        if action == 'end':
            self.doc.object_fast_forward(obj.object_id)
            return
        marker = history.markers.get(obj.object_id, obj.feature_ids[-1] if obj.feature_ids else None)
        position = obj.feature_ids.index(marker) + 1 if marker in obj.feature_ids else 0
        position = 0 if action == 'start' else max(0, min(len(obj.feature_ids), position + (1 if action == 'next' else -1)))
        self.doc.object_step_to(obj.object_id, obj.feature_ids[position - 1] if position else None)

    def activate_object(self, object_id):
        self.doc.object_history.active_id = object_id
        self.doc.object_history.target_object_id = object_id
        self.tree.blockSignals(True)  # a font change emits itemChanged, which would look like a rename
        try:
            for item, _ in self._walk():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == 'object':
                    font = item.font(0)
                    font.setBold(data[1] == object_id)
                    item.setFont(0, font)
        finally:
            self.tree.blockSignals(False)

    def grow_for_editor(self, text, index):
        depth = 1
        parent = index.parent()
        while parent.isValid():
            depth += 1
            parent = parent.parent()
        self._editor_width = max(self._editor_width,
            self.tree.fontMetrics().horizontalAdvance(text) + depth * self.tree.indentation() + 70)
        self.content_width_changed.emit()

    @staticmethod
    def _item_key(item: QTreeWidgetItem):
        """Identity of a node across rebuilds: the item's own data (kind, id) or, for groups, its text."""
        return item.data(0, Qt.ItemDataRole.UserRole) or item.text(0)

    def _walk(self):
        stack = [(self.tree.topLevelItem(i), ()) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item, path = stack.pop()
            key = path + (self._item_key(item),)
            yield item, key
            stack += [(item.child(i), key) for i in range(item.childCount())]

    def _expanded_keys(self) -> dict:
        """key -> expanded? for every node, so a rebuild (e.g. after hiding a plane) keeps the tree as it was."""
        return {key: item.isExpanded() for item, key in self._walk()}

    def _restore_expanded(self, state: dict):
        for item, key in self._walk():
            if key in state:
                item.setExpanded(state[key])

    def _iconify(self, item: QTreeWidgetItem):
        """Leading emoji of an item's text becomes a real icon (so it can be larger than the font)."""
        emoji, rest = theme.split_emoji(item.text(0))
        if emoji:
            item.setText(0, rest)
            item.setIcon(0, theme.emoji_icon(emoji, 22))
        for i in range(item.childCount()):
            self._iconify(item.child(i))

    def _rebuild_tree(self):
        self._rebuild_items()
        for i in range(self.tree.topLevelItemCount()):
            self._iconify(self.tree.topLevelItem(i))

    def _rebuild_items(self):
        self.tree.clear()

        # Root: the document, as in Fusion 360 ("(Unsaved)" until it has been saved)
        name = self.doc.name or ""
        unsaved = (not name) or name.lower().startswith("omacad - untitled") or name.lower() == "untitled"
        root = QTreeWidgetItem(self.tree, ["📁 " + ("(Unsaved)" if unsaved else name), ""])
        root.setExpanded(True)

        # Document Settings
        settings_item = QTreeWidgetItem(root, ["⚙️ Document Settings", ""])
        settings_item.setExpanded(True)
        for text in (f"📏 Units: {self.doc.units}, g", "🧱 Parametric Design"):
            it = QTreeWidgetItem(settings_item, [text, ""])
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable)

        # Named Views
        views_item = QTreeWidgetItem(root, ["🎥 Named Views", ""])
        for view in ("Home", "Top", "Front", "Right", "Back", "Left", "Bottom"):
            it = QTreeWidgetItem(views_item, [f"🎥 {view}", ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("view", view.upper()))

        # Origin
        origin_item = QTreeWidgetItem(root, ["🌐 Origin", ""])
        origin_item.setExpanded(False)
        origin_item.setData(0, Qt.ItemDataRole.UserRole, ("origin", "all"))
        self._style_eye(origin_item, self.doc.origin_visible("all"))
        origin_item.setToolTip(1, "Show or hide the whole origin (axes and planes)")
        for axis, label in (("X", "• X Axis (Red)"), ("Y", "• Y Axis (Green)"), ("Z", "• Z Axis (Blue)")):
            it = QTreeWidgetItem(origin_item, [label, ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("axis", axis))
            self._style_eye(it, self.doc.origin_visible("axis", axis))
        for name_ in ("XY", "XZ", "YZ"):
            it = QTreeWidgetItem(origin_item, [f"📄 {name_} Plane", ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("plane", name_))
            self._style_eye(it, self.doc.origin_visible("plane", name_))
        for pid, c in self.doc.construction_planes.items():
            pi = QTreeWidgetItem(origin_item, ["📄 " + c["name"], ""])
            pi.setData(0, Qt.ItemDataRole.UserRole, ("cplane", pid))
            pi.setFlags(pi.flags() | Qt.ItemFlag.ItemIsEditable)
            self._style_eye(pi, bool(c.get("visible", True)))
        if self.doc.construction_planes:
            origin_item.setExpanded(True)

        # Analysis (section views live here, as in Fusion)
        analysis = QTreeWidgetItem(root, ["🔍 Analysis", ""])
        for sid, sec in self.doc.sections.items():
            it = QTreeWidgetItem(analysis, ["✂️ " + sec["name"], ""])
            it.setData(0, Qt.ItemDataRole.UserRole, ("section", sid))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            self._style_eye(it, bool(sec.get("active")))
            it.setToolTip(1, "Click to turn the section off" if sec.get("active") else "Click to turn the section on")
        if self.doc.sections:
            analysis.setExpanded(True)

        def group(label: str, key: str, visible: bool):
            g = QTreeWidgetItem(root, [label, ""])
            g.setData(0, Qt.ItemDataRole.UserRole, ("group", key))
            g.setExpanded(True)
            self._style_eye(g, visible)
            return g

        from omacad.ui.object_browser import add_favorites, add_histories
        add_favorites(self, root)
        add_histories(self, root)

        # Canvases
        if getattr(self.doc, "canvases", None):
            canv_group = group("🖼️ Canvases", "canvases", any(c.get("visible", True) for c in self.doc.canvases.values()))
            for cid, c in self.doc.canvases.items():
                it = QTreeWidgetItem(canv_group, [c["name"], ""])
                it.setData(0, Qt.ItemDataRole.UserRole, ("canvas", cid))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                self._style_eye(it, bool(c.get("visible", True)))
                it.setToolTip(1, "Click to hide canvas" if c.get("visible", True) else "Click to show canvas")

    @staticmethod
    def _style_eye(item: QTreeWidgetItem, visible: bool):
        """Eye icon in column 1; hidden items are greyed out."""
        item.setText(1, "")
        item.setIcon(1, theme.emoji_icon("👁" if visible else "🚫", 22))
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
        item.setToolTip(1, "Click to hide" if visible else "Click to show")
        grey = QBrush(qcolor(110, 116, 125))
        item.setForeground(0, QBrush() if visible else grey)

    def on_item_renamed(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if column == 0 and data and data[0] == "fav_group":
            if item.text(0) != data[1] and not self.doc.rename_favorite_group(data[1], item.text(0)):
                self.refresh_tree()
            return
        if column == 0 and data and data[0] == "object":
            self.doc.rename_object(data[1], item.text(0))
            return
        if column == 0 and data and data[0] == "feature":
            index = self.doc.object_history.index(self.doc, data[1])
            if index is not None:
                self.doc.rename_feature(index, item.text(0))
            return
        if column != 0 or not data or data[0] not in ("sketch", "body", "section", "canvas", "cplane"):
            return
        kind, item_id = data
        if kind == "canvas":
            self.doc.update_canvas(item_id, name=item.text(0))
            return
        if not self.doc.rename_item(kind, item_id, item.text(0)):
            self.refresh_tree()  # empty or invalid name: put the old one back


    def toggle_visibility(self, item_type: str, item_id: str) -> bool:
        """Show/hide whatever the tree item stands for (eye click, V, right-click menu). False: nothing to toggle."""
        doc = self.doc
        if item_type == "canvas":
            doc.toggle_canvas_visibility(item_id)
        elif item_type == "section":
            doc.set_section_active(item_id, not doc.sections[item_id].get("active"))
        elif item_type == "body":
            doc.toggle_body_visibility(item_id)
        elif item_type == "sketch":
            doc.toggle_sketch_visibility(item_id)
        elif item_type == "object":
            doc.set_object_visibility(item_id, not doc.object_visible(item_id))
        elif item_type == "cplane":
            doc.toggle_construction_plane(item_id)
        elif item_type in ("origin", "axis", "plane"):
            kind, name = ("all", "") if item_type == "origin" else (item_type, item_id)
            doc.set_origin_visibility(kind, name, not doc.origin_visible(kind, name))
        elif item_type == "group" and item_id == "objects":
            shown = any(b.visible for b in doc.bodies.values())
            doc.set_group_visibility("bodies", not shown)
        elif item_type == "group":
            shown = {"bodies": any(b.visible for b in doc.bodies.values()),
                     "sketches": any(sk.visible for sk in doc.sketches.values()),
                     "canvases": any(c.get("visible", True) for c in doc.canvases.values())}.get(item_id, False)
            doc.set_group_visibility(item_id, not shown)
        else:
            return False
        return True

    def toggle_selected_visibility(self):
        for it in self.tree.selectedItems():
            data = it.data(0, Qt.ItemDataRole.UserRole)
            if data:
                self.toggle_visibility(*data)

    def on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        # a dimension row lights up what it measures in the view (Björn #94); any other row clears that
        self.dimension_selected.emit(*(item_id if item_type == "dimension" else ("", "")))
        if column == 1 and item_type in ("parameter", "dimension", "fav"):       # the pencil
            from omacad.ui.object_browser import edit_parameter
            edit_parameter(self, item_type, item_id)
            return
        if item_type == "dimension":
            return
        from omacad.ui.object_browser import FEATURE_ROLE
        fid = item.data(0, FEATURE_ROLE)
        pick = getattr(self, 'pick_feature', None)
        if fid and pick and pick(fid):
            return
        if item_type == "object" and column == 1:
            self.toggle_visibility(item_type, item_id)
            return
        if item_type == "object":
            self.activate_object(item_id)
            return
        if item_type in ("feature", "feature_link"):
            self.activate_object(self.doc.object_history.owners.get(item_id))
            self.feature_selected.emit(item_id)
            return
        if item_type == "view":
            self.named_view_requested.emit(item_id)
            return
        if column == 1 and item_type in ("origin", "axis", "plane", "body", "sketch", "section", "canvas", "cplane", "group"):
            self.toggle_visibility(item_type, item_id)
            return
        if item_type == "body":
            owner = next((oid for oid, obj in self.doc.object_history.objects.items() if item_id in obj.body_ids), None)
            if owner:
                self.activate_object(owner)
            self.doc.select_body(item_id)
            self.body_selected.emit(item_id)
        elif item_type == "sketch":
            from omacad.ui.object_browser import FEATURE_ROLE
            fid = item.data(0, FEATURE_ROLE)
            if fid:
                self.activate_object(self.doc.object_history.owners.get(fid))
            self.sketch_selected.emit(item_id)

    def on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        if item_type in ("parameter", "dimension", "fav"):
            from omacad.ui.object_browser import edit_parameter
            edit_parameter(self, item_type, item_id)
        elif item_type == "feature":
            self.feature_edit_requested.emit(item_id)
        elif item_type == "feature_link":
            from omacad.ui.object_browser import find_feature
            find_feature(self, item_id)
        elif item_type == "history_end":
            self.doc.object_fast_forward(item_id)
        elif item_type == "plane":
            self.start_sketch_on_plane.emit(item_id)
        elif item_type == "cplane":
            self.start_sketch_on_cplane.emit(item_id)
        elif item_type == "body":
            self.doc.toggle_body_visibility(item_id)
        elif item_type == "sketch":
            self.edit_sketch_requested.emit(item_id)
        elif item_type == "sketch_text":
            s_id, ent_id = item_id.split(":", 1)
            self.edit_sketch_text_requested.emit(s_id, ent_id)
        elif item_type == "canvas":
            self.edit_canvas_requested.emit(item_id)
        elif item_type == "section":
            self.doc.set_section_active(item_id, not self.doc.sections[item_id].get("active"))

    def _move_to_new_object(self, fid):
        try:
            self.doc.move_to_new_object(fid)
        except ValueError as e:
            self.status_message.emit(str(e))
            return
        self.status_message.emit("Moved to a new object (F2 renames it).")

    def _owner_name(self, ref) -> str:
        """The name of the object a value belongs to: the first guess for a new favourites group."""
        doc, history = self.doc, self.doc.object_history
        fid = ref[1] if ref[0] == "parameter" else next(
            (f.feature_id for f in doc.timeline.features if f.feature_type == "sketch" and f.sketch.sketch_id == ref[1]), None)
        obj = history.objects.get(history.owners.get(fid))
        return obj.name if obj else "Favorites"

    def new_favorite_group(self, ref):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New favorites group", "Group name:", text=self._owner_name(ref))
        if ok and name.strip():
            self.doc.add_favorite(ref, name)

    def _favorite_menu(self, menu, ref):
        """⭐ Add to favorites (an existing group, or a new one), or take the value out again (Björn #110)."""
        menu.addSeparator()
        current = self.doc.favorite_group_of(ref)
        sub = menu.addMenu(theme.emoji_icon("⭐", 22),
                           "Add to favorites" if current is None else f"Move to another group (now in {current})")
        theme.style_menu(sub)
        for group in self.doc.favorites:
            if group["name"] != current:
                sub.addAction(group["name"]).triggered.connect(
                    lambda checked=False, g=group["name"]: self.doc.add_favorite(ref, g))
        if self.doc.favorites and len(self.doc.favorites) > (current is not None):
            sub.addSeparator()
        sub.addAction("New group…").triggered.connect(lambda: self.new_favorite_group(ref))
        if current is not None:
            theme.action_with_icon(menu, "☆ Remove from favorites").triggered.connect(lambda: self.doc.remove_favorite(ref))

    def show_context_menu(self, pos):
        reason = getattr(self, 'busy_reason', lambda: '')()
        if reason:
            self.status_message.emit(reason)
            return
        item = self.tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, item_id = data
        menu = QMenu(self)
        theme.style_menu(menu)
        add = lambda text, slot: theme.action_with_icon(menu, text).triggered.connect(slot)
        rename = lambda: add("🏷️ Rename\tF2", lambda: self.tree.editItem(item, 0))
        show_hide = lambda: add("👁️ Show/Hide\tV", lambda: self.toggle_visibility(item_type, item_id))
        find = lambda kind: (menu.addSeparator(),
                             add("🔎 Find in Window", lambda: self.find_in_window_requested.emit(kind, item_id)),
                             add("🧭 Find in Timeline", lambda: self.find_in_timeline_requested.emit(kind, item_id)))

        from omacad.ui.object_browser import FEATURE_ROLE
        fid = item.data(0, FEATURE_ROLE)
        if fid:
            index = self.doc.object_history.index(self.doc, fid)
            if index is not None:
                feat = self.doc.timeline.features[index]
                oid = self.doc.object_history.owners[fid]
                add("Edit feature…", lambda: self.feature_edit_requested.emit(fid))
                add("Delete feature…", lambda: self.feature_delete_requested.emit(fid))
                add("Unsuppress" if feat.suppressed else "Suppress", lambda: self.doc.toggle_suppress(index))
                add("Insert next operation after this step", lambda: self.doc.object_insert_after(oid, fid))
                if len(self.doc.object_history.objects.get(oid).feature_ids) > 1:
                    add("Move to new object", lambda: self._move_to_new_object(fid))
                add("Show object after this step", lambda: self.doc.object_step_to(oid, fid))
                add("Show complete object", lambda: self.doc.object_fast_forward(oid))
                for bid in self.doc.object_history.outputs.get(fid, []):
                    if bid not in self.doc.step_states.get(index + 1, {}):
                        continue
                    add("New linked object from " + bid, lambda checked=False, b=bid: self.doc.branch_object(fid, b))
                    add("Independent copy of " + bid, lambda checked=False, b=bid: self.doc.branch_object(fid, b, linked=False))
                menu.addSeparator()
        if item_type == "object":
            rename()
            add("Show complete object", lambda: self.doc.object_fast_forward(item_id))
            show_hide()
        elif item_type in ("parameter", "dimension"):
            from omacad.ui.object_browser import edit_parameter
            add("Edit value…", lambda: edit_parameter(self, item_type, item_id))
            self._favorite_menu(menu, [item_type, *item_id])
            if item_type == "dimension":
                menu.addSeparator()
                add("🗑️ Delete dimension", lambda: self.doc.remove_dimension(*item_id))
        elif item_type in ("fav", "fav_gone"):
            if item_type == "fav":
                from omacad.ui.object_browser import edit_parameter
                add("Edit value…", lambda: edit_parameter(self, item_type, item_id))
            self._favorite_menu(menu, list(item_id))
        elif item_type == "fav_group":
            rename()
            add("🗑️ Remove group from favorites", lambda: self.doc.remove_favorite_group(item_id))
        elif item_type == "plane":
            add(f"✏️ Create Sketch on {item_id} Plane", lambda: self.start_sketch_on_plane.emit(item_id))
            add("📐 Offset Plane…", lambda: self.offset_plane_requested.emit("plane", item_id))
            add(f"🖼️ Insert Canvas on {item_id} Plane…", lambda: self.insert_canvas_requested.emit(item_id))
            add(f"🪚 Split Body with {item_id} Plane…", lambda: self.split_body_requested.emit("", item_id))
            menu.addSeparator()
            show_hide()

        elif item_type == "cplane":
            add("✏️ Create Sketch on this Plane", lambda: self.start_sketch_on_cplane.emit(item_id))
            add("📐 Offset Plane…", lambda: self.offset_plane_requested.emit("cplane", item_id))
            add("🖼️ Insert Canvas on this Plane…", lambda: self.insert_canvas_requested.emit(item_id))
            add("🪚 Split Body with this Plane…", lambda: self.split_body_requested.emit("", item_id))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_construction_plane(item_id))

        elif item_type == "body":
            add("🎨 Appearance / Färg…", lambda: self.body_color_requested.emit(item_id))
            menu.addSeparator()
            add("✥ Move…", lambda: self.move_body_requested.emit(item_id))
            add("🐚 Shell…", lambda: self.shell_body_requested.emit(item_id))
            add("🪚 Split Body…", lambda: self.split_body_requested.emit(item_id, ""))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            find("body")
            menu.addSeparator()
            add("💾 Export as STL…", lambda: self.export_body_stl.emit(item_id))
            add("💾 Export as STEP…", lambda: self.export_body_step.emit(item_id))
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_body(item_id))

        elif item_type == "canvas":
            add("✏️ Edit Canvas (Calibrate / Set Origin)…", lambda: self.edit_canvas_requested.emit(item_id))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_canvas(item_id))

        elif item_type == "section":
            on = bool(self.doc.sections[item_id].get("active"))
            add("🚫 Turn off" if on else "👁️ Turn on", lambda: self.doc.set_section_active(item_id, not on))
            add("✂️ Change the cut…", lambda: self.edit_section_requested.emit(item_id))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.doc.delete_section(item_id))

        elif item_type == "sketch":
            add("⬆️ Extrude\tE", lambda: self.extrude_sketch_requested.emit(item_id))
            add("📐 Offset Plane…", lambda: self.offset_plane_requested.emit("sketch", item_id))
            add("✏️ Edit Sketch", lambda: self.edit_sketch_requested.emit(item_id))
            add("📄 Duplicate", lambda: self.doc.duplicate_sketch(item_id))
            sk = self.doc.sketches.get(item_id)
            if sk is not None:
                from omacad.model.sketch import SketchText
                first_txt = next((e for e in sk.entities if isinstance(e, SketchText)), None)
                if first_txt is not None:
                    add("🔤 Edit Text…", lambda eid=first_txt.entity_id: self.edit_sketch_text_requested.emit(item_id, eid))
            menu.addSeparator()
            rename()
            menu.addSeparator()
            show_hide()
            find("sketch")
            menu.addSeparator()
            add("🗑️ Delete", lambda: self.delete_sketch_requested.emit(item_id))

        elif item_type == "sketch_text":
            s_id, ent_id = item_id.split(":", 1)
            add("🔤 Edit Text…", lambda: self.edit_sketch_text_requested.emit(s_id, ent_id))
            add("✏️ Edit Sketch", lambda: self.edit_sketch_requested.emit(s_id))
            self._favorite_menu(menu, ["text", s_id, ent_id])

        elif item_type in ("origin", "axis", "group"):
            show_hide()

        elif item_type == "view":
            add("🎥 Apply this view", lambda: self.named_view_requested.emit(item_id))

        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(pos))
