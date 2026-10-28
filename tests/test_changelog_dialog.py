"""Help > Changelog shows the whole CHANGELOG.md."""
from pathlib import Path

from PySide6.QtWidgets import QApplication

from omacad.ui.changelog_dialog import ChangelogDialog, find_changelog


def test_dialog_contains_every_version_of_the_changelog():
    QApplication.instance() or QApplication([])
    path = find_changelog()
    assert path is not None and path == Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    dlg = ChangelogDialog()
    shown = dlg.view.toPlainText()
    versions = [line[3:].split(" - ")[0] for line in text.splitlines() if line.startswith("## ")]
    assert len(versions) > 10 and all(v in shown for v in versions)
    dlg.search.setText(versions[-1])
    dlg.find_next()
    assert dlg.view.textCursor().hasSelection()


def test_changelog_has_a_close_button():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.changelog_dialog import ChangelogDialog
    QApplication.instance() or QApplication([])
    dlg = ChangelogDialog()
    dlg.show()
    assert dlg.btn_close.text() == "Close"
    dlg.btn_close.click()
    assert not dlg.isVisible()


def test_changelog_opens_at_the_newest_version():
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from omacad.ui.changelog_dialog import ChangelogDialog
    QApplication.instance() or QApplication([])
    dlg = ChangelogDialog()
    dlg.show()
    QTest.qWait(100)
    assert dlg.view.verticalScrollBar().value() == 0              # not at the oldest entries at the bottom
    assert dlg.view.verticalScrollBar().maximum() > 0
