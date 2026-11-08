"""Regression test for problem report 20261108-073007:
1. Sketch reference segments for a sketch on a face (parent_body_id) must only
   draw from that body, preventing coplanar edges of other bodies from cutting
   drawn circles/profiles in two.
2. Clicking Extrude with a preselected face must consume the face without infinite
   recursion, and clicking a profile must clear face selection.
"""
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.main_window import MainWindow

FIXTURE = Path(__file__).parent / "data" / "extrude_face_sketch_circles_20261108.omacad"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_sketch_on_face_ignores_unrelated_coplanar_body_edges():
    doc = Exporter.load_project(str(FIXTURE))
    sk5 = doc.sketches["sketch_5"]
    assert sk5.parent_body_id == "body_extrude_15"

    doc.refresh_sketch_references(sk5)

    # The 2 circles drawn in sketch_5 must be intact (area = pi * 25^2 ≈ 1963.5 mm²),
    # not sliced in half by the coplanar shelf edge of Box 1.
    circle_profiles = [p for p in sk5.profiles if 1900.0 < p.area < 2000.0]
    assert len(circle_profiles) == 2, f"Expected 2 intact circle profiles, got {len(circle_profiles)}"

    # Extrude one of the circular profiles
    circle_idx = sk5.profiles.index(circle_profiles[0])
    doc.extrude_profile(sk5.sketch_id, circle_idx, distance=10.0, operation="new_body")
    feat = doc.timeline.features[-1]
    extrude_body = doc.bodies.get(f"body_{feat.feature_id}")
    assert extrude_body is not None
    assert 19000.0 < extrude_body.manifold.volume() < 20000.0


def test_prompt_extrude_with_preselected_face_does_not_recurse(app):
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (100, 100))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 10.0)

    win = MainWindow()
    win.doc = doc
    win.viewport.doc = doc

    body = next(iter(doc.bodies.values()))
    top_face = [f for f in body.faces if f.normal[2] > 0.9][0]

    # Preselect top face
    win.viewport.select_face(body.body_id, top_face)
    assert len(win.viewport.selected_faces) == 1

    # Calling prompt_extrude must consume the face selection and open the dialog without RecursionError
    win.prompt_extrude()

    assert len(win.viewport.selected_faces) == 0
    assert win._extrude_dlg is not None
    assert win.doc.selected_profile is not None
    win._extrude_dlg.close()
    win.close()


def test_prompt_extrude_prefers_selected_profile_over_selected_face(app):
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((50, 50), 10.0)
    doc.finish_sketch()

    win = MainWindow()
    win.doc = doc
    win.viewport.doc = doc

    body_sk = doc.start_sketch("XZ")
    body_sk.add_rect((0, 0), (200, 200))
    doc.finish_sketch()
    doc.extrude_profile(body_sk.sketch_id, 0, 10.0)

    body = next(iter(doc.bodies.values()))
    face = body.faces[0]
    win.viewport.select_face(body.body_id, face)

    # Profile explicitly selected
    win.doc.selected_profile = (sk.sketch_id, 0)

    win.prompt_extrude()

    # Must extrude the sketch circle profile, not create a Face sketch
    assert win.doc.selected_profile == (sk.sketch_id, 0)
    assert not any(s.name.startswith("Face ") for s in doc.sketches.values())
    if win._extrude_dlg is not None:
        win._extrude_dlg.close()
    win.close()
