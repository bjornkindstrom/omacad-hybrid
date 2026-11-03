"""Requests #157 (Primitives as a submenu), #158 (move a whole group), #168 (two fields per row in Star Brackets)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui import commands

_app = QApplication.instance() or QApplication([])


def test_primitives_is_a_submenu_in_the_create_menu():
    create = dict(commands.MENUS)["Create"]
    subs = [e for e in create if isinstance(e, tuple)]
    assert subs and subs[0][0] == "primitives"
    assert "box" not in create and "box_row" in subs[0][4]


def _bounds(doc, bid):
    m = doc.bodies[bid].manifold.to_mesh().vert_properties[:, :3]
    return m.min(axis=0)


def test_move_object_group_moves_every_body_in_one_undo_step():
    doc = Document()
    doc.add_box_row(count=2, length=40.0, width=30.0, height=20.0, has_lid=False)
    gid = doc.object_groups[0]["id"]
    ids = doc.object_group_body_ids(gid)
    assert len(ids) >= 2
    before = {b: _bounds(doc, b) for b in ids}
    assert doc.move_object_group(gid, 5.0, -3.0, 2.0) == len(ids)
    for b in ids:
        assert np.allclose(_bounds(doc, b) - before[b], [5.0, -3.0, 2.0], atol=1e-6)
    doc.undo()
    for b in ids:
        assert np.allclose(_bounds(doc, b), before[b], atol=1e-6)


def test_star_brackets_dialog_pairs_fields_side_by_side():
    from omacad.ui.dialogs.primitives_dlg import StarBracketsDialog
    d = StarBracketsDialog()
    d.show()
    _app.processEvents()
    a = d.spn_tube_length.mapTo(d, d.spn_tube_length.rect().topLeft())
    b = d.spn_tube_size.mapTo(d, d.spn_tube_size.rect().topLeft())
    assert abs(a.y() - b.y()) < 3 and b.x() > a.x() + 50


def test_fillet_green_check_button_applies_request_160():
    """Request #160: a green check button near the arrow applies the fillet without going to OK."""
    from PySide6.QtWidgets import QToolButton
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    body = win.doc.add_box(30.0, 20.0, 10.0)
    win.prompt_round_edges("fillet")
    btn = next(b for b in win.viewport.findChildren(QToolButton) if b.text() == "✓")
    top = next(e for e in body.edges if hasattr(e, "p0") and abs(e.p0[2] - 10.0) < 1e-6 and abs(e.p1[2] - 10.0) < 1e-6)
    win.viewport.selected_edges = [top]
    win.viewport.edges_selection_changed.emit()
    _app.processEvents()
    import time
    t = time.time()
    while not btn.isVisible() and time.time() - t < 2:
        _app.processEvents()
    assert btn.isVisible()
    n = len(win.doc.timeline.features)
    btn.click()
    _app.processEvents()
    assert len(win.doc.timeline.features) == n + 1 and win.doc.timeline.features[-1].feature_type == "fillet"


def test_primitive_with_viewport_handles_gets_green_check_button():
    """The green check also appears for primitives that can be shaped with handles in the viewport."""
    import time
    from PySide6.QtWidgets import QToolButton
    from omacad.ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    n = len(win.doc.timeline.features)
    win.prompt_box()
    btn = next(b for b in win.viewport.findChildren(QToolButton) if b.text() == "✓")
    t = time.time()
    while not btn.isVisible() and time.time() - t < 3:
        _app.processEvents()
    assert btn.isVisible()
    btn.click()
    _app.processEvents()
    assert len(win.doc.timeline.features) > n
