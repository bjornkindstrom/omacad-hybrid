"""With the timeline rolled back, a new step goes in at the marker; formulas and the resolved operation must land on
that step, not on the last one in the history."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.jar import JarSpec
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.doc.add_box(10, 10, 10)
    w.doc.add_cylinder(3, 30)
    w.doc.timeline.step_to(1, w.doc)
    return w


def test_box_formula_goes_to_the_inserted_step(win):
    win.prompt_box()
    dlg = win.inspector.current_tool_dlg
    dlg.spn_length.set_expression("4*5")
    dlg.accept()
    feats = win.doc.timeline.features
    assert [f.feature_type for f in feats] == ["box", "box", "cylinder"]
    assert feats[1].exprs.get("length") == "4*5"
    assert not feats[2].exprs.get("length")


def test_jar_at_a_rolled_back_marker_keeps_its_thread():
    from omacad.model.document import Document
    doc = Document()
    doc.add_box(5, 5, 5)
    doc.add_box(6, 6, 6)
    doc.timeline.step_to(1, doc)
    doc.add_jar(JarSpec())
    assert doc.timeline.features[-1].feature_type == "box"           # the later box is still there
    assert any(f.feature_type == "thread" for f in doc.timeline.features)
