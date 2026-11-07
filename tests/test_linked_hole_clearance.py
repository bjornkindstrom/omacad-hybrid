"""Linked pattern holes follow the master's distance to the walls (#216 follow-up)."""
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch_pattern import corner_copies, rectangular_copies


def _plate(doc):
    sk = doc.start_sketch("XY")
    lines = sk.add_rect((-50., -30.), (50., 30.))
    assert doc.add_constraints(sk.sketch_id, [("FIX", [l.entity_id], []) for l in lines])
    return sk, lines


def _wall(lines, x=None, y=None):
    for l in lines:
        if x is not None and l.p1[0] == pytest.approx(x) and l.p2[0] == pytest.approx(x):
            return l
        if y is not None and l.p1[1] == pytest.approx(y) and l.p2[1] == pytest.approx(y):
            return l


def _clearances(sk, holes):
    """(distance to nearest vertical wall, to nearest horizontal wall) from each rim."""
    return [(50. - abs(h.center[0]) - h.radius, 30. - abs(h.center[1]) - h.radius) for h in holes]


def _dim(doc, sk, hole, wall, value):
    assert doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", hole.entity_id, value,
                                        refs=[wall.entity_id], pts=["edge_near"],
                                        moving_entity_id=hole.entity_id)
    return sk.dimensions[-1]


@pytest.mark.parametrize("dims_first", [True, False])
def test_corner_holes_follow_the_master_wall_distance(dims_first, tmp_path):
    doc = Document()
    sk, lines = _plate(doc)
    master = sk.add_circle((-40., 20.), 4.)
    if dims_first:
        left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
        top = _dim(doc, sk, master, _wall(lines, y=30.), 6.)
    copies = corner_copies(sk, [master], (-50., -30., 50., 30.))
    from omacad.model.sketch_linked_clearance import link_clearances
    link_clearances(sk)  # what the Pattern panel does on a linked pattern
    if not dims_first:
        left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
        top = _dim(doc, sk, master, _wall(lines, y=30.), 6.)
    holes = [master, *copies]
    assert _clearances(sk, holes) == pytest.approx([(6., 6.)] * 4)
    assert doc.update_dimension(sk.sketch_id, left.dim_id, 12.)
    assert doc.update_dimension(sk.sketch_id, top.dim_id, 3.)
    assert _clearances(sk, holes) == pytest.approx([(12., 3.)] * 4)
    diameter = next(d for d in sk.dimensions if d.target_entity_id == master.entity_id and d.dim_type == "DIAMETER")
    assert doc.update_dimension(sk.sketch_id, diameter.dim_id, 10.)
    assert all(h.radius == pytest.approx(5.) for h in holes)
    assert _clearances(sk, holes) == pytest.approx([(12., 3.)] * 4)
    ids = [h.entity_id for h in holes]
    doc.undo()
    doc.undo()
    sk = doc.sketches[sk.sketch_id]
    holes = [sk.get_entity(i) for i in ids]
    assert all(h.radius == pytest.approx(4.) for h in holes)
    assert _clearances(sk, holes) == pytest.approx([(12., 6.)] * 4)
    doc.redo()
    path = tmp_path / "plate.omacad"
    doc.finish_sketch()
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    assert loaded.update_dimension(sk.sketch_id, left.dim_id, 8.)
    restored = loaded.sketches[sk.sketch_id]
    assert _clearances(restored, [restored.get_entity(h.entity_id) for h in holes]) == pytest.approx([(8., 3.)] * 4)


def test_editing_a_copy_clearance_unlinks_only_that_hole():
    doc = Document()
    sk, lines = _plate(doc)
    master = sk.add_circle((-40., 20.), 4.)
    copies = corner_copies(sk, [master], (-50., -30., 50., 30.))
    left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
    right = next(d for d in sk.dimensions if d.follows == left.dim_id
                 and sk.get_entity(d.target_entity_id).center[0] > 0 and sk.get_entity(d.target_entity_id).center[1] > 0)
    assert doc.update_dimension(sk.sketch_id, right.dim_id, 15.)
    assert right.follows is None
    assert doc.update_dimension(sk.sketch_id, left.dim_id, 9.)
    rims = {h.entity_id: 50. - abs(h.center[0]) - h.radius for h in [master, *copies]}
    assert rims.pop(right.target_entity_id) == pytest.approx(15.)
    assert list(rims.values()) == pytest.approx([9.] * 3)
    doc.remove_dimension(sk.sketch_id, left.dim_id)
    assert not any(d.follows for d in sk.dimensions)


def test_unlinked_or_middle_copies_are_left_alone():
    doc = Document()
    sk, lines = _plate(doc)
    master = sk.add_circle((-40., 20.), 4.)
    linked = rectangular_copies(sk, [master], 3, 40.)        # middle hole is 40 mm from every wall
    free, = rectangular_copies(sk, [master], 1, 0., 2, -40., linked=False)
    left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
    assert doc.update_dimension(sk.sketch_id, left.dim_id, 10.)
    middle, last = linked
    assert middle.center[0] == pytest.approx(0.)
    assert 50. - last.center[0] - last.radius == pytest.approx(10.)
    assert free.center[0] == pytest.approx(-40.)


def test_pattern_panel_links_existing_clearances(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from omacad.ui import settings as settings_mod
    from omacad.ui.viewport import Viewport3D
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "settings.json"))
    view = Viewport3D(Document())
    view.resize(800, 600)
    try:
        doc = view.doc
        sk, lines = _plate(doc)
        master = sk.add_circle((-40., 20.), 4.)
        left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
        view.selected_entities = {master.entity_id}
        view.set_sketch_tool("PATTERN")
        panel = view.pattern_panel
        panel.kind.setCurrentIndex(panel.kind.findData("corners"))
        assert len([d for d in sk.dimensions if d.follows == left.dim_id]) == 3
        panel.linked.setChecked(False)
        assert not any(d.follows for d in sk.dimensions)
        panel.linked.setChecked(True)
        panel.ok.click()
        assert doc.update_dimension(sk.sketch_id, left.dim_id, 10.)
        holes = [e for e in sk.entities if e.entity_type == "circle"]
        assert len(holes) == 4
        assert [50. - abs(h.center[0]) - h.radius for h in holes] == pytest.approx([10.] * 4)
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()
