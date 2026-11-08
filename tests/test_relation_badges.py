"""SolidWorks-style relation boxes: a two-element relation shows on both elements, click either to remove it."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.model.document import Document  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402


@pytest.fixture
def view(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    v = Viewport3D(Document())
    v.resize(800, 600)
    return v


def _badges(view):
    from PySide6.QtGui import QImage, QPainter
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    view.draw_constraint_badges(p)
    p.end()
    return view.constraint_badges


def test_parallel_shows_on_both_lines(view):
    sk = view.doc.start_sketch("XY")
    a = sk.add_line((0.0, 0.0), (40.0, 0.0))
    b = sk.add_line((0.0, 20.0), (40.0, 25.0))
    view.align_to_plane(sk.plane)
    view.doc.add_constraints(sk.sketch_id, [("PARALLEL", [a.entity_id, b.entity_id], [])])
    view.sketch_palette.chk_show_constraints.setChecked(True)
    cid = sk.constraints[0].cid
    assert [c for _r, c in _badges(view)] == [cid, cid]


def test_one_line_relation_has_one_box(view):
    sk = view.doc.start_sketch("XY")
    a = sk.add_line((0.0, 0.0), (40.0, 1.0))
    view.align_to_plane(sk.plane)
    view.doc.add_constraints(sk.sketch_id, [("HORIZONTAL", [a.entity_id], [])])
    view.sketch_palette.chk_show_constraints.setChecked(True)
    assert len(_badges(view)) == 1
