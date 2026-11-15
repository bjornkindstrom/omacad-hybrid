"""UI tests for Pattern dialogs and previews."""
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.ui.main_window import MainWindow

DATA_DIR = Path(__file__).parent / "data"


def test_pattern_dialog_survives_fill_preview():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    doc = Exporter.load_project(str(DATA_DIR / "request_223_fill_pattern.json"))
    win.attach_document(doc)
    win.prompt_pattern("fill")
    dlg = win._pattern_dlg
    assert dlg is not None
    assert "copies will be made" in dlg.lbl_info.text()
    dlg.reject()
    assert win._pattern_dlg is None
    win.close()
    win.deleteLater()
