"""Right-click on a sketch profile: a menu for that profile, not the face around it."""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402


def test_right_click_on_profile_selects_it_and_offers_extrude(monkeypatch):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication, QMenu
    QApplication.instance() or QApplication([])
    import omacad.ui.viewport as vp
    import omacad.ui.viewport.context_menu_mixin as menus

    seen = []

    class SpyMenu(QMenu):
        def exec(self, *a, **k):
            seen.append([x.text() for x in self.actions() if x.text()])
            return None
    monkeypatch.setattr(menus, "QMenu", SpyMenu)        # the menus are built in context_menu_mixin

    doc = Document()
    doc.add_box(40, 40, 10)
    sk = doc.start_sketch("XY")
    sk.add_circle((0, 0), 5)
    doc.finish_sketch()
    view = vp.Viewport3D(doc)
    view.resize(600, 400)
    view.azimuth, view.elevation = 0.0, 89.9
    x, y = view.world_to_screen(np.array([0.0, 0.0, 0.0]))
    key = view.pick_profile(x, y)
    assert key is not None

    class Ev:
        def __init__(self):
            self._p = QPointF(x, y)

        def position(self):
            return self._p

        def globalPosition(self):
            return self._p

    view._show_profile_menu(Ev(), key)
    assert doc.selected_profile == key
    assert any("Extrude this profile" in t for t in seen[0])
    assert view.ctx_face is None            # the face around it is not highlighted
