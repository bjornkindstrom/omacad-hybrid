"""Thread / Coil from a click on a cylinder: the live preview shows and OK makes the step."""
import time

import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication


def _click(vp, point):
    for kind, buttons, handler in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton, vp.mousePressEvent),
                                   (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton, vp.mouseReleaseEvent)):
        handler(QMouseEvent(kind, QPointF(*point), QPointF(*point), Qt.MouseButton.LeftButton, buttons,
                            Qt.KeyboardModifier.NoModifier))


def test_click_cylinder_previews_and_ok_adds_thread():
    from omacad.ui.main_window import MainWindow
    from omacad.ui.dialogs.thread_dlg import ThreadDialog

    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    doc = win.doc
    doc.add_cylinder(10, 30)
    vp = win.viewport
    vp.resize(1000, 800)
    vp.azimuth, vp.elevation, vp.distance = 0., 10., 80.
    vp.target = np.array([0., 0., 15.], dtype=np.float32)
    previews = []
    vp.set_preview = lambda solid, *a, **k: previews.append(solid)

    win.prompt_thread()
    # This window's dialog: in the full suite earlier tests leave their own ThreadDialogs alive.
    dlg = next(w for w in app.allWidgets() if isinstance(w, ThreadDialog) and w.window() is win)
    _click(vp, vp.world_to_screen(np.array([0., -10., 15.])))
    values = dlg.get_values()
    assert values["diameter"] == 20.0 and values["length"] == 30.0
    previews.clear()
    dlg.changed.emit()
    for _ in range(20):          # the preview is debounced by a 60 ms timer
        app.processEvents()
        if previews:
            break
        time.sleep(0.02)
    assert previews and previews[-1] is not None and not previews[-1].is_empty()

    dlg.accept()
    assert [f.feature_type for f in doc.timeline.features] == ["cylinder", "thread"]
    win.close()
