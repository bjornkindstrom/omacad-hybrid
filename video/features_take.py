#!/usr/bin/env python3
"""What the newer Omacad can do: a narrated tour with a new part for every feature, and fillets shown before and
after. Films the whole window (ribbon, tree, timeline). Script: video/SCRIPT_ALL_FEATURES.md.

    .venv/bin/python video/features_take.py --out ~/Videos/omacad-features-silent.mp4
    .venv/bin/python video/music.py video/audio/music.flac --seconds 260
    .venv/bin/python video/narrate.py video/features/marks.json ~/Videos/omacad-features-silent.mp4 ~/Videos/omacad-features.mp4 --music video/audio/music.flac

Test without speech (5 s per scene, only some scenes, a few frames per second of video):
    .venv/bin/python video/features_take.py --dry --only fillet_hexagon,loft --out /tmp/x.mp4

The sentences in LINES are spoken first (ComfyUI must be running), so every scene lasts as long as its sentence.
Real display needed; the window goes fullscreen while it renders. Your Omarchy theme is never touched.
"""
import argparse
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

import narrate
from omacad.model.document import Document
from omacad.model.jar import JarSpec
from omacad.model.sketch import SketchPlane
from omacad.ui.main_window import MainWindow
from take import Take

OUTDIR = os.path.join(ROOT, "video", "features")
NARRATOR = ("A calm, clear female narrator in her twenties with a warm, friendly tone. Natural pace, "
            "relaxed and confident, like a software tutorial on YouTube.")

# Spoken text: names are respelled so the voice says them right (Omacad, CAD, Omarchy).
LINES = {
    "intro": "This is Oh-mah-cad, and here is what is new. Better fillets, new ways to make shapes, and more help for your prints.",
    "fillet_hexagon": "Fillets and chamfers now work on every corner angle. Here is a hexagon: sharp corners first, then a clean fillet on all six, and a chamfer on top. No notches, whatever the angle.",
    "fillet_rib": "Round the foot of a rib, and the fillet rolls round its outside corner like a rolling ball, so the sides flow into each other. Then bevel the top edge. The shapes meet in one clean line.",
    "fillet_cup": "Fillets also handle the hard cases. This cup gets a rounded rim, and then a honeycomb is cut right through the wall. The cells stay clean all the way round.",
    "loft": "Loft blends between profiles on different planes. From a rectangle to a circle, it makes one smooth skin instead of a hundred small faces.",
    "sweep": "Sweep pulls a profile along a path, with an optional twist. Pipe makes a tube along another path, solid or hollow. Click the path in the 3D view, edges of a body work too.",
    "twist": "Extrude can twist. The profile turns around its centre as it rises, which makes spiral vases and twisted columns in one step.",
    "emboss": "Emboss raises text from a flat face, or presses it in as a deboss. The letters are real profiles, so the holes in an O and an A stay open.",
    "split": "Tilt a plane at any angle to an axis, and split the body with it. The two halves are separate bodies you can move and rotate by numbers.",
    "circular": "Copy a whole feature around an axis. This rib with its fillet is repeated twelve times, and still rebuilds when you change it.",
    "jar": "Jar with Lid makes a threaded jar and a screw lid that really fits, ready to print. Slice it open with Section View to see the thread.",
    "end": "Oh-mah-cad is open source and free. Thanks for watching.",
}


def bounds(doc):
    """Centre and size of all visible bodies."""
    boxes = np.array([b.manifold.bounding_box() for b in doc.bodies.values()])
    lo, hi = boxes[:, :3].min(axis=0), boxes[:, 3:].max(axis=0)
    return (lo + hi) / 2.0, float(np.linalg.norm(hi - lo))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "features_silent.mp4"))
    ap.add_argument("--only", help="comma-separated scene names (LINES keys) to render")
    ap.add_argument("--dry", action="store_true", help="no speech: every scene lasts 5 s")
    args = ap.parse_args()
    names = [k for k in LINES if not args.only or k in args.only.split(",")]
    durations = {}
    for k in names:
        durations[LINES[k]] = 5.0 if args.dry else narrate.clip(LINES[k], voice=NARRATOR)[1]
    print("narration seconds:", round(sum(durations.values()), 1), flush=True)

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    app.setDesktopFileName("omacad-video")   # video/headless.sh sends windows of this class to a virtual monitor
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
        t = Take(app, win, OUTDIR, window=True)
        t.durations = durations

        def doc():
            return win.doc

        def cam(target, dist, az, el):
            v = win.viewport
            v.target, v.distance, v.azimuth, v.elevation = np.array(target, dtype=np.float32), dist, az, el
            v.update()

        def orbit(frames, degrees, bob=0.0):
            v = win.viewport
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

        def frame_all(az=35.0, el=28.0, k=1.5):
            c, size = bounds(doc())
            cam(c, size * k, az, el)
            return c, size

        def fly_all(az, el, k, frames=40):
            c, size = bounds(doc())
            t.fly(c, size * k, az, el, frames)

        def at_z(e, z):
            """True when the whole edge (line, circle or outline loop) lies at height z."""
            zs = [e.p0[2], e.p1[2]] if e.kind == "line" else [e.center[2]] if e.kind == "circle" else list(e.pts[:, 2])
            return all(abs(v - z) < 1e-6 for v in zs)

        def edges_where(body, pred):
            return [e.ref() for e in body.edges if pred(e)]

        def body():
            return next(iter(doc().bodies.values()))

        scenes = {}

        def scene(name):
            def deco(fn):
                scenes[name] = fn
                return fn
            return deco

        # ---- intro: the jar and its lid, turning ----
        @scene("intro")
        def intro():
            fresh()
            doc().add_jar(JarSpec())
            frame_all(25.0, 30.0, 1.2)
            t.shoot(10)
            t.scene("What is new in Omacad", LINES["intro"], lambda: orbit(int(durations[LINES["intro"]] * 30), 150, 5))

        # ---- fillets, before and after ----
        @scene("fillet_hexagon")
        def fillet_hexagon():
            fresh()
            d = doc()
            h = 30.0
            d.add_prism(40.0, h, sides=6)
            frame_all(30.0, 30.0, 1.6)

            def action():
                orbit(60, 40, 0)                                           # sharp corners first
                vertical = lambda e: e.kind == "line" and e.convex and abs(e.p1[2] - e.p0[2]) > h - 1
                f = d.add_fillet(edges_where(body(), vertical), 3.0)
                print("hexagon fillet skipped", f.skipped)
                fly_all(35.0, 25.0, 1.1, 40)
                orbit(75, 90, 0)
                top = lambda e: at_z(e, h)
                c = d.add_fillet(edges_where(body(), top), 1.5, "chamfer")
                print("hexagon chamfer skipped", c.skipped)
                fly_all(60.0, 40.0, 1.1, 30)
                orbit(75, 120, 3)

            t.scene("Fillet and chamfer on any corner angle", LINES["fillet_hexagon"], action)

        @scene("fillet_rib")
        def fillet_rib():
            fresh()
            d = doc()
            d.add_box(70.0, 50.0, 5.0)
            top = SketchPlane.from_face(np.array([0.0, 0, 1]), np.array([0.0, 0, 5.0]))
            sk = d.start_sketch_on_plane(top)
            sk.add_rect((10.0, 23.0), (60.0, 27.0))
            d.finish_sketch()
            idx = next(i for i, p in enumerate(sk.profiles) if len(p.exterior_pts) >= 4 and
                       abs(np.array(p.exterior_pts)[:, 0].mean() - 35.0) < 1.0)
            d.extrude_profile(sk.sketch_id, idx, 18.0, "join")
            frame_all(30.0, 35.0, 1.2)

            def action():
                orbit(50, 30, 0)
                foot = lambda e: e.kind == "line" and not e.convex and at_z(e, 5.0)
                f = d.add_fillet(edges_where(body(), foot), 4.0)
                print("rib foot skipped", f.skipped)
                t.fly((35.0, 25.0, 8.0), 70.0, 20.0, 30.0, 40)
                orbit(60, 70, 0)
                rim = lambda e: e.convex and at_z(e, 23.0)
                c = d.add_fillet(edges_where(body(), rim), 1.5, "chamfer")
                print("rib chamfer skipped", c.skipped)
                orbit(70, 110, 2)

            t.scene("Fillet at the foot of a rib", LINES["fillet_rib"], action)

        @scene("fillet_cup")
        def fillet_cup():
            fresh()
            d = doc()
            cup = d.add_cylinder(20.0, 45.0, wall_thickness=2.0)
            frame_all(30.0, 25.0, 1.15)

            def action():
                orbit(40, 30, 0)
                rim = lambda e: e.kind == "circle" and e.convex and at_z(e, 45.0) and e.radius > 19.0   # outer rim only
                f = d.add_fillet(edges_where(body(), rim), 1.0)
                print("cup fillet skipped", f.skipped)
                orbit(50, 60, 0)
                ref = {"kind": "cylinder", "origin": [0, 0, 0], "axis": [0, 0, 1], "radius": 20.0, "length": 45.0, "internal": False}
                hc = d.add_honeycomb(cup.body_id, [ref], shape="hexagon", size=7.0, wall=1.5, margin=5.0, depth=1.0,
                                     through=True, angle=0.0, partial=False)
                print("honeycomb cells", hc.cells if hc else None)
                orbit(120, 240, 4)

            t.scene("Rounded rim and honeycomb", LINES["fillet_cup"], action)

        # ---- loft ----
        @scene("loft")
        def loft():
            fresh()
            d = doc()
            a = d.start_sketch("XY")
            a.add_rect((-20.0, -14.0), (20.0, 14.0))
            d.finish_sketch()
            plane = d.construction_plane(d.add_construction_plane(d.origin_planes["XY"], 40.0, origin=(0, 0, 0)))
            b = d.start_sketch_on_plane(plane)
            b.add_circle((0.0, 0.0), 12.0)
            d.finish_sketch()
            cam((0.0, 0.0, 20.0), 140.0, 30.0, 30.0)

            def action():
                orbit(50, 30, 0)
                d.add_loft([(a.sketch_id, 0), (b.sketch_id, 0)])
                t.fly((0.0, 0.0, 20.0), 100.0, 60.0, 30.0, 40)
                orbit(100, 200, 4)

            t.scene("Loft: rectangle to circle", LINES["loft"], action)

        # ---- sweep and pipe ----
        @scene("sweep")
        def sweep():
            fresh()
            d = doc()
            prof = d.start_sketch("YZ")
            prof.add_rect((-5.0, -1.5), (5.0, 1.5))
            d.finish_sketch()
            path = d.start_sketch("XY")
            a = path.add_line((0.0, 0.0), (40.0, 0.0))
            arc = path.add_arc((40.0, 0.0), (40.0 + 25 * math.sin(math.pi / 4), 25 - 25 * math.cos(math.pi / 4)), (65.0, 25.0))
            d.finish_sketch()
            p2 = d.start_sketch("XY")
            b = p2.add_line((0.0, -30.0), (40.0, -30.0))
            arc2 = p2.add_arc((40.0, -30.0), (40.0 + 25 * math.sin(math.pi / 4), -30 + 25 * math.cos(math.pi / 4)), (65.0, -5.0))
            d.finish_sketch()
            cam((35.0, -2.0, 0.0), 120.0, 20.0, 40.0)

            def action():
                orbit(40, 15, 0)
                d.add_sweep(prof.sketch_id, 0, (path.sketch_id, [a.entity_id, arc.entity_id]), twist=180.0)
                orbit(60, 40, 0)
                d.add_pipe((p2.sketch_id, [b.entity_id, arc2.entity_id]), 8.0, 1.5)
                orbit(100, 90, 4)

            t.scene("Sweep with twist, and Pipe", LINES["sweep"], action)

        # ---- twisted extrude ----
        @scene("twist")
        def twist():
            fresh()
            d = doc()
            sk = d.start_sketch("XY")
            sk.add_polygon((0.0, 0.0), (16.0, 0.0), 6)
            d.finish_sketch()
            cam((0.0, 0.0, 25.0), 120.0, 30.0, 25.0)

            def action():
                orbit(30, 20, 0)
                d.extrude_profile(sk.sketch_id, 0, 50.0, "new_body", twist=120.0)
                t.fly((0.0, 0.0, 25.0), 105.0, 40.0, 20.0, 30)
                orbit(110, 220, 3)

            t.scene("Extrude with twist", LINES["twist"], action)

        # ---- emboss ----
        @scene("emboss")
        def emboss():
            fresh()
            d = doc()
            d.add_box(70.0, 30.0, 25.0)
            front = SketchPlane.from_face(np.array([0.0, -1, 0]), np.array([35.0, 0.0, 12.5]))
            sk = d.start_sketch_on_plane(front)
            sk.add_text("OMACAD", (3.0, 8.0), height=10.0)
            d.finish_sketch()
            sel = sk.text_profile_indices()    # the letters only: the counters inside O and A stay open
            c = np.array([35.0, 0.0, 12.5])
            cam(c, 110.0, -30.0, 20.0)

            def action():
                orbit(40, 30, 0)
                f = d.add_emboss(sk.sketch_id, sel[0], 1.5, extra_profiles=sel[1:])
                print("emboss profiles", sel, f)
                t.fly((35.0, 0.0, 12.5), 70.0, -10.0, 12.0, 40)
                orbit(90, 50, 2)

            t.scene("Emboss text on a face", LINES["emboss"], action)

        # ---- angled plane, split and move ----
        @scene("split")
        def split():
            fresh()
            d = doc()
            blk = d.add_box(60.0, 40.0, 30.0)
            frame_all(30.0, 25.0, 1.2)

            def action():
                orbit(30, 20, 0)
                mid = (30.0, 20.0, 15.0)
                pid = d.add_construction_plane(d.origin_planes["XY"], 15.0, origin=mid, angle=25.0, axis_point=mid, axis_dir=(1.0, 0.0, 0.0))
                orbit(50, 25, 0)
                d.split_body(blk.body_id, pid)
                ids = list(d.bodies)
                print("bodies after split", ids)
                t.shoot(20)
                d.move_body(ids[-1], dx=0.0, dy=0.0, dz=14.0, rx=0.0, ry=0.0, rz=40.0)
                fly_all(50.0, 25.0, 1.5, 40)
                orbit(90, 90, 3)

            t.scene("Plane at an angle, Split Body and Move", LINES["split"], action)

        # ---- circular feature pattern ----
        @scene("circular")
        def circular():
            fresh()
            d = doc()
            d.add_cylinder(20.0, 20.0, wall_thickness=2.0)
            sk = d.start_sketch("XY")
            sk.add_loop([(19, -1), (23, -1), (23, 1), (19, 1)], closed=True)
            d.finish_sketch()
            from shapely.geometry import Polygon
            idx = next(i for i, p in enumerate(sk.profiles) if Polygon(p.exterior_pts).centroid.x > 20)
            d.extrude_profile(sk.sketch_id, idx, 20.0, operation="join")
            rib = d.timeline.features[-1]
            edges = edges_where(body(), lambda e: e.kind == "line" and abs(e.p0[0] - 23) < 1e-4 and abs(e.p1[0] - 23) < 1e-4
                                and abs(e.p0[2] - e.p1[2]) > 19)
            fil = d.add_fillet(edges, 0.5)
            frame_all(30.0, 40.0, 1.5)

            def action():
                orbit(50, 40, 0)
                d.add_pattern([fil.feature_id, rib.feature_id], "circular", count1=12, about="body")
                fly_all(120.0, 35.0, 1.4, 30)
                orbit(100, 180, 3)

            t.scene("Circular feature pattern", LINES["circular"], action)

        # ---- jar with lid, section ----
        @scene("jar")
        def jar():
            fresh()
            d = doc()
            d.add_jar(JarSpec())
            frame_all(25.0, 30.0, 1.1)

            def action():
                orbit(50, 60, 0)
                c, size = bounds(d)
                sid = d.add_section(c, (0.0, -1.0, 0.0), -c[1] * 0.0 - 22.0)
                n = 150
                for i in range(n + 1):
                    k = i / n
                    d.sections[sid]["offset"] = -22.0 + 44.0 * (0.5 - 0.5 * math.cos(math.pi * k))
                    d.notify_changed()
                    win.viewport.azimuth = 25.0 + 30.0 * math.sin(math.pi * k)
                    win.viewport.update()
                    t.shoot()

            t.scene("Jar with Lid and Section View", LINES["jar"], action)

        @scene("end")
        def end():
            fresh()
            d = doc()
            d.add_jar(JarSpec())
            frame_all(25.0, 30.0, 1.2)
            t.scene("Omacad: open source and free", LINES["end"], lambda: orbit(int(durations[LINES["end"]] * 30) + 30, 70, 3))
            t.shoot(30)

        for name in names:
            scenes[name]()
        t.encode_scaled(args.out, "2560:1440")
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
