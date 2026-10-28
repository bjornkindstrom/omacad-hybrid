"""A wrong dimension can be deleted: from the browser, with Del, or by right-clicking its badge (#101)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402

from omacad.model.document import Document  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402


def _sketch_with_dim():
    doc = Document()
    sk = doc.start_sketch("XY")
    line = sk.add_line((0, 0), (10, 0))
    assert doc.add_dimension_constraint(sk.sketch_id, "LENGTH", line.entity_id, 10.0)
    return doc, sk, sk.dimensions[-1].dim_id


def test_remove_dimension_is_one_undo_step():
    doc, sk, dim_id = _sketch_with_dim()
    n = len(sk.dimensions)
    assert doc.remove_dimension(sk.sketch_id, dim_id)
    assert len(sk.dimensions) == n - 1 and all(d.dim_id != dim_id for d in sk.dimensions)
    assert not doc.remove_dimension(sk.sketch_id, dim_id)
    doc.undo()
    sk = doc.sketches[sk.sketch_id]
    assert any(d.dim_id == dim_id for d in sk.dimensions)


@pytest.fixture
def view(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    doc, sk, dim_id = _sketch_with_dim()
    v = Viewport3D(doc)
    v.resize(800, 600)
    return v, sk, dim_id


def test_del_deletes_the_dimension_picked_in_the_browser(view):
    v, sk, dim_id = view
    v.show_dimension_entities(sk.sketch_id, dim_id)
    v.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier))
    assert all(d.dim_id != dim_id for d in v.doc.sketches[sk.sketch_id].dimensions)
    assert v.picked_dim is None


def test_right_click_on_badge_offers_delete(view, monkeypatch):
    import omacad.ui.viewport.sketch_dimensions_mixin as mod
    v, sk, dim_id = view
    v.dim_badges = {dim_id: (QRectF(100, 100, 40, 20), sk.sketch_id, dim_id, 10.0)}
    assert v.dim_badge_at(110, 110) == (sk.sketch_id, dim_id) and v.dim_badge_at(10, 10) is None

    class Menu(mod.QMenu):
        def exec(self, *a):
            return next(a for a in self.actions() if "Delete" in a.text())
    monkeypatch.setattr(mod, "QMenu", Menu)
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        ev = QMouseEvent(kind, QPointF(110, 110), QPointF(110, 110), Qt.MouseButton.RightButton,
                         Qt.MouseButton.RightButton if kind == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        (v.mousePressEvent if kind == QEvent.Type.MouseButtonPress else v.mouseReleaseEvent)(ev)
    assert all(d.dim_id != dim_id for d in v.doc.sketches[sk.sketch_id].dimensions)
