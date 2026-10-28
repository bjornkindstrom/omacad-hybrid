#!/usr/bin/env python3
"""Stills for the Omacad web page: one picture per feature card, taken in the real app (whole window, fullscreen),
cropped to the 3D view, or the view plus the side panel, or a dialog.

    .venv/bin/python video/stills.py                 # all, into video/stills/*.png
    .venv/bin/python video/stills.py --only smart_circle,fill_pattern

Each still is made in its own try/except, so one broken scene does not stop the rest. Real display needed; the
window goes fullscreen for a couple of minutes. The Omarchy theme is never changed.
"""
import argparse
import math
import os
import sys
import traceback
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QSurfaceFormat
from PySide6.QtWidgets import QApplication, QDialog

from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.ui import theme
from omacad.ui.main_window import MainWindow
from take import Take

OUT = Path(ROOT) / "video" / "stills"
THEME_DIR = Path("/usr/share/omarchy/themes")


class Quiet(Take):
    """A Take that films nothing: only the input helpers (glide, type_number, enter ...) are used."""
    def shoot(self, n=1): self.app.processEvents()
    def hold(self, n): pass
    def say(self, text): pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = [s for s in args.only.split(",") if s]
    fmt = QSurfaceFormat(); fmt.setSamples(4); fmt.setDepthBufferSize(24); fmt.setStencilBufferSize(8)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.showFullScreen()
    OUT.mkdir(parents=True, exist_ok=True)

    def run():
        for _ in range(10):
            app.processEvents()
        t = Quiet(app, win, str(OUT / "_frames"), window=True)
        W = Ctx(app, win, t)
        results = {}
        for name, fn in SCENES:
            if only and name not in only:
                continue
            try:
                fn(W)
                results[name] = "ok"
            except Exception:
                results[name] = "FAILED"
                traceback.print_exc()
            finally:
                W.cleanup()
        print("RESULTS", results, flush=True)
        app.quit()

    QTimer.singleShot(1500, run)
    sys.exit(app.exec())


class Ctx:
    """Everything a scene needs: the window, input helpers, grabbing and saving."""
    def __init__(self, app, win, t):
        self.app, self.win, self.t = app, win, t

    @property
    def vp(self): return self.win.viewport
    @property
    def doc(self): return self.win.doc

    def pump(self, n=6):
        for _ in range(n):
            self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def fresh(self, edges=False):
        self.cleanup()
        self.win.attach_document(Document(), None)
        self.win.doc.auto_include_edges = edges
        self.vp.set_preview(None)
        self.pump()
        return self.win.doc

    def cleanup(self):
        for d in self.win.findChildren(QDialog):
            if d.isVisible():
                d.reject()
        self.vp.set_preview(None)
        try:
            self.vp.set_sketch_tool("NONE")
        except Exception:
            pass
        self.vp.pick_step_mode = False
        self.vp.measure = None
        self.pump(3)

    def cam(self, target, dist, az, el):
        v = self.vp
        v.target, v.distance, v.azimuth, v.elevation = np.array(target, dtype=np.float32), dist, az, el
        v.update()
        self.pump()

    def img(self):
        self.t.cursor = QPointF(-50, -50)
        self.pump()
        return self.t._grab()

    def view_rect(self):
        o = self.vp.mapTo(self.win, QPoint(0, 0))
        return QRect(o, self.vp.size())

    def crop(self, img, rect):
        r = 1.25 if abs(img.devicePixelRatio() - 1.25) < 0.01 else img.devicePixelRatio()
        return img.copy(int(rect.x() * r), int(rect.y() * r), int(rect.width() * r), int(rect.height() * r))

    def save(self, name, image):
        OUT.mkdir(parents=True, exist_ok=True)
        image.save(str(OUT / f"{name}.png"))
        print("saved", name, image.width(), image.height(), flush=True)

    def save_view(self, name):
        self.save(name, self.crop(self.img(), self.view_rect()))

    def save_view_panel(self, name):
        """The 3D view plus the right-hand inspector column."""
        v = self.view_rect()
        panel = self.win.inspector.mapTo(self.win, QPoint(0, 0))
        rect = QRect(v.x(), v.y(), panel.x() + self.win.inspector.width() - v.x(), v.height())
        self.save(name, self.crop(self.img(), rect))

    def save_window(self, name):
        self.save(name, self.img())

    def save_widget(self, name, widget):
        self.pump()
        self.save(name, widget.grab().toImage())

    def with_dialog(self, open_fn, capture_fn, delay=1500):
        """Open a tool panel (some block in their own event loop, some return at once), capture while it is open, close it."""
        from PySide6.QtCore import QEventLoop
        done = []
        loop = QEventLoop()

        def later():
            try:
                capture_fn()
            finally:
                done.append(1)
                for d in self.win.findChildren(QDialog):
                    if d.isVisible():
                        d.reject()
                loop.quit()
        QTimer.singleShot(delay, later)
        open_fn()
        if not done:
            loop.exec()

    # ---- input through the viewport's own handlers ----
    def tool(self, name):
        self.vp.set_sketch_tool(name)
        self.vp.setFocus()

    def move_to(self, uv):
        self.t.move_event(self.t.uv_to_px(uv))
        self.pump(3)

    def click(self, uv):
        self.t.press(uv)

    def type_enter(self, s, enter=True):
        self.t.type_number(s, per_key=1)
        if enter:
            self.t.enter(1)
        self.pump(3)

    def plane_top(self, z):
        return SketchPlane.from_face(np.array([0.0, 0, 1]), np.array([0.0, 0, z]))


SCENES = []


def scene(fn):
    SCENES.append((fn.__name__, fn))
    return fn


# =====================================================================================================================
@scene
def sketch_anywhere(W):
    d = W.fresh(edges=True)
    d.add_box(60, 40, 12)
    sk = d.start_sketch_on_plane(W.plane_top(12))
    sk.add_rect((8, 8), (30, 24))
    sk.add_circle((44, 20), 7.0)
    sk.add_line((8, 32), (52, 32))
    W.cam((30, 20, 12), 115, 25, 52)
    W.save_view("sketch_anywhere")


@scene
def type_numbers(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    W.vp.align_to_plane(sk.plane)
    W.cam((30, 20, 0), 72, 0, 89.9)
    W.tool("RECT")
    W.move_to((-8, -6)); W.click((0, 0)); W.move_to((40, 25))
    W.type_enter("60"); W.type_enter("40", enter=False)
    W.save_view("type_numbers")


def smart_sequence(W, circles):
    """Rounded rectangle 60 x 40 plus Smart Circles typed with numbers; returns the sketch."""
    d = W.fresh()
    sk = d.start_sketch("XY")
    W.vp.align_to_plane(sk.plane)
    W.cam((30, 20, 0), 72, 0, 89.9)
    W.tool("ROUNDED_RECT")
    W.move_to((-8, -6)); W.click((0, 0)); W.move_to((40, 25))
    for s in ("60", "40", "8"):
        W.type_enter(s)
    W.tool("SMART_CIRCLE")
    for dia, a_uv, a, b_uv, b in circles:
        W.move_to((a_uv[0] + 4, a_uv[1] + 4))
        W.type_enter(dia)
        W.move_to(a_uv); W.type_enter(a)
        W.move_to(b_uv); W.type_enter(b)
    return sk


@scene
def dimensions(W):
    smart_sequence(W, [("6", (3, 12), "8", (12, 3), "8"), ("8", (57, 26), "8", (46, 37), "6")])
    W.tool("NONE")
    W.save_view("dimensions")


@scene
def smart_circle(W):
    smart_sequence(W, [("6", (3, 12), "8", (12, 3), "8")])
    W.cam((30, 20, 0), 56, 0, 89.9)
    W.tool("SMART_CIRCLE")
    W.move_to((42, 26)); W.type_enter("8")
    W.move_to((57, 26)); W.type_enter("8", enter=False)
    W.save_view("smart_circle")


@scene
def rounded_rect(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    W.vp.align_to_plane(sk.plane)
    W.cam((30, 20, 0), 72, 0, 89.9)
    W.tool("ROUNDED_RECT")
    W.move_to((-8, -6)); W.click((0, 0)); W.move_to((40, 25))
    W.type_enter("60"); W.type_enter("40"); W.type_enter("12", enter=False)
    W.save_view("rounded_rect")


def plate_with_holes(W, fill=False, cylinder=False):
    d = W.fresh()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (60, 40), 8.0)
    sk.add_circle((8, 8), 3.0)
    d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 8.0)
    return d


@scene
def extrude_arrow(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    sk.add_rounded_rect((0, 0), (60, 40), 8.0)
    d.finish_sketch()
    d.selected_profile = (sk.sketch_id, 0)
    W.cam((30, 20, 4), 95, 30, 40)
    W.with_dialog(lambda: W.win.prompt_extrude(), lambda: (W.save_view("extrude_arrow"), W.save_view_panel("side_panel")), 1800)


@scene
def revolve(W):
    d = W.fresh()
    sk = d.start_sketch("XZ")
    pts = [(0, 0), (22, 0), (22, 6), (14, 26), (17, 44), (0, 44)]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        sk.add_line(a, b)
    d.finish_sketch()
    d.selected_profile = (sk.sketch_id, 0)
    W.cam((6, 0, 22), 120, 30, 20)
    W.with_dialog(lambda: W.win.prompt_revolve(), lambda: W.save_view_panel("revolve"), 1800)


@scene
def shell(W):
    d = W.fresh()
    d.add_box(50, 40, 30)
    body = next(iter(d.bodies.values()))
    d.add_shell(body.body_id, 3.0, [{"normal": [0, 0, 1], "origin": [0, 0, 30]}])
    W.cam((25, 20, 15), 120, 35, 50)
    W.save_view("shell")


@scene
def fillet_chamfer(W):
    d = W.fresh()
    d.add_box(60, 40, 10)
    top = W.plane_top(10)
    sk = d.start_sketch_on_plane(top); sk.add_circle((15, 20), 5.0); d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, -11.0, "cut")
    body = next(iter(d.bodies.values()))
    circ = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 10.0) < 1e-6 and abs(e.radius - 5.0) < 0.3]
    d.add_fillet(circ, 1.5, "chamfer")
    body = next(iter(d.bodies.values()))
    outline = [e.ref() for e in body.edges if e.kind == "line" and abs(e.p0[2] - 10.0) < 1e-6 and abs(e.p1[2] - 10.0) < 1e-6 and e.convex]
    if outline:
        d.add_fillet(outline, 2.5, "fillet")
    W.cam((30, 20, 8), 105, 30, 42)
    W.save_view("fillet_chamfer")


@scene
def pattern_mirror(W):
    d = plate_with_holes(W)
    body = next(iter(d.bodies.values()))
    edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.3]
    d.add_fillet(edges, 1.0, "chamfer")
    d.timeline.recompute(d)
    from omacad.model.timeline import PatternFeature
    from omacad.ui.dialogs import PatternDialog
    dlg = PatternDialog(d, W.win)

    def preview():
        ids = dlg.source_ids()
        feat = PatternFeature("tmp", "tmp", ids, dlg.kind(), **dlg.get_params())
        for bid in list(d.bodies):
            res = feat.compute(d, bid)
            if res is None:
                continue
            rem, add = res
            W.vp.set_preview(rem if rem is not None else add, "cut" if rem is not None else "join", extra=add if rem is not None else None, extra_op="join")
            dlg.lbl_info.setText(f"{feat.copies} copies will be made.")
            break

    dlg.changed.connect(preview)
    W.win.dock(dlg); dlg.show()
    dlg.cmb_kind.setCurrentIndex(1)
    dlg.cmb_mirror.setCurrentIndex(3)
    W.cam((30, 20, 4), 85, 30, 45)
    W.pump(10)
    W.save_view_panel("pattern_mirror")


@scene
def section_view(W):
    d = plate_with_holes(W)
    sk = d.start_sketch_on_plane(W.plane_top(8)); sk.add_circle((38, 20), 7.0); d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 14.0, "join")
    d.add_section((0, 0, 0), (0, 1, 0), 20.0)
    W.cam((30, 20, 8), 100, 30, 28)
    W.save_view("section_view")


@scene
def pick_faces(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    sk.add_circle((0, 0), 24.0); sk.add_circle((0, 0), 14.0); sk.add_circle((0, 0), 6.0)
    d.finish_sketch()
    sk = d.sketches[sk.sketch_id]
    profs = sorted(range(len(sk.profiles)), key=lambda i: -abs(getattr(sk.profiles[i], "area", 0)))
    d.selected_profile = (sk.sketch_id, profs[0] if profs else 0)
    d.selected_extra = [(sk.sketch_id, profs[-1])] if len(profs) > 1 else []
    W.cam((0, 0, 0), 85, 20, 55)
    W.save_view("pick_faces")


@scene
def offset_sketch(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    ents = sk.add_rounded_rect((0, 0), (60, 40), 8.0)
    W.vp.align_to_plane(sk.plane)
    W.cam((30, 20, 0), 72, 0, 89.9)
    ids = [e.entity_id for e in sk.entities]
    sk.offset_entities(ids, -4.0)
    sk.offset_entities(ids, -8.0)
    d.notify_changed()
    W.save_view("offset_sketch")


@scene
def offset_plane(W):
    d = plate_with_holes(W)
    pid = d.add_construction_plane(d.origin_planes["XY"], 22.0, "Plane 1")
    W.cam((30, 20, 8), 120, 35, 35)
    W.save_view("offset_plane")


@scene
def parameters(W):
    d = plate_with_holes(W)
    from omacad.model.document import Parameter
    d.set_parameters([Parameter("plate_w", "60", "width of the plate"), Parameter("plate_h", "plate_w * 2 / 3", "height follows the width"),
                      Parameter("hole_d", "6", "mounting hole"), Parameter("edge", "plate_w / 7.5", "distance from the edge")])
    from omacad.ui.parameters_dialog import ParametersDialog
    dlg = ParametersDialog(d, W.win)
    dlg.show(); W.pump(10)
    W.save_widget("parameters", dlg)
    dlg.close()


@scene
def timeline(W):
    d = plate_with_holes(W)
    body = next(iter(d.bodies.values()))
    edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.3]
    ch = d.add_fillet(edges, 1.0, "chamfer")
    ext = [f for f in d.timeline.features if f.feature_type == "extrude"][0]
    d.add_pattern([ext.feature_id, ch.feature_id], "mirror", mirror_mode="xy")
    hs = d.start_sketch_on_plane(W.plane_top(8)); hs.add_polygon((30, 20), (33, 20), 6); d.finish_sketch()
    d.extrude_profile(hs.sketch_id, 0, -9.0, "cut")
    W.cam((30, 20, 4), 90, 30, 45)
    W.pump(10)
    img = W.img()
    bar = W.win.timeline_bar.mapTo(W.win, QPoint(0, 0))
    v = W.view_rect()
    W.save("timeline", W.crop(img, QRect(v.x(), v.y() + 80, v.width(), bar.y() + W.win.timeline_bar.height() - v.y() - 80)))


@scene
def fill_pattern(W):
    d = plate_with_holes(W)
    sk = d.start_sketch_on_plane(W.plane_top(8)); sk.add_circle((38, 20), 5.0); d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 12.0, "join")
    hs = d.start_sketch_on_plane(W.plane_top(8)); hs.add_polygon((14, 30), (17, 30), 6); d.finish_sketch()
    d.extrude_profile(hs.sketch_id, 0, -9.0, "cut")
    cut = [f for f in d.timeline.features if f.feature_type == "extrude"][-1]
    d.add_pattern([cut.feature_id], "fill", spacing1=1.5, spacing2=3.0, count1=0.0, mirror_mode="stagger")
    W.cam((30, 20, 6), 95, 235, 55)
    W.save_view("fill_pattern")


@scene
def measure(W):
    d = plate_with_holes(W)
    W.cam((30, 20, 6), 95, 30, 50)
    W.vp.begin_measure()
    body = next(iter(d.bodies.values()))
    edges = [e for e in body.edges if e.kind == "line"]
    picks = []
    for e in edges:
        if abs(e.p0[2] - 8) < 1e-6 and abs(e.p1[2] - 8) < 1e-6:
            picks.append(e)
    # click two straight top edges through the viewport
    for e in picks[:2]:
        mid = (np.asarray(e.p0) + np.asarray(e.p1)) / 2.0
        p = W.vp.world_to_screen(mid)
        W.vp._measure_click(p[0], p[1])
    W.pump(6)
    W.save_view_panel("measure")


@scene
def move_lay(W):
    d = plate_with_holes(W)
    W.cam((30, 20, 6), 110, 30, 40)
    W.with_dialog(lambda: W.win.prompt_move_body(), lambda: W.save_view_panel("move_lay"), 1800)


@scene
def rotate_gizmo(W):
    d = plate_with_holes(W)
    W.cam((30, 20, 4), 105, 30, 40)
    W.with_dialog(lambda: W.win.prompt_move_body(), lambda: W.save_view_panel("rotate_gizmo"), 1800)


@scene
def place_primitive(W):
    d = plate_with_holes(W)
    W.cam((30, 20, 4), 105, 30, 40)
    W.with_dialog(lambda: W.win.prompt_box(), lambda: W.save_view_panel("place_primitive"), 1800)


@scene
def icon_sets(W):
    from omacad.ui.settings import get_settings
    st = get_settings()
    old = st.get("icon_theme", "solid")
    imgs = []
    try:
        plate_with_holes(W)
        W.cam((30, 20, 4), 105, 30, 40)
        for name in ("solid", "blueprint", "semantic"):
            st.set("icon_theme", name)
            W.win.on_theme_changed(); W.pump(8)
            imgs.append(W.win.ribbon.grab().toImage())
    finally:
        st.set("icon_theme", old)
        W.win.on_theme_changed(); W.pump(4)
    w, h = max(i.width() for i in imgs), imgs[0].height()
    out = QImage(w, h * 3, QImage.Format.Format_RGB32)
    p = QPainter(out)
    for i, im in enumerate(imgs):
        p.drawImage(0, i * h, im)
    p.end()
    W.save("icon_sets", out)


@scene
def face_edges(W):
    d = W.fresh(edges=True)
    d.add_box(60, 40, 12)
    sk = d.start_sketch_on_plane(W.plane_top(12))
    d.refresh_sketch_references(sk) if hasattr(d, "refresh_sketch_references") else None
    sk.add_circle((30, 20), 6.0)
    W.cam((30, 20, 12), 100, 20, 60)
    W.save_view("face_edges")


@scene
def trim_mirror(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    sk.add_line((0, 0), (20, 0)); l2 = sk.add_line((20, 0), (20, 12)); sk.add_line((20, 12), (8, 24)); sk.add_arc((8, 24), (3, 20), (0, 12)) if False else None
    ids = [e.entity_id for e in sk.entities]
    sk.mirror_entities(ids, (0, -5), (0, 30))
    W.vp.align_to_plane(sk.plane)
    W.cam((0, 12, 0), 72, 0, 89.9)
    W.save_view("trim_mirror")


@scene
def sketch_fillet(W):
    d = W.fresh()
    sk = d.start_sketch("XY")
    a = sk.add_line((0, 0), (50, 0)); b = sk.add_line((50, 0), (50, 30)); c = sk.add_line((50, 30), (0, 30)); e = sk.add_line((0, 30), (0, 0))
    sk.fillet_corner(a, b, 8.0); sk.fillet_corner(b, c, 8.0); sk.fillet_corner(c, e, 3.0)
    W.vp.align_to_plane(sk.plane)
    W.cam((25, 15, 0), 70, 0, 89.9)
    W.save_view("sketch_fillet")


@scene
def themes(W):
    d = plate_with_holes(W)
    W.cam((30, 20, 4), 88, 30, 45)
    imgs = []
    old = theme.COLORS_FILE
    try:
        for name in ("tokyo-night", "catppuccin-latte", "gruvbox", "osaka-jade"):
            theme.COLORS_FILE = THEME_DIR / name / "colors.toml"
            theme.refresh(); W.pump(6)
            imgs.append(W.win.grab().toImage())
    finally:
        theme.COLORS_FILE = old
        theme.refresh()
    sw, sh = imgs[0].width(), imgs[0].height()
    out = QImage(sw, sh, QImage.Format.Format_RGB32)
    p = QPainter(out)
    for i, im in enumerate(imgs):
        r = QRect((i % 2) * sw // 2, (i // 2) * sh // 2, sw // 2, sh // 2)
        p.drawImage(r, im)
    p.end()
    W.save("themes", out)


@scene
def theme_choice(W):
    from omacad.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(W.win)
    dlg.show(); dlg.tabs.setCurrentIndex(0); W.pump(10)
    W.save_widget("theme_choice", dlg)
    dlg.close()


@scene
def camera(W):
    from omacad.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(W.win)
    dlg.show(); dlg.tabs.setCurrentIndex(1); W.pump(10)
    W.save_widget("camera", dlg)
    dlg.close()


def menu_image(W, index):
    bar = W.win.menuBar()
    menu = bar.actions()[index].menu()
    menu.adjustSize()
    return menu.grab().toImage()


@scene
def save_export(W):
    d = plate_with_holes(W)
    W.cam((30, 20, 4), 100, 30, 45)
    view = W.crop(W.img(), W.view_rect())
    m = menu_image(W, 0)
    out = view.copy()
    p = QPainter(out)
    p.drawImage(QPoint(out.width() - m.width() - 30, 30), m)
    p.end()
    W.save("save_export", out)


@scene
def undo_redo(W):
    d = plate_with_holes(W)
    body = next(iter(d.bodies.values()))
    edges = [e.ref() for e in body.edges if e.kind == "circle" and abs(e.center[2] - 8.0) < 1e-6 and abs(e.radius - 3.0) < 0.3]
    d.add_fillet(edges, 1.0, "chamfer")
    W.cam((30, 20, 4), 100, 30, 45)
    view = W.crop(W.img(), W.view_rect())
    m = menu_image(W, 1)
    out = view.copy()
    p = QPainter(out)
    p.drawImage(QPoint(out.width() - m.width() - 30, 30), m)
    p.end()
    W.save("undo_redo", out)


def feedback_shot(W, mode, name, text, who=""):
    from PySide6.QtGui import QPixmap
    from omacad.ui.feedback_dialog import FeedbackDialog
    d = plate_with_holes(W)
    W.cam((30, 20, 4), 95, 30, 45)
    shot = QPixmap.fromImage(W.img())
    dlg = FeedbackDialog(W.win, shot, mode=mode)
    dlg.show(); W.pump(10)
    if dlg.image is not None:                      # a red ring round the hole and an arrow, as a user would draw
        from PySide6.QtCore import QPointF as P
        s = shot.width(), shot.height()
        dlg.image.marks = [("rect", [P(s[0] * 0.30, s[1] * 0.40), P(s[0] * 0.42, s[1] * 0.58)]), ("arrow", [P(s[0] * 0.20, s[1] * 0.25), P(s[0] * 0.30, s[1] * 0.42)])]
        dlg.image.update()
    dlg.note.setPlainText(text)
    if who:
        dlg.edt_name.setText(who)
    W.pump(10)
    W.save_widget(name, dlg)
    dlg.close()


@scene
def report_problem(W):
    feedback_shot(W, "report", "report_problem", "The hole near the corner is cut through the rounded edge.")


@scene
def request_change(W):
    feedback_shot(W, "request", "request_change", "I would like to copy a hole along a curve, not only in straight lines.", "Anna")


if __name__ == "__main__":
    main()
