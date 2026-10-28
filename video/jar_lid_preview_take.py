#!/usr/bin/env python3
"""Silent product preview of the threaded jar and its separately printed lid.

    .venv/bin/python video/jar_lid_preview_take.py --out ~/Videos/omacad-jar-lid-preview.mp4
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.model.jar import JarSpec
from omacad.ui.main_window import MainWindow
from take import Take, W, H

OUTDIR = os.path.join(ROOT, "video", "jar_lid_preview")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.expanduser("~/Videos/omacad-jar-lid-preview.mp4"))
    args = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    log_path = os.path.join(OUTDIR, "render.log")
    log_file = open(log_path, "w", buffering=1)
    sys.stdout = sys.stderr = log_file

    def log_step(message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

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
            started = time.monotonic()
            spec = JarSpec()
            # Match the dialog's preview: scratch document, thread clearance omitted for speed.
            spec.tolerance = 0.0
            log_step("Building jar and lid preview")
            scratch = Document()
            ids = scratch.add_jar(spec)
            log_step(f"Geometry ready in {time.monotonic() - started:.1f}s")
            solids = scratch.bodies[ids["jar"]].manifold + scratch.bodies[ids["lid"]].manifold

            vp = win.viewport
            vp.set_preview(solids, "new_body")
            vp.target = np.array([25.0, 18.0, 24.0], dtype=np.float32)
            vp.distance = 122.0
            vp.azimuth = 35.0
            vp.elevation = 28.0
            vp.update()
            log_step("Preview mesh ready; rendering frames")

            t = Take(app, win, OUTDIR)
            t.cursor = t.cursor.__class__(-50, -50)
            t.caption = "Jar with Lid · threaded preview"
            t.shoot(45)

            # Slow, even orbit to reveal the neck thread and the upside-down lid interior.
            for _ in range(300):
                vp.azimuth += 0.45
                vp.update()
                t.shoot()
            t.caption = "Ø40 × 40 mm · 4 mm pitch"
            t.shoot(45)
            t.encode(args.out)
            log_step(f"Video saved in {time.monotonic() - started:.1f}s")
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            log_file.flush()
            log_file.close()
            app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
