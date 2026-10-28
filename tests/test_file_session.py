"""New/Open/close ask about unsaved changes; Open Recent remembers files."""
import pytest
from PySide6.QtWidgets import QApplication
from omacad.model.document import Document
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win(monkeypatch):
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.answers = []
    monkeypatch.setattr(type(w), "_ask_save_changes", lambda self, name: self.answers.pop(0))
    return w


def draw_something(w):
    w.doc.add_box(10, 10, 10)


def test_clean_document_is_not_asked(win):
    assert not win.is_dirty()
    doc = win.doc
    win.on_file_new()                 # no question: answers is empty, popping would raise
    assert win.doc is not doc


def test_changes_ask_and_cancel_keeps_document(win):
    draw_something(win)
    assert win.is_dirty()
    win.answers = ["cancel"]
    doc = win.doc
    win.on_file_new()
    assert win.doc is doc


def test_discard_replaces_document(win):
    draw_something(win)
    win.answers = ["discard"]
    doc = win.doc
    win.on_file_new()
    assert win.doc is not doc and not win.is_dirty()


def test_save_then_new(win, tmp_path, monkeypatch):
    draw_something(win)
    path = str(tmp_path / "a.omacad")
    monkeypatch.setattr("omacad.ui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (path, ""))
    win.answers = ["save"]
    doc = win.doc
    win.on_file_new()
    assert win.doc is not doc
    assert (tmp_path / "a.omacad").exists()
    assert win.recent_files()[0].endswith("a.omacad")


def test_cancelled_save_as_keeps_document(win, monkeypatch):
    draw_something(win)
    monkeypatch.setattr("omacad.ui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: ("", ""))
    win.answers = ["save"]
    doc = win.doc
    win.on_file_new()
    assert win.doc is doc


def test_saved_document_is_clean_and_edit_makes_it_dirty(win, tmp_path, monkeypatch):
    draw_something(win)
    win._save_to(str(tmp_path / "b.omacad"))
    assert not win.is_dirty()
    win.doc.select_body(next(iter(win.doc.bodies)))      # selecting is not an edit
    win.viewport.azimuth += 20
    assert not win.is_dirty()
    win.doc.add_cylinder(3, 4)
    assert win.is_dirty()


def test_recent_list_order_limit_and_missing_file(win, tmp_path, monkeypatch):
    files = []
    for i in range(12):
        p = tmp_path / f"f{i}.omacad"
        p.write_text("{}")
        files.append(str(p))
        win.add_recent_file(str(p))
    rec = win.recent_files()
    assert len(rec) == 10 and rec[0].endswith("f11.omacad")
    win.add_recent_file(files[5])
    assert win.recent_files()[0].endswith("f5.omacad") and len(win.recent_files()) == 10
    actions = [a.text() for a in win.menu_recent.actions() if a.isEnabled()]
    assert actions[0].startswith("f5.omacad")
    (tmp_path / "f5.omacad").unlink()
    monkeypatch.setattr("omacad.ui.main_window.QMessageBox.warning", lambda *a, **k: None)
    win.open_recent(files[5])
    assert not any(p.endswith("f5.omacad") for p in win.recent_files())


def test_closing_the_window_asks_and_cancel_keeps_it_open(win):
    """Björn #55, Lennart #68: closing Omacad never asked to save, because QMainWindow (first in the bases) hid
    FileSessionMixin.closeEvent."""
    from PySide6.QtGui import QCloseEvent
    draw_something(win)
    win.answers = ["cancel"]
    event = QCloseEvent()
    win.closeEvent(event)
    assert not event.isAccepted() and not win.answers
    win.answers = ["discard"]
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()


def test_no_mixin_method_is_hidden_by_qt():
    from PySide6.QtWidgets import QMainWindow
    hidden = [f"{k.__name__}.{n}" for k in MainWindow.__mro__ if k.__module__.startswith("omacad") and k is not MainWindow
              for n in k.__dict__ if not n.startswith("__") and hasattr(QMainWindow, n) and n not in MainWindow.__dict__]
    assert not hidden
