"""Timeline and step browser UI tests: chip display, hover highlights, step edges, and browser interactions."""
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.kernel import CadKernel
from omacad.model.sketch import SketchPlane
from omacad.ui.browser import BrowserTree
from omacad.ui.object_browser import FEATURE_ROLE, add_histories
from omacad.ui.timeline_bar import FeatureNodeWidget, TimelineBar, STEP_CHANGE_MIN_THICKNESS

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def bar():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(20, 20, 10)
    doc.add_cylinder(4.0, 6.0)
    doc.add_cylinder(2.0, 3.0)
    b = TimelineBar(doc)
    b.show()
    return b


def _wait_for(condition, timeout_ms):
    """Wait for the hover timer rather than a fixed time: a busy CI worker can be slow to fire it."""
    for _ in range(timeout_ms // 10):
        if condition():
            return True
        QTest.qWait(10)
    return bool(condition())


def _chips(bar):
    return bar.findChildren(FeatureNodeWidget)


def _enter(chip):
    chip.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))


def _leave(chip):
    chip.leaveEvent(QEvent(QEvent.Type.Leave))


def _area(render_mesh) -> float:
    t = render_mesh.vertices.reshape(-1, 3, 3).astype(float)
    return float(np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() / 2)


# =========================================================================
# 1. Timeline Chips & Hover Highlights
# =========================================================================

def test_only_the_last_chip_shows_its_name_and_hover_expands_the_others(bar):
    chips = sorted(_chips(bar), key=lambda c: c.index)
    assert [c.lbl_name.isVisible() for c in chips] == [False, False, True]
    narrow = chips[0].sizeHint().width()
    _enter(chips[0])
    assert chips[0].lbl_name.isVisible() and chips[0].sizeHint().width() > narrow
    _leave(chips[0])
    assert not chips[0].lbl_name.isVisible()


def test_hover_shows_what_the_step_added_and_leaving_restores(bar):
    seen = []
    bar.highlight_changed.connect(lambda a, r: seen.append((a is not None, r is not None)))
    chips = sorted(_chips(bar), key=lambda c: c.index)
    _enter(chips[1])
    assert seen == []
    assert _wait_for(lambda: seen, 5000)
    assert seen[-1] == (True, False)
    _leave(chips[1])
    assert seen[-1] == (False, False)
    bar.on_node_clicked(1)
    _enter(chips[2])
    n = len(seen)
    assert _wait_for(lambda: len(seen) > n, 5000)
    _leave(chips[2])
    assert seen[-1] == (True, False)


def test_a_quick_pass_over_a_chip_does_nothing(bar):
    seen = []
    bar.highlight_changed.connect(lambda a, r: seen.append(1))
    chip = sorted(_chips(bar), key=lambda c: c.index)[0]
    _enter(chip)
    _leave(chip)
    QTest.qWait(200)
    assert seen == []


def test_hovering_a_sketch_step_lights_the_sketch_up():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 5)
    sk = doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    sk.add_circle((0.0, 0.0), 3.0)
    doc.finish_sketch()
    b = TimelineBar(doc)
    b.show()
    flashes = []
    b.flash_sketch_requested.connect(flashes.append)
    chip = [c for c in _chips(b) if c.feature.feature_type == "sketch"][0]
    _enter(chip)
    assert _wait_for(lambda: flashes, 5000)
    assert flashes[-1] == sk.sketch_id
    _leave(chip)


def test_buttons_have_icons_and_no_text():
    QApplication.instance() or QApplication([])
    bar = TimelineBar(Document())
    for btn in (bar.btn_rewind, bar.btn_prev, bar.btn_next, bar.btn_ff):
        assert btn.text() == "" and not btn.icon().isNull()
        assert not btn.icon().pixmap(16, 16).toImage().isNull()
    bar.update_icons()


def test_click_on_a_chamfer_outlines_its_own_edge():
    QApplication.instance() or QApplication([])
    d = Document()
    d.add_box(20, 20, 10)
    body = next(iter(d.bodies.values()))
    tops = [e for e in body.edges if e.kind == "line" and abs(e.p0[2] - e.p1[2]) < 1e-6 and e.p0[2] > 5]
    d.add_fillet([tops[0].ref()], 1.0, "chamfer")
    d.add_fillet([tops[1].ref()], 1.0, "chamfer")
    bar = TimelineBar(d)
    seen = []
    bar.step_edges_changed.connect(seen.append)
    for step, want in ((2, tops[0]), (3, tops[1])):
        bar.on_node_clicked(step)
        assert len(seen[-1]) == 1
        got = seen[-1][0]
        dist = (want.p1 - want.p0) / np.linalg.norm(want.p1 - want.p0)
        for p in (got.p0, got.p1):
            off = (p - want.p0) - ((p - want.p0) @ dist) * dist
            assert np.linalg.norm(off) < 1e-6
    bar.on_node_clicked(3)
    assert seen[-1] == []
    bar.on_node_clicked(1)
    assert seen[-1] == []


def test_timeline_chip_says_why():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 10)
    feat = doc.timeline.features[0]
    feat.error = "wall thicker than the box"
    chip = FeatureNodeWidget(1, feat, True)
    assert chip.toolTip().startswith("Failed: wall thicker than the box")


# =========================================================================
# 2. Step Highlights & Browser Tree
# =========================================================================

def test_chamfer_step_shows_the_chamfer_ring_not_skins_over_the_thread():
    doc = Exporter.load_project(str(DATA_DIR / "jar_chamfer_step_highlight.omacad"))
    doc.timeline.recompute(doc)
    index = next(i for i, f in enumerate(doc.timeline.features) if f.name == "Chamfer 5")
    added, removed = doc.step_changes(index)
    shown = CadKernel.extract_render_mesh(added, min_thickness=STEP_CHANGE_MIN_THICKNESS)
    z = shown.vertices.reshape(-1, 3, 3).mean(axis=1)[:, 2]
    assert z.min() > 23.9
    ring = max(added.decompose(), key=lambda part: part.volume())
    ring_mesh = ring.to_mesh()
    v, f = np.asarray(ring_mesh.vert_properties)[:, :3], np.asarray(ring_mesh.tri_verts)
    areas = np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1) / 2
    assert abs(_area(shown) - areas[v[f].mean(axis=1)[:, 2] > 23.9].sum()) < 1e-3
    assert added.surface_area() - _area(shown) > 2000
    assert _area(CadKernel.extract_render_mesh(removed, min_thickness=STEP_CHANGE_MIN_THICKNESS)) == 0


def test_solid_material_is_drawn_in_full():
    doc = Exporter.load_project(str(DATA_DIR / "jar_chamfer_step_highlight.omacad"))
    doc.timeline.recompute(doc)
    for name in ("Jar", "Shell 1", "Move Lid (1)"):
        index = next(i for i, f in enumerate(doc.timeline.features) if f.name == name)
        for part in doc.step_changes(index):
            if part is not None:
                shown = CadKernel.extract_render_mesh(part, min_thickness=STEP_CHANGE_MIN_THICKNESS)
                assert abs(_area(shown) - part.surface_area()) < 1e-3 * part.surface_area(), name


def test_clicking_a_step_in_the_browser_does_not_rename_or_rebuild():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(3, 10)
    widget = BrowserTree(doc)
    widget.show()
    widget.tree.expandAll()
    app.processEvents()
    changes = []
    doc.change_listeners.append(lambda: changes.append(1))
    try:
        for fid in [f.feature_id for f in doc.timeline.features]:
            item = next(it for it, _ in widget._walk() if it.data(0, FEATURE_ROLE) == fid
                        and it.data(0, Qt.ItemDataRole.UserRole)[0] == "feature")
            widget.on_item_clicked(item, 0)
        assert changes == []
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_the_removed_half_leaves_no_empty_row_in_the_browser():
    app = QApplication.instance() or QApplication([])
    doc = Document()
    source = doc.add_box(40, 10, 10)
    left = source.manifold.bounding_box()[0]
    plane = doc.add_construction_plane(SketchPlane.create_named("YZ"), left + 30)
    split = doc.split_body(source.body_id, plane)
    doc.delete_body(split.result_body_id)
    doc.branch_object(split.feature_id, source.body_id, linked=False)
    tree = BrowserTree(doc)
    root = QTreeWidgetItem(["root"])
    add_histories(tree, root)
    objects = root.child(0)
    labels = [objects.child(i).text(0) for i in range(objects.childCount())]
    assert labels.count("Split Body 1 result") == 0
