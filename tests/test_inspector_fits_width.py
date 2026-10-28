"""The Inspector is as wide as what it shows (Design overview, Shortcuts) and stays anchored to the right edge."""
from PySide6.QtWidgets import QApplication

from omacad.ui.dialogs import PatternDialog
from omacad.ui.main_window import MainWindow
from omacad.ui.side_panel import InspectorPanel


def test_inspector_width_follows_content():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    QApplication.processEvents()
    insp, vp = w.inspector, w.viewport
    insp.fit_to_content()
    overview = insp.width()
    assert InspectorPanel.MIN_WIDTH <= overview < InspectorPanel.MAX_WIDTH - 60   # not the old fixed 380
    assert overview >= insp.content_widget.sizeHint().width()                      # nothing is cut
    assert insp.x() + insp.width() == vp.width() - InspectorPanel.EDGE_GAP          # anchored right
    assert vp.viewcube.right_margin == overview + 25                                # cube keeps clear

    w.doc.add_box(10, 10, 10)
    dlg = PatternDialog(w.doc, w)
    insp.dock_tool(dlg)
    QApplication.processEvents()
    insp.fit_to_content()
    assert insp.width() >= dlg.width()                                              # a tool gets its room
    assert insp.x() + insp.width() == vp.width() - InspectorPanel.EDGE_GAP

    insp.undock_tool(dlg)
    QApplication.processEvents()
    insp.fit_to_content()
    assert insp.width() < InspectorPanel.MAX_WIDTH - 60                             # shrinks back
    w.close()
