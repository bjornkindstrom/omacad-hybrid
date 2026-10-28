"""Help > Changelog: the whole CHANGELOG.md, newest version first, readable inside the app."""
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout


def find_changelog() -> Optional[Path]:
    """CHANGELOG.md next to the sources, or inside the packaged app."""
    roots = [Path(__file__).resolve().parents[2]]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, Path(sys._MEIPASS))
    return next((r / "CHANGELOG.md" for r in roots if (r / "CHANGELOG.md").is_file()), None)


def changelog_text() -> str:
    path = find_changelog()
    if path is None:
        return "# Changelog\n\nCHANGELOG.md was not found."
    return path.read_text(encoding="utf-8")


class ChangelogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Changelog")
        self.resize(760, 680)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the changelog…")
        self.search.returnPressed.connect(self.find_next)
        btn = QPushButton("Find next")
        btn.clicked.connect(self.find_next)
        bar.addWidget(self.search)
        bar.addWidget(btn)
        layout.addLayout(bar)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        # no raw HTML: a text like <name> would otherwise be read as a tag and swallow the rest of the page
        flags = QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML
        self.view.document().setMarkdown(changelog_text(), flags)
        self.view.moveCursor(QTextCursor.MoveOperation.Start)      # setMarkdown leaves the cursor, and so the view, at the end
        layout.addWidget(self.view)
        row = QHBoxLayout()
        row.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.setDefault(True)
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        layout.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._to_top)     # the newest version is at the top of the file: start there

    def _to_top(self):
        self.view.verticalScrollBar().setValue(0)

    def find_next(self):
        text = self.search.text()
        if text and not self.view.find(text):          # wrap around to the top
            self.view.moveCursor(self.view.textCursor().MoveOperation.Start)
            self.view.find(text)
