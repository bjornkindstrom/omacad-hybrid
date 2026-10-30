import pytest
from PySide6.QtWidgets import QApplication
from omacad.ui.main_window import MainWindow

@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()

def test_polygon_sides_pencil_click_edits_inline(win):
    doc = win.doc
    sketch = doc.start_sketch("XY")
    res = sketch.add_polygon((0.0, 0.0), (20.0, 0.0), sides=6)
    gid = res[0].group
    doc.finish_sketch()

    win.browser.refresh_tree()
    tree = win.browser.tree

    # Find the polygon sides item
    target_item = None
    for item, _ in win.browser._walk():
        data = item.data(0, 256) # ROLE = Qt.ItemDataRole.UserRole = 256
        if data and data[0] == "polygon_sides":
            target_item = item
            break

    assert target_item is not None
    assert "Polygon sides: 6" in target_item.text(0)

    # Click on column 1 (pencil)
    win.browser.on_item_clicked(target_item, 1)
    QApplication.processEvents()

    # The tree should enter editing state, not open inspector/dock_tool
    assert win.inspector.current_tool_dlg is None
