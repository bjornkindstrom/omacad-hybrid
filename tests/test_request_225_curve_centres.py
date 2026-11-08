"""#225: circles and arcs show their centre point in the sketch, and the arc centre can be snapped to."""
from omacad.model.sketch import Sketch
from omacad.model.sketch_entities import SketchPlane
from omacad.model.sketch_snap import SketchSnapper


def test_arc_centre_is_a_snap_point():
    sk = Sketch("s", "Sketch", SketchPlane.create_named("XY"))
    sk.add_arc((10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    r = SketchSnapper.snap((0.3, 5.2), sk, None, snap_distance=0.5, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type != "ENDPOINT"
    sk2 = Sketch("s", "Sketch", SketchPlane.create_named("XY"))
    sk2.add_arc((30.0, 20.0), (20.0, 30.0), (10.0, 20.0))
    r = SketchSnapper.snap((20.2, 20.1), sk2, None, snap_distance=0.5, grid_step=0.0, enable_grid_snap=False)
    assert r.snap_type == "ENDPOINT" and abs(r.uv[0] - 20.0) < 1e-6 and abs(r.uv[1] - 20.0) < 1e-6


def test_overlay_draws_a_centre_dot_per_circle_and_arc():
    from PySide6.QtWidgets import QApplication
    from omacad.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.start_sketch_on_plane("XY")
    sk = win.doc.active_sketch
    sk.add_circle((5.0, 5.0), 3.0)
    sk.add_arc((30.0, 20.0), (20.0, 30.0), (10.0, 20.0))
    sk.add_line((0.0, 0.0), (10.0, 0.0))
    drawn = []

    class P:
        def __getattr__(self, name):
            return lambda *a, **k: drawn.append(a) if name == "drawEllipse" else None
    win.viewport.world_to_screen = lambda p: (float(p[0]), float(p[1]))
    win.viewport._draw_curve_centres(P(), sk)
    assert len(drawn) == 2
    win.close()
