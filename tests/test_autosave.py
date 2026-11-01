"""Request #143: unsaved work is autosaved to a recovery file and offered back after a crash."""
import subprocess
import sys

import pytest
from PySide6.QtWidgets import QApplication

from omacad import autosave


def _crashed_autosave(folder):
    """A separate Omacad-like process that autosaves and dies without closing normally."""
    code = (
        "import os, sys; from omacad import autosave; from omacad.model.document import Document\n"
        "d = Document('Omacad - Crashed'); d.start_sketch('XY').add_rect((0, 0), (12, 7))\n"
        f"a = autosave.Autosave(sys.argv[1]); a.write(d, None, {{'azimuth': 30.0}}); os._exit(1)\n")
    subprocess.run([sys.executable, "-c", code, str(folder)], check=False, timeout=60)


def test_live_process_is_not_an_orphan_but_a_crashed_one_is(tmp_path):
    mine = autosave.Autosave(tmp_path)
    from omacad.model.document import Document
    mine.write(Document(), None, {})
    assert autosave.orphans(tmp_path) == []                   # held by this process
    _crashed_autosave(tmp_path)
    found = autosave.orphans(tmp_path, own=mine.file)
    assert len(found) == 1 and found[0] != mine.file
    assert autosave.load(found[0])["document"]["sketches"]
    mine.release()
    assert not mine.file.exists()


@pytest.fixture
def win(tmp_path):
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    w.start_autosave(folder=tmp_path / "autosave")
    yield w
    w._autosave.release()


def test_unsaved_work_is_written_and_saving_removes_it(win, tmp_path):
    win.autosave_now(force=True)
    assert not win._autosave.file.exists()                    # nothing changed: nothing to recover
    win.doc.add_box(10, 20, 30)
    win.autosave_now(force=True)
    assert win._autosave.file.exists()
    win._save_to(str(tmp_path / "part.omacad"))
    assert not win._autosave.file.exists()


def test_autosave_off_writes_nothing(win, monkeypatch):
    from omacad.ui import settings
    monkeypatch.setattr(settings.get_settings(), "get",
                        lambda key, default=None: 0 if key == "autosave_minutes" else default)
    win.doc.add_box(10, 20, 30)
    win._autosave_at -= 3600
    win.autosave_now()
    assert not win._autosave.file.exists()


def test_crashed_work_is_resumed_on_start(win, tmp_path, monkeypatch):
    folder = tmp_path / "autosave"
    _crashed_autosave(folder)
    monkeypatch.setattr(win, "_ask_resume_autosave", lambda name, when: "resume")
    assert win.offer_autosave_resume()
    sk = next(iter(win.doc.sketches.values())) if isinstance(win.doc.sketches, dict) else win.doc.sketches[0]
    assert len(sk.entities) == 4
    assert win.viewport.azimuth == pytest.approx(30.0)
    assert win.is_dirty()                                     # still unsaved: the user decides where it goes
    assert autosave.orphans(folder, own=win._autosave.file) == []
    assert win._autosave.file.exists()                        # protected again right away


def test_discarded_crash_file_is_gone_and_later_keeps_it(win, tmp_path, monkeypatch):
    folder = tmp_path / "autosave"
    _crashed_autosave(folder)
    monkeypatch.setattr(win, "_ask_resume_autosave", lambda name, when: "later")
    assert not win.offer_autosave_resume()
    assert len(autosave.orphans(folder, own=win._autosave.file)) == 1
    monkeypatch.setattr(win, "_ask_resume_autosave", lambda name, when: "discard")
    assert not win.offer_autosave_resume()
    assert autosave.orphans(folder, own=win._autosave.file) == []
