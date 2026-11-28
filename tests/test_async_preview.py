"""Big previews read their mesh on a worker thread; only the latest one is shown (P6)."""
import time

import manifold3d as m3d
import pytest

from omacad.model.document import Document


def _wait(app, cond, seconds=20.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def view():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    vp = Viewport3D(Document())
    vp.ASYNC_PREVIEW = True
    yield app, vp
    vp.deleteLater()


def test_a_big_preview_arrives_later_and_the_latest_one_wins(view):
    app, vp = view
    small = m3d.Manifold.cube([10, 10, 10])
    vp.set_preview(small)
    assert vp.preview_mesh is not None                         # small: drawn at once, as before
    shown = vp.preview_mesh
    big = [m3d.Manifold.sphere(r, 400) for r in (5.0, 9.0, 13.0)]
    for solid in big:                                          # a slider dragged through three values
        vp.set_preview(solid, "join")
    assert vp.preview_mesh is shown                            # the old preview stays until the new one is ready
    assert _wait(app, lambda: vp.preview_mesh is not shown)
    assert _wait(app, lambda: vp.preview_mesh.bounds_max[0] == pytest.approx(13.0, abs=0.05))
    app.processEvents()
    assert vp.preview_mesh.bounds_max[0] == pytest.approx(13.0, abs=0.05) and vp.preview_op == "join"


def test_clearing_drops_a_preview_still_on_its_way(view):
    app, vp = view
    vp.set_preview(m3d.Manifold.sphere(10.0, 400))
    vp.set_preview(None)
    assert vp.preview_mesh is None
    worker = vp._preview_worker()
    assert _wait(app, lambda: worker.thread is None)
    for _ in range(5):
        app.processEvents()
    assert vp.preview_mesh is None
