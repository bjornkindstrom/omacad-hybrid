"""#246 jar shoulder, #247 thread in an open hole, #248 red tool in Combine (cut), #249 a whole thread in one click."""
import math
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from omacad.io.exporter import Exporter
from omacad.model import brep
from omacad.model.document import Document

DATA = Path(__file__).parent / "data"


@pytest.mark.skipif(not brep.available(), reason="OpenCascade not installed")
def test_exact_shell_keeps_the_jars_shoulder_sharp():
    from omacad.model.jar import JarSpec, build_jar
    vol = {}
    was = brep.active()
    try:
        for on in (False, True):
            brep.set_enabled(on)
            doc = Document()
            ids = build_jar(doc, JarSpec())
            vol[on] = doc.bodies[ids["jar"]].manifold.volume()
            shell = Document()
            jar = shell.add_cylinder(20, 40)
            neck = shell.add_cylinder(16, 10, plane_origin=[0, 0, 40], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0])
            shell.combine_bodies(jar.body_id, neck.body_id, "join")
            shell.add_shell(jar.body_id, 2.0, open_faces=[{"normal": [0, 0, 1], "origin": [0, 0, 50], "body_id": jar.body_id}])
            if on:
                body = shell.bodies[jar.body_id]
                assert body.brep is not None
                exact = math.pi * (400 * 40 + 256 * 10 - 324 * 36 - 196 * 12)
                assert brep.volume(body.brep) == pytest.approx(exact, rel=1e-6)
    finally:
        brep.set_enabled(was)
    assert vol[True] == pytest.approx(vol[False], rel=1e-3)


def _thread(doc):
    return next(f for f in doc.timeline.features if f.feature_type == "thread")


def test_thread_in_an_open_hole_runs_out_through_its_mouth():
    doc = Exporter.load_project(str(DATA / "thread_mouth_247.omacad"))
    feat = _thread(doc)
    assert not feat.run_out and feat._run == (0.0, 0.0)           # an older file stays as it was
    old = feat.build_solid()
    before = next(iter(doc.bodies.values())).manifold.volume()
    doc.edit_feature(doc.timeline.features.index(feat), run_out=True)
    feat = _thread(doc)
    assert feat._run[0] >= feat.pitch and feat._run[1] >= feat.pitch
    new = feat.build_solid()
    assert (old - new).volume() < 0.02 * old.volume()             # the turns stay where they were
    after = next(iter(doc.bodies.values())).manifold
    assert 0.0 < before - after.volume() < 30.0
    # a groove leaves through the mouth on every side: the cutter covers the whole circle just outside it
    ring = new.transform(feat._to_local()).slice(-0.5 * feat.pitch)
    assert not ring.is_empty()


def test_thread_in_a_blind_hole_does_not_run_into_its_bottom_and_round_trips():
    doc = Document()
    box = doc.add_box(30, 30, 20)
    top = box.manifold.bounding_box()[5]
    x, y = (box.manifold.bounding_box()[0] + box.manifold.bounding_box()[3]) / 2, (box.manifold.bounding_box()[1] + box.manifold.bounding_box()[4]) / 2
    hole = doc.add_cylinder(5, 12, plane_origin=[x, y, top - 10], plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0])
    doc.combine_bodies(box.body_id, hole.body_id, "cut")
    doc.add_thread(10, 2, 10, is_female=True, operation="cut", target_body_id=box.body_id, plane_origin=[x, y, top - 10],
                   plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0], host_length=10, run_out=True, taper_turns=0.3)
    feat = _thread(doc)
    assert feat._run[0] == 0.0 and feat._run[1] >= feat.pitch
    assert type(feat).from_dict(feat.to_dict()).run_out


def test_any_point_of_a_cut_thread_gives_the_whole_thread():
    doc = Exporter.load_project(str(DATA / "thread_cut_pick_249.omacad"))
    body, feat = doc.bodies["body_extrude_2"], _thread(doc)
    tri = np.asarray(body.render_mesh.vertices, dtype=float).reshape(-1, 3, 3)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(n, axis=1)
    c = tri.mean(axis=1)
    inside = np.flatnonzero((c[:, 2] > 27) & (c[:, 2] < 33) & (np.linalg.norm(c[:, :2], axis=1) < 8) & (area > 1e-3))
    assert len(inside) > 50
    for i in inside[::max(1, len(inside) // 40)]:
        ref = doc.thread_at(c[i], n[i] / area[i])
        assert ref is not None and ref["thread_id"] == feat.feature_id and ref["sign"] == -1
    outer = np.flatnonzero((np.abs(np.hypot(c[:, 0], c[:, 2] - 10) - 25) < 0.1) & (c[:, 2] < 0) & (area > 1e-3))[0]
    assert doc.thread_at(c[outer], n[outer] / area[outer]) is None

    picked = doc.thread_triangles(ref, body.render_mesh)
    r = np.linalg.norm(picked.reshape(-1, 3)[:, :2], axis=1)
    assert len(picked) > 1000 and r.max() < 8.0                   # not the outside wall as well

    bolt, before = doc.bodies["body_cylinder_8"].manifold.volume(), body.manifold.volume()
    doc.add_offset_face(body.body_id, [ref], -0.2)
    assert doc.bodies["body_extrude_2"].manifold.volume() < before - 50
    assert doc.bodies["body_cylinder_8"].manifold.volume() == pytest.approx(bolt)
    gap = doc.bodies["body_extrude_2"].manifold.min_gap(doc.bodies["body_cylinder_8"].manifold, 1.0)
    assert 0.1 < gap < 0.25


def test_offset_dialog_takes_a_thread_once_and_starts_on_the_loose_side():
    from omacad.ui.dialogs import OffsetFaceDialog
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(str(DATA / "thread_cut_pick_249.omacad"))
    ref = {"kind": "thread", "thread_id": _thread(doc).feature_id, "sign": -1, "shift": [0.0, 0.0, 0.0]}
    dlg = OffsetFaceDialog(doc=doc)
    dlg.toggle(ref, "body_extrude_2")
    assert dlg.distance() == pytest.approx(-0.2) and dlg.drag_frame(doc.bodies["body_extrude_2"]) is not None
    assert len(dlg.highlights(doc.bodies["body_extrude_2"])[0]["tris"]) > 1000
    dlg.toggle(dict(ref), "body_extrude_2")
    assert dlg.faces == []


def test_combine_cut_marks_the_tool_until_the_panel_closes():
    from omacad.ui.main_window import MainWindow
    from omacad.ui.dialogs import CombineDialog
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    a = win.doc.add_box(20, 20, 20)
    b = win.doc.add_cylinder(5, 40)
    win.doc.selected_body_ids = []
    win.prompt_combine()
    dlg = next(w for w in app.allWidgets() if isinstance(w, CombineDialog) and w.window() is win)
    assert win.viewport.cut_tool_ids == set()
    dlg.cmb_op.setCurrentIndex(1)                # no target clicked yet: the tool shows all the same
    assert win.viewport.cut_tool_ids == {b.body_id}
    dlg.cmb_target.setCurrentIndex(1)
    dlg.cmb_tool.setCurrentIndex(0)
    assert win.viewport.cut_tool_ids == {a.body_id}
    dlg.cmb_op.setCurrentIndex(0)
    assert win.viewport.cut_tool_ids == set()
    dlg.cmb_op.setCurrentIndex(1)
    dlg.reject()
    assert win.viewport.cut_tool_ids == set()
