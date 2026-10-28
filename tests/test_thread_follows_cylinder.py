"""Request #37: a thread on a cylinder follows the cylinder's diameter when an earlier step (Offset Face) changes it."""
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.offset_face import cylinder_face_ref

DOC = str(Path(__file__).parent / "data" / "thread_follows_cylinder.omacad")


def _neck_doc(follow=True):
    """A Ø40 cylinder, 10 high, whose side is first pulled in by an Offset Face, then a thread sits on it."""
    doc = Document()
    doc.add_cylinder(20.0, 10.0)
    cyl = next(iter(doc.bodies))
    ref = {"kind": "cylinder", "origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0], "radius": 20.0, "length": 10.0,
           "internal": False}
    doc.add_offset_face(cyl, [ref], -2.0)                              # Ø36 now
    doc.add_thread(diameter=35.99, pitch=3.0, length=8.0, target_body_id=cyl, operation="join", profile="round",
                   plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0],
                   host_length=10.0, follow_host=follow, host_offset=-0.01)
    return doc, cyl


def _max_radius(doc, bid):
    v = np.asarray(doc.bodies[bid].manifold.to_mesh().vert_properties)[:, :3]
    return float(np.hypot(v[:, 0], v[:, 1]).max())


def test_measure_host_male_and_female():
    doc = Document()
    doc.add_cylinder(12.0, 20.0)
    cyl = next(iter(doc.bodies))
    doc.add_thread(diameter=24.0, pitch=2.5, length=10.0, target_body_id=cyl, operation="join",
                   plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], host_length=20.0)
    doc.timeline.recompute(doc)
    th = doc.timeline.features[-1]
    assert th.measure_host(doc.step_states[1][cyl]) == pytest.approx(24.0, abs=0.01)
    # a hole: the wall around the axis, not the outside of the block
    hole = Document()
    hole.add_box(60, 60, 20, center="bottom_center")
    box = next(iter(hole.bodies))
    hole.add_cylinder(8.0, 20.0, name="Pin")
    pin = [k for k in hole.bodies if k != box][0]
    hole.combine_bodies(box, pin, "cut")
    hole.add_thread(diameter=16.0, pitch=2.0, length=10.0, is_female=True, target_body_id=box, operation="cut",
                    plane_origin=[0, 0, 0], plane_normal=[0, 0, 1], host_length=20.0)
    hole.timeline.recompute(hole)
    th = hole.timeline.features[-1]
    assert th.measure_host(hole.step_states[len(hole.timeline.features) - 1][box]) == pytest.approx(16.0, abs=0.01)


def test_thread_follows_when_the_offset_face_is_edited():
    doc, cyl = _neck_doc(follow=True)
    th = doc.timeline.features[-1]
    assert th.used_diameter == pytest.approx(35.99, abs=0.02)          # Ø36 neck - 0.01
    r_before = _max_radius(doc, cyl)
    doc.edit_feature(1, distance=-5.0)                                 # the neck is Ø30 now
    assert th.used_diameter == pytest.approx(29.99, abs=0.02)
    assert _max_radius(doc, cyl) == pytest.approx(r_before - 3.0, abs=0.05)      # the whole thread moved in 3 mm


def test_a_thread_that_does_not_follow_stays_put():
    doc, cyl = _neck_doc(follow=False)
    th = doc.timeline.features[-1]
    doc.edit_feature(1, distance=-5.0)
    assert th.used_diameter == 35.99
    assert th.follow_host is False


def test_the_request_document_gets_its_thread_back_when_following_is_switched_on():
    doc = Exporter.load_project(DOC)
    jar = "body_split_2"
    th = [f for f in doc.timeline.features if f.feature_type == "thread"][0]
    assert th.follow_host is False and th.used_diameter == 29.99       # buried inside the Ø36 neck
    v0 = doc.bodies[jar].manifold.volume()
    idx = doc.timeline.features.index(th)
    host = th.measure_host(doc.step_states[idx]["body_cylinder_1"])
    doc.edit_feature(idx, follow_host=True, host_offset=-0.01)
    assert th.used_diameter == pytest.approx(host - 0.01, abs=1e-6)
    assert doc.bodies[jar].manifold.volume() < v0 - 50                 # the thread now cuts its groove in the jar


def test_dialog_new_thread_on_a_cylinder_follows_by_default_and_keeps_the_offset():
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs import ThreadDialog
    doc = Document()
    doc.add_cylinder(15.0, 10.0)
    dlg = ThreadDialog(doc)
    dlg.apply_cylinder_info({"diameter": 30.0, "length": 10.0, "is_internal": False, "origin": [0, 0, 0],
                             "axis": [0, 0, 1]})
    assert dlg.chk_follow.isChecked() and dlg.chk_follow.isEnabled()
    dlg.spn_dia.setValue(29.99)
    v = dlg.get_values()
    assert v["follow_host"] is True and v["host_offset"] == pytest.approx(-0.01)
    dlg.set_plane(None)
    assert not dlg.chk_follow.isEnabled() and dlg.get_values()["follow_host"] is False


def test_dialog_switching_follow_on_takes_the_cylinders_diameter():
    QApplication.instance() or QApplication([])
    from omacad.ui.dialogs import ThreadDialog
    dlg = ThreadDialog(Document())
    dlg.set_anchor("bottom", 0.0, 5.0)
    dlg.spn_dia.setValue(29.99)
    dlg.set_host(35.99, False)
    assert not dlg.chk_follow.isChecked()
    dlg.chk_follow.setChecked(True)
    assert dlg.spn_dia.value() == pytest.approx(35.99)
    assert dlg.get_values()["host_offset"] == pytest.approx(0.0)
