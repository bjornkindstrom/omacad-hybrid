"""#222: hint boxes in the viewport (value boxes, snap badges, relation and dimension badges) never cover each other."""
from PySide6.QtCore import QRectF


def test_place_label_moves_a_box_off_an_earlier_one():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    v = win.viewport
    v._label_rects = []
    badge = v.place_label(QRectF(100, 100, 18, 18), movable=False)      # relation badge stays where it is
    assert badge == QRectF(100, 100, 18, 18)
    box = v.place_label(QRectF(90, 95, 64, 24))                         # value box placed on top of it
    assert not box.intersects(badge)
    third = v.place_label(QRectF(92, 97, 64, 24))
    assert not third.intersects(badge) and not third.intersects(box)
    v._label_rects = []
    assert v.place_label(QRectF(90, 95, 64, 24)) == QRectF(90, 95, 64, 24)   # free spot: unchanged
    win.close()
