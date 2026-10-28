"""Björn #112: after moving a body with the arrows a green face stayed where the body used to be. The hovered face
holds the triangles of the body it was picked on; the hover compared only body and face number, which a moved body
keeps, so the old triangles stayed lit."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


def _win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.viewport.resize(900, 700)
    w.doc.add_box(40, 20, 10)
    return w, next(iter(w.doc.bodies))


def test_a_move_clears_the_hovered_face():
    w, bid = _win()
    vp = w.viewport
    vp._update_edge_hover(*vp.world_to_screen(np.array([20.0, 10.0, 10.0])))      # the top face
    assert vp.hover_face is not None
    w.doc.selected_body_ids = [bid]
    rh = vp.rotate_handles
    pos, along, _ = rh.handles()["MY"]
    rh.press(*pos)
    rh.move(*(pos + along * 60))
    rh.release()
    assert w.doc.timeline.features[-1].feature_type == "move"
    assert vp.hover_face is None and vp.hover_edge is None


def test_same_face_number_on_a_moved_body_takes_its_new_triangles():
    w, bid = _win()
    vp = w.viewport
    spot = vp.world_to_screen(np.array([20.0, 10.0, 10.0]))
    vp._update_edge_hover(*spot)
    old = vp.hover_face
    w.doc.move_body(bid, dx=2)
    vp.hover_face = old               # still lit from before the move (no mouse move in between)
    vp._update_edge_hover(*spot)
    face = vp.hover_face
    assert face is not None and face.index == old.index
    assert face.tris is not old.tris
    assert np.asarray(face.tris)[..., 0].min() == np.asarray(old.tris)[..., 0].min() + 2
