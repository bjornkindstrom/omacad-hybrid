"""Right-click with two bodies selected offers Join (one undo step); the thread dialog has a short lead-in."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.kernel import CadKernel
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    return MainWindow()


def _two_boxes(doc):
    doc.add_box(10, 10, 10)
    a = next(iter(doc.bodies))
    doc.add_box(10, 10, 10)
    b = [k for k in doc.bodies if k != a][0]
    doc.move_body(b, dx=5)
    return a, b


def test_join_bodies_is_one_undo_step_and_unions(win):
    doc = win.doc
    a, b = _two_boxes(doc)
    v = doc.bodies[a].manifold.volume() + doc.bodies[b].manifold.volume() - 5 * 10 * 10   # they overlap 5x10x10
    doc.select_body(a)
    doc.select_body(b, multi=True)
    body = doc.join_bodies(doc.selected_body_ids)
    assert len(doc.bodies) == 1 and abs(body.manifold.volume() - v) < 1e-6
    doc.undo()
    assert len(doc.bodies) == 2


def test_join_entry_in_the_context_menu_only_with_two_selected(win):
    doc = win.doc
    a, b = _two_boxes(doc)
    vp = win.viewport
    seen = []
    vp.join_bodies_requested.connect(seen.append)

    class Menu:                                    # records what a menu would get
        def __init__(self):
            self.actions = []
        def addAction(self, a):
            self.actions.append(a)
        def addSeparator(self): pass
        def addMenu(self, *_):
            return Menu()

    from omacad.ui import theme
    labels = []
    real = theme.action_with_icon
    theme.action_with_icon = lambda menu, text: (labels.append(text), real(menu, text))[1]
    try:
        from PySide6.QtWidgets import QMenu
        doc.select_body(a)
        vp._add_history_and_view(QMenu(), {}, False)
        assert not any("Combine" in t for t in labels)
        doc.select_body(b, multi=True)
        acts = {}
        vp._add_history_and_view(QMenu(), acts, False)
        assert any("Combine 2 Bodies" in t for t in labels)      # one name with the ribbon
        kind, ids = next(v for v in acts.values() if v[0] == "join_bodies")
    finally:
        theme.action_with_icon = real
    vp._run_general(kind, ids)
    assert seen == [[a, b]]
    win.on_join_bodies(ids)
    assert len(doc.bodies) == 1


def test_short_lead_in_is_shorter():
    full = CadKernel.create_thread(20, 2.5, 10, profile="round", include_core=False, taper_turns=0.75)
    short = CadKernel.create_thread(20, 2.5, 10, profile="round", include_core=False, taper_turns=0.3)
    none = CadKernel.create_thread(20, 2.5, 10, profile="round", include_core=False, taper_lead_in=False)
    assert full.volume() < short.volume() < none.volume()          # the shorter the fade, the more thread


def test_thread_dialog_offers_short_lead_in(win):
    from omacad.ui.dialogs import ThreadDialog
    dlg = ThreadDialog(win.doc, win)
    labels = [dlg.cmb_taper.itemText(i) for i in range(dlg.cmb_taper.count())]
    assert any("short" in t for t in labels)
    v = dlg.get_values()            # the short lead-in is the default (it works best for coils)
    assert v["taper_lead_in"] is True and abs(v["taper_turns"] - 0.3) < 1e-9
    dlg.set_lead_in(True, 0.75)
    assert dlg.get_values()["taper_turns"] == 0.75
    dlg.set_lead_in(False, 0.75)
    assert dlg.get_values()["taper_lead_in"] is False
