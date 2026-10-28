"""Extruding a big profile leaves the shapes of other sketches inside it open (as in Fusion);
Shift+clicking them (same plane, other sketch) fills them in again."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.timeline import ExtrudeFeature

H = 10.0


def doc():
    d = Exporter.load_project(str(Path(__file__).parent / "data" / "coplanar_sketches_nested.omacad"))
    d.timeline.recompute(d)
    return d


def extrude(d, selected_extra=()):
    extra, refs, holes = ExtrudeFeature.selection_parts(d, "sketch_1", 0, list(selected_extra))
    feat = ExtrudeFeature("t", "t", "sketch_1", 0, H, "new_body", extra_profiles=extra, extra_refs=refs, holes=holes)
    return feat, feat.build_solid(d), holes


def area(d, sid):
    return d.sketches[sid].profiles[0].area


def test_shapes_inside_the_big_profile_stay_open():
    d = doc()
    feat, solid, holes = extrude(d)
    assert {h[0] for h in holes} == {"sketch_2", "sketch_3"}
    want = (area(d, "sketch_1") - area(d, "sketch_2") - area(d, "sketch_3")) * H
    assert solid.volume() == pytest.approx(want, rel=1e-6)


def test_shift_clicking_a_shape_from_another_sketch_fills_it_in():
    d = doc()
    feat, solid, holes = extrude(d, [("sketch_2", 0)])
    assert {h[0] for h in holes} == {"sketch_3"}
    want = (area(d, "sketch_1") - area(d, "sketch_3")) * H
    assert solid.volume() == pytest.approx(want, rel=1e-6)


def test_the_open_shapes_survive_save_load_and_hidden_sketches(tmp_path):
    d = doc()
    extra, refs, holes = ExtrudeFeature.selection_parts(d, "sketch_1", 0, [])
    d.extrude_profile("sketch_1", 0, H, "new_body", extra_profiles=extra, extra_refs=refs, holes=holes)
    path = str(tmp_path / "a.omacad")
    Exporter.save_project(d, path)
    d2 = Exporter.load_project(path)
    for sk in d2.sketches.values():
        sk.visible = False                      # visibility must not decide what the step builds
    d2.timeline.recompute(d2)
    body = next(iter(d2.bodies.values()))
    want = (area(d, "sketch_1") - area(d, "sketch_2") - area(d, "sketch_3")) * H
    assert body.manifold.volume() == pytest.approx(want, rel=1e-6)


def test_selection_highlight_leaves_the_open_shapes_unshaded():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport import Viewport3D
    d = doc()
    v = Viewport3D(d)
    d.selected_profile, d.selected_extra = ("sketch_1", 0), []
    plain = v._profile_fill(("sketch_1", 0))
    sel = v._selection_fill()
    assert sel is not None and len(sel) != len(plain)          # holes change the triangulation
    d.selected_extra = [("sketch_2", 0)]
    assert v._selection_fill() is not None
