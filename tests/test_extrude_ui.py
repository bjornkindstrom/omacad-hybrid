"""Extrude UI interaction, profile picking, dialog focus, and viewport tests."""
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import CircularEdge
from omacad.ui.dialogs import ExtrudeDialog
import omacad.ui.dialogs as dialogs_mod
from omacad.ui.main_window import MainWindow
from omacad.ui.math3d import camera_matrices
from omacad.ui.viewport import Viewport3D
from omacad.model import quality

DATA_DIR = Path(__file__).parent / "data"


class DummySideHost:
    def __init__(self):
        self.inspector = self
        self.current_tool_dlg = None

    def dock(self, dlg):
        self.current_tool_dlg = dlg


def test_extrude_dialog_focus_and_direct_typing():
    QApplication.instance() or QApplication([])

    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((0.0, 0.0), 15.0)
    doc.finish_sketch()
    assert len(sk.profiles) == 1

    view = Viewport3D(doc)
    view.paintGL = lambda: None
    view.initializeGL = lambda: None
    host = DummySideHost()
    dialogs_mod.SIDE_HOST = host

    try:
        dlg = ExtrudeDialog(doc, view, embedded=True)
        dlg.place(view.size())
        dlg.show()
        dlg.focus_primary()

        line_edit = dlg.spn_dist.lineEdit()
        assert line_edit is not None
        assert line_edit.hasSelectedText()

        dlg.select_profile((sk.sketch_id, 0))
        dlg.focus_primary()
        assert line_edit.hasSelectedText()

        evt = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_5, Qt.KeyboardModifier.NoModifier, "5")
        view.keyPressEvent(evt)
        assert "5" in line_edit.text()

        accepted = []
        dlg.accepted.connect(lambda: accepted.append(True))
        evt_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        view.keyPressEvent(evt_enter)
        assert accepted == [True]
    finally:
        dialogs_mod.SIDE_HOST = None
        view.close()


def test_release_after_dragging_the_extrude_arrow():
    QApplication.instance() or QApplication([])
    vp = Viewport3D(Document())
    vp.paintGL = lambda: None
    vp.initializeGL = lambda: None
    finished = []
    vp.extrude_handle_drag_finished.connect(lambda: finished.append(True))
    vp._handle_drag = True
    quality.set_interactive_mode(True)
    ev = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    vp.mouseReleaseEvent(ev)
    assert finished and not quality.is_interactive_mode() and not vp._handle_drag
    vp.close()


def test_extrude_ring_edge_picking_from_shallow_angle():
    doc = Exporter.load_project(str(DATA_DIR / "extrude_ring_edge_pick.omacad"))
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    inner_edges = [e for e in body.edges if isinstance(e, CircularEdge) and abs(e.radius - 10.0) < 0.5]
    assert len(inner_edges) == 2

    class MockViewport(Viewport3D):
        def __init__(self):
            self.doc = doc
            self.edge_pick_mode = True
            self.plane_pick_mode = False
            self.edge_xray = False
            self._w, self._h = 2048, 1122
            self.cam_az, self.cam_el, self.cam_dist = 144.296875, 28.946875, 124.7076644897461
            self.cam_target = np.array([0.0, 0.0, 20.0])

        def width(self):
            return self._w

        def height(self):
            return self._h

        def get_matrices(self):
            proj, view = camera_matrices(self.cam_target, self.cam_dist, self.cam_az,
                                         self.cam_el, self._w / self._h)
            return proj, view, np.eye(4)

    vp = MockViewport()
    inner_at_top = [e for e in inner_edges if abs(e.center[2] - 30.0) < 1.0][0]

    for angle in [0, 90, 180, 270]:
        point = np.array([10.0 * np.cos(np.radians(angle)),
                          10.0 * np.sin(np.radians(angle)),
                          30.0])
        sx, sy = vp.world_to_screen(point)
        picked = vp._pick_edge(sx, sy)
        assert picked is not None, f"Failed to pick inner top edge at angle {angle}"
        assert picked.same_as(inner_at_top)


def test_selection_highlight_leaves_the_open_shapes_unshaded():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(str(DATA_DIR / "coplanar_sketches_nested.omacad"))
    doc.timeline.recompute(doc)
    v = Viewport3D(doc)
    v.paintGL = lambda: None
    v.initializeGL = lambda: None
    doc.selected_profile, doc.selected_extra = ("sketch_1", 0), []
    plain = v._profile_fill(("sketch_1", 0))
    sel = v._selection_fill()
    assert sel is not None and len(sel) != len(plain)
    doc.selected_extra = [("sketch_2", 0)]
    assert v._selection_fill() is not None
    v.close()


def test_prompt_extrude_with_preselected_face_does_not_recurse():
    QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (100, 100))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 10.0)

    win = MainWindow()
    win.viewport.paintGL = lambda: None
    win.viewport.initializeGL = lambda: None
    win.doc = doc
    win.viewport.doc = doc

    body = next(iter(doc.bodies.values()))
    top_face = [f for f in body.faces if f.normal[2] > 0.9][0]

    win.viewport.select_face(body.body_id, top_face)
    assert len(win.viewport.selected_faces) == 1

    win.prompt_extrude()
    assert len(win.viewport.selected_faces) == 0
    assert win._extrude_dlg is not None
    assert win.doc.selected_profile is not None
    win._extrude_dlg.close()
    win.close()


def test_prompt_extrude_prefers_selected_profile_over_selected_face():
    QApplication.instance() or QApplication([])
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((50, 50), 10.0)
    doc.finish_sketch()

    win = MainWindow()
    win.viewport.paintGL = lambda: None
    win.viewport.initializeGL = lambda: None
    win.doc = doc
    win.viewport.doc = doc

    body_sk = doc.start_sketch("XZ")
    body_sk.add_rect((0, 0), (200, 200))
    doc.finish_sketch()
    doc.extrude_profile(body_sk.sketch_id, 0, 10.0)

    body = next(iter(doc.bodies.values()))
    face = body.faces[0]
    win.viewport.select_face(body.body_id, face)

    win.doc.selected_profile = (sk.sketch_id, 0)
    win.prompt_extrude()

    assert win.doc.selected_profile == (sk.sketch_id, 0)
    assert not any(s.name.startswith("Face ") for s in doc.sketches.values())
    if win._extrude_dlg is not None:
        win._extrude_dlg.close()
    win.close()
