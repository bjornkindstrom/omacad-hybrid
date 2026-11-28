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


def test_fill_preview_survives_setting_changes_and_kind_switches():
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtTest import QTest
    import shiboken6
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.attach_document(Exporter.load_project(str(DATA_DIR / 'request_223_fill_pattern.json')))
    win.prompt_pattern('fill')
    dlg = win._pattern_dlg
    sources = dlg.source_ids()
    try:
        for kind in ('fill', 'linear', 'circular', 'mirror', 'fill'):
            dlg.cmb_kind.setCurrentIndex(dlg.KINDS.index(kind))
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert shiboken6.isValid(dlg.chk_second)
            for rows in dlg.rows.values():
                assert all(shiboken6.isValid(widget) for _, widget in rows)
        for widget, value in ((dlg.spn_gap, 6), (dlg.spn_margin, 2), (dlg.spn_partial, 50)):
            widget.setValue(value)
            QTest.qWait(150)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert dlg.source_ids() == sources
            assert 'copies will be made' in dlg.lbl_info.text(), dlg.lbl_info.text()
            assert win.viewport.preview_mesh is not None
        dlg.cmb_layout.setCurrentIndex(1)
        QTest.qWait(150)
        assert 'copies will be made' in dlg.lbl_info.text(), dlg.lbl_info.text()
        dlg.accept()
        pattern = win.doc.timeline.features[-1]
        assert pattern.feature_type == 'pattern'
        assert pattern.copies > 0
        assert pattern.spacing1 == 6
        assert pattern.spacing2 == 2
    finally:
        if win._pattern_dlg is not None:
            dlg.reject()
        win.close()
        win.deleteLater()
