"""The extrude arrow is drawn a couple of mm off the surface, and dragging still gives the true distance."""
import os

import numpy as np
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
    v.resize(600, 400)
    yield v
    v.deleteLater()


@pytest.mark.parametrize("dist", [10.0, -10.0, 0.0])
def test_arrow_starts_off_the_surface_and_drag_returns_the_distance(view, dist):
    view.set_extrude_handle([0, 0, 0], [0, 0, 1], dist)
    lift = 2.0 if dist >= 0 else -2.0
    so = view._handle_geometry()[0]
    want = view.world_to_screen(np.array([0.0, 0.0, lift]))
    assert so[0] == pytest.approx(want[0], abs=0.01) and so[1] == pytest.approx(want[1], abs=0.01)
    tip_screen = view.world_to_screen(np.array([0.0, 0.0, dist + lift]))
    assert view._handle_value(*tip_screen) == pytest.approx(dist, abs=0.15)


def test_arrow_size_setting_scales_the_head(view):
    base = view._arrow_size()
    settings_mod.get_settings().set("arrow_size", 2.0)
    assert view._arrow_size() == pytest.approx(2 * base)
