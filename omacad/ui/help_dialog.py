"""Help & Commands (F1): a window beside the work with every function, grouped as in the ribbon, its help text,
shortcut and where to find it. Type keywords to search (hole, round, parameter ...); Enter runs the selected
function, so the window doubles as a command search."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QTextBrowser,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from omacad.ui import commands
from omacad.ui.help_topics import search, topics


class HelpWindow(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main = main_window
        self.setWindowTitle("Help & Commands")
        self.setWindowFlag(Qt.WindowType.Tool)
        self.resize(820, 540)
        self._all = topics()
        lay = QVBoxLayout(self)
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("Search: hole, round, parameter, copy, print …   (Enter runs the selected function)")
        self.edt_search.setClearButtonEnabled(True)
        self.edt_search.textChanged.connect(self._fill)
        self.edt_search.installEventFilter(self)
        lay.addWidget(self.edt_search)
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Function", "Key"])
        self.tree.setColumnWidth(0, 210)
        self.tree.currentItemChanged.connect(lambda *_: self._show())
        self.tree.itemActivated.connect(lambda *_: self.run_selected())
        split.addWidget(self.tree)
        self.txt = QTextBrowser()
        self.txt.setOpenExternalLinks(False)
        split.addWidget(self.txt)
        split.setSizes([330, 490])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        self.lbl_count = QLabel("")
        row.addWidget(self.lbl_count, 1)
        self.btn_run = QPushButton("Run")
        self.btn_run.setToolTip("Start the selected function (Enter)")
        self.btn_run.clicked.connect(self.run_selected)
        row.addWidget(self.btn_run)
        self.btn_close = QPushButton("Close")
        self.btn_close.setToolTip("Close this window (Esc)")
        self.btn_close.clicked.connect(self.hide)
        row.addWidget(self.btn_close)
        lay.addLayout(row)
        self._fill("")
        self.edt_search.setFocus()

    def eventFilter(self, obj, event):
        """In the search field: Up/Down move through the list, Enter runs the selection."""
        from PySide6.QtCore import QEvent
        if obj is self.edt_search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._step(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.run_selected()
                return True
        return super().eventFilter(obj, event)

    def _leaves(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            out += [g.child(j) for j in range(g.childCount())]
        return out

    def _step(self, delta: int):
        leaves = self._leaves()
        if not leaves:
            return
        cur = self.tree.currentItem()
        i = leaves.index(cur) if cur in leaves else -1
        self.tree.setCurrentItem(leaves[max(0, min(len(leaves) - 1, i + delta))])

    def _fill(self, query: str):
        hits = search(query, self._all)
        self.tree.clear()
        groups = {}
        for t in hits:
            if t.group not in groups:
                groups[t.group] = QTreeWidgetItem(self.tree, [t.group])
                groups[t.group].setFlags(Qt.ItemFlag.ItemIsEnabled)
                groups[t.group].setFirstColumnSpanned(True)
            item = QTreeWidgetItem(groups[t.group], [t.title, t.shortcut])
            item.setData(0, Qt.ItemDataRole.UserRole, t)
            item.setToolTip(0, t.text)
        self.tree.expandAll()
        leaves = self._leaves()
        self.lbl_count.setText(f"{len(leaves)} function(s)" + (f" for '{query}'" if query.strip() else ""))
        if leaves:      # the best match is selected (Enter runs it), wherever its group is in the list
            best = hits[0] if query.strip() else None
            self.tree.setCurrentItem(next((i for i in leaves if i.data(0, Qt.ItemDataRole.UserRole) is best), leaves[0]))
        else:
            self.txt.setHtml("<p>Nothing found. Try another word (for example <i>round</i>, <i>hole</i>, "
                             "<i>copy</i>, <i>parameter</i>).</p>")
        self._show()

    def selected(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def _show(self):
        t = self.selected()
        self.btn_run.setEnabled(bool(t and t.cid))
        if t is None:
            return
        key = f"<p><b>Key:</b> {t.shortcut}</p>" if t.shortcut else ""
        where = f"<p><b>Where:</b> {t.where}</p>" if t.where else ""
        run = "<p style='color:#9AA0A6'>Enter or Run starts it.</p>" if t.cid else ""
        self.txt.setHtml(f"<h3>{t.title}</h3><p>{t.text}</p>{key}{where}{run}")

    def run_selected(self):
        t = self.selected()
        if t is None or not t.cid:
            return
        c = commands.get(t.cid)
        sketching = self.main.doc.active_sketch is not None
        if c.modes == ("sketch",) and not sketching:
            self.main.status_label.setText(f"{c.label} is a sketch tool: open or create a sketch first.")
            return
        self.hide()
        self.main.ribbon._emit_command(t.cid)
