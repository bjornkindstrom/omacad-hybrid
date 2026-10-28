"""Jar with Lid end to end: the Primitives menu entry opens the panel with -0.2 tolerance, sliders on the fields, OK
adds the jar and the lid as one undo step, and the panel remembers the sizes."""
import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow
from omacad.ui.numeric_slider import NumericSlider


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def test_jar_tool_adds_jar_and_lid_as_one_step(win):
    win.ribbon.jar_clicked.emit()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None and dlg.windowTitle() == "Jar with Lid"
    assert dlg.spins["tolerance"].value() == pytest.approx(-0.2)
    assert all(isinstance(s.parentWidget(), NumericSlider) for s in dlg.spins.values())
    dlg.spins["diameter"].setValue(50.0)
    dlg.spins["neck_diameter"].setValue(40.0)
    dlg.accept()
    assert sorted(b.name for b in win.doc.bodies.values()) == ["Jar", "Lid"]
    assert len(win.doc.undo_stack) == 1
    win.doc.undo()
    assert not win.doc.bodies
    win.prompt_jar()                                         # remembers the last sizes
    again = win.inspector.current_tool_dlg
    assert again.spins["diameter"].value() == pytest.approx(50.0)
    again.reject()
    assert not win.doc.bodies


def test_impossible_jar_cannot_be_made(win):
    win.prompt_jar()
    dlg = win.inspector.current_tool_dlg
    dlg.spins["neck_diameter"].setValue(39.5)                # no lid wall left outside the thread
    QApplication.processEvents()
    from PySide6.QtTest import QTest
    QTest.qWait(400)
    assert not dlg.btn_ok.isEnabled() and "lid's wall" in dlg.lbl_info.text()
    dlg.reject()


def test_hidden_inside_edge_is_found_by_see_through(win):
    import numpy as np
    from omacad.model.jar import JarSpec
    ids = win.doc.add_jar(JarSpec(inside_chamfer=0.0))
    vp = win.viewport
    vp.resize(800, 600)
    vp.target, vp.distance, vp.azimuth, vp.elevation = np.array([0.0, 0.0, 25.0]), 120.0, 45.0, 60.0
    shoulder = next(e for e in win.doc.bodies[ids["jar"]].edges
                    if e.kind == "circle" and abs(e.radius - 18) < 0.05 and abs(e.center[2] - 38) < 0.01)
    p = np.asarray(shoulder.polyline()).reshape(-1, 3)[0]
    (x, y), = vp.project_points(p[None])[0]
    assert vp._pick_edge(x, y) is not shoulder                 # under the shoulder: hidden from outside
    assert vp._hidden_edge_at(x, y) is shoulder and not vp.edge_xray
