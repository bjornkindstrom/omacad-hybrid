from PySide6.QtWidgets import QApplication
from omacad.ui.main_window import MainWindow


def test_lid_command_preview_cancel_and_accept():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    try:
        win.doc.add_box(30, 20, 20)
        win.ribbon.make_lid_clicked.emit()
        dlg = win.inspector.current_tool_dlg
        assert dlg.windowTitle() == 'Make a lid'
        dlg.fields['overlap'].setValue(25)
        assert not dlg.btn_ok.isEnabled()
        dlg.fields['overlap'].setValue(5)
        assert dlg.btn_ok.isEnabled()
        dlg.reject()
        assert len(win.doc.bodies) == 1
        win.prompt_make_lid()
        win.inspector.current_tool_dlg.accept()
        assert len(win.doc.bodies) == 2
        from omacad.ui.feature_edit import can_edit
        assert can_edit(win.doc.timeline.features[-1])
    finally:
        win.close()
        app.processEvents()


def test_timeline_edit(monkeypatch):
    from omacad.ui.dialogs.lid_dlg import LidDialog
    from omacad.ui.feature_edit import edit_feature
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    try:
        win.doc.add_box(30,20,20)
        win.doc.add_lid(next(iter(win.doc.bodies)))
        def accept(dlg):
            dlg.fields['thickness'].setValue(3)
            return 1
        monkeypatch.setattr(LidDialog, 'exec', accept)
        assert edit_feature(win, win.doc, 1)
        assert win.doc.timeline.features[1].thickness == 3
    finally:
        win.close()
        app.processEvents()


def test_lid_has_own_thumbnail_and_edge_settings():
    from omacad.ui.browser import BrowserTree
    from omacad.ui.dialogs.lid_dlg import LidDialog
    from omacad.model.document import Document
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(30,20,20)
    feat = doc.add_lid(next(iter(doc.bodies)))
    browser = BrowserTree(doc)
    dlg = LidDialog(doc)
    try:
        browser.thumbnails.finish()
        oid = doc.object_history.owners[feat.feature_id]
        assert not browser.thumbnails.icon(oid).isNull()
        assert len(doc.object_history.objects) == 2
        dlg.edge_kind.setCurrentIndex(dlg.edge_kind.findData('fillet'))
        assert dlg.fields['edge_size'].isEnabled()
        dlg.fields['edge_size'].setValue(.7)
        assert dlg.values()[1]['edge_kind'] == 'fillet'
        assert dlg.values()[1]['edge_size'] == .7
    finally:
        dlg.close()
        browser.close()
        app.processEvents()
