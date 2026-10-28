"""Compact, animated help for sketch constraints."""

import math

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget


HELP = {
    "HORIZONTAL": ("Horizontal", "Make a line level.", "Select a straight line in an active sketch.", "Choose a line, not a circle, arc or rectangle edge."),
    "VERTICAL": ("Vertical", "Make a line upright.", "Select a straight line in an active sketch.", "Choose a line, not a circle, arc or rectangle edge."),
    "PARALLEL": ("Parallel", "Align two lines in the same direction.", "Select two straight lines, one at a time.", "The first line is used as the reference."),
    "PERPENDICULAR": ("Perpendicular", "Make two lines meet at 90 degrees.", "Select two straight lines, one at a time.", "Choose lines that can move to meet at a right angle."),
    "EQUAL": ("Equal", "Match two line lengths or circle radii.", "Select two lines or two circles, one at a time.", "Use two items of the same type."),
    "TANGENT": ("Tangent", "Make two curves touch smoothly at one point.", "Select a line and circle, or two circles.", "Choose a supported line/circle pair."),
    "CONCENTRIC": ("Concentric", "Give two circles the same centre.", "Select two circles, one at a time.", "Choose circles in the active sketch."),
    "COINCIDENT": ("Coincident", "Join the nearest end points of two lines.", "Select two straight lines, one at a time.", "The closest pair of end points will be joined."),
    "MIDPOINT": ("Midpoint", "Place a line end or circle centre at a line's midpoint.", "Select the point-carrying line or circle, then the target line.", "The second selection must be the target line."),
    "SYMMETRIC": ("Symmetric", "Mirror two elements across a centre line.", "Select two lines (or two circles), then the mirror line.", "Choose matching geometry, then a straight mirror line."),
    "CENTER": ("Center", "Align the horizontal centres of two rectangles.", "Select the reference rectangle, then the rectangle to centre.", "Use a vertical distance dimension between edges to set the height offset."),
    "FIX": ("Fix", "Lock selected geometry in place.", "Select a line or circle in the active sketch.", "Only lines and circles can be fixed."),
}

GUIDE_STEPS = {
    "HORIZONTAL": ("Click a line",), "VERTICAL": ("Click a line",), "FIX": ("Click a line or circle",),
    "PARALLEL": ("Click the reference line", "Click another line"),
    "PERPENDICULAR": ("Click the first line", "Click the second line"),
    "EQUAL": ("Click a line or circle", "Click another of the same type"),
    "TANGENT": ("Click a line or circle", "Click a compatible second curve"),
    "CONCENTRIC": ("Click the first circle", "Click the second circle"),
    "COINCIDENT": ("Click the first line", "Click the second line"),
    "MIDPOINT": ("Click the line end or circle centre", "Click the target line"),
    "SYMMETRIC": ("Click the first line or circle", "Click a matching second element", "Click the mirror line"),
    "CENTER": ("Click a side of the reference rectangle", "Click a side of the rectangle to centre"),
}


class ConstraintHelp(QWidget):
    """Viewport child anchored at bottom-right; its small diagram animates the constraint idea."""

    dismissed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.ctype = None
        self.progress_text = ""
        self.phase = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self._tick)

    def begin_guide(self, ctype):
        if ctype not in HELP:
            return
        self.ctype = ctype
        self.set_progress(0)
        self.phase = 0.0
        self.show()
        self.raise_()
        self.timer.start()
        self.update()

    def set_progress(self, picked, error=None, done=False):
        steps = GUIDE_STEPS.get(self.ctype, ())
        if done:
            self.progress_text = (
                "Horizontal centres aligned. Add a vertical dimension between edges to set the offset."
                if self.ctype == "CENTER" else "Constraint applied. You can now adjust the sketch."
            )
        elif error:
            self.progress_text = error
        elif picked >= len(steps):
            self.progress_text = "Applying constraint…"
        else:
            self.progress_text = f"Step {picked + 1} of {len(steps)} · {steps[picked]}"
        self.update()

    def _tick(self):
        self.phase = (self.phase + 0.018) % 1.0
        self.update()

    def dismiss(self):
        self.timer.stop()
        self.hide()
        self.dismissed.emit()

    def paintEvent(self, _event):
        if not self.ctype:
            return
        title, summary, _step_hint, trouble = HELP[self.ctype]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(37, 40, 44, 248))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.setPen(QPen(QColor(76, 82, 91), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

        p.setPen(QColor(241, 151, 92))
        p.setFont(QFont("sans-serif", 10, QFont.Weight.DemiBold))
        p.drawText(16, 22, "SKETCH  ·  CONSTRAINT")
        p.setPen(QColor(231, 233, 236))
        p.setFont(QFont("sans-serif", 15, QFont.Weight.DemiBold))
        p.drawText(16, 45, title)
        p.setPen(QColor(165, 173, 182))
        p.setFont(QFont("sans-serif", 9))
        p.drawText(self.width() - 31, 28, "×")
        p.setPen(QPen(QColor(65, 70, 78), 1))
        p.drawLine(12, 57, self.width() - 12, 57)

        p.setPen(QColor(197, 203, 211))
        p.setFont(QFont("sans-serif", 10))
        p.drawText(QRectF(16, 67, self.width() - 32, 32), Qt.TextFlag.TextWordWrap, summary)
        self._draw_diagram(p, QRectF(16, 103, self.width() - 32, 122))

        p.setPen(QColor(231, 233, 236))
        p.setFont(QFont("sans-serif", 10, QFont.Weight.Medium))
        p.drawText(QRectF(16, 233, self.width() - 32, 43), Qt.TextFlag.TextWordWrap, self.progress_text)

        box = QRectF(12, self.height() - 62, self.width() - 24, 49)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(49, 53, 59))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor(231, 233, 236))
        p.setFont(QFont("sans-serif", 9, QFont.Weight.DemiBold))
        p.drawText(box.adjusted(9, 5, -7, -26), Qt.TextFlag.AlignVCenter, "If it doesn't work")
        p.setPen(QColor(187, 194, 202))
        p.setFont(QFont("sans-serif", 8))
        p.drawText(box.adjusted(9, 23, -7, -4), Qt.TextFlag.TextWordWrap, trouble)
        p.end()

    def _draw_diagram(self, p, box):
        ctype = self.ctype
        t = self.phase
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(31, 34, 38))
        p.drawRoundedRect(box, 7, 7)
        cx, cy = box.center().x(), box.center().y()
        left, right = box.left() + 35, box.right() - 35
        top, bottom = box.top() + 22, box.bottom() - 20
        pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * math.tau))
        orange = QColor(226, 109, 40)
        green = QColor(131, 200, 145)
        blue = QColor(97, 168, 232)
        dim = QColor(123, 132, 143)

        def line(a, b, color=orange, width=3):
            p.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(*a), QPointF(*b))

        def circle(x, y, r, color=orange, width=3):
            p.setPen(QPen(color, width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, y), r, r)

        if ctype in ("HORIZONTAL", "VERTICAL"):
            angle = (-16 * (1 - min(t * 1.4, 1))) if ctype == "HORIZONTAL" else (74 * (1 - min(t * 1.4, 1)))
            p.save(); p.translate(cx, cy); p.rotate(angle)
            line((-56, 0), (56, 0), orange)
            p.restore()
            line((cx - 56, 19), (cx + 56, 19), green, 2)
            p.setPen(QPen(QColor(131, 200, 145, int(255 * pulse)), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(cx - 62, cy + 19), QPointF(cx + 62, cy + 19))
        elif ctype == "PARALLEL":
            for y in (cy - 18, cy + 18): line((cx - 55, y + 18), (cx + 55, y - 18), green if y > cy else orange)
            p.setPen(QPen(blue, 2)); p.drawLine(QPointF(cx - 65, cy + 34), QPointF(cx + 65, cy + 34))
        elif ctype == "PERPENDICULAR":
            line((cx - 60, cy), (cx + 60, cy), orange)
            line((cx, cy + 42), (cx, cy - 42), green)
            p.setPen(QPen(blue, 2)); p.drawRect(QRectF(cx, cy - 12, 12, 12))
        elif ctype == "EQUAL":
            line((cx - 68, cy + 10), (cx - 12, cy - 10), orange)
            line((cx + 12, cy + 10), (cx + 68, cy - 10), green)
            p.setPen(QPen(blue, 2)); p.drawLine(QPointF(cx - 43, cy - 2), QPointF(cx - 38, cy + 12)); p.drawLine(QPointF(cx + 38, cy - 2), QPointF(cx + 43, cy + 12))
        elif ctype in ("TANGENT", "CONCENTRIC"):
            if ctype == "CONCENTRIC":
                circle(cx, cy, 35, orange); circle(cx, cy, 20, green)
            else:
                circle(cx - 20, cy, 25, orange)
                line((cx + 5, cy + 25), (cx + 65, cy + 25), green)
                p.setPen(QPen(blue, 5)); p.drawPoint(QPointF(cx + 5, cy + 25))
        elif ctype == "COINCIDENT":
            line((cx - 64, cy + 18), (cx, cy), orange)
            line((cx + 64, cy - 18), (cx, cy), green)
            p.setPen(QPen(blue, 6)); p.drawPoint(QPointF(cx, cy))
        elif ctype == "MIDPOINT":
            line((cx - 68, cy + 20), (cx + 68, cy + 20), dim, 2)
            line((cx, cy + 20), (cx, cy - 30), green, 2)
            circle(cx, cy - 30, 12, orange)
            p.setPen(QPen(blue, 5)); p.drawPoint(QPointF(cx, cy + 20))
        elif ctype == "SYMMETRIC":
            line((cx, cy - 43), (cx, cy + 43), blue, 2)
            line((cx - 5, cy), (cx - 48, cy - 24), orange)
            line((cx + 5, cy), (cx + 48, cy - 24), green)
            p.setPen(QPen(QColor(131, 200, 145, int(255 * pulse)), 1, Qt.PenStyle.DashLine)); p.drawLine(QPointF(cx - 48, cy - 24), QPointF(cx + 48, cy - 24))
        elif ctype == "CENTER":
            shift = 27 * (1.0 - min(t * 1.5, 1.0))
            p.setPen(QPen(green, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(cx - 62, cy - 37, 124, 74))
            p.setPen(QPen(orange, 2))
            p.drawRect(QRectF(cx - 25 + shift, cy + 7, 50, 30))
            p.setPen(QPen(blue, 1.5, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(cx, cy - 42), QPointF(cx, cy + 48))
            line((cx + shift - 7, cy + 22), (cx - 13, cy + 22), blue, 2)
        else:  # FIX
            line((cx - 42, cy + 20), (cx + 42, cy - 20), orange)
            p.setPen(QPen(green, 3)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx - 13, cy - 39, 26, 27), 0, 180 * 16)
            p.setBrush(green); p.drawRoundedRect(QRectF(cx - 18, cy - 26, 36, 33), 4, 4)
        p.setPen(QColor(150, 158, 167)); p.setFont(QFont("sans-serif", 8))
        p.drawText(QRectF(box.left() + 6, box.bottom() - 18, box.width() - 12, 14), Qt.AlignmentFlag.AlignRight, "illustration")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            close_area = QRectF(self.width() - 38, 7, 30, 29)
            if close_area.contains(event.position()):
                self.dismiss()
                event.accept()
                return
        event.accept()
