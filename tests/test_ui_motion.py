"""A10: docked tool panels glide in and ribbon buttons fade their hover look, ending in their plain state."""
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QLineEdit


def _app():
    return QApplication.instance() or QApplication([])


def _wait_for(cond, ms):
    """Process events until cond() holds (animations run on timers, slow when the machine is busy)."""
    import time
    from PySide6.QtTest import QTest
    end = time.monotonic() + ms / 1000.0
    while not cond():
        if time.monotonic() > end:
            return False
        QTest.qWait(10)
    return True


def _on():
    from omacad.ui.settings import get_settings
    get_settings()._data["ui_animations"] = True


def test_a_docked_tool_fades_in_and_ends_without_an_effect_or_extra_margin():
    _app()
    _on()
    from PySide6.QtTest import QTest
    from omacad.model.document import Document
    from omacad.ui.side_panel import InspectorPanel
    panel = InspectorPanel(Document())
    top = panel.tool_layout.contentsMargins().top()
    dlg = QDialog()
    QFormLayout(dlg).addRow("Size", QLineEdit())
    panel.dock_tool(dlg)
    assert dlg.graphicsEffect() is not None and dlg.graphicsEffect().opacity() < 0.05
    assert panel.tool_layout.contentsMargins().top() > top
    assert _wait_for(lambda: dlg.graphicsEffect() is None, 5000)       # timer driven: slow under load
    assert panel.tool_layout.contentsMargins().top() == top
    dlg.reject()
    panel.deleteLater()


def test_off_in_settings_nothing_moves():
    _app()
    from omacad.model.document import Document
    from omacad.ui.side_panel import InspectorPanel
    panel = InspectorPanel(Document())
    dlg = QDialog()
    panel.dock_tool(dlg)
    assert dlg.graphicsEffect() is None
    panel.deleteLater()


def test_a_ribbon_button_fades_its_hover_and_paints_mid_fade():
    _app()
    _on()
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtTest import QTest
    from omacad.ui.ribbon import RibbonButton
    btn = RibbonButton("Extrude", "⬆️", command="extrude")
    btn.resize(60, 60)
    btn.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    anim = btn._hover_anim
    anim.pause()
    anim.setCurrentTime(anim.duration() // 2)               # half way, whatever the machine's load
    assert 0.0 < btn._hover_t < 1.0
    btn.grab()                                              # the two-pass paint mid-fade
    anim.resume()
    assert _wait_for(lambda: btn._hover_t == 1.0, 5000)
    btn.leaveEvent(QEvent(QEvent.Type.Leave))
    assert _wait_for(lambda: btn._hover_t == 0.0, 5000)
    btn.grab()
    btn.deleteLater()
