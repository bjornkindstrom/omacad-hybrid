"""Request/report dialog: the user can replace the built-in screenshot with an image file from the computer."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


def _dialog(mode, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication, QFileDialog
    QApplication.instance() or QApplication([])
    from omacad.ui.feedback_dialog import FeedbackDialog
    shot = QPixmap(400, 300)
    shot.fill(QColor(255, 255, 255))
    mine = QPixmap(120, 80)
    mine.fill(QColor(0, 0, 255))
    path = tmp_path / "mine.png"
    mine.save(str(path))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    return FeedbackDialog(None, shot, mode=mode)


@pytest.mark.parametrize("mode", ["request", "report"])
def test_own_image_replaces_the_screenshot_and_can_be_undone(mode, tmp_path, monkeypatch):
    dlg = _dialog(mode, tmp_path, monkeypatch)
    assert dlg.own_image() is None
    dlg.choose_own_image()
    img = dlg.own_image()
    assert (img.width(), img.height()) == (120, 80)
    dlg.use_builtin_image()
    assert dlg.own_image() is None and dlg.image.pixmap.width() == 400


def test_unreadable_file_keeps_the_screenshot(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    dlg = _dialog("request", tmp_path, monkeypatch)
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(bad), ""))
    dlg.choose_own_image()
    assert dlg.own_image() is None and dlg.image.pixmap.width() == 400
