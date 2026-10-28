#!/usr/bin/env python3
"""A part turning smoothly while the Omarchy theme changes again and again: the whole window (ribbon, tree,
timeline, 3D view) changes colour.

    .venv/bin/python video/theme_take.py --out ~/Videos/omacad-theme-spin.mp4

Frame-exact: the camera is a pure function of the frame number, so the rotation never stutters however long a
theme switch takes. Each switch is cross-faded over a few frames. The themes are applied to the app only
(theme.COLORS_FILE + theme.refresh()); your real Omarchy theme is never touched. Real display needed; the window goes fullscreen while it renders (about 4 minutes), so
leave the workspace alone or switch to another one.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPainter, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.ui import theme
from omacad.ui.main_window import MainWindow

THEMES = ["tokyo-night", "catppuccin-latte", "gruvbox", "osaka-jade", "flexoki-light", "rose-pine", "nord", "white", "ristretto", "kanagawa"]   # dark and light mixed, for contrast
FPS, SECONDS, HOLD, FADE = 30, 20, 54, 7      # frames per theme and cross-fade length
OUTDIR = os.path.join(ROOT, "video", "theme")
THEME_DIR = Path("/usr/share/omarchy/themes")


def apply(name, app):
    theme.COLORS_FILE = THEME_DIR / name / "colors.toml"
    theme.refresh()
    for _ in range(4):
        app.processEvents()


def build_part(doc):
    """A plate with a chamfered hole mirrored to the four corners and a hexagon fill in the middle."""
    from omacad.model.sketch import SketchPlane
    doc.auto_include_edges = False
    doc.add_box(80.0, 50.0, 8.0)
    top = SketchPlane.from_face(np.array([0.0, 0, 1]), np.array([0.0, 0, 8.0]))
    sk = doc.start_sketch_on_plane(top)
    sk.add_circle((10.0, 10.0), 3.0)
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, -9.0, "cut")
    cut = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    body = next(iter(doc.bodies.values()))
    edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.2]
    ch = doc.add_fillet(edges, 1.0, "chamfer")
    doc.add_pattern([cut.feature_id, ch.feature_id], "mirror", mirror_mode="xy")
    hs = doc.start_sketch_on_plane(top)
    hs.add_polygon((40.0, 25.0), (44.0, 25.0), 6)
    doc.finish_sketch()
    doc.extrude_profile(hs.sketch_id, 0, -9.0, "cut")
    hexcut = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([hexcut.feature_id], "fill", spacing1=2.0, spacing2=14.0, count1=0.0, mirror_mode="stagger")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "theme.mp4"))
    ap.add_argument("--seconds", type=float, default=SECONDS)
    args = ap.parse_args()
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.showFullScreen()    # a tiled window is far too small; fullscreen gives the whole screen for the take

    def run():
        try:
            _run()
        except Exception:
            import traceback
            traceback.print_exc()
            app.quit()

    def _run():
        for _ in range(10):
            app.processEvents()
        vp, doc = win.viewport, win.doc
        original = theme.COLORS_FILE
        shutil.rmtree(OUTDIR, ignore_errors=True)
        os.makedirs(OUTDIR)
        apply(THEMES[0], app)
        build_part(doc)
        vp.target = np.array([40.0, 25.0, 4.0], dtype=np.float32)
        vp.distance = 135.0
        n = int(args.seconds * FPS)
        print("window", win.width(), win.height(), "frames", n)
        shown = THEMES[0]

        def grab(az, el, name):
            nonlocal shown
            if name != shown:
                apply(name, app)
                shown = name
            vp.azimuth, vp.elevation = az, el
            vp.repaint()
            app.processEvents()
            return win.grab().toImage()

        try:
            for i in range(n):
                t = i / n
                az = 20.0 + 360.0 * 1.0 * t                      # one smooth turn, constant speed
                el = 30.0 + 8.0 * math.sin(2 * math.pi * t * 2)   # gentle nodding
                k, f = divmod(i, HOLD)
                cur, nxt = THEMES[k % len(THEMES)], THEMES[(k + 1) % len(THEMES)]
                img = grab(az, el, cur)
                if f >= HOLD - FADE:                              # cross-fade into the next theme
                    a = (f - (HOLD - FADE) + 1) / (FADE + 1)
                    other = grab(az, el, nxt)
                    p = QPainter(img)
                    p.setOpacity(a * a * (3 - 2 * a))
                    p.drawImage(0, 0, other)
                    p.end()
                img.save(os.path.join(OUTDIR, f"f{i:05d}.png"))
        finally:
            theme.COLORS_FILE = original
            theme.refresh()
        out = os.path.abspath(os.path.expanduser(args.out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(OUTDIR, "f%05d.png"),
                        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", out], check=True)
        print("Saved", out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
