"""Thread UI dialog, cylinder clicking, live preview, and anchor interaction tests."""
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui.dialogs import ThreadDialog
from omacad.ui.main_window import MainWindow


def _click(vp, point):
    for kind, buttons, handler in ((QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton, vp.mousePressEvent),
                                   (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton, vp.mouseReleaseEvent)):
        handler(QMouseEvent(kind, QPointF(*point), QPointF(*point), Qt.MouseButton.LeftButton, buttons,
                            Qt.KeyboardModifier.NoModifier))


def test_click_cylinder_previews_and_ok_adds_thread():
    import time
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.viewport.paintGL = lambda: None
    win.viewport.initializeGL = lambda: None
    doc = win.doc
    doc.add_cylinder(10, 30)
    vp = win.viewport

    vp.resize(1000, 800)
    vp.azimuth, vp.elevation, vp.distance = 0.0, 10.0, 80.0
    vp.target = np.array([0.0, 0.0, 15.0], dtype=np.float32)
    previews = []
    vp.set_preview = lambda solid, *a, **k: previews.append(solid)

    win.prompt_thread()
    dlg = next(w for w in app.allWidgets() if isinstance(w, ThreadDialog) and w.window() is win)
    _click(vp, vp.world_to_screen(np.array([0.0, -10.0, 15.0])))
    values = dlg.get_values()
    assert values["diameter"] == 20.0 and values["length"] == 30.0
    previews.clear()
    dlg.changed.emit()
    for _ in range(20):
        app.processEvents()
        if previews:
            break
        time.sleep(0.02)
    assert previews and previews[-1] is not None and not previews[-1].is_empty()

    dlg.accept()
    assert [f.feature_type for f in doc.timeline.features] == ["cylinder", "thread"]
    win.close()


def test_dialog_values_carry_the_anchor():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_cylinder(10.0, 40.0)
    dlg = ThreadDialog(doc)
    assert not dlg.cmb_anchor.isEnabled()
    dlg.apply_cylinder_info({"diameter": 20.0, "length": 40.0, "is_internal": False, "origin": [0, 0, 0], "axis": [0, 0, 1]})
    assert dlg.cmb_anchor.isEnabled()
    dlg.cmb_anchor.setCurrentIndex(dlg.cmb_anchor.findData("top"))
    dlg.spn_length.setValue(10.0)
    v = dlg.get_values()
    assert (v["anchor"], v["host_length"]) == ("top", 40.0)


def test_dialog_new_thread_on_a_cylinder_follows_by_default_and_keeps_the_offset():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_cylinder(15.0, 10.0)
    dlg = ThreadDialog(doc)
    dlg.apply_cylinder_info({"diameter": 30.0, "length": 10.0, "is_internal": False, "origin": [0, 0, 0],
                             "axis": [0, 0, 1]})
    assert dlg.chk_follow.isChecked() and dlg.chk_follow.isEnabled()
    dlg.spn_dia.setValue(29.99)
    v = dlg.get_values()
    assert v["follow_host"] is True and v["host_offset"] == pytest.approx(-0.01)
    dlg.set_plane(None)
    assert not dlg.chk_follow.isEnabled() and dlg.get_values()["follow_host"] is False


def test_dialog_switching_follow_on_takes_the_cylinders_diameter():
    QApplication.instance() or QApplication([])
    dlg = ThreadDialog(Document())
    dlg.set_anchor("bottom", 0.0, 5.0)
    dlg.spn_dia.setValue(29.99)
    dlg.set_host(35.99, False)
    assert not dlg.chk_follow.isChecked()
    dlg.chk_follow.setChecked(True)
    assert dlg.spn_dia.value() == pytest.approx(35.99)
    assert dlg.get_values()["host_offset"] == pytest.approx(0.0)
