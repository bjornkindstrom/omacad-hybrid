from pathlib import Path
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.faces_hit_tests import detect_cylinder_surface
from omacad.model.features.offset_face import cylinder_face_ref, OffsetFaceFeature
from omacad.ui.main_window import MainWindow

_app = QApplication.instance() or QApplication([])

REPORT_PROJECT = Path(__file__).parent.parent / ".state" / "data" / "feedback" / "20261115-082920" / "document.omacad"


@pytest.fixture
def win():
    window = MainWindow()
    window.resize(1000, 700)
    yield window
    if window.inspector.current_tool_dlg is not None:
        window.inspector.current_tool_dlg.reject()
    window.close()
    window.deleteLater()
    _app.processEvents()


def test_inward_cylinder_offset_thickens_thin_wall():
    doc = Exporter.load_project(str(REPORT_PROJECT))
    b3 = doc.bodies["body_cylinder_3"]
    mesh = b3.render_mesh
    for i in range(len(mesh.vertices) // 3):
        cyl = detect_cylinder_surface(mesh, i)
        if cyl and cyl["is_internal"]:
            break
    ref = cylinder_face_ref(cyl)

    # Positive distance adds material inward into the bore (thickening the wall from 1.0 to 1.5 mm)
    feat = doc.add_offset_face("body_cylinder_3", [ref], 0.5)
    assert feat.skipped == 0
    b3_after = doc.bodies["body_cylinder_3"]
    bb = b3_after.manifold.bounding_box()
    # Outer cylinder wall radius must remain 35.0 mm (not balloon to 36.7+ mm)
    assert abs(bb[0] - (-35.0)) < 0.05 and abs(bb[3] - 35.0) < 0.05
    assert abs(bb[1] - (-35.0)) < 0.05 and abs(bb[4] - 35.0) < 0.05
    assert abs(bb[2] - 0.0) < 0.05 and abs(bb[5] - 10.0) < 0.05

    # Check slice: inner radius should now be ~33.5 mm
    polys = b3_after.manifold.slice(5.0).to_polygons()
    radii = [float(np.mean(np.hypot(p[:, 0], p[:, 1]))) for p in polys]
    assert any(abs(r - 35.0) < 0.05 for r in radii)
    assert any(abs(r - 33.5) < 0.05 for r in radii)


def test_outward_cylinder_offset_thins_wall():
    doc = Exporter.load_project(str(REPORT_PROJECT))
    b3 = doc.bodies["body_cylinder_3"]
    mesh = b3.render_mesh
    for i in range(len(mesh.vertices) // 3):
        cyl = detect_cylinder_surface(mesh, i)
        if cyl and cyl["is_internal"]:
            break
    ref = cylinder_face_ref(cyl)

    # Negative distance removes material from the bore (thinning the wall from 1.0 to 0.5 mm)
    feat = doc.add_offset_face("body_cylinder_3", [ref], -0.5)
    assert feat.skipped == 0
    b3_after = doc.bodies["body_cylinder_3"]
    bb = b3_after.manifold.bounding_box()
    assert abs(bb[0] - (-35.0)) < 0.05 and abs(bb[3] - 35.0) < 0.05
    assert abs(bb[5] - 10.0) < 0.05  # Wall is intact, not obliterated

    polys = b3_after.manifold.slice(5.0).to_polygons()
    radii = [float(np.mean(np.hypot(p[:, 0], p[:, 1]))) for p in polys]
    assert any(abs(r - 35.0) < 0.05 for r in radii)
    assert any(abs(r - 34.5) < 0.05 for r in radii)


def test_preselected_curved_patch_in_prompt_offset_face(win):
    doc = Exporter.load_project(str(REPORT_PROJECT))
    win.attach_document(doc)
    b3 = doc.bodies["body_cylinder_3"]
    mesh = b3.render_mesh
    for i in range(len(mesh.vertices) // 3):
        cyl = detect_cylinder_surface(mesh, i)
        if cyl and cyl["is_internal"]:
            tris = mesh.curved_surface(i)
            break

    # Viewport face pre-selection stores (body_id, tris_patch)
    win.viewport.selected_faces = [("body_cylinder_3", tris)]
    win.prompt_offset_face()
    dlg = win.inspector.current_tool_dlg
    assert dlg is not None
    assert len(dlg.faces) == 1
    assert dlg.faces[0]["kind"] == "cylinder"
    assert dlg.faces[0]["internal"] is True
    assert dlg.body_id == "body_cylinder_3"

    # Drag frame arrow points inward (into the bore)
    point, normal = dlg.drag_frame(b3)
    assert np.dot(point[:2], normal[:2]) < 0  # Inward normal adds material into the bore
