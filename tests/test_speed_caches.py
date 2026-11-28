"""Speed work that must not change a result: unique rows in weld_to, cached sketch chords in the viewport."""
import numpy as np
import pytest


def test_unique_pairs_is_numpys_unique_rows_exactly():
    from omacad.model.kernel import _unique_pairs
    rng = np.random.default_rng(7)
    for n, lo, hi in ((0, 0, 1), (1, 0, 1), (500, -20, 20), (50000, 0, 2 ** 62), (20000, 0, 30)):
        a, b = rng.integers(lo, hi, n), rng.integers(0, 40, n)
        ref = np.unique(np.stack([a, b], axis=1), axis=0) if n else np.empty((0, 2), dtype=np.int64)
        got = _unique_pairs(a, b)
        assert got.dtype == np.int64 and np.array_equal(got, ref.reshape(-1, 2))


def test_sketch_chords_are_reused_until_the_element_plane_or_smoothness_changes():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.model import quality
    from omacad.model.document import Document
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    c = sk.add_circle((0.0, 0.0), 5.0)
    first = vp._entity_world_lines(sk.plane, c)
    assert vp._entity_world_lines(sk.plane, c) is first                  # the same list: nothing rebuilt
    c.center = (10.0, 0.0)                                               # moved in place (a drag)
    moved = vp._entity_world_lines(sk.plane, c)
    assert moved is not first and moved[0] == pytest.approx(first[0] + 10.0)
    sk.plane.origin = sk.plane.origin + np.array([0.0, 0.0, 3.0], dtype=np.float32)
    lifted = vp._entity_world_lines(sk.plane, c)
    assert lifted[2] == pytest.approx(3.0)
    n = quality.circle_segments()
    quality.set_circle_segments(n * 2)
    try:
        assert len(vp._entity_world_lines(sk.plane, c)) == 2 * len(lifted)
    finally:
        quality.set_circle_segments(n)
    vp.deleteLater()


def test_brep_warm_up_loads_opencascade_on_a_worker_thread():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    import threading
    from PySide6.QtTest import QTest
    from omacad.model import brep
    if not brep.available():
        pytest.skip("OpenCascade bindings not installed")
    brep.warm_up()                                   # safe to call directly, and again
    started = []
    real = threading.Thread.start
    threading.Thread.start = lambda self: started.append(self.name) or real(self)
    try:
        brep.warm_up_later(0)
        QTest.qWait(50)
    finally:
        threading.Thread.start = real
    assert started == ["brep-warm-up"]
