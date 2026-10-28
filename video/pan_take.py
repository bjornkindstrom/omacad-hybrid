#!/usr/bin/env python3
"""Frame-exact camera pan over the finished demo part, one take per Omarchy theme.

The camera is a pure function of the frame number and every frame is rendered with
`QWidget.grab()` (no screen recording, no wall-clock timing), so every take has the identical
motion and the takes line up frame for frame: cut or cross-dissolve between them at any point.

    .venv/bin/python video/pan_take.py --themes tokyo-night,catppuccin,gruvbox,nord,rose-pine
    .venv/bin/python video/pan_take.py --themes current --seconds 6 --fps 30

Output: video/pan/<theme>/frame_0000.png ... and video/pan/<theme>.mp4 (needs ffmpeg).
Run on the real display (Wayland), like record_demo.py. Your theme is restored at the end.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.ui import theme
from omacad.ui.main_window import MainWindow
from record_demo import Demo

# The pan, edit these to taste. Keys are (azimuth, elevation, distance factor, target shift x/y/z in
# units of the part's size) at t=0 and t=1; motion is eased with smootherstep.
START = dict(az=20.0, el=16.0, dist=1.15, shift=(-0.25, 0.0, 0.0))
END = dict(az=115.0, el=34.0, dist=0.80, shift=(0.20, 0.0, 0.05))


def smootherstep(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def camera_at(t: float, base_target, base_distance, size):
    """Pure function: same t, same camera."""
    k = smootherstep(min(1.0, max(0.0, t)))
    lerp = lambda a, b: a + (b - a) * k
    shift = np.array([lerp(a, b) for a, b in zip(START["shift"], END["shift"])]) * size
    return (lerp(START["az"], END["az"]), lerp(START["el"], END["el"]),
            base_distance * lerp(START["dist"], END["dist"]), np.asarray(base_target, dtype=np.float32) + shift)


def wait(ms: int):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def set_theme(win: MainWindow, name: str):
    """Switch the Omarchy theme and wait until the app has reloaded its colours."""
    if name == "current":
        return
    loop = QEventLoop()
    win.theme_watcher.changed.connect(loop.quit)
    QTimer.singleShot(8000, loop.quit)       # give up after 8 s
    subprocess.run(["omarchy-theme-set", name], check=True)
    loop.exec()
    win.theme_watcher.changed.disconnect(loop.quit)
    wait(1500)                               # let every widget repaint


def build_part(win: MainWindow) -> Demo:
    demo = Demo(win, 1.0, lambda: None)
    demo.s2_sketch()
    demo.s3_extrude()
    demo.spin.stop()
    demo.s4_hole()
    demo.s4b_mirror()
    demo.s4c_fill()
    demo.caption.hide()
    demo.win.viewport.zoom_fit()
    return demo


def render_take(win, base, frames, outdir):
    os.makedirs(outdir, exist_ok=True)
    vp = win.viewport
    for i in range(frames):
        az, el, dist, target = camera_at(i / (frames - 1), *base)
        vp.azimuth, vp.elevation, vp.distance, vp.target = az, el, dist, target
        vp.repaint()
        QApplication.processEvents()
        win.grab().save(os.path.join(outdir, f"frame_{i:04d}.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--themes", default="current", help="comma separated Omarchy theme names, or 'current'")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--fps", type=int, default=30)
    args = ap.parse_args()

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    win = MainWindow()
    win.setFixedSize(1920, 1080)             # identical frames in every take
    win.show()
    wait(2000)

    try:
        orig = theme.NAME_FILE.read_text().strip()
    except OSError:
        orig = None
    build_part(win)
    wait(500)
    vp = win.viewport
    base_target, base_distance = np.array(vp.target, dtype=np.float32), float(vp.distance)
    b = [bd.render_mesh for bd in win.doc.bodies.values() if bd.render_mesh is not None]
    size = float(max(np.linalg.norm(m.bounds_max - m.bounds_min) for m in b)) if b else 100.0
    frames = max(2, int(args.seconds * args.fps))

    outroot = os.path.join(ROOT, "video", "pan")
    for name in [t.strip() for t in args.themes.split(",") if t.strip()]:
        set_theme(win, name)
        label = name if name != "current" else (orig or "current")
        outdir = os.path.join(outroot, label)
        print(f"Rendering {frames} frames for theme {label} ...")
        render_take(win, (base_target, base_distance, size), frames, outdir)
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(args.fps),
                            "-i", os.path.join(outdir, "frame_%04d.png"), "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "14", os.path.join(outroot, f"{label}.mp4")], check=True)
    if orig:
        set_theme(win, orig.lower().replace(" ", "-"))
    print("Done:", outroot)
    app.quit()


if __name__ == "__main__":
    main()
