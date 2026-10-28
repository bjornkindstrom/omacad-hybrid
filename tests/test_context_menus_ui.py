"""Right-click menus use the commands' names and offer what was missing: Delete Sketch and Emboss in the view,
Project in the sketch menu; Browser > Offset Plane starts from the plane or sketch that was right-clicked."""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QMenu

import omacad.ui.viewport.context_menu_mixin as menus
from omacad.ui.main_window import MainWindow


@pytest.fixture
def win(monkeypatch):
    QApplication.instance() or QApplication([])
    seen = []

    class SpyMenu(QMenu):
        def exec(self, *a, **k):
            texts = []
            for act in self.actions():
                texts.append(act.text())
                if act.menu():
                    texts += [s.text() for s in act.menu().actions()]
            seen.append(texts)
            return None
    monkeypatch.setattr(menus, "QMenu", SpyMenu)
    w = MainWindow()
    w.seen = seen
    return w


class _Ev:
    def position(self):
        return QPointF(10, 10)

    def globalPosition(self):
        return QPointF(10, 10)


def test_sketch_menu_offers_delete(win):
    sk = win.doc.start_sketch("XY")
    sk.add_rect((0, 0), (10, 10))
    win.doc.finish_sketch()
    win.viewport._show_sketch_menu(_Ev(), sk.sketch_id)
    assert any("Delete Sketch" in t for t in win.seen[-1])


def test_sketch_mode_menu_has_project_and_construction(win):
    win.doc.start_sketch("XY")
    win.viewport._show_general_menu(_Ev())
    texts = win.seen[-1]
    assert "Project" in texts and "Construction\tX" in texts
    assert "Line\tL" in texts and "Dimension\tD" in texts


def test_two_bodies_say_combine(win):
    win.doc.add_box(5, 5, 5)
    win.doc.add_box(5, 5, 5, translation=[10, 0, 0])
    win.doc.selected_body_ids = list(win.doc.bodies)
    win.viewport._show_general_menu(_Ev())
    assert any("Combine 2 Bodies" in t for t in win.seen[-1])


def test_browser_offset_plane_starts_from_the_clicked_plane(win):
    picked = []
    win.on_offset_base_picked = picked.append
    win.on_browser_offset_plane("plane", "XZ")
    assert picked and list(picked[0].normal) == list(win.doc.origin_planes["XZ"].normal)
