"""Every tool panel: no button, checkbox, list choice or label is cut off (the panel is only ~360 px wide, so names
are short and the explanations sit in tooltips)."""
import pytest
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox, QLabel, QMessageBox, QPushButton, QRadioButton

from omacad.ui.main_window import MainWindow

PROMPTS = ["prompt_move_body", "prompt_box", "prompt_cylinder", "prompt_prism", "prompt_sphere", "prompt_thread",
           "prompt_jar", "prompt_shell", "prompt_split_body", "prompt_offset_face", "prompt_honeycomb", "prompt_pattern",
           "prompt_extrude", "prompt_revolve", "prompt_emboss"]


@pytest.fixture(scope="module")
def win():
    if QApplication.instance() is None:
        fmt = QSurfaceFormat()
        fmt.setDepthBufferSize(24)
        QSurfaceFormat.setDefaultFormat(fmt)
        QApplication([])
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    QTest.qWait(500)
    w.doc.add_box(20, 20, 20)
    sk = w.doc.start_sketch("XY")
    sk.add_rect((30, 0), (40, 10))
    sk.add_text("AB", (30, 20))
    w.doc.finish_sketch()
    w.doc.selected_body_ids = [next(iter(w.doc.bodies))]
    yield w
    w.close()


def _cut(dlg):
    out = []
    for b in dlg.findChildren(QPushButton) + dlg.findChildren(QCheckBox) + dlg.findChildren(QComboBox) \
            + dlg.findChildren(QRadioButton) + dlg.findChildren(QLabel):
        if not b.isVisible() or (isinstance(b, QLabel) and (b.wordWrap() or not b.text())):
            continue
        fm = b.fontMetrics()
        if isinstance(b, QComboBox):
            texts = [b.itemText(i) for i in range(b.count())]
            need = max([fm.horizontalAdvance(t) for t in texts] or [0]) + 34      # every choice, once picked
        elif isinstance(b, QLabel):
            texts, need = [b.text()], fm.horizontalAdvance(b.text().split("\n")[0])
        else:
            texts, need = [b.text()], b.sizeHint().width()
        if need > b.width() + 3:
            out.append((max(texts, key=len), b.width(), need))
    return out


@pytest.mark.parametrize("prompt", PROMPTS)
def test_panel_texts_fit(win, prompt):
    getattr(win, prompt)()
    QTest.qWait(150)
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None
    try:
        assert _cut(dlg) == []
    finally:
        dlg.reject()
        QTest.qWait(50)
