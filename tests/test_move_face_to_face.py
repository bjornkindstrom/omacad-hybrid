"""Move: click a face on a body, then the face it should go to. Touch / Flush / Slide, centred or not. The values
fill the Move dialog and the result is checked on the moved body itself."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.geometry import face_centroid, face_to_face_values


def _scene():
    doc = Document()
    doc.add_box(20, 20, 10)                    # A: x,y -10..10 (bottom_center), z 0..10
    a = next(iter(doc.bodies))
    doc.add_box(6, 6, 4)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=40, dy=7, dz=3, rx=25, ry=-15, rz=70)       # B somewhere, turned
    return doc, a, b


def _face(doc, bid, normal, how="max"):
    faces = doc.bodies[bid].faces
    score = lambda f: float(np.dot(f.normal, normal))
    return max(faces, key=score)


def _centre(doc, bid):
    b = doc.bodies[bid]
    return (np.asarray(b.render_mesh.bounds_min, float) + np.asarray(b.render_mesh.bounds_max, float)) * 0.5


def _apply(doc, a, b, mode, centre_on):
    src = _face(doc, b, np.array([0.0, 0.0, -1.0]))                 # B's bottom-ish face (it is turned)
    dst = _face(doc, a, np.array([0.0, 0.0, 1.0]))                  # A's top face
    vals = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst), _centre(doc, b),
                               True, mode, centre_on)
    doc.move_body(b, *vals, pivot="center")
    return src, dst


def _moved_face(doc, b, direction):
    return _face(doc, b, direction)


def test_touch_puts_the_face_on_the_target_face_centred():
    doc, a, b = _scene()
    src, dst = _apply(doc, a, b, "touch", True)
    f = _moved_face(doc, b, np.array([0.0, 0.0, -1.0]))
    assert np.allclose(f.normal, [0, 0, -1], atol=1e-4)               # it now faces down onto A's top
    assert np.allclose(face_centroid(f), face_centroid(dst), atol=1e-3)
    overlap = (doc.bodies[a].manifold ^ doc.bodies[b].manifold).volume()
    assert overlap < 1e-4                                             # touching, not inside


def _moved(doc, bid, src):
    """Where the source face is after the move: the face of the moved body with the same area, nearest the target."""
    return min((g for g in doc.bodies[bid].faces if abs(g.area - src.area) < 1e-3 * src.area),
               key=lambda g: np.linalg.norm(face_centroid(g) - TARGET[0]))


TARGET = [None]


def test_flush_turns_the_face_to_look_the_same_way():
    doc, a, b = _scene()
    src = _face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _face(doc, a, np.array([0.0, 0.0, 1.0]))
    TARGET[0] = face_centroid(dst)
    vals = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst), _centre(doc, b),
                               True, "flush", True)
    doc.move_body(b, *vals, pivot="center")
    f = _moved(doc, b, src)
    assert np.allclose(face_centroid(f), face_centroid(dst), atol=1e-3)
    assert np.allclose(f.normal, dst.normal, atol=1e-4)               # looks up, like A's top: flush


def test_not_centred_only_moves_along_the_normal():
    doc, a, b = _scene()
    before = _centre(doc, b)
    src = _face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _face(doc, a, np.array([0.0, 0.0, 1.0]))
    dx, dy, dz, rx, ry, rz = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst),
                                                 before, True, "touch", False)
    assert np.allclose(np.cross([dx, dy, dz], dst.normal), 0.0, atol=1e-9)    # the shift is purely along the normal


def test_slide_does_not_turn():
    doc, a, b = _scene()
    src = _face(doc, b, np.array([0.0, 0.0, -1.0]))
    dst = _face(doc, a, np.array([0.0, 0.0, 1.0]))
    v = face_to_face_values(src.normal, face_centroid(src), dst.normal, face_centroid(dst), _centre(doc, b), True, "slide", True)
    assert np.allclose(v[3:], 0.0)


def test_dialog_flow_two_clicks_fills_the_numbers_and_the_option_recomputes():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    doc = w.doc
    doc.add_box(20, 20, 10)
    a = next(iter(doc.bodies))
    doc.add_box(6, 6, 4)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=40)
    w.prompt_move_body(b)
    dlg = w.inspector.current_tool_dlg
    vp = w.viewport
    src = max(doc.bodies[b].faces, key=lambda f: -f.normal[2])        # B's underside
    dst = max(doc.bodies[a].faces, key=lambda f: f.normal[2])         # A's top
    dlg.btn_f2f.setChecked(True)
    assert vp.move_gizmo is None
    assert doc.bodies[b].visible                                  # source face stays visible for picking
    vp.move_body_picked.emit(vp.plane_from_target(("face", src)))
    assert dlg.btn_f2f.isChecked()                                    # waiting for the target
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", dst)))
    assert not dlg.btn_f2f.isChecked()
    assert vp.move_gizmo is not None
    assert not doc.bodies[b].visible                                 # normal Move preview replaces source
    # B's underside already looks down: no turning, just from its centre to A's top centre
    want = face_centroid(dst) - face_centroid(src)
    assert np.allclose([dlg.spn_dx.value(), dlg.spn_dy.value(), dlg.spn_dz.value()], want, atol=1e-3)
    assert abs(want[2] - 10.0) < 1e-6 and np.linalg.norm(want[:2]) > 1.0
    assert np.allclose([dlg.spn_rx.value(), dlg.spn_ry.value(), dlg.spn_rz.value()], 0, atol=1e-3)
    dlg.chk_f2f_centre.setChecked(False)                              # recomputed from the same two clicks
    assert np.allclose([dlg.spn_dx.value(), dlg.spn_dy.value(), dlg.spn_dz.value()], [0, 0, 10], atol=1e-3)   # normal only
    dlg.reject()


def test_dialog_flow_accepts_target_face_before_moving_face():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    doc = w.doc
    doc.add_box(20, 20, 10)
    a = next(iter(doc.bodies))
    doc.add_box(6, 6, 4)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=40)
    w.prompt_move_body(b)
    dlg, vp = w.inspector.current_tool_dlg, w.viewport
    src = max(doc.bodies[b].faces, key=lambda f: -f.normal[2])
    dst = max(doc.bodies[a].faces, key=lambda f: f.normal[2])
    dlg.btn_f2f.setChecked(True)
    assert vp.move_gizmo is None
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", dst)))
    assert dlg.btn_f2f.isChecked()
    assert doc.bodies[b].visible
    vp.move_body_picked.emit(vp.plane_from_target(("face", src)))
    assert not dlg.btn_f2f.isChecked()
    assert vp.move_gizmo is not None
    assert not doc.bodies[b].visible
    want = face_centroid(dst) - face_centroid(src)
    assert np.allclose([dlg.spn_dx.value(), dlg.spn_dy.value(), dlg.spn_dz.value()], want, atol=1e-3)
    dlg.reject()


def test_lay_on_ground_hides_gizmo_and_accepts_a_body_face():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    doc = w.doc
    doc.add_box(6, 6, 4)
    bid = next(iter(doc.bodies))
    doc.move_body(bid, dx=40, dz=12)
    w.prompt_move_body(bid)
    dlg, vp = w.inspector.current_tool_dlg, w.viewport

    assert vp.move_gizmo is not None
    dlg.btn_lay.setChecked(True)
    assert vp.move_gizmo is None
    assert doc.bodies[bid].visible
    face = max(doc.bodies[bid].faces, key=lambda f: f.normal[0])
    vp.move_body_picked.emit(vp.plane_from_target(("face", face)))
    assert not dlg.btn_lay.isChecked()
    assert vp.move_gizmo is not None
    assert dlg.spn_rx.value() != 0 or dlg.spn_ry.value() != 0
    dlg.reject()
