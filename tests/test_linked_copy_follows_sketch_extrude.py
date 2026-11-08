"""Regression tests for linked copy following operations on the original body:
When a sketch is created on the face of a body (parent_body_id), subsequent
features (such as cut or join extrusions) reference that body. The feature
must target the referenced body so ObjectHistory attributes it to the original
object, allowing Timeline._place_linked_objects to position the linked copy
(and its branch steps) after the new operation so the linked copy updates.
"""
from pathlib import Path
import pytest
from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane

FIXTURE = Path(__file__).parent / "data" / "extrude_face_sketch_circles_20261108.omacad"


def test_linked_copy_follows_cut_from_sketch_on_face():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_rect((0, 0), (100, 100))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 50.0)
    orig_feat = doc.timeline.last_added
    orig_body_id = f"body_{orig_feat.feature_id}"

    # Create linked copy and move it to the side
    link_body = doc.branch_object(orig_feat.feature_id, orig_body_id, linked=True)
    doc.move_body(link_body.body_id, dx=200.0)

    # Sketch on top face of the original body
    face = [f for f in doc.bodies[orig_body_id].faces if f.normal[2] > 0.9][0]
    plane = SketchPlane.from_face(face.normal, face.origin)
    plane.face = face
    face_sk = doc.start_sketch_on_plane(plane)
    face_sk.add_circle((50, 50), 20.0)
    doc.finish_sketch()

    # Extrude cut into the original body
    doc.extrude_profile(face_sk.sketch_id, 0, -25.0, operation="cut")
    v_cut = doc.bodies[orig_body_id].manifold.volume()

    # Both original and linked copy must have the cut applied
    assert doc.bodies[orig_body_id].manifold.volume() == pytest.approx(v_cut)
    assert doc.bodies[link_body.body_id].manifold.volume() == pytest.approx(v_cut)

    # Timeline order: branch and move should be moved after the cut extrude
    types = [f.feature_type for f in doc.timeline.features]
    assert types == ["sketch", "extrude", "sketch", "extrude", "branch", "move"]

    # Undo cut: both return to pre-cut volume (500000.0 mm³)
    doc.undo()
    assert doc.bodies[orig_body_id].manifold.volume() == pytest.approx(500000.0)
    assert doc.bodies[link_body.body_id].manifold.volume() == pytest.approx(500000.0)

    # Redo cut: both have cut again
    doc.redo()
    assert doc.bodies[orig_body_id].manifold.volume() == pytest.approx(v_cut)
    assert doc.bodies[link_body.body_id].manifold.volume() == pytest.approx(v_cut)

    # Save and reload maintains identical geometry
    data = Exporter.document_to_dict(doc)
    loaded = Document()
    Exporter.apply_dict(loaded, data)
    assert loaded.bodies[orig_body_id].manifold.volume() == pytest.approx(v_cut)
    assert loaded.bodies[link_body.body_id].manifold.volume() == pytest.approx(v_cut)


def test_problem_report_20261108_linked_copy_follows_extrude_2_cut():
    """Verify that in the user problem report project, cutting a circle profile on
    Sketch 5 updates the linked copy (branch_16) to match Extrude 2 (body_extrude_15)."""
    doc = Exporter.load_project(str(FIXTURE))
    sk5 = doc.sketches["sketch_5"]
    assert sk5.parent_body_id == "body_extrude_15"
    doc.refresh_sketch_references(sk5)

    circle_profiles = [p for p in sk5.profiles if 1900.0 < p.area < 2000.0]
    assert len(circle_profiles) == 2
    idx = sk5.profiles.index(circle_profiles[0])

    # Perform cut into Extrude 2
    doc.extrude_profile(sk5.sketch_id, idx, distance=-50.0, operation="cut")

    b_orig = doc.bodies["body_extrude_15"]
    b_link = doc.bodies["body_branch_16"]
    assert b_orig.manifold.volume() == pytest.approx(b_link.manifold.volume(), rel=1e-5)
    assert b_orig.manifold.volume() < 9000000.0
