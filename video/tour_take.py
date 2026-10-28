#!/usr/bin/env python3
"""The two-minute feature tour: narrated, with background music. Films the whole window (ribbon, tree, timeline).

    .venv/bin/python video/tour_take.py --out ~/Videos/omacad-tour-silent.mp4
    .venv/bin/python video/music.py video/audio/music.flac --seconds 130
    .venv/bin/python video/narrate.py video/tour/marks.json ~/Videos/omacad-tour-silent.mp4 ~/Videos/omacad-tour.mp4 --music video/audio/music.flac

The sentences in SCENES are spoken first (ComfyUI must be running), so every scene lasts as long as its sentence.
Real display needed; the window goes fullscreen while it renders (10-20 minutes). Your Omarchy theme is never
changed (the theme scene only swaps the app's own colours).
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
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QPainter, QSurfaceFormat
from PySide6.QtWidgets import QApplication

import narrate
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.ui import theme
from omacad.ui.main_window import MainWindow
from take import Take
from theme_take import build_part

OUTDIR = os.path.join(ROOT, "video", "tour")
THEMES = ["tokyo-night", "catppuccin-latte", "gruvbox", "osaka-jade", "rose-pine", "nord"]
TOP = SketchPlane.from_face(np.array([0.0, 0, 1]), np.array([0.0, 0, 8.0]))
PLATE_C = (30.0, 20.0, 4.0)

FEMALE_NARRATOR = ("A calm, clear female narrator in her twenties with a warm, friendly tone. Natural pace, "
                   "relaxed and confident, like a software tutorial on YouTube.")

# Spoken text: names are respelled so the voice says them right (Omacad, CAD, Omarchy).
LINES = {
    "intro": "This is Oh-mah-cad: a native, parametric 3D C A D for Oh-mar-key Linux. Here is a quick tour.",
    "sketch": "Everything starts with a sketch. Pick the rounded rectangle, then just type the width, the height and the corner radius.",
    "smart_a": "Smart Circle places a hole with numbers. First type the diameter, and press Enter. The diameter shows up on the circle straight away.",
    "smart_b": "Then move next to a wall, and type how far from it the centre should be. The wall lights up, and the distance appears as a dimension.",
    "smart_c": "Do the same for the other direction. Every number is now a real dimension on the sketch, so the hole stays fully defined.",
    "extrude": "Extrude the sketch, and the circle becomes a hole. Drag the arrow or type the distance, and Auto mode decides whether to add or cut.",
    "chamfer": "Round or bevel edges with fillet and chamfer. It works on straight edges, circles and whole outlines.",
    "mirror_a": "Now copy the hole with its chamfer. Open Pattern and Mirror, and tick the steps you want copied. The preview shows the result as you change the settings: mirrored left to right, front to back, or all four corners at once.",
    "mirror_b": "It is all adjustable. Switch to evenly spaced copies, and set the number and the spacing, or go around an axis. Settle on the four corners, press OK, and the hole is copied with its chamfer.",
    "fill": "Fill pattern covers a whole face. Draw one polygon, and Oh-mah-cad packs the surface with exact gaps, steering around anything that stands on it.",
    "polygons": "It works for any polygon from three to eight sides, and everything is parametric. Change the sketch, and the pattern packs itself again.",
    "revolve": "Revolve turns a profile into a turned part, around any axis you choose.",
    "thread": "Thread and coil wrap 3D printable threads or bottle spirals directly onto any cylinder, with automatic end trimming.",
    "section": "Shell hollows out any body with open faces, and Section View slides through to inspect inside.",
    "undo": "Undo and redo cover every single step, so nothing you try can be lost.",
    "theme": "Oh-mah-cad follows your Oh-mar-key theme live: colours, fonts, everything.",
    "report": "Found a bug? Press F9. Oh-mah-cad sends a screenshot and your model to your choice of AI agent, fixing it while you work.",
    "end": "Oh-mah-cad is open source and free. Thanks for watching.",
}


def splice(t, old_dir, out):
    """New frames so far + the old run's frames from its "Fill pattern" scene to the end, then encode."""
    import json
    old = json.load(open(os.path.join(old_dir, "marks.json")))
    first = next(i for i, m in enumerate(old["marks"]) if m["text"] == "Fill pattern")
    start = old["marks"][first]["frame"]
    delta = t.frame - start
    for f in range(start, old["frames"]):
        dest = os.path.join(t.outdir, f"f{f + delta:05d}.png")
        try:
            os.link(os.path.join(old_dir, f"f{f:05d}.png"), dest)
        except OSError:
            import shutil
            shutil.copyfile(os.path.join(old_dir, f"f{f:05d}.png"), dest)
    t.marks += [{**m, "frame": m["frame"] + delta} for m in old["marks"][first:]]
    t.frame = old["frames"] + delta
    t.encode_scaled(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "tour_silent.mp4"))
    ap.add_argument("--reuse", help="directory of an earlier full run: render only up to the Pattern/Mirror scenes and take the "
                                    "frames from the Fill pattern scene onward from that run (replaces just those scenes)")
    args = ap.parse_args()
    # speak every sentence first, so the scenes can be as long as the speech
    durations = {}
    for k, line in LINES.items():
        durations[line] = narrate.clip(line, voice=FEMALE_NARRATOR)[1]
    print("narration seconds:", round(sum(durations.values()), 1), flush=True)

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

        # ---- 1. intro: a finished part turning ----
        fresh()
        build_part(doc())
        cam((40.0, 25.0, 4.0), 125.0, 25.0, 30.0)
        t.shoot(10)
        t.scene("Omacad: parametric CAD for Omarchy", L["intro"], lambda: orbit(int(5.5 * 30), 170, 6))

        # ---- 2. sketch ----
        fresh()
        d, v = doc(), vp()
        sk = d.start_sketch("XY")
        v.align_to_plane(sk.plane)
        cam((30.0, 20.0, 0.0), 72.0, 0.0, 89.9)
        t.cursor = QPointF(120, 400)
        t.shoot(8)

        def sketch_scene():
            v.set_sketch_tool("ROUNDED_RECT")
            v.setFocus()
            t.move_event(t.uv_to_px((-8.0, -6.0)))
            t.shoot(10)
            t.glide((0.0, 0.0), 20)
            t.press((0.0, 0.0))
            t.glide((40.0, 25.0), 25)
            for s in ("60", "40", "8"):
                t.type_number(s)
                t.shoot(8)
                t.enter(12)
            t.shoot(20)

        t.scene("Sketch: rounded rectangle", L["sketch"], sketch_scene)

        # ---- 3. smart circle: slow, zoomed in, every typed number shows up as a dimension ----
        def smart_a():
            v.set_sketch_tool("SMART_CIRCLE")
            v.setFocus()
            t.fly((18.0, 12.0, 0.0), 46.0, v.azimuth, v.elevation, 30)
            t.glide((18.0, 18.0), 24)
            t.shoot(15)
            t.type_number("6", per_key=20)
            t.shoot(25)
            t.enter(60)

        def smart_b():
            t.glide((3.0, 12.0), 30)
            t.shoot(30)
            t.type_number("8", per_key=20)
            t.shoot(20)
            t.enter(60)

        def smart_c():
            t.glide((12.0, 3.0), 30)
            t.shoot(30)
            t.type_number("8", per_key=20)
            t.shoot(20)
            t.enter(90)
            v.set_sketch_tool("NONE")
            t.fly((30.0, 20.0, 0.0), 72.0, v.azimuth, v.elevation, 40)

        t.scene("Smart Circle: the diameter", L["smart_a"], smart_a)
        t.scene("Smart Circle: distance from a wall", L["smart_b"], smart_b)
        t.scene("Smart Circle: the other direction", L["smart_c"], smart_c)

        # ---- 4. extrude ----
        def extrude_scene():
            d.finish_sketch()
            d.extrude_profile(sk.sketch_id, 0, 8.0)
            t.fly(PLATE_C, 80.0, 30.0, 45.0, 60)
            t.fly((8.0, 8.0, 8.0), 38.0, 35.0, 48.0, 40)

        t.scene("Extrude", L["extrude"], extrude_scene)

        # ---- 5. chamfer ----
        ch_holder = {}

        def chamfer_scene():
            body = next(iter(d.bodies.values()))
            edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.2]
            ch_holder["f"] = d.add_fillet(edges, 1.0, "chamfer")
            t.fly((8.0, 8.0, 8.0), 24.0, 40.0, 50.0, 40)

        t.scene("Fillet and Chamfer", L["chamfer"], chamfer_scene)

        # ---- 6. pattern / mirror: the real docked panel, driven step by step with a live preview ----
        pat = {}

        def preview():
            from omacad.model.timeline import PatternFeature
            dlg = pat["dlg"]
            ids = dlg.source_ids()
            if not ids:
                dlg.lbl_info.setText("Tick the steps to copy (for example the hole's sketch, cut and chamfer).")
                vp().set_preview(None)
                return
            feat = PatternFeature("tmp", "tmp", ids, dlg.kind(), **dlg.get_params())
            solid, op, extra, copies = None, "cut", None, 0
            for bid in list(d.bodies):
                res = feat.compute(d, bid)
                if res is None:
                    continue
                rem, add = res
                copies = feat.copies
                solid, op = (rem, "cut") if rem is not None else (add, "join")
                extra = add if rem is not None else None
                break
            dlg.lbl_info.setText(f"{copies} copies will be made." if solid is not None else "Nothing to copy with these settings.")
            vp().set_preview(solid, op, extra=extra, extra_op="join")

        def mirror_a():
            from omacad.ui.dialogs import PatternDialog
            from PySide6.QtCore import Qt
            t.fly(PLATE_C, 85.0, 30.0, 45.0, 30)
            d.timeline.recompute(d)
            dlg = PatternDialog(d, win)
            pat["dlg"] = dlg
            dlg.changed.connect(preview)
            win.dock(dlg)
            dlg.show()
            dlg.cmb_kind.setCurrentIndex(1)                       # Mirror around the body
            items = [dlg.lst.item(i) for i in range(dlg.lst.count())]
            for it in items:                                      # start with nothing ticked, then tick the hole's steps one by one
                it.setCheckState(Qt.CheckState.Unchecked)
            t.shoot(40)
            for it in items:
                it.setCheckState(Qt.CheckState.Checked)
                t.shoot(30)
            for idx in (1, 2, 3):                                 # left-right, front-back, all four corners
                dlg.cmb_mirror.setCurrentIndex(idx)
                t.shoot(55)

        def mirror_b():
            dlg = pat["dlg"]
            dlg.cmb_kind.setCurrentIndex(0)                       # evenly spaced copies
            t.shoot(30)
            for n in (3, 2, 3):
                dlg.spn_count1.setValue(n)
                t.shoot(30)
            dlg.spn_space1.setValue(22.0)
            t.shoot(45)
            dlg.cmb_kind.setCurrentIndex(1)                       # back to mirror, four corners
            dlg.cmb_mirror.setCurrentIndex(3)
            t.shoot(45)
            d.add_pattern(dlg.source_ids(), dlg.kind(), **dlg.get_params())
            dlg.accept()
            vp().set_preview(None)
            t.fly(PLATE_C, 85.0, 30.0, 45.0, 40)

        t.scene("Pattern and Mirror: preview", L["mirror_a"], mirror_a)
        t.scene("Pattern and Mirror: adjustable", L["mirror_b"], mirror_b)

        if args.reuse:
            splice(t, args.reuse, args.out)
            app.quit()
            return

        # ---- 7. cylinder + polygon fill ----
        hex_holder = {}

        def fill_scene():
            cs = d.start_sketch_on_plane(TOP)
            cs.add_circle((40.0, 20.0), 5.0)
            d.finish_sketch()
            d.extrude_profile(cs.sketch_id, 0, 12.0, "join")
            t.fly(PLATE_C, 85.0, 215.0, 45.0, 30)
            hs = d.start_sketch_on_plane(TOP)
            hs.add_polygon((16.0, 30.0), (19.0, 30.0), 6)
            d.finish_sketch()
            d.extrude_profile(hs.sketch_id, 0, -9.0, "cut")
            hex_holder["sk"] = hs.sketch_id
            hexcut = [f for f in d.timeline.features if f.feature_type == "extrude"][-1]
            d.add_pattern([hexcut.feature_id], "fill", spacing1=1.5, spacing2=3.0, count1=0.0, mirror_mode="stagger")
            t.fly(PLATE_C, 80.0, 235.0, 55.0, 40)
            orbit(60, 55, 0)

        t.scene("Fill pattern", L["fill"], fill_scene)

        # ---- 8. polygons: pentagon, triangle ----
        def polygon_scene():
            for sides in (5, 3, 8):
                s1 = d.edit_sketch(hex_holder["sk"])
                before = s1.to_dict()
                s1.delete_entities([e.entity_id for e in s1.entities])
                s1.add_polygon((16.0, 30.0), (19.0, 30.0), sides)
                d.record_sketch_change(s1, before)
                d.finish_sketch()
                t.shoot(8)
                orbit(60, 40, 0)

        t.scene("Any polygon, 3 to 8 sides", L["polygons"], polygon_scene)

        # ---- 9. revolve ----
        fresh()
        d, v = doc(), vp()

        def revolve_scene():
            rs = d.start_sketch("XZ")
            pts = [(0, 0), (22, 0), (22, 6), (14, 26), (17, 44), (0, 44)]
            for a, b in zip(pts, pts[1:] + pts[:1]):
                rs.add_line(a, b)
            v.align_to_plane(rs.plane)
            cam((10.0, 0.0, 22.0), 110.0, v.azimuth, v.elevation)
            t.shoot(30)
            d.finish_sketch()
            d.add_revolve(rs.sketch_id, 0, ("v",), 360.0, "new_body")
            t.fly((0.0, 0.0, 22.0), 120.0, 30.0, 25.0, 45)
            orbit(60, 70, 4)

        t.scene("Revolve", L["revolve"], revolve_scene)

        # ---- 9b. thread and coil ----
        def thread_scene():
            fresh()
            d, v = doc(), vp()
            cyl = d.add_cylinder(radius=15.0, height=40.0, center=False)
            d.add_thread(
                diameter=30.0,
                pitch=3.5,
                length=30.0,
                is_female=False,
                profile="trapezoidal_45",
                target_body_id=cyl.body_id,
                operation="join",
                plane_origin=[0.0, 0.0, 5.0],
                plane_normal=[0.0, 0.0, 1.0],
            )
            cam((0.0, 0.0, 20.0), 90.0, 35.0, 25.0)
            t.shoot(20)
            orbit(int(durations[L["thread"]] * 30), 120, 4)

        t.scene("Thread & Coil: 3D printable threads", L["thread"], thread_scene)

        # ---- 10. section view & shell ----
        def section_scene():
            fresh()
            d, v = doc(), vp()
            box = d.add_box(50.0, 40.0, 30.0, center=False)
            open_faces = [{"normal": [0.0, 0.0, 1.0], "origin": [0.0, 0.0, 30.0]}]
            d.add_shell(box.body_id, 3.0, open_faces=open_faces)
            sid = d.add_section((25.0, 20.0, 15.0), (0.0, -1.0, 0.0), -18.0)
            cam((25.0, 20.0, 15.0), 105.0, 25.0, 28.0)
            t.shoot(20)
            n = int(durations[L["section"]] * 30)
            for i in range(n + 1):
                k = i / n
                # Slide plane through the front to reveal the hollow interior and opening
                d.sections[sid]["offset"] = -18.0 + 36.0 * (0.5 - 0.5 * math.cos(math.pi * k))
                d.notify_changed()
                v.azimuth = 25.0 + 30.0 * math.sin(math.pi * k)
                v.update()
                t.shoot()

        t.scene("Shell & Section View", L["section"], section_scene)

        # ---- 11. undo / redo ----
        def undo_scene():
            t.fly((0.0, 0.0, 22.0), 120.0, 30.0, 25.0, 15)
            for _ in range(3):
                d.undo()
                t.shoot(24)
            for _ in range(3):
                d.redo()
                t.shoot(24)

        t.scene("Undo and Redo", L["undo"], undo_scene)

        # ---- 12. theme ----
        def theme_scene():
            n, hold, fade = int(durations[L["theme"]] * 30) + 20, 40, 8
            for i in range(n):
                v.azimuth += 1.6
                v.elevation = 25.0 + 6.0 * math.sin(i / 20.0)
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
            t.scene("Follows your Omarchy theme", L["theme"], theme_scene)
        finally:
            theme.COLORS_FILE = theme.COLORS_FILE_ORIGINAL
            theme.refresh()

        # ---- 13. report, end ----
        t.scene("F9: report a problem to your AI agent", L["report"], lambda: orbit(int(durations[L["report"]] * 30), 120, 4))
        t.scene("Omacad: open source and free", L["end"], lambda: orbit(int(durations[L["end"]] * 30) + 30, 60, 3))
        t.shoot(30)
        t.encode_scaled(args.out)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
