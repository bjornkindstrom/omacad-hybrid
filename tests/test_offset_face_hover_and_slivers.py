"""Request #32: offset face on a cylinder left slivers behind, and the surface must light up when it can be clicked."""
import math
import os
import time
from pathlib import Path

import numpy as np
import pytest

from omacad.io.exporter import Exporter


def test_cylinder_offset_leaves_one_clean_body():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "offset_face_cylinder_slivers.omacad"))
    top = doc.bodies["body_cylinder_1"].manifold      # the upper part after the split, 19 mm radius after the offset
    assert len(top.decompose()) == 1                  # no hair-thin pieces left of the old wall
    n = 96
    area = 0.5 * n * 19.0 ** 2 * math.sin(2 * math.pi / n)
    assert abs(top.volume() - area * 10.0) / (area * 10.0) < 1e-3


@pytest.fixture
def viewport(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.model.document import Document
    from omacad.ui import settings as settings_mod
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.viewport import Viewport3D
    d = Document()
    d.add_cylinder(10, 20)
    v = Viewport3D(d)
    v.resize(900, 700)
    v.begin_plane_pick("offset_face")
    return v


def _hover(v, world):
    v._hover_patch_time = 0.0
    x, y = v.world_to_screen(np.asarray(world, dtype=float))
    v._update_offset_hover(x, y)
    return x, y


def test_cylinder_wall_lights_up_and_picks(viewport):
    v = viewport
    picked = []
    v.offset_face_picked.connect(lambda ref, bid: picked.append(ref))
    x, y = _hover(v, (7.0, 7.0, 10.0))               # on the wall, facing the default camera
    assert v.hover_patch is not None and len(v.hover_patch) > 24 and v.hover_plane is None
    v._offset_face_click(x, y)
    assert picked and picked[0]["kind"] == "cylinder"


def test_flat_face_lights_up_as_a_face(viewport):
    v = viewport
    _hover(v, (0.0, 0.0, 20.0))                      # the top
    assert v.hover_patch is None and v.hover_plane is not None and v.hover_plane[0] == "face"
