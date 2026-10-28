"""#46 in the window: Cone panel, and the Sweep / Loft / Pipe panel building a body from clicked profiles."""
import math

import pytest
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()


def test_cone_panel_makes_a_pointed_cone(win):
    from omacad.ui.dialogs.primitives_dlg import ConeDialog
    win.prompt_cone()
    QApplication.processEvents()
    d = win.findChildren(ConeDialog)[-1]
    d.spn_radius.setValue(10.0)
    d.spn_height.setValue(30.0)
    d.spn_top.setValue(0.0)
    d.accept()
    QApplication.processEvents()
    feat = win.doc.timeline.features[-1]
    assert feat.feature_type == "cone"
    vol = next(iter(win.doc.bodies.values())).manifold.volume()
    assert abs(vol - math.pi * 100 * 30 / 3) < 0.01 * math.pi * 1000


def test_loft_and_pipe_panels(win):
    from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog
    doc = win.doc
    a = doc.start_sketch("XY")
    a.add_circle((0, 0), 10)
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["XY"], 20.0, origin=(0, 0, 0)))
    b = doc.start_sketch_on_plane(plane)
    b.add_circle((0, 0), 5)
    doc.finish_sketch()
    win.prompt_sweep_tool("loft")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    # clicks in the view: each adds a profile, though they lie on different planes (Shift+click used to drop the
    # second one, so a Loft never got two profiles)
    win.viewport.toggle_profile_in_selection((a.sketch_id, 0))
    win.viewport.toggle_profile_in_selection((b.sketch_id, 0))
    assert dlg.profiles == [(a.sketch_id, 0), (b.sketch_id, 0)]
    dlg.accept()
    QApplication.processEvents()
    assert doc.timeline.features[-1].feature_type == "loft"
    want = math.pi * 20 / 3 * (100 + 50 + 25)
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - want) < 0.01 * want

    path = doc.start_sketch("XZ")
    line = path.add_line((30, 0), (30, 40))
    doc.finish_sketch()
    win.prompt_sweep_tool("pipe")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    win.viewport.sketch_curve_picked.emit(path.sketch_id, line.entity_id)
    dlg.spn_diam.setValue(4.0)
    dlg.accept()
    QApplication.processEvents()
    pipe = doc.timeline.features[-1]
    assert pipe.feature_type == "pipe"
    assert abs(doc.bodies[f"body_{pipe.feature_id}"].manifold.volume() - math.pi * 4 * 40) < 0.01 * math.pi * 160


def test_sweep_path_is_clicked_not_the_newest_sketch(win):
    """Drawn as most people do it: the path first, then the profile. The newest sketch (the profile) used to become
    the path, so the circle was swept round itself. Now the other sketch is taken, or the path is clicked."""
    from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog
    doc = win.doc
    path = doc.start_sketch("XY")
    a = path.add_line((0, 0), (30, 0))
    path.add_arc((30, 0), (30 + 20 * math.sin(math.pi / 4), 20 - 20 * math.cos(math.pi / 4)), (50, 20))
    doc.finish_sketch()
    prof = doc.start_sketch("YZ")
    prof.add_circle((0, 0), 2)
    doc.finish_sketch()
    win.prompt_sweep_tool("sweep")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    assert dlg.active == "profile" and dlg.path() is None
    doc.selected_profile, doc.selected_extra = (prof.sketch_id, 0), []
    win.viewport.profile_picked.emit()
    assert dlg.path() is not None and dlg.path()[0] == path.sketch_id and len(dlg.path()[1]) == 2
    win.viewport.sketch_curve_picked.emit(path.sketch_id, a.entity_id)       # a click on the line: the whole chain
    assert len(dlg.path()[1]) == 2
    dlg.accept()
    QApplication.processEvents()
    feat = doc.timeline.features[-1]
    length = 30 + math.pi / 2 * 20
    assert feat.feature_type == "sweep"
    assert abs(doc.bodies[f"body_{feat.feature_id}"].manifold.volume() - math.pi * 4 * length) < 0.01 * math.pi * 4 * length


def test_sweep_from_a_profile_in_the_middle_of_a_curved_path():
    from omacad.model.document import Document
    doc = Document()
    path = doc.start_sketch("XY")
    path.add_line((0, 0), (30, 0))
    path.add_arc((30, 0), (30 + 20 * math.sin(math.pi / 4), 20 - 20 * math.cos(math.pi / 4)), (50, 20))
    doc.finish_sketch()
    plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes["YZ"], 15.0, origin=(0, 0, 0)))
    prof = doc.start_sketch_on_plane(plane)
    prof.add_circle(tuple(prof.plane.world_to_uv((15.0, 0.0, 0.0))), 2)
    doc.finish_sketch()
    from omacad.ui.dialogs.sweep_dlg import path_entities
    doc.add_sweep(prof.sketch_id, 0, (path.sketch_id, path_entities(path)))
    m = next(iter(doc.bodies.values())).manifold
    length = 30 + math.pi / 2 * 20
    assert abs(m.volume() - math.pi * 4 * length) < 0.01 * math.pi * 4 * length
    bb = m.bounding_box()
    assert abs(bb[4] - 20.0) < 0.1 and abs(bb[3] - 52.0) < 0.1      # it follows the arc up to its end at (50, 20)


def test_pipe_along_body_edges_picked_like_fillet(win):
    """The path can be body edges, picked as in Fillet (joined edges follow): a pipe round the top of a box."""
    from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog
    doc = win.doc
    box = doc.add_box(40, 20, 10)
    top = box.manifold.bounding_box()[5]
    win.prompt_sweep_tool("pipe")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    v = win.viewport
    assert v.edge_pick_mode and v.path_pick_mode
    edge = next(e for e in box.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - top) < 1e-9 and abs(e.p1[2] - top) < 1e-9 and abs(e.p0[1] - e.p1[1]) < 1e-9)
    v._toggle_edge(edge)            # a click on one top edge
    v.selected_edges = [e for e in box.edges if getattr(e, "kind", "line") == "line"
                        and abs(e.p0[2] - top) < 1e-9 and abs(e.p1[2] - top) < 1e-9]   # + the other three (Shift-like)
    v.edges_selection_changed.emit()
    assert dlg.path()[0] == "@edges" and len(dlg.path()[1]) == 4
    dlg.spn_diam.setValue(2.0)
    dlg.spn_thick.setValue(0.0)
    dlg.cmb_op.setCurrentIndex(1)   # Join
    dlg.accept()
    QApplication.processEvents()
    feat = doc.timeline.features[-1]
    assert feat.feature_type == "pipe" and not v.edge_pick_mode
    ring = 2 * (40 + 20)            # a closed square ring: half the round section sticks out of the box
    added = next(iter(doc.bodies.values())).manifold.volume() - 40 * 20 * 10
    assert 0.4 * math.pi * ring < added < 0.85 * math.pi * ring
    from omacad.io.exporter import Exporter
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), "e.omacad")
    Exporter.save_project(doc, path)
    again = Exporter.load_project(path)
    assert abs(next(iter(again.bodies.values())).manifold.volume() - next(iter(doc.bodies.values())).manifold.volume()) < 1e-6


def test_sweep_panel_keeps_shift_clicked_profiles_of_one_sketch(win):
    from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog
    doc = win.doc
    path = doc.start_sketch("XY")
    path.add_line((0, 0), (30, 0))
    doc.finish_sketch()
    prof = doc.start_sketch("YZ")
    prof.add_rect((-12, -1), (-8, 1))
    prof.add_rect((8, -1), (12, 1))
    doc.finish_sketch()
    win.prompt_sweep_tool("sweep")
    dlg = win.findChildren(SweepLoftDialog)[-1]
    assert win.viewport.profile_chain_mode            # plain clicks add profiles, no Shift needed
    win.viewport.toggle_profile_in_selection((prof.sketch_id, 0))
    win.viewport.profile_picked.emit()
    win.viewport.toggle_profile_in_selection((prof.sketch_id, 1))
    win.viewport.profile_picked.emit()
    assert dlg.active == "profile"                    # still on Profile: more may follow, Path has its own button
    dlg.set_active("path")
    assert not win.viewport.profile_chain_mode
    assert dlg.profiles == [(prof.sketch_id, 0), (prof.sketch_id, 1)] and "2 profiles" in dlg.lbl_profiles.text()
    dlg.accept()
    QApplication.processEvents()
    feat = doc.timeline.features[-1]
    assert feat.feature_type == "sweep" and feat.extra_profiles == [1]
    assert abs(doc.bodies[f"body_{feat.feature_id}"].manifold.volume() - 480) < 1.0


def test_loft_profile_list_and_edit_add_third_section(win, monkeypatch):
    from omacad.ui import feature_edit
    from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog
    doc = win.doc
    profiles = []
    for z in (0, 10, 20):
        plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes['XY'], z, origin=(0, 0, 0)))
        sketch = doc.start_sketch_on_plane(plane)
        sketch.add_rect((-10, -10), (10, 10))
        doc.finish_sketch()
        profiles.append((sketch.sketch_id, 0))
    feat = doc.add_loft(profiles[:2])
    assert feature_edit.can_edit(feat)
    before = next(iter(doc.bodies.values())).manifold.volume()

    def edit(dlg):
        assert dlg.profiles == profiles[:2]
        choices = [dlg.profile_choice.itemData(i) for i in range(dlg.profile_choice.count())]
        assert profiles[2] in choices, choices
        dlg.profile_choice.setCurrentIndex(choices.index(profiles[2]))
        dlg.add_profile()
        assert dlg.profiles == profiles
        dlg.move_profile(-1)
        assert dlg.profiles == [profiles[0], profiles[2], profiles[1]]
        dlg.move_profile(1)
        return 1

    monkeypatch.setattr(SweepLoftDialog, 'exec', edit)
    index = doc.timeline.features.index(feat)
    assert feature_edit.edit_feature(win, doc, index)
    assert len(doc.timeline.features[index].sections) == 3
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(8000)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(before)
    monkeypatch.setattr(SweepLoftDialog, 'exec', lambda dlg: (dlg.remove_profile(), 0)[1])
    assert not feature_edit.edit_feature(win, doc, index)
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(before)
