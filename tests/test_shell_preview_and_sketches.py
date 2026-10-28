import pytest
from omacad.model.document import Document
from omacad.model.timeline import ShellFeature


def test_shell_feature_compute_shell_and_hide_sketches():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((0, 0), 10)
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 10.0)
    assert len(doc.bodies) == 1
    body_id = list(doc.bodies.keys())[0]
    body = doc.bodies[body_id]

    # Make the used sketch visible again to test that add_shell hides it
    sk.visible = True

    # Test compute_shell
    orig_vol = body.manifold.volume()
    assert orig_vol > 0

    # Shell hollow inside (no open faces)
    shelled = ShellFeature.compute_shell(body.manifold, thickness=1.0, direction="inside", thickness2=0.0, open_faces=[])
    assert shelled is not None
    assert 0 < shelled.volume() < orig_vol

    # Shell with open face (top face normal +Z)
    open_faces = [{"normal": [0, 0, 1], "origin": [0, 0, 10]}]
    shelled_open = ShellFeature.compute_shell(body.manifold, thickness=1.0, direction="inside", thickness2=0.0, open_faces=open_faces)
    assert shelled_open is not None
    assert 0 < shelled_open.volume() < orig_vol

    # Add shell feature and verify sketches are hidden
    doc.add_shell(body_id, thickness=1.0, open_faces=open_faces)
    assert sk.visible is False


def test_face_sketch_parent_body_and_tree_grouping():
    doc = Document()
    sk1 = doc.start_sketch("XY")
    sk1.add_circle((0, 0), 10)
    doc.finish_sketch()
    doc.extrude_profile(sk1.sketch_id, 0, 10.0)
    body_id = list(doc.bodies.keys())[0]
    body = doc.bodies[body_id]

    # Create a sketch on the top face of the body
    face = body.faces[0]
    from omacad.model.sketch import SketchPlane
    face_plane = SketchPlane.from_face(face.normal, face.origin)
    face_plane.face = face

    sk2 = doc.start_sketch_on_plane(face_plane)
    assert sk2.parent_body_id == body_id

    # Standalone sketch on XZ
    sk3 = doc.start_sketch("XZ")
    assert sk3.parent_body_id is None

    # Test serialization of parent_body_id
    d = sk2.to_dict()
    assert d.get("parent_body_id") == body_id
    from omacad.model.sketch import Sketch
    sk2_restored = Sketch.from_dict(d)
    assert sk2_restored.parent_body_id == body_id
