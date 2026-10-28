#!/usr/bin/env python3
"""Frame-exact demo: draw a rounded rectangle, place a hole with Smart Circle, extrude, chamfer the hole and
copy it to all four corners with Mirror.

    .venv/bin/python video/plate_take.py --out ~/Videos/omacad-plate-holes.mp4

Uses video/take.py (frame-exact capture, cursor and captions drawn on the frames). Real display needed.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.ui.main_window import MainWindow
from take import Take, W, H

OUTDIR = os.path.join(ROOT, "video", "plate")
HOLE = (8.0, 8.0)       # hole centre from the corner: 8 mm from each wall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "plate.mp4"))
    args = ap.parse_args()
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1600, 900)
    win.show()
    win.viewport.setFixedSize(W, H)

    def run():
        try:
            _run()
        except Exception:
            import traceback
            traceback.print_exc()
            app.quit()

    def _run():
        t = Take(app, win, OUTDIR)
        vp, doc = win.viewport, win.doc
        sk = doc.start_sketch("XY")
        vp.align_to_plane(sk.plane)
        vp.target = np.array([30.0, 20.0, 0.0], dtype=np.float32)
        vp.distance = 80.0
        vp.update()
        t.shoot(20)

        # 1. rounded rectangle: click the corner, type width, height, radius
        t.say("Rounded rectangle: width, height, radius")
        vp.set_sketch_tool("ROUNDED_RECT")
        vp.setFocus()
        t.move_event(t.uv_to_px((-10.0, -8.0)))
        t.shoot(10)
        t.glide((0.0, 0.0), 20)
        t.press((0.0, 0.0))
        t.glide((40.0, 25.0), 25)
        t.type_number("60")
        t.shoot(8)
        t.enter(10)
        t.type_number("40")
        t.shoot(8)
        t.enter(10)
        t.type_number("8")
        t.shoot(14)
        t.enter(30)

        # 2. a hole with Smart Circle
        t.say("Smart Circle: diameter, then distance to a wall each way")
        vp.set_sketch_tool("SMART_CIRCLE")
        vp.setFocus()
        t.glide((14.0, 14.0), 24)
        t.circle("6", (3.0, 12.0), "8", (12.0, 3.0), "8")
        vp.set_sketch_tool("NONE")
        t.shoot(20)

        # 3. extrude, the circle becomes a hole
        t.say("Extrude: the circle becomes a hole")
        doc.finish_sketch()
        doc.extrude_profile(sk.sketch_id, 0, 8.0)
        ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
        t.fly((8.0, 8.0, 8.0), 55.0, 30.0, 45.0, 60)
        t.shoot(10)

        # 4. chamfer the hole's top edge
        t.say("Chamfer the edge of the hole")
        body = next(iter(doc.bodies.values()))
        edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.2]
        ch = doc.add_fillet(edges, 1.0, "chamfer")
        t.fly((8.0, 8.0, 8.0), 28.0, 40.0, 50.0, 40)
        t.shoot(40)

        # 5. mirror the hole with its chamfer to all four corners
        t.say("Mirror: the hole and its chamfer, copied to all four corners")
        doc.add_pattern([ext.feature_id, ch.feature_id], "mirror", mirror_mode="xy")
        t.fly((30.0, 20.0, 4.0), 95.0, 30.0, 45.0, 45)
        t.shoot(20)
        for _ in range(90):
            vp.azimuth += 1.2
            vp.update()
            t.shoot()
        t.shoot(20)
        t.encode(args.out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
