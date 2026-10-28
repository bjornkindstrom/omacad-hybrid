import numpy as np
from types import SimpleNamespace
from omacad.model.document import Document
from omacad.ui import dialogs
from omacad.ui.viewport import Viewport3D


def _two_boxes():
    doc = Document()
    for cx in (0, 40):
        sk = doc.start_sketch("XY")
        sk.add_rect((cx, 0), (cx + 10, 10))
        doc.finish_sketch()
        doc.extrude_profile(sk.sketch_id, 0, 10.0)
    return doc


def test_toggle_face_uses_numpy():
    assert dialogs.np is np   # toggle_face crashed with NameError on the first face click


def test_shell_pick_hits_hidden_target_body_only(monkeypatch):
    doc = _two_boxes()
    a, b = list(doc.bodies.values())
    a.visible = False                     # the shell preview hides the target
    vp = SimpleNamespace(doc=doc, plane_pick_mode=True, plane_pick_purpose="shell_face",
                         shell_target_body_id=a.body_id, width=lambda: 100, height=lambda: 100,
                         get_matrices=lambda: (None, None, None),
                         _origin_quadrant_size=lambda: 100.0)
    top = next(f for f in a.faces if f.normal[2] > 0.9)
    monkeypatch.setattr("omacad.ui.viewport.ray_from_screen",
                        lambda *args: (np.array([5.0, 5.0, 50.0]), np.array([0.0, 0.0, -1.0])))
    hit = Viewport3D._pick_plane_target(vp, 0, 0)
    assert hit[0] == "face" and hit[1].body_id == a.body_id
    assert np.allclose(hit[1].normal, top.normal)
    # a ray through the other body (not the target) hits nothing, and origin planes are not pickable
    monkeypatch.setattr("omacad.ui.viewport.ray_from_screen",
                        lambda *args: (np.array([45.0, 5.0, 50.0]), np.array([0.0, 0.0, -1.0])))
    assert Viewport3D._pick_plane_target(vp, 0, 0) is None


def test_shell_with_picked_open_face_can_be_saved():
    """The dialog's picks carry the live face ("_face"); it leaked into the step, so F8/F9 and Save crashed in json.dumps."""
    import json
    from omacad.io.exporter import Exporter
    doc = _two_boxes()
    a = next(iter(doc.bodies.values()))
    top = next(f for f in a.faces if f.normal[2] > 0.9)
    pick = {"normal": [float(x) for x in top.normal], "origin": [float(x) for x in top.origin], "body_id": a.body_id, "_face": top}
    doc.add_shell(a.body_id, 1.0, open_faces=[pick])
    idx = next(i for i, f in enumerate(doc.timeline.features) if f.feature_type == "shell")
    doc.edit_feature(idx, open_faces=[dict(pick)])      # editing from the timeline sets the attribute directly
    json.dumps(Exporter.document_to_dict(doc))
