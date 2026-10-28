import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Tests never read or write the user's real settings (they also set the global curve smoothness)."""
    try:
        from omacad.ui import settings as settings_mod
    except Exception:   # CI installs only the modelling dependencies
        yield
        return
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "settings.json"))
    yield
    from omacad.model import quality
    quality.set_circle_segments(quality.DEFAULT_SEGMENTS)
    quality.set_interactive_mode(False)     # a test that ends mid-drag must not leave coarse curves for the next


@pytest.fixture(autouse=True, scope="session")
def never_ask_to_save():
    """Closing a test window with changes would open the modal "save changes?" box and hang the run: discard.
    Session-wide, because module-scoped window fixtures close their windows after per-test patches are undone.
    Tests of the question itself patch `_ask_save_changes` on MainWindow, which wins over this."""
    try:
        from omacad.ui.controllers.file_session import FileSessionMixin
    except Exception:   # CI installs only the modelling dependencies
        yield
        return
    original = FileSessionMixin._ask_save_changes
    FileSessionMixin._ask_save_changes = lambda self, name: "discard"
    yield
    FileSessionMixin._ask_save_changes = original


def pytest_sessionfinish(session, exitstatus):
    """Close every window the tests left open while Qt is still fully alive: Python tearing down live widgets at
    interpreter exit can segfault after all tests have passed (seen in CI)."""
    try:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    from omacad.ui.controllers.file_session import FileSessionMixin
    FileSessionMixin._ask_save_changes = lambda self, name: "discard"
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
