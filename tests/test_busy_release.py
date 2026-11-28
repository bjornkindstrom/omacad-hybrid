"""A spin box arrow let go of while a preview is being worked out takes one step, not a run of them.

The busy keeper holds back mouse input while busy.run works; it used to drop the release too, so the spin box
still thought its arrow was held and its auto-repeat stepped on (each step another preview)."""
import time

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QStyle, QStyleOptionSpinBox, QWidget


def test_a_release_during_busy_work_reaches_the_spin_box(monkeypatch):
    app = QApplication.instance() or QApplication([])
    from omacad import busy
    from omacad.ui import busy_dialog
    win = QWidget()
    win.resize(200, 80)
    spin = QDoubleSpinBox(win)
    spin.setRange(0, 1000)
    spin.setValue(10)
    spin.resize(120, 30)
    win.show()
    QTest.qWait(300)                                   # first-show style events out of the way
    monkeypatch.setattr(busy, "_ui", None)
    keeper = busy_dialog.install(win)
    try:
        opt = QStyleOptionSpinBox()
        spin.initStyleOption(opt)
        up = QPointF(spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                                 QStyle.SubControl.SC_SpinBoxUp, spin).center())

        def mouse(kind, buttons):
            return QMouseEvent(kind, up, QPointF(spin.mapToGlobal(up.toPoint())), Qt.MouseButton.LeftButton, buttons,
                               Qt.KeyboardModifier.NoModifier)
        steps = []

        def changed(value):
            if not steps:                              # the user lets go while the preview is worked out
                app.postEvent(spin, mouse(QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton))
            steps.append(value)
            busy.run("preview", lambda: time.sleep(0.3))   # longer than quick, shorter than the busy box
        spin.valueChanged.connect(changed)
        app.sendEvent(spin, mouse(QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton))
        QTest.qWait(1500)                              # three auto-repeat periods
        assert steps == [11.0] and spin.value() == 11.0
    finally:
        busy.install(None)
        win.deleteLater()
    assert keeper._releases == []
