#!/usr/bin/env python3
"""Frame-exact how-to: make a thread looser with Offset Face (the jar and lid from report 20261016-212334).
Hide the lid, look at the thread in a section view, click the thread, type -0.2, OK, look again.

    .venv/bin/python video/offset_thread_take.py --out ~/Videos/omacad-offset-face-gänga.mp4
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.ui.main_window import MainWindow
from take import Take


class WindowTake(Take):
    """Films the whole window with the panels that float over the 3D view (Browser, tool panel): the view is drawn
    first, then each floating panel on top of it, as the user sees it."""

    def _grab(self):
        from PySide6.QtCore import QEvent, QRect
        from PySide6.QtGui import QPainter
        from PySide6.QtWidgets import QWidget
        for _ in range(3):
            self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        img = self.win.grab().toImage()
        fb = self.vp.grabFramebuffer()
        off = self.vp.mapTo(self.win, QPoint(0, 0))
        p = QPainter(img)
        p.drawImage(QRect(off.x(), off.y(), self.vp.width(), self.vp.height()), fb)
        for w in self.vp.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if w.isVisible():
                pos = w.mapTo(self.win, QPoint(0, 0))
                p.drawPixmap(pos, w.grab())
        p.end()
        return img

OUTDIR = os.path.join(ROOT, "video", "offset_thread")
DOC = os.path.join(ROOT, "tests", "data", "offset_face_coil_stuck.omacad")
WORK = ((0.0, 0.0, 15.0), 17.0, 193.3, 22.0)        # target, distance, azimuth, elevation
CLOSE = ((-11.0, 0.0, 15.0), 9.0, 180.0, 0.0)       # straight at the cut face, left wall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(OUTDIR, "offset_thread.mp4"))
    args = ap.parse_args()
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
            _run(app, win, args.out)
        except Exception:
            import traceback
            traceback.print_exc()
        app.quit()

    QTimer.singleShot(1500, run)
    app.exec()


def _run(app, win, out):
    doc = Exporter.load_project(DOC)
    doc.timeline.features.pop()                       # the old mesh offset from the report
    doc.timeline.marker_index = len(doc.timeline.features)
    doc.timeline.recompute(doc)
    win.attach_document(doc)
    vp = win.viewport
    for sid in doc.sections:
        doc.set_section_active(sid, True)
    vp.target = np.array(WORK[0], dtype=np.float32)
    vp.distance, vp.azimuth, vp.elevation = WORK[1:]
    vp.update()
    t = WindowTake(app, win, OUTDIR, window=True)
    off = vp.mapTo(win, QPoint(0, 0))

    def to_view(widget, pt):
        p = widget.mapTo(win, pt) - off
        return np.array([p.x(), p.y()], dtype=float)

    def glide_px(px, frames=24):
        a = np.array([t.cursor.x(), t.cursor.y()])
        for i in range(1, frames + 1):
            k = i / frames
            k = k * k * (3 - 2 * k)
            t.cursor = QPointF(*(a + (np.asarray(px) - a) * k))
            if 0 <= t.cursor.x() < vp.width() and 0 <= t.cursor.y() < vp.height():
                t.move_event((t.cursor.x(), t.cursor.y()))
            t.shoot()

    def wait(ms):
        QTest.qWait(ms)

    t.say("Locket ligger inne i burken och skymmer gängan")
    t.shoot(60)

    # 1. hide the lid with its eye
    t.say("1. Dölj Locket: klicka på ögat bredvid Locket i Browser")
    tree = win.browser.tree
    item = next(it for it in tree.findItems("Locket", __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MatchFlag.MatchRecursive))
    rect = tree.visualItemRect(item)
    eye = to_view(tree.viewport(), QPoint(tree.columnViewportPosition(1) + 12, rect.center().y()))
    glide_px(eye, 30)
    t.shoot(10)
    win.browser.toggle_visibility("body", "body_cylinder_1")
    wait(100)
    t.shoot(45)

    # 2. a look at the thread before
    t.say("Så här ser gängan ut före (section view)")
    t.fly(*CLOSE, frames=45)
    t.shoot(60)
    t.fly(*WORK, frames=45)

    # 3. Offset Face
    t.say("2. Starta Offset Face (Modify > Offset Face)")
    t.shoot(20)
    win.prompt_offset_face()
    wait(200)
    t.shoot(40)
    dlg = win.inspector.current_tool_dlg
    t.say("Guiden finns i panelen till höger (Bigger gör den större)")
    t.shoot(75)
    # a spot on the thread, found the way the user would: where a click picks the thread
    got = []
    vp.offset_face_picked.connect(lambda ref, bid: got.append((ref, bid)))
    spot = None
    for y in range(int(vp.height() * 0.30), int(vp.height() * 0.55), 12):
        for x in range(int(vp.width() * 0.40), int(vp.width() * 0.60), 12):
            got.clear()
            surf = vp._pick_surface(float(x), float(y))
            if surf is not None and doc._thread_offset([{"kind": "surface", "point": list(surf["point"]),
                                                         "normal": list(surf["normal"])}]) is not None:
                spot = (x, y)
                break
        if spot:
            break
    t.say("3. Klicka på gängan i burken")
    glide_px(spot, 36)
    t.shoot(10)
    vp._offset_face_click(float(spot[0]), float(spot[1]))
    wait(800)
    t.shoot(40)

    t.say("4. Skriv -0.2 (minus = lösare passning)")
    le = dlg.spn_dist.lineEdit()
    glide_px(to_view(le, le.rect().center()), 24)
    le.selectAll()
    text = ""
    for ch in "-0.2":
        text += ch
        le.setText(text)
        t.shoot(8)
    dlg.spn_dist.interpretText()
    wait(900)
    t.say("Står det 'Thread 1 coil' i panelen har du klickat rätt")
    t.shoot(90)

    t.say("5. Tryck OK")
    ok = next(b for b in dlg.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
              if b.text() == "OK")
    glide_px(to_view(ok, ok.rect().center()), 30)
    t.shoot(10)
    dlg.accept()
    wait(800)
    t.shoot(30)

    t.say("Klart: spåret är bredare och väggen är slät")
    t.fly(*CLOSE, frames=45)
    t.shoot(120)
    t.encode_scaled(out)


if __name__ == "__main__":
    main()
