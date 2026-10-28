"""Offset Face on a thread changes only the body you click: the threaded zone (coil + bore/pin) is rebuilt bigger or
smaller and cut from / added to that body, so a jar gets real clearance against its lid (whose shape stays). Before,
the Thread step itself was changed, so the lid grew with the groove and the fit stayed exact."""
from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.features.thread import ThreadFeature

DOC = str(Path(__file__).parent / "data" / "offset_face_coil_stuck.omacad")
LID, JAR = "body_cylinder_1", "body_split_2"


def _doc(path=DOC):
    doc = Exporter.load_project(path)
    last = doc.timeline.features[-1]
    last.suppressed = True
    doc.timeline.recompute(doc)
    return doc, last


def _gap_in_thread(doc) -> float:
    """Smallest distance between lid and jar inside the threaded zone (z 10..20; the lid rests on the floor and rim)."""
    lid = doc.bodies[LID].manifold.trim_by_plane((0, 0, -1), -19.7).trim_by_plane((0, 0, 1), 10.3)
    return doc.bodies[JAR].manifold.min_gap(lid, 1.0)


def test_surface_of_the_coil_is_recognised_and_signed():
    doc, last = _doc()
    thread, sign, shift = doc._thread_offset(last.faces)
    assert isinstance(thread, ThreadFeature) and sign == -1 and list(shift) == [0.0, 0.0, -10.0]   # the lid was moved


def test_minus_gives_the_jar_clearance_and_leaves_the_lid():
    doc, last = _doc()
    lid0, jar0, grow0 = doc.bodies[LID].manifold.volume(), doc.bodies[JAR].manifold.volume(), doc.timeline.features[4].grow
    assert _gap_in_thread(doc) < 1e-6                                   # an exact fit to begin with
    feat = doc.add_offset_face(JAR, last.faces, -0.2)
    assert feat.feature_type == "offset_face" and feat.faces[0]["kind"] == "thread" and feat.skipped == 0
    assert doc.timeline.features[4].grow == grow0                      # the Thread step is left alone
    assert abs(doc.bodies[LID].manifold.volume() - lid0) < 1e-6        # the lid keeps its size
    jar = doc.bodies[JAR].manifold
    assert jar.volume() < jar0 - 100 and len(jar.decompose()) == 1 and jar.status().name == "NoError"
    assert 0.18 < _gap_in_thread(doc) < 0.21                           # ~0.2 mm all round (tessellation)
    doc.undo()
    assert abs(doc.bodies[JAR].manifold.volume() - jar0) < 1e-6


def test_plus_adds_material_into_the_lid():
    doc, last = _doc()
    doc.add_offset_face(JAR, last.faces, 0.1)
    overlap = (doc.bodies[JAR].manifold ^ doc.bodies[LID].manifold).volume()
    assert overlap > 30                                                 # tighter: the jar now overlaps the lid


def test_grow_widens_every_profile_also_in_the_lead_in():
    from omacad.model.kernel import CadKernel
    for prof in ("round", "trapezoidal_45", "iso_60"):
        a = CadKernel.create_thread(20, 2.5, 10, profile=prof, include_core=False, attached_to_cylinder=True)
        b = CadKernel.create_thread(20, 2.5, 10, profile=prof, include_core=False, attached_to_cylinder=True, grow=0.2)
        assert b.volume() > a.volume() and len((b - a).decompose()) >= 1


def test_dialog_says_which_body_changes():
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    doc, last = _doc()
    w = MainWindow()
    w.attach_document(doc)
    w.prompt_offset_face()
    dlg = w.inspector.current_tool_dlg
    dlg.spn_dist.setValue(-0.2)
    dlg.toggle(last.faces[0], JAR)
    QTest.qWait(400)
    assert "only Burk changes" in dlg.lbl_note.text() and "looser" in dlg.lbl_note.text()
    dlg.reject()


def test_click_on_the_wall_between_the_turns_is_the_thread_too():
    """The user's own click (burk med coils.omacad): the bore wall between the turns is a cylinder face. Before, it went
    to the cylinder offset, which could not move a band that short (nothing happened)."""
    doc, last = _doc(str(Path(__file__).parent / "data" / "offset_face_thread_band.omacad"))
    assert last.faces[0]["kind"] == "cylinder" and last.faces[0]["internal"]
    thread, sign, _ = doc._thread_offset(last.faces)
    assert thread.feature_type == "thread" and sign == -1
    v0 = doc.bodies[JAR].manifold.volume()
    feat = doc.add_offset_face(JAR, last.faces, -0.2)
    assert feat.skipped == 0 and doc.bodies[JAR].manifold.volume() < v0 - 100


def test_cylinder_far_from_the_thread_is_not_taken():
    doc, last = _doc()
    far = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 12.0, "length": 10.0, "internal": False}
    assert doc._thread_offset([far]) is None                        # the outside of the jar, below the thread
