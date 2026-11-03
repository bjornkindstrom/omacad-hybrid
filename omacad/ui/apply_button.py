"""A green check button floating in the viewport that applies the open tool panel (Björn #160)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QToolButton


def add_apply_button(viewport, dialog, anchor, interval_ms: int = 60) -> QToolButton:
    """Show a green ✓ next to `anchor()` (a viewport pixel (x, y), or None to hide it) while `dialog` is open;
    clicking it accepts the dialog, so the mouse never has to travel to OK. It follows the anchor when the camera
    moves and is removed when the dialog finishes."""
    btn = QToolButton(viewport)
    btn.setText("✓")
    btn.setToolTip("Apply (Enter)")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(36, 36)
    btn.setStyleSheet("QToolButton { background: #2E9F4F; color: white; border: 2px solid #BFF0CC; "
                      "border-radius: 18px; font-size: 20px; font-weight: bold; }"
                      "QToolButton:hover { background: #3CC264; }")
    btn.clicked.connect(dialog.accept)
    btn.hide()

    def place():
        try:
            pos = anchor()
            if pos is None:
                btn.hide()
                return
            x = int(min(max(pos[0] + 28, 4), viewport.width() - btn.width() - 4))
            y = int(min(max(pos[1] - 44, 4), viewport.height() - btn.height() - 4))
            btn.move(x, y)
            btn.show()
            btn.raise_()
        except RuntimeError:        # the button or viewport is already gone
            pass

    timer = QTimer(dialog)
    timer.setInterval(interval_ms)
    timer.timeout.connect(place)
    timer.start()

    def done(*_):
        timer.stop()
        try:
            btn.hide()
            btn.deleteLater()
        except RuntimeError:
            pass

    dialog.finished.connect(done)
    dialog.destroyed.connect(done)
    return btn
