#!/usr/bin/env python3
"""
True Fullscreen Animated Take for Omacad 48-Hour Evolution:
Renders the app in true fullscreen native 1440p (2560x1440 at DPR 1.25):
1. Intro: 3D orbit around the assembly model.
2. Modern UI: Showing the transparent floating Browser & Inspector, no status bar, equal ribbon buttons.
3. Move Face to Face: Picking faces live, animating Touch / Centering assembly alignment.
4. Technical Section View: Enabling section plane live with diagonal hatching and per-body tint.
5. Offset Face on Threads: Interactive tolerance offset for 3D printed threads.
6. Outro: Final dynamic camera fly-around.

Narrated with English female voice (pronouncing 'cad' as word) and ComfyUI lo-fi music.
Output: crisp 2560x1440 (1440p QHD) video!
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/kindstrom/Work/omacad")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "video"))

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPolygonF, QSurfaceFormat
from PySide6.QtWidgets import QApplication, QWidget

import narrate
import tts
from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui.main_window import MainWindow

OUTDIR = ROOT / "video" / "take_48h_frames"
AUDIO_DIR = ROOT / "video" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

FPS = 30

FEMALE_VOICE = (
    "A calm, clear female narrator in her twenties with a warm, friendly tone. Natural pace, "
    "relaxed and confident, like a high quality software tutorial on YouTube."
)

with open(ROOT / "video" / "lines_48h.json", "r") as f:
    LINES = json.load(f)


class AppWindowTake:
    def __init__(self, app, win, outdir):
        self.app = app
        self.win = win
        self.vp = win.viewport
        self.outdir = Path(outdir)
        self.marks = []
        self.frame = 0
        self.caption = ""
        self.cursor = QPointF(self.vp.width() * 0.5, self.vp.height() * 0.5)
        self.durations = {}
        shutil.rmtree(self.outdir, ignore_errors=True)
        self.outdir.mkdir(parents=True, exist_ok=True)

    def shoot(self, n=1):
        for _ in range(n):
            self._render()

    def hold(self, n):
        if n <= 0 or self.frame == 0:
            return
        last = self.outdir / f"f{self.frame - 1:05d}.png"
        for _ in range(n):
            dest = self.outdir / f"f{self.frame:05d}.png"
            try:
                os.link(last, dest)
            except OSError:
                shutil.copyfile(last, dest)
            self.frame += 1

    def _grab(self):
        for _ in range(2):
            self.app.processEvents()
        dpr = self.win.devicePixelRatio()
        img = self.win.grab().toImage()
        fb = self.vp.grabFramebuffer()
        off = self.vp.mapTo(self.win, QPoint(0, 0))
        
        p = QPainter(img)
        target_rect = QRect(int(off.x() * dpr), int(off.y() * dpr), fb.width(), fb.height())
        p.drawImage(target_rect, fb)
        
        # Draw floating children on top
        for w in self.vp.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if w.isVisible():
                pos = w.mapTo(self.win, QPoint(0, 0))
                pix = w.grab()
                p.drawPixmap(int(pos.x() * dpr), int(pos.y() * dpr), pix)
        p.end()
        return img, dpr

    def _render(self):
        img, dpr = self._grab()
        off = self.vp.mapTo(self.win, QPoint(0, 0))
        vw, vh = int(self.vp.width() * dpr), int(self.vp.height() * dpr)
        off_x, off_y = int(off.x() * dpr), int(off.y() * dpr)
        
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw caption box in crisp high-res
        if self.caption:
            p.setFont(QFont("Liberation Sans", 24, QFont.Weight.Bold))
            w = p.fontMetrics().horizontalAdvance(self.caption) + 60
            x = off_x + (vw - w) // 2
            y = off_y + vh - 110
            p.setBrush(QColor(15, 20, 32, 230))
            p.setPen(QColor(60, 80, 120))
            p.drawRoundedRect(x, y, w, 62, 10, 10)
            p.setPen(QColor(255, 255, 255))
            p.drawText(x, y, w, 62, Qt.AlignmentFlag.AlignCenter, self.caption)

        # Draw high-res cursor
        c = (self.cursor + QPointF(off)) * dpr
        p.setBrush(QColor("white"))
        p.setPen(QColor("black"))
        p.drawPolygon(QPolygonF([
            c, c + QPointF(0, 24), c + QPointF(7, 19), c + QPointF(12, 30),
            c + QPointF(16, 28), c + QPointF(11, 18), c + QPointF(19, 18)
        ]))
        p.end()
        img.save(str(self.outdir / f"f{self.frame:05d}.png"))
        self.frame += 1

    def say(self, text, line_key=None):
        self.caption = text
        if line_key:
            self.marks.append({"frame": self.frame, "text": text, "line": LINES[line_key]})

    def glide_px(self, target_px, frames=24):
        a = np.array([self.cursor.x(), self.cursor.y()])
        b = np.asarray(target_px, dtype=float)
        for i in range(1, frames + 1):
            k = i / frames
            k = k * k * (3 - 2 * k)
            cur = a + (b - a) * k
            self.cursor = QPointF(cur[0], cur[1])
            self.shoot()

    def fly(self, target, dist, az, el, frames=30):
        t0 = np.array(self.vp.target, dtype=float)
        t1 = np.array(target, dtype=float)
        d0, d1 = float(self.vp.distance), float(dist)
        a0, a1 = float(self.vp.azimuth), float(az)
        e0, e1 = float(self.vp.elevation), float(el)
        for i in range(1, frames + 1):
            k = i / frames
            k = k * k * (3 - 2 * k)
            self.vp.target = (t0 + (t1 - t0) * k).astype(np.float32)
            self.vp.distance = d0 + (d1 - d0) * k
            self.vp.azimuth = a0 + (a1 - a0) * k
            self.vp.elevation = e0 + (e1 - e0) * k
            self.vp.update()
            self.shoot()

    def orbit(self, frames, deg=60.0):
        a0 = self.vp.azimuth
        for i in range(1, frames + 1):
            self.vp.azimuth = a0 + deg * (i / frames)
            self.vp.update()
            self.shoot()

    def scene(self, caption, line_key, action_fn, min_hold=30):
        self.say(caption, line_key)
        start_frame = self.frame
        action_fn()
        dur = self.durations.get(line_key, 4.0)
        needed = int(dur * FPS)
        elapsed = self.frame - start_frame
        if elapsed < needed:
            self.hold(needed - elapsed)
        elif min_hold > 0:
            self.hold(min_hold)


def main():
    print("Pre-synthesizing narration sentences with ComfyUI TTS...")
    durations = {}
    for k, line in LINES.items():
        out_f = AUDIO_DIR / f"{k}.flac"
        if not out_f.exists():
            tts.synthesize(line, str(out_f), voice=FEMALE_VOICE, seed=77, language="English")
        dur = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_f)
        ]).strip())
        durations[k] = dur
        print(f"Clip {k}: {dur:.2f}s")

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.showFullScreen()

    def run():
        try:
            _execute_scenes(app, win, durations)
        except Exception:
            import traceback
            traceback.print_exc()
        app.quit()

    QTimer.singleShot(1500, run)
    app.exec()


def _execute_scenes(app, win, durations):
    for _ in range(15):
        app.processEvents()

    t = AppWindowTake(app, win, OUTDIR)
    t.durations = durations
    vp = win.viewport

    # SCENE 1: INTRO (3D Orbit over assembled model)
    model_path = str(ROOT / "tests" / "data" / "thread_follows_cylinder.omacad")
    if os.path.exists(model_path):
        doc = Exporter.load_project(model_path)
        win.attach_document(doc, model_path)
    vp.target = np.array([0.0, 0.0, 15.0], dtype=np.float32)
    vp.distance, vp.azimuth, vp.elevation = 120.0, 30.0, 25.0
    vp.update()

    def act_intro():
        t.orbit(int(durations["intro"] * FPS), deg=80.0)

    t.scene("Omacad: 48 Hours of Rapid Evolution", "intro", act_intro)

    # SCENE 2: CLEAN MODERN UI (Glide across Browser, Inspector & HUD)
    def act_ui():
        b_pos = win.browser.mapTo(vp, QPoint(100, 100))
        t.glide_px((b_pos.x(), b_pos.y()), frames=25)
        t.shoot(20)
        insp_pos = win.inspector.mapTo(vp, QPoint(50, 140))
        t.glide_px((insp_pos.x(), insp_pos.y()), frames=30)
        t.shoot(20)
        t.glide_px((vp.width() * 0.5, vp.height() * 0.6), frames=20)
        t.orbit(30, deg=20.0)

    t.scene("Clean UI: Floating Overlays & In-View HUD", "ui", act_ui)

    # SCENE 3: MOVE FACE TO FACE
    def act_move():
        box_doc = Document()
        box_doc.add_box(36, 36, 16)
        b1 = list(box_doc.bodies.keys())[0]
        box_doc.add_cylinder(10, 24)
        b2 = [k for k in box_doc.bodies.keys() if k != b1][0]
        box_doc.move_body(b2, dx=40, dy=10, dz=8, rx=30, ry=-15)
        win.attach_document(box_doc, None)
        vp.target = np.array([18.0, 5.0, 12.0], dtype=np.float32)
        vp.distance, vp.azimuth, vp.elevation = 110.0, 45.0, 28.0
        vp.update()
        t.shoot(15)

        win.prompt_move_body(b2)
        t.shoot(20)
        dlg = win.inspector.current_tool_dlg

        btn_pos = dlg.btn_f2f.mapTo(vp, QPoint(dlg.btn_f2f.width() // 2, dlg.btn_f2f.height() // 2))
        t.glide_px((btn_pos.x(), btn_pos.y()), frames=25)
        dlg.btn_f2f.setChecked(True)
        t.shoot(15)

        src_f = max(box_doc.bodies[b2].faces, key=lambda f: -f.normal[2])
        dst_f = max(box_doc.bodies[b1].faces, key=lambda f: f.normal[2])
        from omacad.model.geometry import face_centroid, face_to_face_values
        c2 = (np.asarray(box_doc.bodies[b2].render_mesh.bounds_min, float) + np.asarray(box_doc.bodies[b2].render_mesh.bounds_max, float)) * 0.5
        vals = face_to_face_values(src_f.normal, face_centroid(src_f), dst_f.normal, face_centroid(dst_f), c2, True, "touch", True)
        
        for step in range(1, 25):
            k = step / 24.0
            cur_vals = [v * k for v in vals]
            dlg.spn_dx.setValue(cur_vals[0])
            dlg.spn_dy.setValue(cur_vals[1])
            dlg.spn_dz.setValue(cur_vals[2])
            dlg.spn_rx.setValue(cur_vals[3])
            dlg.spn_ry.setValue(cur_vals[4])
            dlg.spn_rz.setValue(cur_vals[5])
            t.shoot()

        dlg.btn_f2f.setChecked(False)
        dlg.accept()
        t.shoot(15)

    t.scene("Move Face to Face: Touch & Automatic Centering", "move", act_move)

    # SCENE 4: TECHNICAL SECTION VIEW WITH HATCHING
    def act_section():
        jar_path = str(ROOT / "tests" / "data" / "offset_face_section_thread.omacad")
        if os.path.exists(jar_path):
            doc = Exporter.load_project(jar_path)
            win.attach_document(doc, jar_path)
        vp.target = np.array([0.0, 0.0, 15.0], dtype=np.float32)
        vp.distance, vp.azimuth, vp.elevation = 75.0, 200.0, 20.0
        vp.update()
        t.shoot(15)

        vp.enable_section = True
        vp.section_pos = 0.0
        vp.update()
        t.shoot(25)
        t.fly(target=[0.0, 0.0, 15.0], dist=38.0, az=185.0, el=10.0, frames=35)
        t.orbit(35, deg=25.0)

    t.scene("Section View: Technical Diagonal Hatching", "section", act_section)

    # SCENE 5: OFFSET FACE ON THREADS
    def act_offset():
        vp.target = np.array([0.0, 0.0, 15.0], dtype=np.float32)
        vp.distance, vp.azimuth, vp.elevation = 42.0, 192.0, 14.0
        vp.update()
        t.shoot(15)

        win.prompt_offset_face()
        t.shoot(20)
        dlg = win.inspector.current_tool_dlg

        spot = (int(vp.width() * 0.48), int(vp.height() * 0.45))
        t.glide_px(spot, frames=24)
        t.shoot(10)
        vp._offset_face_click(float(spot[0]), float(spot[1]))
        t.shoot(20)

        if hasattr(dlg, "spn_offset"):
            dlg.spn_offset.setValue(-0.2)
        t.shoot(25)
        dlg.accept()
        t.shoot(20)
        t.fly(target=[-8.0, 0.0, 15.0], dist=22.0, az=180.0, el=0.0, frames=30)
        t.shoot(30)

    t.scene("Offset Face: -0.2mm 3D-Print Thread Clearance", "thread", act_offset)

    # SCENE 6: OUTRO
    def act_outro():
        vp.enable_section = False
        vp.update()
        t.fly(target=[0.0, 0.0, 15.0], dist=120.0, az=35.0, el=30.0, frames=40)
        t.orbit(int(durations["outro"] * FPS), deg=75.0)

    t.scene("Omacad: Parametric CAD for Omarchy Linux", "outro", act_outro)

    print(f"Rendered {t.frame} animated frames! Building audio and muxing in native 1440p...")

    # Write marks
    marks_file = OUTDIR / "marks.json"
    with open(marks_file, "w") as f:
        json.dump(t.marks, f, indent=2)

    # Build audio track
    speech_track = AUDIO_DIR / "speech_full.flac"
    inputs = []
    delays = []
    for idx, m in enumerate(t.marks):
        line_key = [k for k, v in LINES.items() if v == m["line"]][0]
        audio_file = AUDIO_DIR / f"{line_key}.flac"
        inputs.extend(["-i", str(audio_file)])
        delays.append(int((m["frame"] / FPS) * 1000))

    filter_str = ""
    for idx, d_ms in enumerate(delays):
        filter_str += f"[{idx}:a]adelay={d_ms}|{d_ms}[a{idx}];"
    amix_in = "".join(f"[a{idx}]" for idx in range(len(delays)))
    filter_str += f"{amix_in}amix=inputs={len(delays)}:dropout_transition=0,volume=1.8[aout]"

    subprocess.run(["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[aout]", str(speech_track)], check=True)

    # Final video encode in native full resolution (2560x1440)
    music_file = ROOT / "video" / "audio" / "music.flac"
    out_video = Path("/home/kindstrom/Videos/omacad-senaste-2-dagarna.mp4")
    total_dur = t.frame / FPS

    mux_cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(OUTDIR / "f%05d.png"),
        "-i", str(music_file),
        "-i", str(speech_track),
        "-filter_complex",
        f"[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2[v];"
        f"[1:a]afade=t=in:ss=0:d=1.5,volume=0.22[bgm];"
        f"[bgm][2:a]sidechaincompress=threshold=0.15:ratio=4:attack=50:release=300[ducked];"
        f"[ducked][2:a]amix=inputs=2:weights=1 1.2[audio_mix];"
        f"[audio_mix]afade=t=out:st={total_dur - 2.5}:d=2.5[final_audio]",
        "-map", "[v]",
        "-map", "[final_audio]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "16",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(total_dur),
        str(out_video)
    ]
    subprocess.run(mux_cmd, check=True)
    print("SUCCESS! Fullscreen 1440p video written to:", out_video)


if __name__ == "__main__":
    main()
