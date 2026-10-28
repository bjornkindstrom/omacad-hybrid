#!/usr/bin/env python3
"""Frame-exact demo: a big plate with a cylinder on it. Sketch one hexagon, cut it, Fill pattern packs the whole
face and keeps clear of the cylinder; then the polygon is changed to a pentagon and the pattern packs itself again.

    .venv/bin/python video/fill_take.py --out ~/Videos/omacad-fill-cylinder.mp4
    .venv/bin/python video/narrate.py video/fill/marks.json <that mp4> <narrated mp4> --lines video/lines_fill.json
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.model.sketch import SketchPlane
from omacad.ui.main_window import MainWindow
from take import Take, W, H

OUTDIR = os.path.join(ROOT, "video", "fill")
PLATE = (120.0, 80.0, 6.0)
CENTRE = (60.0, 40.0, 6.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "fill.mp4"))
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
        top = SketchPlane.from_face(np.array([0.0, 0, 1]), np.array([0.0, 0, PLATE[2]]))
        # scene set-up (not filmed): the plate and a cylinder standing on it
        doc.auto_include_edges = False
        doc.add_box(*PLATE)
        cs = doc.start_sketch_on_plane(top)
        cs.add_circle((80.0, 40.0), 12.0)
        doc.finish_sketch()
        doc.extrude_profile(cs.sketch_id, 0, 16.0, "join")
        vp.target = np.array(CENTRE, dtype=np.float32)
        vp.distance, vp.azimuth, vp.elevation = 190.0, 215.0, 38.0
        vp.update()

        t.say("A big plate with a cylinder standing on it")
        t.shoot(20)
        for _ in range(70):
            vp.azimuth += 0.9
            vp.update()
            t.shoot()

        # 1. sketch one hexagon on the top face
        t.say("Sketch one hexagon on the face")
        sk = doc.start_sketch_on_plane(top)
        vp.align_to_plane(top)
        vp.set_sketch_tool("POLYGON")
        vp.sketch_palette.spn_sides.setValue(6)
        vp.setFocus()
        t.fly(CENTRE, 175.0, vp.azimuth, 89.9, 45)
        t.move_event(t.uv_to_px((10.0, 10.0)))
        t.shoot(12)
        t.glide((20.0, 20.0), 22)
        t.press((20.0, 20.0))
        t.glide((25.0, 20.0), 18)
        t.press((25.0, 20.0))
        t.shoot(25)
        vp.set_sketch_tool("NONE")

        # 2. cut it through the plate
        t.say("Cut it through the plate")
        doc.finish_sketch()
        doc.extrude_profile(sk.sketch_id, 0, -7.0, "cut")
        ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
        t.fly(CENTRE, 175.0, 215.0, 40.0, 50)
        t.shoot(20)

        # 3. fill the face
        t.say("Fill the face: exact gaps, and a margin at the edge")
        doc.add_pattern([ext.feature_id], "fill", spacing1=2.0, spacing2=4.0, count1=0.0, mirror_mode="stagger")
        t.fly(CENTRE, 150.0, 235.0, 55.0, 45)
        t.shoot(25)

        # 4. it keeps clear of the cylinder
        t.say("It keeps clear of the cylinder")
        t.fly((80.0, 40.0, 8.0), 70.0, 260.0, 40.0, 50)
        for _ in range(60):
            vp.azimuth += 1.0
            vp.update()
            t.shoot()

        # 5. change the polygon: pentagons
        t.say("Change the polygon to a pentagon: the pattern packs itself again")
        t.fly(CENTRE, 160.0, 215.0, 55.0, 40)
        s1 = doc.edit_sketch(sk.sketch_id)
        before = s1.to_dict()
        s1.delete_entities([e.entity_id for e in s1.entities])
        s1.add_polygon((20.0, 20.0), (25.0, 20.0), 5)
        doc.record_sketch_change(s1, before)
        doc.finish_sketch()
        t.shoot(30)
        for _ in range(120):
            vp.azimuth += 0.9
            vp.update()
            t.shoot()
        t.shoot(20)
        t.encode(args.out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
