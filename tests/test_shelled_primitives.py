"""Hollow primitives come from Shell Wall in the Box / Cylinder / Hexagon panels (no separate Shelled commands)."""
import math

import pytest
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

from omacad.model import quality
from omacad.ui.main_window import MainWindow
from omacad.ui.settings import get_settings


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("kind", ["box", "cylinder"])
def test_shell_wall_in_the_panel_volume_and_undo(app, kind):
    w = MainWindow()
    getattr(w, "prompt_"+kind)()
    dlg = w.viewport.primitive_handles.dialog
    assert dlg.spn_wall.value() == 0
    assert w.viewport.preview_mesh is not None
    assert not w.doc.bodies
    dlg.spn_wall.setValue(4)
    dlg.accept()
    feat = w.doc.timeline.features[-1]
    assert feat.wall_thickness == 4
    body = next(iter(w.doc.bodies.values()))
    if kind == "box":
        expected = 50*50*25 - 42*42*21
    else:
        n = quality.circle_segments()
        expected = n/2 * math.sin(2*math.pi/n) * (20**2*40 - 16**2*36)
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    w.doc.undo()
    assert not w.doc.bodies
    w.doc.redo()
    assert next(iter(w.doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    w.close()


@pytest.mark.parametrize("grouped", [True, False])
def test_no_separate_shelled_commands_in_either_ribbon_layout(app, grouped):
    get_settings().set("group_primitives", grouped)
    w = MainWindow()
    texts = [a.text() for m in w.ribbon.findChildren(QMenu) for a in m.actions()]
    texts += [b.text() for b in w.ribbon.findChildren(QToolButton)]
    assert "Prism" in texts
    assert not [t for t in texts if t.startswith("Shelled")]
    w.close()
