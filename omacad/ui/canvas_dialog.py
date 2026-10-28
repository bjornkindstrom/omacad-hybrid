"""
Omacad - Canvas / Reference Image Editor & Calibration Dialog
Allows importing an image onto a sketch plane, pre-editing (brightness, contrast, crop, rotate, flip),
calibrating with a virtual tape measure for tracing blueprints and sketches,
and setting an exact origin point (0, 0) on the reference image.
"""

import base64
import math
from io import BytesIO
from typing import Optional, Tuple
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QBrush,
    QFont, QTransform
)
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QSlider, QCheckBox, QComboBox, QDoubleSpinBox,
    QGroupBox, QFormLayout, QMessageBox, QWidget, QScrollArea, QSplitter
)
from omacad.model.document import Document
from omacad.ui.theme import style


class ImageCanvasWidget(QWidget):
    """Interactive canvas widget displaying the image with crop box, calibration tape measure, and origin point."""

    point_picked = Signal(float, float)
    origin_picked = Signal(float, float)
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.raw_image: Optional[QImage] = None
        self.processed_pixmap: Optional[QPixmap] = None
        self.crop_rect: Optional[QRectF] = None  # in image coords

        # Calibration state
        self.calibrate_mode: bool = False
        self.calib_pt1: Optional[QPointF] = None  # in pixel coords
        self.calib_pt2: Optional[QPointF] = None

        # Origin picking state
        self.origin_mode: bool = False
        self.origin_pt: Optional[QPointF] = None  # in pixel coords (ix, iy)

        # Crop drag state
        self.crop_mode: bool = False
        self.crop_start: Optional[QPointF] = None
        self.crop_current: Optional[QPointF] = None

        # Zoom & Pan state
        self.zoom: float = 1.0
        self.pan_offset: QPointF = QPointF(0.0, 0.0)
        self.is_panning: bool = False
        self.last_pan_pos: QPointF = QPointF(0.0, 0.0)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setMinimumSize(420, 420)
        style(self, "background-color: #1A1C1E; border: 1px solid #33373D; border-radius: 4px;")
        self.update_cursor()

    def update_cursor(self):
        if self.origin_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.calibrate_mode or self.crop_mode:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.processed_pixmap and not self.processed_pixmap.isNull():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                p = self.window()
                if hasattr(p, "load_image_file"):
                    p.load_image_file(path)
                    break
        event.acceptProposedAction()

    def set_pixmap(self, pix: QPixmap):
        self.processed_pixmap = pix
        self.update_cursor()
        self.update()

    def zoom_fit(self):
        self.zoom = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.25)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.25)

    def set_zoom(self, z: float):
        self.zoom = max(0.1, min(30.0, z))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event):
        if not self.processed_pixmap or self.processed_pixmap.isNull():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        new_zoom = max(0.1, min(30.0, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-4:
            return

        pos = event.position()
        w_half = self.width() / 2.0
        h_half = self.height() / 2.0

        rel_x = pos.x() - w_half - self.pan_offset.x()
        rel_y = pos.y() - h_half - self.pan_offset.y()
        ratio = new_zoom / self.zoom
        self.pan_offset = QPointF(
            pos.x() - w_half - rel_x * ratio,
            pos.y() - h_half - rel_y * ratio
        )
        self.zoom = new_zoom
        self.zoom_changed.emit(self.zoom)
        self.update()

    def image_to_widget_rect(self) -> QRectF:
        if not self.processed_pixmap or self.processed_pixmap.isNull():
            return QRectF()
        pw, ph = self.processed_pixmap.width(), self.processed_pixmap.height()
        ww, wh = self.width() - 16, self.height() - 16
        scale = min(ww / max(pw, 1), wh / max(ph, 1)) * self.zoom
        dw, dh = pw * scale, ph * scale
        dx = (self.width() - dw) / 2.0 + self.pan_offset.x()
        dy = (self.height() - dh) / 2.0 + self.pan_offset.y()
        return QRectF(dx, dy, dw, dh)

    def widget_to_image_coords(self, wx: float, wy: float) -> Optional[QPointF]:
        r = self.image_to_widget_rect()
        if r.isEmpty() or not r.contains(wx, wy):
            return None
        pw = self.processed_pixmap.width()
        ph = self.processed_pixmap.height()
        ix = (wx - r.x()) / r.width() * pw
        iy = (wy - r.y()) / r.height() * ph
        return QPointF(ix, iy)

    def image_to_widget_coords(self, ix: float, iy: float) -> QPointF:
        r = self.image_to_widget_rect()
        if r.isEmpty() or not self.processed_pixmap:
            return QPointF()
        pw = self.processed_pixmap.width()
        ph = self.processed_pixmap.height()
        wx = r.x() + (ix / pw) * r.width()
        wy = r.y() + (iy / ph) * r.height()
        return QPointF(wx, wy)

    def mousePressEvent(self, event):
        if not self.processed_pixmap or self.processed_pixmap.isNull():
            if event.button() == Qt.MouseButton.LeftButton:
                p = self.window()
                if hasattr(p, "choose_image"):
                    p.choose_image()
            return

        # Panning with middle button or right button or left button (when not in calibrate/crop/origin mode)
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) or (
            event.button() == Qt.MouseButton.LeftButton and not self.calibrate_mode and not self.crop_mode and not self.origin_mode
        ):
            self.is_panning = True
            self.last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            pt = self.widget_to_image_coords(event.position().x(), event.position().y())
            if not pt:
                return
            if self.origin_mode:
                self.origin_pt = pt
                self.origin_mode = False
                self.update_cursor()
                self.update()
                self.origin_picked.emit(pt.x(), pt.y())
            elif self.calibrate_mode:
                if self.calib_pt1 is None or self.calib_pt2 is not None:
                    self.calib_pt1 = pt
                    self.calib_pt2 = None
                else:
                    self.calib_pt2 = pt
                self.update()
                if self.calib_pt1 and self.calib_pt2:
                    self.point_picked.emit(self.calib_pt1.x(), self.calib_pt1.y())
            elif self.crop_mode:
                self.crop_start = pt
                self.crop_current = pt
                self.update()

    def mouseMoveEvent(self, event):
        if self.is_panning:
            delta = event.position() - self.last_pan_pos
            self.last_pan_pos = event.position()
            self.pan_offset = QPointF(self.pan_offset.x() + delta.x(), self.pan_offset.y() + delta.y())
            self.update()
            return

        if self.crop_mode and self.crop_start is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pt = self.widget_to_image_coords(event.position().x(), event.position().y())
            if pt:
                self.crop_current = pt
                self.update()

    def mouseReleaseEvent(self, event):
        if self.is_panning and event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton, Qt.MouseButton.LeftButton):
            self.is_panning = False
            self.update_cursor()
            return

        if self.crop_mode and self.crop_start and self.crop_current:
            x0 = min(self.crop_start.x(), self.crop_current.x())
            y0 = min(self.crop_start.y(), self.crop_current.y())
            x1 = max(self.crop_start.x(), self.crop_current.x())
            y1 = max(self.crop_start.y(), self.crop_current.y())
            if abs(x1 - x0) > 5 and abs(y1 - y0) > 5:
                self.crop_rect = QRectF(x0, y0, x1 - x0, y1 - y0)
            self.crop_start = None
            self.crop_current = None
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self.processed_pixmap or self.processed_pixmap.isNull():
            p.setPen(QColor(160, 168, 180))
            p.setFont(QFont("sans-serif", 12))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "📁 Click here or drop an image file\n(PNG, JPG, WEBP, BMP)\n\nYou can also click 'Choose image...' on the right")
            return

        img_rect = self.image_to_widget_rect()
        p.drawPixmap(img_rect.toRect(), self.processed_pixmap)

        # Draw Crop Box
        if self.crop_rect:
            p0 = self.image_to_widget_coords(self.crop_rect.x(), self.crop_rect.y())
            p1 = self.image_to_widget_coords(self.crop_rect.right(), self.crop_rect.bottom())
            r_crop = QRectF(p0, p1)
            p.setPen(QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine))
            p.setBrush(QBrush(QColor(0, 180, 255, 30)))
            p.drawRect(r_crop)
        elif self.crop_start and self.crop_current:
            p0 = self.image_to_widget_coords(min(self.crop_start.x(), self.crop_current.x()), min(self.crop_start.y(), self.crop_current.y()))
            p1 = self.image_to_widget_coords(max(self.crop_start.x(), self.crop_current.x()), max(self.crop_start.y(), self.crop_current.y()))
            p.setPen(QPen(QColor(0, 180, 255), 2, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(p0, p1))

        # Draw Calibration Tape Measure
        if self.calib_pt1:
            w1 = self.image_to_widget_coords(self.calib_pt1.x(), self.calib_pt1.y())
            p.setPen(QPen(QColor(255, 200, 0), 2))
            p.setBrush(QBrush(QColor(255, 200, 0)))
            p.drawEllipse(w1, 5, 5)

            if self.calib_pt2:
                w2 = self.image_to_widget_coords(self.calib_pt2.x(), self.calib_pt2.y())
                p.drawEllipse(w2, 5, 5)
                # Tape measure line
                p.setPen(QPen(QColor(255, 200, 0), 2, Qt.PenStyle.SolidLine))
                p.drawLine(w1, w2)
                # Cross ticks at ends
                dx, dy = w2.x() - w1.x(), w2.y() - w1.y()
                dist_px = math.hypot(dx, dy)
                if dist_px > 1e-3:
                    nx, ny = -dy / dist_px * 8, dx / dist_px * 8
                    p.drawLine(QPointF(w1.x() - nx, w1.y() - ny), QPointF(w1.x() + nx, w1.y() + ny))
                    p.drawLine(QPointF(w2.x() - nx, w2.y() - ny), QPointF(w2.x() + nx, w2.y() + ny))
                    mid = QPointF((w1.x() + w2.x()) / 2.0, (w1.y() + w2.y()) / 2.0 - 10)
                    raw_dist = math.hypot(self.calib_pt2.x() - self.calib_pt1.x(), self.calib_pt2.y() - self.calib_pt1.y())
                    p.setPen(QColor(255, 220, 50))
                    p.setFont(QFont("sans-serif", 10, QFont.Weight.Bold))
                    p.drawText(mid, f"📏 {raw_dist:.1f} px")

        # Draw Origin Crosshair Target
        if self.origin_pt:
            ow = self.image_to_widget_coords(self.origin_pt.x(), self.origin_pt.y())
            p.setPen(QPen(QColor(255, 60, 60), 2))
            p.setBrush(QBrush(QColor(255, 60, 60, 60)))
            p.drawEllipse(ow, 7, 7)
            # Cross lines
            p.setPen(QPen(QColor(255, 60, 60), 2, Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(ow.x() - 14, ow.y()), QPointF(ow.x() + 14, ow.y()))
            p.drawLine(QPointF(ow.x(), ow.y() - 14), QPointF(ow.x(), ow.y() + 14))
            # Text label
            p.setPen(QColor(255, 100, 100))
            p.setFont(QFont("sans-serif", 9, QFont.Weight.Bold))
            p.drawText(QPointF(ow.x() + 10, ow.y() - 8), "📍 Origo (0, 0)")


class CanvasEditorDialog(QDialog):
    """Full-featured editor dialog for importing, pre-processing, calibrating, and positioning reference canvases."""

    def __init__(
        self,
        doc: Document,
        parent=None,
        initial_image_path: Optional[str] = None,
        preselected_plane_id: Optional[str] = None,
        existing_canvas_id: Optional[str] = None,
        preselected_face=None,
    ):
        super().__init__(parent)
        self.doc = doc
        self.existing_canvas_id = existing_canvas_id
        is_edit = bool(existing_canvas_id and existing_canvas_id in doc.canvases)
        self.setWindowTitle("Edit Canvas (Reference Image)" if is_edit else "Insert Canvas (Reference Image)")
        self.resize(920, 660)
        style(self, "background-color: #22252A; color: #D0D5DD;")

        self.original_image: Optional[QImage] = None
        self.current_image: Optional[QImage] = None
        self.px_per_mm: float = 1.0  # calibration scale
        self.rotation_quarter: int = 0  # 0, 1, 2, 3 (90-deg steps)
        self.flip_h: bool = False
        self.flip_v: bool = False
        self._updating_spins: bool = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Left / Center: Interactive Image Viewer with Zoom Controls
        left_box = QWidget()
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Zoom & Navigation toolbar
        zoom_bar = QHBoxLayout()
        self.btn_zoom_in = QPushButton("🔍 +")
        self.btn_zoom_in.setToolTip("Zoom in (or scroll up with the mouse wheel)")
        self.btn_zoom_in.setFixedWidth(44)

        self.btn_zoom_out = QPushButton("🔍 −")
        self.btn_zoom_out.setToolTip("Zoom out (or scroll down with the mouse wheel)")
        self.btn_zoom_out.setFixedWidth(44)

        self.btn_zoom_100 = QPushButton("1:1")
        self.btn_zoom_100.setToolTip("Reset to 100% scale")
        self.btn_zoom_100.setFixedWidth(44)

        self.btn_zoom_fit = QPushButton("🔲 Anpassa")
        self.btn_zoom_fit.setToolTip("Fit the image to the window")

        self.lbl_zoom = QLabel("Zoom: 100%")
        self.lbl_zoom.setStyleSheet("font-weight: bold; color: #A0AAB8; min-width: 80px;")

        lbl_hint = QLabel("💡 Scroll: zoom • Drag: pan")
        lbl_hint.setStyleSheet("color: #717885; font-size: 11px;")

        zoom_bar.addWidget(self.btn_zoom_in)
        zoom_bar.addWidget(self.btn_zoom_out)
        zoom_bar.addWidget(self.btn_zoom_100)
        zoom_bar.addWidget(self.btn_zoom_fit)
        zoom_bar.addWidget(self.lbl_zoom)
        zoom_bar.addSpacing(10)
        zoom_bar.addWidget(lbl_hint)
        zoom_bar.addStretch()

        self.canvas_view = ImageCanvasWidget(self)

        self.btn_zoom_in.clicked.connect(self.canvas_view.zoom_in)
        self.btn_zoom_out.clicked.connect(self.canvas_view.zoom_out)
        self.btn_zoom_100.clicked.connect(lambda: self.canvas_view.set_zoom(1.0))
        self.btn_zoom_fit.clicked.connect(self.canvas_view.zoom_fit)
        self.canvas_view.zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"Zoom: {int(round(z * 100))}%"))

        left_layout.addLayout(zoom_bar)
        left_layout.addWidget(self.canvas_view, stretch=1)
        layout.addWidget(left_box, stretch=3)

        # Right: Tool Panel
        tools_widget = QWidget()
        tools_widget.setFixedWidth(360)
        tools_layout = QVBoxLayout(tools_widget)
        tools_layout.setContentsMargins(0, 0, 0, 0)
        tools_layout.setSpacing(10)

        # 1. File Group
        grp_file = QGroupBox("Bildfil")
        form_file = QVBoxLayout(grp_file)
        h_file_btns = QHBoxLayout()
        self.btn_load = QPushButton("📁 Choose image...")
        self.btn_load.clicked.connect(self.choose_image)
        h_file_btns.addWidget(self.btn_load)
        self.btn_paste = QPushButton("📋 Paste")
        self.btn_paste.setToolTip("Paste an image from the clipboard (Ctrl+V)")
        self.btn_paste.clicked.connect(self.paste_image_from_clipboard)
        h_file_btns.addWidget(self.btn_paste)
        form_file.addLayout(h_file_btns)
        self.lbl_file_info = QLabel("No file chosen")
        self.lbl_file_info.setWordWrap(True)
        form_file.addWidget(self.lbl_file_info)
        tools_layout.addWidget(grp_file)

        # 2. Calibration Group (measuring tape)
        grp_calib = QGroupBox("Kalibrera storlek (känd distans)")
        form_calib = QFormLayout(grp_calib)
        self.btn_calib = QPushButton("📏 Starta kalibrering")
        self.btn_calib.setCheckable(True)
        self.btn_calib.clicked.connect(self.toggle_calibrate)
        form_calib.addRow(self.btn_calib)

        self.spn_calib_dist = QDoubleSpinBox()
        self.spn_calib_dist.setRange(0.1, 100000.0)
        self.spn_calib_dist.setValue(100.0)
        self.spn_calib_dist.setSuffix(" mm")
        self.spn_calib_dist.setDecimals(2)
        self.spn_calib_dist.valueChanged.connect(self.apply_calibration)
        form_calib.addRow("Verklig längd:", self.spn_calib_dist)

        self.lbl_calib_status = QLabel("Klicka 2 punkter i bilden vars avstånd du känner till.")
        self.lbl_calib_status.setWordWrap(True)
        style(self.lbl_calib_status, "color: #9AA2B0; font-size: 11px;")
        form_calib.addRow(self.lbl_calib_status)
        tools_layout.addWidget(grp_calib)

        # 3. Origin Point Group (📍 Origo i bilden)
        grp_origin = QGroupBox("Origo (0, 0)")
        form_origin = QFormLayout(grp_origin)

        h_origin_btns = QHBoxLayout()
        self.btn_set_origin = QPushButton("📍 Sätt origo i bild")
        self.btn_set_origin.setCheckable(True)
        self.btn_set_origin.setToolTip("Klicka på en punkt i bilden som ska motsvara origo (0, 0)")
        self.btn_set_origin.clicked.connect(self.toggle_pick_origin)
        h_origin_btns.addWidget(self.btn_set_origin)

        self.btn_center_origin = QPushButton("🎯 Centrera")
        self.btn_center_origin.setToolTip("Återställ origo till bildens mittpunkt")
        self.btn_center_origin.clicked.connect(self.reset_origin_to_center)
        h_origin_btns.addWidget(self.btn_center_origin)
        form_origin.addRow(h_origin_btns)

        # Numerical Offset X / Y in mm
        h_offset = QHBoxLayout()
        self.spn_offset_x = QDoubleSpinBox()
        self.spn_offset_x.setRange(-100000.0, 100000.0)
        self.spn_offset_x.setValue(0.0)
        self.spn_offset_x.setSuffix(" mm")
        self.spn_offset_x.setDecimals(2)
        self.spn_offset_x.setToolTip("Horisontell position för bildens origo")
        self.spn_offset_x.valueChanged.connect(self.on_offset_spins_changed)

        self.spn_offset_y = QDoubleSpinBox()
        self.spn_offset_y.setRange(-100000.0, 100000.0)
        self.spn_offset_y.setValue(0.0)
        self.spn_offset_y.setSuffix(" mm")
        self.spn_offset_y.setDecimals(2)
        self.spn_offset_y.setToolTip("Vertikal position för bildens origo")
        self.spn_offset_y.valueChanged.connect(self.on_offset_spins_changed)

        h_offset.addWidget(QLabel("X:"))
        h_offset.addWidget(self.spn_offset_x)
        h_offset.addWidget(QLabel("Y:"))
        h_offset.addWidget(self.spn_offset_y)
        form_origin.addRow("Placering:", h_offset)

        self.lbl_origin_status = QLabel("Klicka 'Sätt origo' och klicka sedan på den punkt i bilden som ska hamna i origo.")
        self.lbl_origin_status.setWordWrap(True)
        style(self.lbl_origin_status, "color: #9AA2B0; font-size: 11px;")
        form_origin.addRow(self.lbl_origin_status)
        tools_layout.addWidget(grp_origin)

        # 4. Light & Color Adjustments (Light & Colour & Crop)
        grp_adj = QGroupBox("Ljus, Färg & Beskärning")
        form_adj = QFormLayout(grp_adj)

        self.sld_bright = QSlider(Qt.Orientation.Horizontal)
        self.sld_bright.setRange(-100, 100)
        self.sld_bright.setValue(0)
        self.sld_bright.valueChanged.connect(self.refresh_image_processing)
        form_adj.addRow("Ljusstyrka:", self.sld_bright)

        self.sld_contrast = QSlider(Qt.Orientation.Horizontal)
        self.sld_contrast.setRange(-100, 100)
        self.sld_contrast.setValue(0)
        self.sld_contrast.valueChanged.connect(self.refresh_image_processing)
        form_adj.addRow("Kontrast:", self.sld_contrast)

        self.chk_gray = QCheckBox("Svartvitt (gråskala)")
        self.chk_gray.toggled.connect(self.refresh_image_processing)
        form_adj.addRow(self.chk_gray)

        self.chk_invert = QCheckBox("Invertera färger (negativ)")
        self.chk_invert.toggled.connect(self.refresh_image_processing)
        form_adj.addRow(self.chk_invert)

        # Rotate & Flip buttons
        h_rot = QHBoxLayout()
        btn_rot = QPushButton("🔄 Rotera 90°")
        btn_rot.clicked.connect(self.rotate_image)
        btn_fliph = QPushButton("↔ Spegla H")
        btn_fliph.clicked.connect(self.flip_horizontal)
        h_rot.addWidget(btn_rot)
        h_rot.addWidget(btn_fliph)
        form_adj.addRow(h_rot)

        # Crop tool
        h_crop = QHBoxLayout()
        self.btn_crop_tool = QPushButton("✂ Markera beskärning")
        self.btn_crop_tool.setCheckable(True)
        self.btn_crop_tool.clicked.connect(self.toggle_crop)
        self.btn_apply_crop = QPushButton("Beskär nu")
        self.btn_apply_crop.clicked.connect(self.apply_crop)
        h_crop.addWidget(self.btn_crop_tool)
        h_crop.addWidget(self.btn_apply_crop)
        form_adj.addRow(h_crop)

        tools_layout.addWidget(grp_adj)

        # 5. Placement & Opacity Group
        grp_place = QGroupBox("Plan & Opacitet")
        form_place = QFormLayout(grp_place)

        self.cmb_plane = QComboBox()
        # Add origin planes
        for p in ("XY", "XZ", "YZ"):
            self.cmb_plane.addItem(f"🌐 {p} Plane", p)
        # Add construction planes
        for pid, cp in doc.construction_planes.items():
            self.cmb_plane.addItem(f"📐 {cp['name']}", pid)
        from omacad.model.canvas import face_plane_data
        for body in doc.bodies.values():
            if not body.visible:
                continue
            for face in body.faces:
                if face.index < 0:
                    continue
                self.cmb_plane.addItem(f"{body.name} — Face {face.index + 1}", face_plane_data(face))
        if preselected_face is not None:
            data = face_plane_data(preselected_face)
            self.cmb_plane.addItem("Selected face", data)
            self.cmb_plane.setCurrentIndex(self.cmb_plane.count() - 1)
        if preselected_plane_id:
            idx = self.cmb_plane.findData(preselected_plane_id)
            if idx >= 0:
                self.cmb_plane.setCurrentIndex(idx)
        form_place.addRow("Plan:", self.cmb_plane)

        self.sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self.sld_opacity.setRange(5, 100)
        self.sld_opacity.setValue(50)
        form_place.addRow("Opacitet:", self.sld_opacity)

        self.lbl_dims = QLabel("Storlek: - x - mm")
        form_place.addRow(self.lbl_dims)
        tools_layout.addWidget(grp_place)

        tools_layout.addStretch()

        # OK / Cancel
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Avbryt")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        self.btn_ok = QPushButton("Spara ändringar" if is_edit else "Infoga Canvas")
        self.btn_ok.setObjectName("PrimaryButton")
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_ok)
        tools_layout.addLayout(btn_box)

        layout.addWidget(tools_widget)
        from omacad.ui.numeric_slider import add_numeric_sliders
        add_numeric_sliders(tools_widget)

        self.canvas_view.point_picked.connect(self.on_points_picked)
        self.canvas_view.origin_picked.connect(self.on_origin_picked)

        if is_edit:
            self._load_existing_canvas(existing_canvas_id)
        elif initial_image_path:
            self.load_image_file(initial_image_path)

    def _load_existing_canvas(self, cid: str):
        c = self.doc.canvases.get(cid)
        if not c:
            return
        b64_data = c.get("image_data", "")
        if b64_data:
            raw_bytes = base64.b64decode(b64_data.encode("ascii"))
            img = QImage()
            if img.loadFromData(raw_bytes, "PNG"):
                self.original_image = img
                self.current_image = img.copy()
                self.lbl_file_info.setText(f"{c.get('name', 'Canvas')} ({img.width()}x{img.height()} px)")
                self.btn_ok.setEnabled(True)

                w_mm = float(c.get("width_mm", img.width()))
                if w_mm > 0 and img.width() > 0:
                    self.px_per_mm = img.width() / w_mm

                plane_id = c.get("plane_id", "XY")
                if c.get("face_plane"):
                    self.cmb_plane.addItem("Canvas face", c["face_plane"])
                    plane_id = c["face_plane"]
                idx = self.cmb_plane.findData(plane_id)
                if idx >= 0:
                    self.cmb_plane.setCurrentIndex(idx)

                op = float(c.get("opacity", 0.5))
                self.sld_opacity.setValue(int(round(op * 100)))

                ox, oy = c.get("origin_uv", [-w_mm / 2.0, -float(c.get("height_mm", img.height())) / 2.0])
                # ox = -x_orig_mm  =>  x_orig_mm = -ox
                # oy = -y_orig_mm  =>  y_orig_mm = -oy
                # In pixel coords:
                # x_orig_px = x_orig_mm * px_per_mm
                # y_orig_px = img.height() - y_orig_mm * px_per_mm
                x_orig_px = (-ox) * self.px_per_mm
                y_orig_px = img.height() - (-oy) * self.px_per_mm
                self.canvas_view.origin_pt = QPointF(x_orig_px, y_orig_px)
                self.update_origin_display()

                self.refresh_image_processing()

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Välj referensbild", "", "Bilder (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;Alla filer (*.*)"
        )
        if path:
            self.load_image_file(path)

    def paste_image_from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        img = cb.image()
        if not img.isNull():
            self.original_image = img
            self.current_image = img.copy()
            self.lbl_file_info.setText(f"Urklipp ({img.width()}x{img.height()} px)")
            self.rotation_quarter = 0
            self.flip_h = False
            self.flip_v = False
            self.px_per_mm = 1.0
            self.btn_ok.setEnabled(True)
            self.canvas_view.origin_pt = QPointF(img.width() / 2.0, img.height() / 2.0)
            self.refresh_image_processing()
            self.update_origin_display()
        else:
            QMessageBox.information(self, "Urklipp", "Ingen bild hittades i urklipp. Kopiera en bild eller ta en skärmdump först.")

    def load_image_file(self, path: str):
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Fel", f"Kunde inte ladda bilden:\n{path}")
            return
        self.original_image = img
        self.current_image = img.copy()
        import os
        self.lbl_file_info.setText(f"{os.path.basename(path)} ({img.width()}x{img.height()} px)")
        self.rotation_quarter = 0
        self.flip_h = False
        self.flip_v = False
        self.px_per_mm = 1.0  # default 1 px = 1 mm until calibrated
        self.btn_ok.setEnabled(True)
        self.canvas_view.origin_pt = QPointF(img.width() / 2.0, img.height() / 2.0)
        self.refresh_image_processing()
        self.update_origin_display()

    def toggle_calibrate(self, checked: bool):
        self.canvas_view.calibrate_mode = checked
        if checked:
            self.canvas_view.crop_mode = False
            self.canvas_view.origin_mode = False
            self.btn_crop_tool.setChecked(False)
            self.btn_set_origin.setChecked(False)
            self.lbl_calib_status.setText("Klicka punkt 1 och punkt 2 i bilden.")
        else:
            self.lbl_calib_status.setText("Kalibrering avslutad.")
        self.canvas_view.update_cursor()

    def on_points_picked(self, x, y):
        p1 = self.canvas_view.calib_pt1
        p2 = self.canvas_view.calib_pt2
        if p1 and p2:
            dist_px = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            self.lbl_calib_status.setText(f"Mätt: {dist_px:.1f} px. Ange verklig längd i fältet ovan.")
            self.apply_calibration()

    def apply_calibration(self):
        p1 = self.canvas_view.calib_pt1
        p2 = self.canvas_view.calib_pt2
        if p1 and p2:
            dist_px = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            mm = self.spn_calib_dist.value()
            if dist_px > 1.0 and mm > 0.01:
                self.px_per_mm = dist_px / mm
                self.update_dimension_labels()
                self.update_origin_display()

    def toggle_pick_origin(self, checked: bool):
        self.canvas_view.origin_mode = checked
        if checked:
            self.canvas_view.calibrate_mode = False
            self.canvas_view.crop_mode = False
            self.btn_calib.setChecked(False)
            self.btn_crop_tool.setChecked(False)
            self.lbl_origin_status.setText("📍 Klicka på den punkt i bilden som ska vara i origo (0, 0).")
        else:
            self.lbl_origin_status.setText("Origo-val avbrutet.")
        self.canvas_view.update_cursor()

    def on_origin_picked(self, x: float, y: float):
        self.btn_set_origin.setChecked(False)
        self.lbl_origin_status.setText(f"Origo satt till punkt ({x:.1f}, {y:.1f}) px.")
        self.update_origin_display()

    def reset_origin_to_center(self):
        if not self.current_image:
            return
        self.canvas_view.origin_pt = QPointF(self.current_image.width() / 2.0, self.current_image.height() / 2.0)
        self.canvas_view.update()
        self.lbl_origin_status.setText("Origo centrerat till mitten av bilden.")
        self.update_origin_display()

    def update_origin_display(self):
        if not self.current_image:
            return
        orig = self.canvas_view.origin_pt or QPointF(self.current_image.width() / 2.0, self.current_image.height() / 2.0)
        # Origin offset from bottom-left corner in mm
        x_orig_mm = orig.x() / max(self.px_per_mm, 1e-4)
        y_orig_mm = (self.current_image.height() - orig.y()) / max(self.px_per_mm, 1e-4)

        self._updating_spins = True
        self.spn_offset_x.setValue(x_orig_mm)
        self.spn_offset_y.setValue(y_orig_mm)
        self._updating_spins = False

    def on_offset_spins_changed(self):
        if self._updating_spins or not self.current_image:
            return
        x_mm = self.spn_offset_x.value()
        y_mm = self.spn_offset_y.value()
        px = x_mm * self.px_per_mm
        py = self.current_image.height() - y_mm * self.px_per_mm
        self.canvas_view.origin_pt = QPointF(px, py)
        self.canvas_view.update()

    def update_dimension_labels(self):
        if not self.current_image:
            return
        w_mm = self.current_image.width() / max(self.px_per_mm, 1e-4)
        h_mm = self.current_image.height() / max(self.px_per_mm, 1e-4)
        self.lbl_dims.setText(f"Storlek: {w_mm:.1f} x {h_mm:.1f} mm\n({self.px_per_mm:.2f} px/mm)")

    def rotate_image(self):
        self.rotation_quarter = (self.rotation_quarter + 1) % 4
        self.canvas_view.origin_pt = None
        self.refresh_image_processing()
        self.update_origin_display()

    def flip_horizontal(self):
        self.flip_h = not self.flip_h
        self.canvas_view.origin_pt = None
        self.refresh_image_processing()
        self.update_origin_display()

    def toggle_crop(self, checked: bool):
        self.canvas_view.crop_mode = checked
        if checked:
            self.canvas_view.calibrate_mode = False
            self.canvas_view.origin_mode = False
            self.btn_calib.setChecked(False)
            self.btn_set_origin.setChecked(False)
        self.canvas_view.update_cursor()

    def apply_crop(self):
        if not self.canvas_view.crop_rect or not self.current_image:
            return
        cr = self.canvas_view.crop_rect
        ix, iy, iw, ih = int(cr.x()), int(cr.y()), int(cr.width()), int(cr.height())
        ix = max(0, min(self.current_image.width() - 1, ix))
        iy = max(0, min(self.current_image.height() - 1, iy))
        iw = max(1, min(self.current_image.width() - ix, iw))
        ih = max(1, min(self.current_image.height() - iy, ih))

        self.current_image = self.current_image.copy(ix, iy, iw, ih)
        self.original_image = self.current_image.copy()
        self.canvas_view.crop_rect = None
        self.btn_crop_tool.setChecked(False)
        self.canvas_view.crop_mode = False
        self.canvas_view.origin_pt = None
        self.canvas_view.update_cursor()
        self.canvas_view.zoom_fit()
        self.refresh_image_processing()
        self.update_origin_display()

    def refresh_image_processing(self):
        if not self.original_image:
            return

        # 1. Start with copy
        img = self.original_image.copy()

        # 2. Rotation & Flip
        if self.rotation_quarter != 0 or self.flip_h:
            t = QTransform()
            if self.rotation_quarter:
                t.rotate(self.rotation_quarter * 90)
            if self.flip_h:
                t.scale(-1, 1)
            img = img.transformed(t)

        # 3. Grayscale
        if self.chk_gray.isChecked():
            img = img.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(QImage.Format.Format_ARGB32)
        else:
            img = img.convertToFormat(QImage.Format.Format_ARGB32)

        # 4. Brightness & Contrast adjustment
        bright = self.sld_bright.value()
        contrast = self.sld_contrast.value()
        invert = self.chk_invert.isChecked()

        if bright != 0 or contrast != 0 or invert:
            cf = (contrast + 100.0) / 100.0 if contrast >= 0 else (100.0 + contrast) / 100.0
            cf = cf * cf if contrast >= 0 else cf
            b_offset = bright * 2.55

            lut = bytearray(256)
            for i in range(256):
                val = i
                if invert:
                    val = 255 - val
                val = (val - 128) * cf + 128 + b_offset
                lut[i] = max(0, min(255, int(val)))

            bits = img.bits()
            import numpy as np
            arr = np.frombuffer(bits, dtype=np.uint8).reshape((img.height(), img.bytesPerLine()))
            lut_arr = np.array(lut, dtype=np.uint8)
            arr[:, 0:img.width()*4:4] = lut_arr[arr[:, 0:img.width()*4:4]]
            arr[:, 1:img.width()*4:4] = lut_arr[arr[:, 1:img.width()*4:4]]
            arr[:, 2:img.width()*4:4] = lut_arr[arr[:, 2:img.width()*4:4]]

        self.current_image = img
        pix = QPixmap.fromImage(img)
        self.canvas_view.set_pixmap(pix)
        self.update_dimension_labels()

    def get_canvas_data(self) -> dict:
        """Returns the finalized canvas properties to be added or updated in Document."""
        if not self.current_image:
            return {}

        w_mm = self.current_image.width() / max(self.px_per_mm, 1e-4)
        h_mm = self.current_image.height() / max(self.px_per_mm, 1e-4)
        plane_id = self.cmb_plane.currentData()

        # Origin UV coordinates so that the picked origin point is at (0, 0)
        orig = self.canvas_view.origin_pt
        if orig is not None:
            # Distance from bottom-left corner of the image in mm
            x_orig_mm = orig.x() / max(self.px_per_mm, 1e-4)
            y_orig_mm = (self.current_image.height() - orig.y()) / max(self.px_per_mm, 1e-4)
            origin_u = -float(x_orig_mm)
            origin_v = -float(y_orig_mm)
        else:
            origin_u = -float(w_mm / 2.0)
            origin_v = -float(h_mm / 2.0)

        # Convert image to Base64 PNG
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.current_image.save(buffer, "PNG")
        b64 = ba.toBase64().data().decode("ascii")

        return {
            "name": "Canvas (Face)" if isinstance(plane_id, dict) else f"Canvas ({plane_id})",
            "plane_id": "FACE" if isinstance(plane_id, dict) else plane_id,
            "face_plane": plane_id if isinstance(plane_id, dict) else None,
            "image_data": b64,
            "width_mm": float(w_mm),
            "height_mm": float(h_mm),
            "origin_uv": [origin_u, origin_v],
            "rotation_deg": 0.0,
            "opacity": self.sld_opacity.value() / 100.0,
            "visible": True,
        }
