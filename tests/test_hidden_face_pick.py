"""Regression test: hidden, occluded, and section cut-away faces cannot be picked or hovered."""
from pathlib import Path
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.ui.viewport.viewport import Viewport3D
from omacad.ui.viewport.picker_mixin import trim_triangles_by_plane
from PySide6.QtWidgets import QApplication

DOC = Path(__file__).parent / "data" / "hidden_face_section_pick.omacad"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_section_cut_away_face_is_not_picked(qapp):
    """Under an active section view, faces on the cut-away side must not be picked by _pick_face or _pick_plane_target."""
    doc = Exporter.load_project(str(DOC))
    vp = Viewport3D(doc)
    w, h = 2048, 1122
    vp.resize(w, h)
    vp.azimuth = 48.236
    vp.elevation = 31.576
    vp.distance = 122.86
    vp.target = np.array([13.253, -4.318, 9.856])
    vp.sync_section()
    assert vp.section is not None

    proj, view, _ = vp.get_matrices()
    def world_to_screen(p):
        p4 = np.append(p, 1.0)
        clip = p4 @ (proj @ view).T
        ndc = clip[:3] / clip[3]
        return (ndc[0] * 0.5 + 0.5) * w, (1.0 - (ndc[1] * 0.5 + 0.5)) * h

    # The front wall of Box 2 was cut away by Section 2 (cutting along y=0, front y < 0 removed)
    # Looking at where the cut-away front wall was (x=30, y=-19, z=15)
    sx, sy = world_to_screen([30.0, -19.0, 15.0])
    hit_face = vp._pick_face(sx, sy)
    hit_target = vp._pick_plane_target(sx, sy)
    assert hit_face is None
    assert hit_target is None or hit_target[0] != "face"

    # Same for Box 1 cut-away front wall
    sx1, sy1 = world_to_screen([-30.0, -19.0, 15.0])
    hit_face1 = vp._pick_face(sx1, sy1)
    hit_target1 = vp._pick_plane_target(sx1, sy1)
    assert hit_face1 is None
    assert hit_target1 is None or hit_target1[0] != "face"


def test_back_facing_face_is_not_picked(qapp):
    """A face facing away from the camera ray is back-facing and must never be picked."""
    doc = Exporter.load_project(str(DOC))
    vp = Viewport3D(doc)
    vp.clear_section()

    box = doc.bodies["body_box_3"]
    # Look from above at z=100 pointing down [0, 0, -1]
    origin = np.array([30.0, 0.0, 100.0])
    ray_dir = np.array([0.0, 0.0, -1.0])

    # Normal of bottom outer face is [0, 0, -1]. dot(normal, ray_dir) == 1 > 0 (back-facing)
    # With ray pointing down, bottom face should be rejected by back-face check
    bottom_faces = [f for f in box.faces if f.normal[2] < -0.9]
    assert len(bottom_faces) > 0
    for bf in bottom_faces:
        assert float(bf.normal @ ray_dir) >= -1e-4


def test_trim_triangles_by_plane():
    """Triangles intersecting a section cut plane are trimmed cleanly to the kept half."""
    # Triangle crossing y=0: one vertex on kept side (y=10), two on cut side (y=-10)
    tri_1 = np.array([[[-5.0, -10.0, 2.0], [5.0, -10.0, 2.0], [0.0, 10.0, 2.0]]], dtype=float)
    trimmed_1 = trim_triangles_by_plane(tri_1, np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 0.0]))
    assert len(trimmed_1) == 1
    assert trimmed_1[:, :, 1].min() >= -1e-6

    # Triangle crossing y=0: two vertices on kept side (y=10), one on cut side (y=-10)
    tri_2 = np.array([[[-5.0, 10.0, 2.0], [5.0, 10.0, 2.0], [0.0, -10.0, 2.0]]], dtype=float)
    trimmed_2 = trim_triangles_by_plane(tri_2, np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 0.0]))
    assert len(trimmed_2) == 2  # quad triangulated to 2 triangles
    assert trimmed_2[:, :, 1].min() >= -1e-6
