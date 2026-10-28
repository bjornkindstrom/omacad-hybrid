#!/usr/bin/env python3
"""Frame-exact demo of the Smart Circle tool: type a diameter, then the distance to the nearest
vertical and horizontal line, Enter after each. Two circles are placed in a 60 x 40 mm plate.

    .venv/bin/python video/smart_circle_take.py                 # -> video/smart_circle/smart_circle.mp4
    .venv/bin/python video/smart_circle_take.py --out ~/Videos/omacad-smart-circle.mp4

Same approach as pan_take.py: every frame is rendered with grabFramebuffer(), no screen recorder, so the
result is identical on every run. The cursor and the captions are drawn onto the frames here (the real
cursor is not captured). Real display (Wayland) needed, the viewport needs a GL context.
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

PLATE = (60.0, 40.0)
OUTDIR = os.path.join(ROOT, "video", "smart_circle")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "smart_circle.mp4"))
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
    win.viewport.show_grid = True

    def run():
        t = Take(app, win, OUTDIR)
        vp, doc = win.viewport, win.doc
        sk = doc.start_sketch("XY")
        before = sk.to_dict()
        sk.add_rect((0.0, 0.0), PLATE)
        doc.record_sketch_change(sk, before)
        vp.align_to_plane(sk.plane)
        vp.target = np.array([PLATE[0] / 2, PLATE[1] / 2, 0.0], dtype=np.float32)
        vp.distance = 80.0
        vp.update()
        t.shoot(20)
        t.say("Smart Circle: place a circle with numbers")
        t.shoot(30)
        vp.set_sketch_tool("SMART_CIRCLE")
        vp.setFocus()
        t.move_event(t.uv_to_px((44.0, 14.0)))
        t.shoot(20)
        t.circle("8", (50.0, 20.0), "10", (40.0, 36.0), "6")        # right wall 10 mm, top wall 6 mm
        t.say("The circle keeps its dimensions: change one and it follows")
        t.glide((24.0, 12.0))
        t.shoot(20)
        t.circle("6", (3.0, 20.0), "12", (20.0, 3.0), "9")          # left wall 12 mm, bottom wall 9 mm
        vp.set_sketch_tool("NONE")
        t.say("Done: every circle is fully dimensioned")
        t.shoot(60)
        # finish the sketch and cut the plate so the result shows
        doc.finish_sketch()
        doc.extrude_profile(sk.sketch_id, 0, 8.0)
        vp.set_view("HOME")
        vp.zoom_fit()
        t.say("Extrude: the circles become holes")
        for i in range(75):
            vp.azimuth += 1.6
            vp.update()
            t.cursor = QPointF(-50, -50)
            t.shoot()
        t.shoot(15)
        t.encode(args.out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
