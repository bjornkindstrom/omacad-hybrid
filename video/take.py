"""Shared frame-exact capture helper for the video takes: renders the viewport frame by frame (no screen
recorder), draws cursor and captions on the frames and drives the viewport through its own event handlers."""
import os
import shutil
import subprocess

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPolygonF

W, H, FPS = 1280, 720, 30


class Take:
    def __init__(self, app, win, outdir, window=False):
        """window=True films the whole window (ribbon, tree, timeline) instead of just the 3D view; static
        waits (shoot(n)) then render one frame and copy it, which saves a lot of time."""
        self.outdir = outdir
        self.window = window
        self.scene_active = False
        self.marks = []
        self.app, self.win, self.vp = app, win, win.viewport
        self.frame, self.caption, self.cursor = 0, "", QPointF(W * 0.62, H * 0.75)
        shutil.rmtree(outdir, ignore_errors=True)
        os.makedirs(outdir)

    # --- rendering ---
    def shoot(self, n: int = 1):
        if self.window and n > 1:
            self._render()
            self.hold(n - 1)
            return
        for _ in range(n):
            self._render()

    def hold(self, n):
        """n more copies of the last frame."""
        last = os.path.join(self.outdir, f"f{self.frame - 1:05d}.png")
        for _ in range(n):
            dest = os.path.join(self.outdir, f"f{self.frame:05d}.png")
            try:
                os.link(last, dest)
            except OSError:
                shutil.copyfile(last, dest)
            self.frame += 1

    def _grab(self):
        for _ in range(3):
            self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)   # old timeline chips etc. are gone before the grab
        if not self.window:
            return self.vp.grabFramebuffer()
        # win.grab() leaves out what the 3D view paints itself (dimension badges, tool tips, ViewCube, the
        # Orbit/Pan/Fit bar), so the view is grabbed on its own and drawn over its place in the window picture
        self._keep_fullscreen()
        img = self.win.grab().toImage()
        fb = self.vp.grabFramebuffer()
        off = self.vp.mapTo(self.win, QPoint(0, 0))
        p = QPainter(img)
        p.drawImage(QRect(off.x(), off.y(), self.vp.width(), self.vp.height()), fb)   # fb is in device pixels (1.25x here)
        p.end()
        return img

    def _keep_fullscreen(self):
        """The compositor can take fullscreen away mid-take (another window, a workspace switch); the window then
        shrinks and every frame after it is small. Ask for fullscreen again and stop if the size still changes."""
        size = self.win.size()
        self._size = getattr(self, "_size", size)
        for _ in range(40):
            if self.win.size() == self._size:
                return
            self.win.showFullScreen()
            for _ in range(5):
                self.app.processEvents()
        raise RuntimeError(f"window is {self.win.width()}x{self.win.height()}, was {self._size.width()}x{self._size.height()}: fullscreen was lost")

    def _render(self):
        self._finish(self._grab())

    def _finish(self, img):
        """Draw caption and cursor on a grabbed image and save it as the next frame."""
        if self.window:
            off = self.vp.mapTo(self.win, QPoint(0, 0))
            vw, vh = self.vp.width(), self.vp.height()
        else:
            off, vw, vh = QPoint(0, 0), W, H
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.caption:
            p.setFont(QFont("sans", 20 if not self.window else 22))
            w = p.fontMetrics().horizontalAdvance(self.caption) + 48
            x, y = off.x() + (vw - w) // 2, off.y() + vh - 110
            p.setBrush(QColor(0, 0, 0, 175))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, w, 54, 10, 10)
            p.setPen(QColor("white"))
            p.drawText(x, y, w, 54, Qt.AlignmentFlag.AlignCenter, self.caption)
        c = self.cursor + QPointF(off)
        p.setBrush(QColor("white"))
        p.setPen(QColor("black"))
        p.drawPolygon(QPolygonF([c, c + QPointF(0, 19), c + QPointF(5, 15), c + QPointF(9, 24), c + QPointF(12, 22.5),
                                 c + QPointF(8, 14), c + QPointF(14, 14)]))
        p.end()
        img.save(os.path.join(self.outdir, f"f{self.frame:05d}.png"))
        self.frame += 1

    def scene(self, caption, line, action, seconds=None):
        """One narrated scene: the action runs, then the picture is held until the sentence has been spoken."""
        start = self.frame
        self.marks.append({"frame": start, "text": caption, "line": line})
        self.caption = caption
        self.scene_active = True
        try:
            action()
        finally:
            self.scene_active = False
        want = start + int(round((seconds if seconds is not None else self.durations.get(line, 0) + 0.7) * FPS))
        if self.frame < want:
            self.hold(want - self.frame)

    durations = {}

    def say(self, text):
        if self.scene_active:
            return
        self.caption = text
        self.marks.append({"frame": self.frame, "text": text})   # scene starts, used by narrate.py

    # --- input, through the viewport's own event handlers ---
    def uv_to_px(self, uv):
        plane = self.vp.doc.active_sketch.plane
        return self.vp.world_to_screen(plane.uv_to_world(uv[0], uv[1]))

    def move_event(self, px):
        self.cursor = QPointF(*px)
        pt = QPointF(*px)
        self.vp.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, pt, pt, Qt.MouseButton.NoButton,
                                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

    def glide(self, uv, frames=24):
        a, b = np.array([self.cursor.x(), self.cursor.y()]), np.array(self.uv_to_px(uv))
        for i in range(1, frames + 1):
            t = i / frames
            t = t * t * (3 - 2 * t)
            self.move_event(a + (b - a) * t)
            self.shoot()

    def key(self, k, text=""):
        self.vp.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier, text))

    def type_number(self, s, per_key=5):
        for ch in s:
            self.key(Qt.Key.Key_Period if ch == "." else getattr(Qt.Key, f"Key_{ch}"), ch)
            self.shoot(per_key)

    def enter(self, hold=18):
        self.key(Qt.Key.Key_Return)
        self.shoot(hold)

    def press(self, uv):
        pt = QPointF(*self.uv_to_px(uv))
        for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            fn = self.vp.mousePressEvent if t == QEvent.Type.MouseButtonPress else self.vp.mouseReleaseEvent
            fn(QMouseEvent(t, pt, pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton if t == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        self.shoot(6)

    def fly(self, target, distance, az, el, frames=45):
        """Smooth camera move to a new target/distance/azimuth/elevation."""
        vp = self.vp
        a0 = (np.array(vp.target, dtype=float), vp.distance, vp.azimuth, vp.elevation)
        for i in range(1, frames + 1):
            k = i / frames
            k = k * k * (3 - 2 * k)
            vp.target = np.array(a0[0] + (np.asarray(target, dtype=float) - a0[0]) * k, dtype=np.float32)
            vp.distance = a0[1] + (distance - a0[1]) * k
            vp.azimuth = a0[2] + (az - a0[2]) * k
            vp.elevation = a0[3] + (el - a0[3]) * k
            vp.update()
            self.cursor = QPointF(-50, -50)
            self.shoot()

    def encode(self, out):
        out = os.path.abspath(os.path.expanduser(out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(self.outdir, "f%05d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", out], check=True)
        import json
        json.dump({"fps": FPS, "frames": self.frame, "marks": self.marks}, open(os.path.join(self.outdir, "marks.json"), "w"), indent=1)
        print("Saved", out)

    def encode_scaled(self, out, size="1920:1080"):
        """Encode full-window frames (any 16:9 size) to `size` (1080p by default)."""
        out = os.path.abspath(os.path.expanduser(out))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(self.outdir, "f%05d.png"),
                        "-vf", f"scale={size}:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", out], check=True)
        import json
        json.dump({"fps": FPS, "frames": self.frame, "marks": self.marks}, open(os.path.join(self.outdir, "marks.json"), "w"), indent=1)
        print("Saved", out)

    def circle(self, d, across_uv, across, down_uv, down):
        self.say(f"Type the diameter: {d} mm, Enter")
        self.shoot(8)
        self.type_number(d)
        self.shoot(10)
        self.enter()
        self.say("Move next to a vertical line, type the distance, Enter")
        self.glide(across_uv)
        self.shoot(10)
        self.type_number(across)
        self.shoot(10)
        self.enter()
        self.say("Same to a horizontal line")
        self.glide(down_uv)
        self.shoot(10)
        self.type_number(down)
        self.shoot(10)
        self.enter(26)
