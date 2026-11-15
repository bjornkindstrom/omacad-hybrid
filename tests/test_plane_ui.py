"""Plane UI tests: hover, visibility, picking, framing, and angle/offset dialogs."""
import math
import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.ui import settings as settings_mod
from omacad.ui.dialogs.sketch_plane_dlg import OffsetPlaneDialog
from omacad.ui.main_window import MainWindow
from omacad.ui.viewport import Viewport3D


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    w.resize(1200, 800)
    w.viewport.resize(800, 600)
    w.doc.add_box(20, 10, 5)
    for name in ("XY", "XZ", "YZ"):
        w.doc.set_origin_visibility("plane", name, True)
    yield w
    w.close()


def _top_view(vp):
    vp.azimuth, vp.elevation, vp.distance = 0.0, 89.9, 120.0
    vp.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)


def _xy_spot(vp):
    vp.doc.add_box(2, 2, 2, translation=(40, 40, 0))
    return vp.world_to_screen(np.array([30.0, 25.0, 0.0]))


# =========================================================================
# 1. Plane Hover & Visibility Actions
# =========================================================================

def test_plane_lights_up_and_is_a_target_only_while_shown(win):
    vp = win.viewport
    _top_view(vp)
    x, y = _xy_spot(vp)
    vp._update_idle_plane_hover(x, y)
    assert vp.hover_plane == ("origin", "XY")
    assert ("origin", "XY") in [k for k, *_ in vp._plane_quads()]
    vp._run_general("hide_plane", ("origin", "XY"))
    assert not win.doc.origin_visible("plane", "XY")
    assert ("origin", "XY") not in [k for k, *_ in vp._plane_quads()]
    hit = vp._pick_plane_target(x, y)
    assert hit is None or hit[1] != "XY"


def test_hide_construction_plane(win):
    pid = win.doc.add_construction_plane(win.doc.origin_planes["XY"], 15.0, "Top plane")
    vp = win.viewport
    assert any(k == ("cplane", pid) and name == "Top plane" for k, name, *_ in vp._plane_quads())
    vp._run_general("hide_plane", ("cplane", pid))
    assert not win.doc.construction_planes[pid]["visible"]


def test_plane_names_are_drawn(win):
    vp = win.viewport
    _top_view(vp)
    drawn = []

    class Rec(QPainter):
        def drawText(self, *a):
            drawn.append(a[-1])

    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    p = Rec(img)
    vp._draw_plane_labels(p)
    p.end()
    assert "XY Plane" in drawn
    assert "XZ Plane" not in drawn


def test_split_with_plane_from_menu_and_by_clicking(win):
    vp = win.viewport
    vp._run_general("split_plane", "XZ")
    dlg = win.inspector.current_tool_dlg
    assert dlg.get_values()[1] == "XZ"
    vp.plane_clicked.emit("YZ")
    assert dlg.get_values()[1] == "YZ"
    dlg.reject()
    vp.plane_clicked.emit("XY")


def test_offset_plane_from_face_or_plane(win):
    vp = win.viewport
    vp.offset_base_picked.disconnect()
    got = []
    vp.offset_base_picked.connect(got.append)
    body = next(iter(win.doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    vp._run_general("offset_plane", vp.plane_from_target(("face", top)))
    vp._run_general("offset_plane", vp.plane_from_target(("origin", "XZ")))
    assert abs(got[0].normal[2] - 1.0) < 1e-9 and abs(got[0].origin[2] - 5.0) < 1e-6
    assert got[1].name == "XZ"


def test_offset_plane_panel_turns_the_preview_and_the_plane():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    seen = {}

    def drive():
        dlgs = w.findChildren(OffsetPlaneDialog)
        if not dlgs:
            QTimer.singleShot(20, drive)
            return
        dlg = dlgs[-1]
        try:
            dlg.spn_dist.setValue(0.0)
            dlg.cmb_axis.setCurrentIndex(1)
            dlg.spn_angle.setValue(90.0)
            QApplication.processEvents()
            seen["preview"] = np.asarray(w.viewport.preview_plane.normal, dtype=float)
        finally:
            dlg.accept()

    QTimer.singleShot(0, drive)
    w.on_offset_base_picked(w.doc.origin_planes["XY"])
    c = next(iter(w.doc.construction_planes.values()))
    assert np.allclose(np.abs(c["normal"]), (1, 0, 0), atol=1e-6)
    assert np.allclose(np.abs(seen["preview"]), (1, 0, 0), atol=1e-6)
    w.close()


# =========================================================================
# 2. Origin Plane Quadrant Bounds & Picking
# =========================================================================

@pytest.fixture
def view(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    v = Viewport3D(Document())
    v.paintGL = lambda: None
    v.initializeGL = lambda: None
    v.resize(800, 600)
    return v


def test_marker_size_is_small_and_grows_with_the_model(view):
    assert view._origin_quadrant_size() == pytest.approx(20.0)
    view.doc.add_box(100, 100, 100)
    assert view._origin_quadrant_size() == pytest.approx(75.0)


def test_origin_plane_is_picked_on_all_sides_of_the_origin_but_not_far_away(view):
    view.begin_plane_pick("sketch")
    view.azimuth, view.elevation = 0.0, 89.9
    plane = view.doc.origin_planes["XY"]
    at = lambda u, v: view.world_to_screen(plane.uv_to_world(u, v))
    assert view._pick_plane_target(*at(8, 8)) == ("origin", "XY")
    assert view._pick_plane_target(*at(-8, -8)) == ("origin", "XY")
    assert view._pick_plane_target(*at(35, 8)) is None


def test_origin_plane_grows_to_cover_a_body_beside_the_origin(view):
    view.doc.add_box(40, 40, 10)
    view.begin_plane_pick("sketch")
    view.azimuth, view.elevation = 0.0, 89.9
    plane = view.doc.origin_planes["XY"]
    mesh = next(iter(view.doc.bodies.values())).render_mesh
    far = max(abs(float(mesh.bounds_min[0])), abs(float(mesh.bounds_max[0])))
    u0, u1, v0, v1 = view._plane_rect(plane)
    assert u1 >= far and v1 >= far


def test_plane_hugs_a_tall_box_standing_on_the_origin(view):
    view.doc.add_box(500, 500, 500, center="bottom_center")
    u0, u1, v0, v1 = view._plane_rect(view.doc.origin_planes["XZ"])
    assert (u1 - u0, v1 - v0) == (pytest.approx(550.0), pytest.approx(550.0))
    plane = view.doc.origin_planes["XZ"]
    zs = sorted(float(plane.uv_to_world(u, v)[2]) for u in (u0, u1) for v in (v0, v1))
    assert zs[0] == pytest.approx(-25.0) and zs[-1] == pytest.approx(525.0)


# =========================================================================
# 3. Sketch on Face Framing
# =========================================================================

@pytest.mark.parametrize("size", [8.0, 300.0])
def test_sketch_on_face_frames_the_face(size):
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.viewport.paintGL = lambda: None
    w.viewport.initializeGL = lambda: None
    w.resize(1200, 800)
    w.doc.add_box(size, size, 10)
    body = next(iter(w.doc.bodies.values()))
    face = max(body.faces, key=lambda f: float(np.asarray(f.normal) @ [0, 0, 1]) * 1e6 + float(np.asarray(f.origin)[2]))
    plane = SketchPlane.from_face(face.normal, face.origin)
    plane.face = face
    w.viewport.distance, w.viewport.target = 900.0, np.array([500.0, 500.0, 0.0], dtype=np.float32)
    w.on_plane_picked(plane)
    v = w.viewport
    pts = np.asarray(face.tris, dtype=float).reshape(-1, 3)
    assert np.allclose(v.target[:2], (pts.min(axis=0)[:2] + pts.max(axis=0)[:2]) / 2, atol=1e-3)
    seen = 2.0 * v.distance * math.tan(math.radians(v.fovy) / 2.0) * min(1.0, v.width() / max(1, v.height()))
    assert 0.6 < size / seen < 0.95
    w.close()
