"""Global undo/redo: every kind of change can be undone and redone, and the document comes back exactly."""
import copy
import math

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane


def state(doc):
    """Everything that defines the document, plus what it builds."""
    vols = sorted(round(b.manifold.volume(), 4) for b in doc.bodies.values())
    return copy.deepcopy(Exporter.document_to_dict(doc)), vols


def check(doc, op):
    """Do `op`, then undo, then redo; the states must match before / after / after."""
    before = state(doc)
    op()
    after = state(doc)
    assert after != before, "the operation changed nothing"
    assert doc.undo() is not None
    assert state(doc) == before, "undo did not restore the previous state"
    assert doc.redo() is not None
    assert state(doc) == after, "redo did not restore the result"
    return after


def box_doc():
    d = Document()
    d.add_box(40, 30, 20)
    return d


def sketch_rect(d, plane="XY", a=(5, 5), b=(15, 15)):
    sk = d.start_sketch(plane)
    sk.add_rect(a, b)
    d.finish_sketch()
    return sk


def test_primitives_undo():
    d = Document()
    for op in (lambda: d.add_box(10, 10, 10), lambda: d.add_cylinder(5, 10), lambda: d.add_sphere(4)):
        check(d, op)
    assert len(d.bodies) == 3


def test_extrude_and_sketch_steps():
    d = Document()
    check(d, lambda: d.start_sketch("XY"))
    assert d.active_sketch is not None
    d.undo()
    assert d.active_sketch is None and not d.sketches
    d.redo()
    assert d.active_sketch is not None
    sk = d.active_sketch
    sk.add_rect((0, 0), (10, 10))
    check(d, d.finish_sketch)
    check(d, lambda: d.extrude_profile(sk.sketch_id, 0, 5, "new_body"))
    assert math.isclose(list(d.bodies.values())[0].manifold.volume(), 500, rel_tol=1e-6)


def test_finish_sketch_undo_returns_to_sketch_mode():
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    d.finish_sketch()
    assert d.active_sketch is None
    d.undo()                                  # undo "Finish Sketch"
    assert d.active_sketch is not None and d.active_sketch.sketch_id == sk.sketch_id
    assert len(d.active_sketch.entities) == 4


def test_feature_steps():
    d = box_doc()
    body = list(d.bodies.values())[0]
    top = [e.ref() for e in body.edges if e.kind == "line" and abs(e.p0[2] - 20) < 1e-6 and abs(e.p1[2] - 20) < 1e-6]
    bid = body.body_id
    check(d, lambda: d.add_fillet(top, 2, "chamfer"))
    check(d, lambda: d.add_shell(bid, 2.0, []))
    check(d, lambda: d.move_body(bid, dx=5, dy=0, dz=0))
    check(d, lambda: d.add_hole([{"origin": [20, 15, 20], "normal": [0, 0, 1]}], hole_type="simple", diameter=4, depth=5))
    check(d, lambda: d.add_pattern([d.timeline.features[-1].feature_id], "mirror", mirror_mode="plane:YZ"))


def test_revolve_undo():
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_rect((10, 0), (20, 30))
    d.finish_sketch()
    check(d, lambda: d.add_revolve(sk.sketch_id, 0, axis=("v",), angle=180))


def test_timeline_edits():
    d = box_doc()
    check(d, lambda: d.edit_feature(0, length=60))
    check(d, lambda: d.rename_feature(0, "Base"))
    check(d, lambda: d.toggle_suppress(0))
    d.toggle_suppress(0)
    check(d, lambda: d.delete_feature(0))


def test_parameters_planes_sections_canvases():
    d = box_doc()
    from omacad.model.document import Parameter
    check(d, lambda: d.set_parameters([Parameter("w", "10", "")]))
    pid = []
    check(d, lambda: pid.append(d.add_construction_plane(d.origin_planes["XY"], 7.0)))
    check(d, lambda: d.delete_construction_plane(pid[0]))
    sid = []
    check(d, lambda: sid.append(d.add_section((0, 0, 0), (0, 0, 1), 5.0)))
    check(d, lambda: d.delete_section(sid[0]))
    cid = []
    check(d, lambda: cid.append(d.add_canvas("c", "XY", "AAAA", 10, 10)))
    check(d, lambda: d.delete_canvas(cid[0]))


def test_delete_body_is_a_real_step():
    d = Document()
    d.add_box(10, 10, 10)
    d.add_cylinder(3, 4)
    first = list(d.bodies)[0]
    check(d, lambda: d.delete_body(first))
    d.timeline.recompute(d)                    # a rebuild keeps it deleted
    assert first not in d.bodies and len(d.bodies) == 1
    d.undo()
    assert first in d.bodies and len(d.bodies) == 2


def test_a_chain_of_steps_walks_down_and_up():
    d = Document()
    s0 = state(d)
    d.add_box(40, 30, 20); s1 = state(d)
    d.add_cylinder(5, 10); s2 = state(d)
    d.edit_feature(0, length=50); s3 = state(d)
    d.rename_feature(1, "Pin"); s4 = state(d)
    sk = d.start_sketch("XY")
    sk.add_rect((5, 5), (15, 15)); s6 = state(d)      # drawing is not a step of its own; it is part of the sketch
    d.finish_sketch(); s7 = state(d)
    d.extrude_profile(sk.sketch_id, 0, 8, "new_body"); s8 = state(d)
    down = [s8, s7, s6, s4, s3, s2, s1, s0]            # undoing "Start Sketch" returns to before the sketch
    for i, want in enumerate(down):
        assert state(d) == want, f"going down, step {i}"
        d.undo()
    assert d.undo() is None
    for i, want in enumerate([s1, s2, s3, s4, s6, s7, s8]):
        d.redo()
        assert state(d) == want, f"going up, step {i}"
    assert d.redo() is None


def test_new_step_clears_redo():
    d = box_doc()
    d.add_cylinder(3, 4)
    d.undo()
    assert d.redo_label() == "Cylinder"
    d.add_sphere(2)
    assert d.redo_label() is None


def test_noop_is_not_a_step():
    d = box_doc()
    n = len(d.undo_stack)
    d.rename_feature(0, d.timeline.features[0].name)       # same name: nothing changed
    assert len(d.undo_stack) == n


def test_sketch_edits_inside_a_sketch_still_undo_one_at_a_time():
    d = Document()
    sk = d.start_sketch("XY")
    n_start = len(sk.entities)
    before = sk.to_dict()
    sk.add_line((0, 0), (10, 0))
    d.record_sketch_change(sk, before)
    before = sk.to_dict()
    sk.add_line((10, 0), (10, 10))
    d.record_sketch_change(sk, before)
    assert len(sk.entities) == n_start + 2
    d.undo()
    assert len(d.active_sketch.entities) == n_start + 1
    d.undo()
    assert len(d.active_sketch.entities) == n_start
    d.undo()                                               # now the "Start Sketch" step itself
    assert d.active_sketch is None


def test_undo_keeps_listeners_and_identity():
    d = box_doc()
    calls = []
    d.add_change_listener(lambda: calls.append(1))
    d.add_cylinder(2, 3)
    n = len(calls)
    ident = id(d)
    d.undo()
    assert id(d) == ident and len(calls) > n


def test_file_roundtrip_unchanged_by_undo_machinery(tmp_path):
    d = box_doc()
    d.add_cylinder(3, 4)
    p = tmp_path / "a.omacad"
    Exporter.save_project(d, str(p))
    d2 = Exporter.load_project(str(p))
    assert state(d2)[1] == state(d)[1]


def test_snapshot_speed_with_many_steps():
    import time
    d = Document()
    for i in range(30):
        d.add_box(5 + i, 5, 5)
    t = time.time()
    snap = d.snapshot()
    d.restore(snap)
    assert time.time() - t < 3.0
