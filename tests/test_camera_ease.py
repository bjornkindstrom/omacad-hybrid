"""View presets, Fit and Find glide: the camera state is final at once, only the drawn camera eases there."""
import time

import numpy as np
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui import settings
from omacad.ui.viewport import camera_ease
from omacad.ui.viewport.viewport import Viewport3D


def _view():
    app = QApplication.instance() or QApplication([])
    vp = Viewport3D(Document())
    vp.resize(400, 300)
    vp.show()
    app.processEvents()
    return app, vp


def test_view_preset_is_final_at_once_and_drawn_camera_glides(monkeypatch):
    settings.get_settings().set("camera_animation", True)
    app, vp = _view()
    vp.azimuth, vp.elevation = 45.0, 30.0
    vp.set_view("TOP")
    assert vp.elevation == 89.9 and vp.azimuth == 0.0                 # what code reads is final
    eased = vp.camera_ease.current(vp)
    assert eased is not None and 30.0 <= eased[3] < 89.9              # what is drawn starts where it was
    monkeypatch.setattr(camera_ease.time, "perf_counter", lambda: time.perf_counter_ns() / 1e9 + 10.0)
    assert vp.camera_ease.current(vp) is None                         # and lands on the final view
    vp.close()


def test_azimuth_takes_the_short_way_round_and_user_input_wins():
    settings.get_settings().set("camera_animation", True)
    app, vp = _view()
    vp.azimuth, vp.elevation = 170.0, 0.0
    before = camera_ease.state(vp)
    vp.azimuth = -170.0
    vp.camera_ease.start(vp, before)
    vp.camera_ease._start -= camera_ease.DURATION / 2
    mid = vp.camera_ease.current(vp)[2]
    assert 170.0 < mid < 190.0                                        # through 180, not back through 0
    vp.azimuth = 10.0                                                 # an orbit with the mouse
    assert vp.camera_ease.current(vp) is None
    vp.close()


def test_animation_off_in_settings_jumps():
    settings.get_settings().set("camera_animation", False)
    app, vp = _view()
    vp.zoom_to_points(np.array([[0, 0, 0], [100, 100, 100]], dtype=float))
    assert vp.camera_ease.current(vp) is None
    vp.close()
