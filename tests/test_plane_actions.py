"""Planes without a tool: they light up under the cursor, show their name, a right-click offers Split / Offset Plane /
Sketch / Hide, a face offers Offset Plane, and clicking a plane while Split Body is open picks it as splitting plane."""
import numpy as np
import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.viewport.resize(800, 600)
    w.doc.add_box(20, 10, 5)
    for name in ("XY", "XZ", "YZ"):              # origin planes start hidden in a new document
        w.doc.set_origin_visibility("plane", name, True)
    return w


def _top_view(vp):
    vp.azimuth, vp.elevation, vp.distance = 0.0, 89.9, 120.0
    vp.target = np.array([0.0, 0.0, 0.0], dtype=np.float32)


def _xy_spot(vp):
    """A pixel on the XY plane away from the bodies. The plane spans the bodies' bounds (+5 %), so a small second box
    at (40, 40) stretches it; (30, 25) lies between the two boxes."""
    vp.doc.add_box(2, 2, 2, translation=(40, 40, 0))
    return vp.world_to_screen(np.array([30.0, 25.0, 0.0]))


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
    assert hit is None or hit[1] != "XY"                     # a hidden plane is not under the cursor any more


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
    assert "XY Plane" in drawn                               # seen from above: the XY plane has room for its name
    assert "XZ Plane" not in drawn                           # edge-on from above: no label


def test_split_with_plane_from_menu_and_by_clicking(win):
    vp = win.viewport
    vp._run_general("split_plane", "XZ")
    dlg = win.inspector.current_tool_dlg
    assert dlg.get_values()[1] == "XZ"
    vp.plane_clicked.emit("YZ")                              # clicking a plane in the view while the dialog is open
    assert dlg.get_values()[1] == "YZ"
    dlg.reject()
    vp.plane_clicked.emit("XY")                              # disconnected after the dialog closed: no error


def test_offset_plane_from_face_or_plane(win):
    vp = win.viewport
    vp.offset_base_picked.disconnect()                       # the real Offset Plane dialog runs its own event loop
    got = []
    vp.offset_base_picked.connect(got.append)
    body = next(iter(win.doc.bodies.values()))
    top = max(body.faces, key=lambda f: f.normal[2])
    vp._run_general("offset_plane", vp.plane_from_target(("face", top)))
    vp._run_general("offset_plane", vp.plane_from_target(("origin", "XZ")))
    assert abs(got[0].normal[2] - 1.0) < 1e-9 and abs(got[0].origin[2] - 5.0) < 1e-6   # the box's top face
    assert got[1].name == "XZ"
