"""The dialog behind 'Report problem': write what is wrong, zoom into the screenshot and draw where the problem is."""
import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QApplication, QFileDialog, QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

MARK_COLOUR = QColor(255, 45, 45)
MARK_WIDTH = 5.0           # in screenshot pixels, so marks look the same at any zoom
Mark = Tuple[str, List[QPointF]]   # (tool, points in screenshot coordinates)


def draw_mark(painter: QPainter, mark: Mark, width: float = MARK_WIDTH) -> None:
    tool, pts = mark
    if not pts:
        return
    painter.setPen(QPen(MARK_COLOUR, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    a, b = pts[0], pts[-1]
    if tool == "pen":
        painter.drawPolyline(QPolygonF(pts) if len(pts) > 1 else QPolygonF([a, a + QPointF(0.1, 0.1)]))
    elif tool == "rect":
        painter.drawRect(QRectF(a, b).normalized())
    elif tool == "arrow":
        painter.drawLine(a, b)
        d = b - a
        n = math.hypot(d.x(), d.y())
        if n > 1e-6:
            ux, uy = d.x() / n, d.y() / n
            head = min(28.0, max(12.0, n * 0.3))
            for sgn in (1, -1):
                ang = math.radians(150) * sgn
                cs, sn = math.cos(ang), math.sin(ang)
                painter.drawLine(b, QPointF(b.x() + head * (ux * cs - uy * sn), b.y() + head * (ux * sn + uy * cs)))


class MarkableImage(QWidget):
    """A screenshot you can zoom (mouse wheel, around the pointer), pan (middle or right button, or Ctrl+drag)
    and draw on (pen, rectangle, arrow). Marks live in screenshot coordinates."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        # A grab on a scaled (HiDPI) screen has devicePixelRatio > 1: pixmap.width() counts real pixels but drawPixmap draws it
        # smaller, so the fitted picture ended up too small (zoomed out). Work in real pixels throughout.
        self.pixmap = QPixmap(pixmap)
        self.pixmap.setDevicePixelRatio(1.0)
        self.marks: List[Mark] = []
        self.tool = "pen"
        self.scale = 1.0
        self.offset = QPointF(0, 0)
        self._current: Optional[Mark] = None
        self._pan_from: Optional[QPointF] = None
        self._fitted = False
        self.setMinimumSize(320, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(False)

    # ---- coordinates -------------------------------------------------------------
    def to_image(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self.offset.x()) / self.scale, (p.y() - self.offset.y()) / self.scale)

    def fit(self) -> None:
        if self.pixmap.isNull() or self.width() < 2 or self.height() < 2:
            return
        self.scale = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        self.offset = QPointF((self.width() - self.pixmap.width() * self.scale) / 2,
                              (self.height() - self.pixmap.height() * self.scale) / 2)
        self._fitted = True
        self.update()

    def zoom_at(self, pos: QPointF, factor: float) -> None:
        """Zoom so that the screenshot point under `pos` stays under it."""
        anchor = self.to_image(pos)
        self.scale = max(0.05, min(40.0, self.scale * factor))
        self.offset = QPointF(pos.x() - anchor.x() * self.scale, pos.y() - anchor.y() * self.scale)
        self.update()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Shows another picture (marks belong to the old one, so they go)."""
        self.pixmap = QPixmap(pixmap)
        self.pixmap.setDevicePixelRatio(1.0)
        self.marks.clear()
        self._fitted = False
        self.fit()

    # ---- marks --------------------------------------------------------------------
    def undo(self) -> None:
        if self.marks:
            self.marks.pop()
            self.update()

    def clear(self) -> None:
        self.marks.clear()
        self.update()

    def annotated_image(self) -> QImage:
        """The screenshot with the marks drawn on it."""
        img = self.pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for m in self.marks:
            draw_mark(p, m)
        p.end()
        return img

    # ---- events -------------------------------------------------------------------
    def resizeEvent(self, event):
        if not self._fitted or not self.marks:
            self.fit()
        super().resizeEvent(event)

    def wheelEvent(self, event):
        self.zoom_at(event.position(), 1.25 if event.angleDelta().y() > 0 else 0.8)

    def mouseDoubleClickEvent(self, event):
        self.fit()

    def mousePressEvent(self, event):
        pos = event.position()
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) or \
                (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._pan_from = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            self._current = (self.tool, [self.to_image(pos)])

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._pan_from is not None:
            self.offset += pos - self._pan_from
            self._pan_from = pos
            self.update()
        elif self._current is not None:
            tool, pts = self._current
            if tool == "pen":
                pts.append(self.to_image(pos))
            else:
                self._current = (tool, [pts[0], self.to_image(pos)])
            self.update()

    def mouseReleaseEvent(self, event):
        if self._pan_from is not None:
            self._pan_from = None
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._current is not None:
            self.marks.append(self._current)
            self._current = None
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(30, 32, 36))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.scale < 1.0)   # crisp pixels when zoomed in
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.offset)
        p.scale(self.scale, self.scale)
        p.drawPixmap(0, 0, self.pixmap)
        for m in self.marks + ([self._current] if self._current else []):
            draw_mark(p, m)


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, screenshot: QPixmap = None, mode: str = "report"):
        """mode "report": a problem, handed to the AI agent. mode "request": a wish for a change, sent to GitHub for review."""
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("Request a change" if mode == "request" else "Report problem")
        # Fit the screen: on a small or scaled (Windows) display a fixed 1000x760 pushed the text box and buttons out of sight.
        from PySide6.QtGui import QGuiApplication
        scr = (parent.screen() if parent is not None else QGuiApplication.primaryScreen()) or QGuiApplication.primaryScreen()
        avail = scr.availableGeometry() if scr is not None else None
        self.resize(min(1000, int(avail.width() * 0.9)) if avail else 1000, min(760, int(avail.height() * 0.9)) if avail else 760)
        lay = QVBoxLayout(self)
        if mode == "request":
            lay.addWidget(QLabel("What would you like to change or add? Describe it in a few sentences. The screenshot, the model "
                                 "and the log are sent along so it is easy to understand. Zoom with the mouse wheel and draw "
                                 "what you mean."))
        else:
            lay.addWidget(QLabel("What is wrong? A sentence is enough. The screenshot, the model and the log are sent along. "
                                 "Zoom with the mouse wheel and draw where the problem is."))
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, QLabel):
                w.setWordWrap(True)
        self.image: Optional[MarkableImage] = None
        self._attachments: List[Tuple[str, QImage]] = []
        self._note_label = QLabel("<b>Your message:</b> (type in the framed box below)")
        if screenshot is not None and not screenshot.isNull():
            tools = QHBoxLayout()
            group = QButtonGroup(self)
            self.image = MarkableImage(screenshot)
            for key, label in (("pen", "✏️ Pen"), ("rect", "▭ Rectangle"), ("arrow", "➚ Arrow")):
                b = QToolButton()
                b.setText(label)
                b.setCheckable(True)
                b.setChecked(key == "pen")
                b.clicked.connect(lambda _=False, k=key: setattr(self.image, "tool", k))
                group.addButton(b)
                tools.addWidget(b)
            self._builtin = QPixmap(screenshot)
            self.own = False
            for label, slot in (("Undo mark", lambda: self.image.undo()), ("Clear marks", lambda: self.image.clear()),
                                ("Fit", lambda: self.image.fit()), ("Use my own image…", self.choose_own_image),
                                ("Paste image from clipboard", self.paste_own_image),
                                ("Use the screenshot", self.use_builtin_image)):
                b = QPushButton(label)
                b.clicked.connect(slot)
                tools.addWidget(b)
            if mode == "request":
                b = QPushButton("Add images…")
                b.clicked.connect(self.choose_attachments)
                tools.addWidget(b)
            tools.addStretch()
            lay.addLayout(tools)
            hint = QLabel("Wheel = zoom · middle/right button or Ctrl+drag = move · double-click = fit")
            hint.setWordWrap(True)
            lay.addWidget(hint)
            lay.addWidget(self.image, 1)
        self.note = QPlainTextEdit()
        self.note.setStyleSheet("QPlainTextEdit { border: 2px solid #E26D28; border-radius: 4px; }")
        self.note.setPlaceholderText("e.g. I would like to be able to ..." if mode == "request"
                                     else "e.g. the corner of the offset is not rounded like the original")
        self.note.setMinimumHeight(90)
        self.note.setMaximumHeight(140)
        lay.addWidget(self._note_label)
        lay.addWidget(self.note)

        from omacad.ui.settings import get_settings
        from omacad import feedback
        self.settings = get_settings()

        self.chk_fix = QCheckBox("Let the AI fix it now:")
        self.chk_fix.setChecked(True)
        self.chk_fix.setToolTip("Opens the coding agent in a terminal with the report. Untick to only save the report.")

        from PySide6.QtWidgets import QComboBox
        self.cmb_agent = QComboBox()
        cur_agent = self.settings.get("ai_agent", "omarchy")
        for key, name in feedback.available_agents():
            self.cmb_agent.addItem(name, key)
        idx = self.cmb_agent.findData(cur_agent)
        if idx >= 0:
            self.cmb_agent.setCurrentIndex(idx)
        self.chk_fix.toggled.connect(self.cmb_agent.setEnabled)

        fix_row = QHBoxLayout()
        fix_row.addWidget(self.chk_fix)
        fix_row.addWidget(self.cmb_agent)
        fix_row.addStretch()

        self.edt_name = QLineEdit()
        if mode == "request":
            self.chk_fix.setVisible(False)
            self.cmb_agent.setVisible(False)
            self.edt_name.setPlaceholderText("Your name (so the owner knows who asked)")
            self.edt_name.setText(str(self.settings.get("rfc_name") or ""))
            lay.addWidget(self.edt_name)
            sent = QLabel("Sent to the owner of Omacad on GitHub: your text, the screenshot, the model and the log of this session.")
            sent.setWordWrap(True)
            lay.addWidget(sent)
        else:
            lay.addLayout(fix_row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Send request" if mode == "request" else "Report")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.note.setFocus()

    def choose_own_image(self) -> None:
        """Replaces the built-in screenshot with a picture from the user's computer (marks can be drawn on it)."""
        path, _ = QFileDialog.getOpenFileName(self, "Choose an image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)")
        if not path:
            return
        pix = QPixmap(path)
        if pix.isNull():
            self._note_label.setText("<b>That file could not be read as an image.</b> Choose a PNG or JPEG.")
            return
        self.image.set_pixmap(pix)
        self.own = True

    def paste_own_image(self) -> None:
        """Uses an image copied from another application as the request image."""
        clipboard = QApplication.clipboard()
        image = clipboard.image()
        if image.isNull():
            pixmap = clipboard.pixmap()
            if not pixmap.isNull():
                image = pixmap.toImage()
        if image.isNull():
            self._note_label.setText("<b>No image found in the clipboard.</b> Copy a screenshot first.")
            return
        self.image.set_pixmap(QPixmap.fromImage(image))
        self.own = True

    def choose_attachments(self) -> None:
        """Adds several images alongside the screenshot to a change request."""
        paths, _ = QFileDialog.getOpenFileNames(self, "Add images to request", "",
                                                "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)")
        for path in paths:
            pix = QPixmap(path)
            if not pix.isNull():
                from pathlib import Path
                self._attachments.append((Path(path).name, pix.toImage()))
        self._note_label.setText(f"<b>Your message:</b> ({len(self._attachments)} additional image(s) attached)")

    def additional_images(self) -> List[Tuple[str, QImage]]:
        return list(self._attachments)

    def use_builtin_image(self) -> None:
        self.image.set_pixmap(self._builtin)
        self.own = False

    def own_image(self) -> Optional[QImage]:
        """The user's own picture (with the drawing on it), or None while the built-in screenshot is used."""
        return self.image.annotated_image() if self.image is not None and self.own else None

    def selected_agent(self) -> str:
        return str(self.cmb_agent.currentData() or "omarchy")

    def text(self) -> str:
        return self.note.toPlainText().strip()

    def name(self) -> str:
        return self.edt_name.text().strip()

    def fix_now(self) -> bool:
        return self.chk_fix.isChecked()

    def marked_image(self) -> Optional[QImage]:
        """The screenshot with the user's drawing, or None when nothing was drawn."""
        return self.image.annotated_image() if self.image is not None and self.image.marks else None
