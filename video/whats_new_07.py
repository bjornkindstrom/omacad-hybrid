#!/usr/bin/env python3
"""Feature tour for Omacad 0.7+: narrated with female voiceover and background music.
Films the whole window (ribbon, tree, timeline, 3D view). All new models, showcasing 0.7 features:
1. Intro: Hexagonal drone motor mount / heatsink turning smoothly
2. Primitives without sketches: Box base + Cylinder boss + Sphere dome on faces
3. 3D Rotation Gizmo rings: interactive Fusion 360-style rotation and translation
4. Model Browser: nested hierarchy showing sketches grouped under bodies (parent_body_id)
5. Direct typing in Extrude badge & smooth tangent chain edge selection for Fillet
6. Parametric Shell with open face and Section View slicing through front
7. Smart 3D-print threads and coils (metric, trapezoidal, round) with automatic end trimming
8. Theme switcher: 3 theme modes (Tokyo Night, Catppuccin Latte, Osaka Jade) and scalable ribbon
9. F9 bug reporting with choice of AI agent (including Antigravity)
10. Outro
"""
import argparse
import math
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QPainter, QSurfaceFormat
from PySide6.QtWidgets import QApplication

import narrate
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.ui import theme
from omacad.ui.main_window import MainWindow
from take import Take

OUTDIR = os.path.join(ROOT, "video", "tour")
THEMES = ["tokyo-night", "catppuccin-latte", "gruvbox", "osaka-jade", "rose-pine", "nord"]

FEMALE_NARRATOR = ("A calm, clear female narrator in her twenties with a warm, friendly tone. Natural pace, "
                   "relaxed and confident, like a software tutorial on YouTube.")

LINES = {
    "intro": "Welcome to Oh-mah-cad. Native, parametric 3D C A D for Oh-mar-key Linux, built with clean geometry and pure speed.",
    "primitives": "Add boxes, cylinders or spheres directly onto any face or plane, with no sketch needed.",
    "gizmo": "Rotate or translate bodies with interactive 3D rotation gizmo rings, just like in Fusion 360.",
    "browser": "The Model Browser groups sketches directly under their parent bodies, keeping complex assemblies organized.",
    "extrude_fillet": "Type distances directly into the Extrude badge, and select entire tangent chains with a single click in Fillet.",
    "shell_section": "Parametric Shell hollows any shape with open faces, while Section View slices through the front to reveal the inside.",
    "thread": "Wrap 3D printable threads and coils directly onto cylinders, with automatic end trimming and clean, flush cuts.",
    "themes": "Switch between three theme modes and enjoy high-DPI scalable ribbon buttons with crisp Blueprint icons.",
    "feedback": "Encounter an issue? Press F9 to send a screenshot and model to your choice of AI agent, including Antigravity.",
    "outro": "Oh-mah-cad is open source, lightning fast, and free. Thank you for watching.",
}


def build_intro_mount(doc: Document):
    """Modern hexagonal motor mount / heatsink bracket."""
    sk = doc.start_sketch("XY")
    sk.add_polygon((0.0, 0.0), (32.0, 0.0), 6)
    sk.add_circle((0.0, 0.0), 14.0)
    # 3 mounting bolt holes on alternating corners
    for ang in (0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0):
        sk.add_circle((24.0 * math.cos(ang), 24.0 * math.sin(ang)), 2.5)
    doc.finish_sketch()
    b = doc.extrude_profile(sk.sketch_id, 0, 8.0)
    top_plane = SketchPlane.from_face(np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 8.0]))
    sk2 = doc.start_sketch_on_plane(top_plane)
    if hasattr(b, "body_id"):
        sk2.parent_body_id = b.body_id
    sk2.add_circle((0.0, 0.0), 19.0)
    sk2.add_circle((0.0, 0.0), 14.0)
    doc.finish_sketch()
    doc.extrude_profile(sk2.sketch_id, 0, 16.0, "join")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "tour_silent.mp4"))
    args = ap.parse_args()

    durations = {}
    for k, line in LINES.items():
        durations[line] = narrate.clip(line, voice=FEMALE_NARRATOR)[1]
    print("Narration total seconds:", round(sum(durations.values()), 1), flush=True)

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    win = MainWindow()
    win.showFullScreen()

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
        theme.COLORS_FILE_ORIGINAL = theme.COLORS_FILE
        t = Take(app, win, OUTDIR, window=True)
        t.durations = durations
        L = LINES

        def vp():
            return win.viewport

        def doc():
            return win.doc

        def cam(target, dist, az, el):
            v = vp()
            v.target, v.distance, v.azimuth, v.elevation = np.array(target, dtype=np.float32), dist, az, el
            v.update()

        def orbit(frames, degrees, bob=0.0):
            v = vp()
            a0, e0 = v.azimuth, v.elevation
            for i in range(1, frames + 1):
                k = i / frames
                v.azimuth = a0 + degrees * k
                v.elevation = e0 + bob * math.sin(math.pi * 2 * k)
                v.update()
                t.cursor = QPointF(-50, -50)
                t.shoot()

        def fresh():
            win.attach_document(Document(), None)
            win.doc.auto_include_edges = False
            for _ in range(5):
                app.processEvents()

        # =====================================================================
        # 1. INTRO: Hexagonal drone motor mount / heatsink turning smoothly
        # =====================================================================
        fresh()
        build_intro_mount(doc())
        cam((0.0, 0.0, 10.0), 110.0, 30.0, 28.0)
        t.shoot(10)
        t.scene("Omacad: Parametric CAD for Omarchy Linux", L["intro"],
                lambda: orbit(int(durations[L["intro"]] * 30), 160, 5))

        # =====================================================================
        # 2. PRIMITIVES: Box, Cylinder and Sphere directly without sketches
        # =====================================================================
        fresh()
        d, v = doc(), vp()
        cam((0.0, 0.0, 15.0), 115.0, 35.0, 30.0)
        t.shoot(10)

        def primitives_scene():
            # Add base box
            d.add_box(60.0, 45.0, 10.0, center=True)
            t.shoot(25)
            # Add cylinder directly on top face
            d.add_cylinder(radius=12.0, height=20.0, center=False,
                           plane_origin=[0.0, 0.0, 5.0], plane_normal=[0.0, 0.0, 1.0])
            t.shoot(25)
            # Add dome sphere on top of cylinder
            d.add_sphere(radius=12.0)
            # move sphere to sit exactly on the cylinder top
            sph_id = [b for b in d.bodies if "sphere" in b][0]
            d.move_body(sph_id, dz=25.0)
            t.shoot(20)
            orbit(int(durations[L["primitives"]] * 30) - 70, 90, 4)

        t.scene("Primitives: Box, Cylinder & Sphere without sketches", L["primitives"], primitives_scene)

        # =====================================================================
        # 3. 3D ROTATION GIZMO: Interactive Fusion 360 style rotation rings
        # =====================================================================
        def gizmo_scene():
            body_id = next(iter(d.bodies.keys()))
            v.set_move_gizmo((0.0, 0.0, 15.0), length=35.0)
            t.shoot(20)
            n = int(durations[L["gizmo"]] * 30)
            for i in range(n):
                k = i / n
                # Animate rotation around the green (RY) ring
                v.move_gizmo["hover_axis"] = "RY"
                v.move_gizmo["active_axis"] = "RY"
                v.move_gizmo["dragging"] = True
                v.azimuth = 35.0 + 40.0 * math.sin(math.pi * k)
                v.elevation = 30.0 + 8.0 * math.cos(math.pi * k)
                v.update()
                t.shoot()
            v.clear_move_gizmo()

        t.scene("3D Move & Rotation Gizmo Rings", L["gizmo"], gizmo_scene)

        # =====================================================================
        # 4. MODEL BROWSER: Hierarchy grouping sketches under bodies
        # =====================================================================
        fresh()
        d, v = doc(), vp()

        def browser_scene():
            # Build an enclosure with two child face sketches
            b = d.add_box(50.0, 35.0, 15.0, center=True)
            top_plane = SketchPlane.from_face(np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 7.5]))
            sk1 = d.start_sketch_on_plane(top_plane)
            sk1.parent_body_id = b.body_id
            sk1.name = "Connector Slot"
            sk1.add_rounded_rect((-15.0, -6.0), (15.0, 6.0), 3.0)
            d.finish_sketch()
            # Second sketch on same body
            sk2 = d.start_sketch_on_plane(top_plane)
            sk2.parent_body_id = b.body_id
            sk2.name = "Pin Array"
            sk2.add_circle((-10.0, 0.0), 1.5)
            sk2.add_circle((0.0, 0.0), 1.5)
            sk2.add_circle((10.0, 0.0), 1.5)
            d.finish_sketch()
            cam((0.0, 0.0, 7.5), 90.0, 25.0, 32.0)
            t.shoot(25)
            # Expand and highlight in the browser tree
            win.browser.tree.expandAll()
            t.shoot(30)
            orbit(int(durations[L["browser"]] * 30) - 55, 70, 3)

        t.scene("Model Browser: sketches organized under bodies", L["browser"], browser_scene)

        # =====================================================================
        # 5. DIRECT EXTRUDE BADGE & TANGENT CHAIN FILLET
        # =====================================================================
        fresh()
        d, v = doc(), vp()

        def extrude_fillet_scene():
            sk = d.start_sketch("XY")
            sk.add_rounded_rect((0.0, 0.0), (55.0, 35.0), 8.0)
            d.finish_sketch()
            # Extrude badge visible
            v.set_extrude_handle(np.array([27.5, 17.5, 0.0]), np.array([0.0, 0.0, 1.0]), 18.0)
            cam((27.5, 17.5, 9.0), 105.0, 30.0, 35.0)
            t.shoot(35)
            v.clear_extrude_handle()
            d.extrude_profile(sk.sketch_id, 0, 18.0)
            b = next(iter(d.bodies.values()))
            # Tangent chain / loop fillet on the top continuous edge
            top_edges = [e.ref() for e in b.edges if abs(float(e.polyline()[:, 2].mean()) - 18.0) < 1e-3]
            d.add_fillet(top_edges, 3.0, "fillet")
            t.shoot(25)
            orbit(int(durations[L["extrude_fillet"]] * 30) - 60, 80, 4)

        t.scene("Direct typing Extrude badge & Tangent chain Fillet", L["extrude_fillet"], extrude_fillet_scene)

        # =====================================================================
        # 6. PARAMETRIC SHELL & SECTION VIEW
        # =====================================================================
        fresh()
        d, v = doc(), vp()

        def shell_section_scene():
            box = d.add_box(56.0, 40.0, 28.0, center=False)
            # Open face on top
            open_faces = [{"normal": [0.0, 0.0, 1.0], "origin": [0.0, 0.0, 28.0]}]
            d.add_shell(box.body_id, 2.5, open_faces=open_faces)
            # Section plane sliding through from the front
            sid = d.add_section((28.0, 20.0, 14.0), (0.0, -1.0, 0.0), -18.0)
            cam((28.0, 20.0, 14.0), 100.0, 25.0, 28.0)
            t.shoot(20)
            n = int(durations[L["shell_section"]] * 30) - 20
            for i in range(n + 1):
                k = i / n
                d.sections[sid]["offset"] = -18.0 + 34.0 * (0.5 - 0.5 * math.cos(math.pi * k))
                d.notify_changed()
                v.azimuth = 25.0 + 35.0 * math.sin(math.pi * k)
                v.update()
                t.shoot()

        t.scene("Parametric Shell with open face & Section View", L["shell_section"], shell_section_scene)

        # =====================================================================
        # 7. 3D-PRINT THREADS & COILS WITH FLUSH END TRIMMING
        # =====================================================================
        fresh()
        d, v = doc(), vp()

        def thread_scene():
            # Modern bolt/threaded cylinder
            cyl = d.add_cylinder(radius=14.0, height=36.0, center=False)
            d.add_thread(
                diameter=28.0,
                pitch=3.5,
                length=26.0,
                is_female=False,
                profile="trapezoidal_45",
                target_body_id=cyl.body_id,
                operation="join",
                plane_origin=[0.0, 0.0, 5.0],
                plane_normal=[0.0, 0.0, 1.0],
            )
            cam((0.0, 0.0, 18.0), 85.0, 35.0, 25.0)
            t.shoot(20)
            orbit(int(durations[L["thread"]] * 30) - 20, 130, 4)

        t.scene("3D-Print Threads & Coils with flush end trimming", L["thread"], thread_scene)

        # =====================================================================
        # 8. THEME MODES & SCALABLE RIBBON ICONS
        # =====================================================================
        def theme_scene():
            n, hold, fade = int(durations[L["themes"]] * 30) + 15, 45, 8
            for i in range(n):
                v.azimuth += 1.6
                v.elevation = 25.0 + 5.0 * math.sin(i / 22.0)
                v.update()
                k, f = divmod(i, hold)
                cur, nxt = THEMES[k % len(THEMES)], THEMES[(k + 1) % len(THEMES)]
                set_theme(cur)
                img = t._grab()
                if f >= hold - fade:
                    a = (f - (hold - fade) + 1) / (fade + 1)
                    set_theme(nxt)
                    other = t._grab()
                    p = QPainter(img)
                    p.setOpacity(a * a * (3 - 2 * a))
                    p.drawImage(0, 0, other)
                    p.end()
                t.cursor = QPointF(-50, -50)
                t._finish(img)
            set_theme(THEMES[0])

        shown = {"n": None}

        def set_theme(name):
            if shown["n"] != name:
                theme.COLORS_FILE = Path("/usr/share/omarchy/themes") / name / "colors.toml"
                theme.refresh()
                for _ in range(4):
                    app.processEvents()
                shown["n"] = name

        try:
            t.scene("Live Omarchy themes & scalable ribbon buttons", L["themes"], theme_scene)
        finally:
            theme.COLORS_FILE = theme.COLORS_FILE_ORIGINAL
            theme.refresh()

        # =====================================================================
        # 9. F9 BUG REPORTING & AI AGENT (ANTIGRAVITY) SELECTION
        # =====================================================================
        def feedback_scene():
            cam((0.0, 0.0, 18.0), 90.0, 35.0, 25.0)
            t.shoot(15)
            # Show the F9 feedback dialog briefly
            from omacad.ui.feedback_dialog import FeedbackDialog
            view_shot = vp().grabFramebuffer()
            window_shot = win.grab_with_overlay(view_shot)
            dlg = FeedbackDialog(win, window_shot)
            dlg.note.setPlainText("Thread pitch preview aligns cleanly with the chamfered cylinder shoulder.")
            # Set agent combo to agy / Antigravity
            idx = dlg.cmb_agent.findData("agy")
            if idx >= 0:
                dlg.cmb_agent.setCurrentIndex(idx)
            dlg.show()
            for _ in range(5):
                app.processEvents()
            # Capture dialog open
            t.shoot(int(durations[L["feedback"]] * 30) - 25)
            dlg.close()
            t.shoot(10)

        t.scene("F9 Bug Reporting: screenshot & model to Antigravity AI", L["feedback"], feedback_scene)

        # =====================================================================
        # 10. OUTRO: Smooth final orbit
        # =====================================================================
        t.scene("Omacad: open source, lightning fast, and free", L["outro"],
                lambda: orbit(int(durations[L["outro"]] * 30) + 30, 80, 3))

        t.shoot(30)
        t.encode_scaled(args.out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
