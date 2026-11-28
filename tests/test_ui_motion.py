"""A10: docked tool panels glide in and ribbon buttons fade their hover look, ending in their plain state."""
from PySide6.QtWidgets import QApplication, QDialog, QFormLayout, QLineEdit


def _app():
    return QApplication.instance() or QApplication([])


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
    QTest.qWait(400)
    assert dlg.graphicsEffect() is None and panel.tool_layout.contentsMargins().top() == top
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
    QTest.qWait(40)
    assert 0.0 < btn._hover_t < 1.0
    btn.grab()                                              # the two-pass paint mid-fade
    QTest.qWait(250)
    assert btn._hover_t == 1.0
    btn.leaveEvent(QEvent(QEvent.Type.Leave))
    QTest.qWait(300)
    assert btn._hover_t == 0.0
    btn.grab()
    btn.deleteLater()
