"""
Omacad - Right-Hand Inspector & Tool Host Panel
Provides a persistent right-hand dock for tool dialogs (Extrude, Fillet, Shell, etc.)
and displays live properties for bodies, sketches, measurements, and document statistics,
eliminating intrusive floating windows that block the 3D model.
"""

from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QGroupBox, QFormLayout
)
from omacad.model.document import Document
from omacad.ui import theme
from omacad.ui.theme import style


class InspectorPanel(QWidget):
    """Right-hand side panel hosting active tool dialogs and live model/sketch properties."""

    width_fitted = Signal(int)                   # the panel's new width (the ViewCube keeps clear of it)

    MIN_WIDTH, MAX_WIDTH, EDGE_GAP = 200, 380, 10

    def __init__(self, doc: Document, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.max_height = 10_000          # set by the main window: the room the panel may use

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header Bar (subtle floating card-style header)
        self.header = QWidget()
        style(self.header, "background-color: rgba(32, 34, 37, 0.85); border: 1px solid #33373D; border-radius: 6px; margin: 4px; padding: 4px 8px;",
              "QWidget { background: transparent; border: none; margin: 4px 4px 0 4px; padding: 6px 8px 0 8px; }")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(8, 4, 8, 4)
        self.lbl_title = QLabel("INSPECTOR")
        style(self.lbl_title, "font-weight: bold; font-size: 11px; color: #8E95A0; letter-spacing: 0.5px; background: transparent;",
              "QLabel { color: @muted; font-size: 11px; font-weight: 600; letter-spacing: 1px; margin: 0; padding: 0; }")
        h_layout.addWidget(self.lbl_title)
        h_layout.addStretch()
        main_layout.addWidget(self.header)

        # Scroll Area for Content (transparent so only actual cards/dialogs show backgrounds)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        style(self.scroll, "QScrollArea { background: transparent; border: none; }")

        self.content_widget = QWidget()
        self.content_widget.setObjectName("InspectorContent")
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        style(self.content_widget, "QWidget#InspectorContent { background: transparent; }")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        self.content_layout.setSpacing(8)

        self.setObjectName("InspectorPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        style(self, "QWidget#InspectorPanel { background: transparent; }",
              "QWidget#InspectorPanel { background-color: @surface; border: 1px solid @border; border-radius: 8px; }")

        # 1. Tool Dock Container (when a tool/dialog is active)
        self.tool_container = QWidget()
        self.tool_layout = QVBoxLayout(self.tool_container)
        self.tool_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_layout.setSpacing(6)
        self.tool_container.hide()
        self.content_layout.addWidget(self.tool_container)

        # Sketch palette slot (filled by set_palette; shown only while a sketch is open)
        self.palette_layout = QVBoxLayout()
        self.palette_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addLayout(self.palette_layout)

        # What the mouse rests on (a sketch line, a solid edge): its measures, shown above the context info
        self.hover_layout = QVBoxLayout()
        self.hover_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addLayout(self.hover_layout)

        # 2. Properties & Info Container (when no tool is active or context info)
        self.info_container = QWidget()
        self.info_layout = QVBoxLayout(self.info_container)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(8)
        self.content_layout.addWidget(self.info_container)

        self.content_layout.addStretch()
        self.scroll.setWidget(self.content_widget)
        self.content_widget.installEventFilter(self)       # a change in what is shown re-fits the panel to it
        main_layout.addWidget(self.scroll)

        self.current_tool_dlg = None
        self.refresh_info()

    def eventFilter(self, obj, event):
        if obj is self.content_widget and event.type() == QEvent.Type.LayoutRequest:
            QTimer.singleShot(0, self, self.fit_to_content)
        return super().eventFilter(obj, event)

    def set_max_height(self, h: int):
        self.max_height = int(h)
        self.fit_to_content()

    def fit_to_content(self):
        """As tall and as wide as what is shown needs (so nothing has to be scrolled), but never taller than
        the room; the panel stays anchored to the right edge of the view it floats on."""
        content = self.content_widget.sizeHint()
        want_h = self.header.sizeHint().height() + 8 + content.height()
        h = max(100, min(want_h, self.max_height))
        w = max(content.width(), self.header.sizeHint().width())
        if want_h > h:                                   # it scrolls: leave room for the scroll bar
            w += self.scroll.verticalScrollBar().sizeHint().width()
        w = max(self.MIN_WIDTH, min(w, self.MAX_WIDTH))
        x = self.parentWidget().width() - w - self.EDGE_GAP if self.parentWidget() else self.x()
        x = max(self.EDGE_GAP, x)
        if (x, w, h) != (self.x(), self.width(), self.height()):
            self.setGeometry(x, self.y(), w, h)
        self.width_fitted.emit(w)

    def set_palette(self, palette):
        """Host the sketch palette at the top of the panel (it hides itself outside sketch mode)."""
        palette.embed()
        self.palette_layout.addWidget(palette)

    def dock_tool(self, dlg):
        """Docks a tool dialog into the side panel."""
        if self.current_tool_dlg is dlg:
            return

        previous = self.current_tool_dlg
        nested = getattr(dlg, "_nested", False)     # a short value prompt asked from inside the open tool
        if previous is not None:
            self.undock_tool(previous)
            if not nested:
                # a new tool ends the open one properly, as Cancel would: its preview, hidden bodies,
                # pick mode and "busy" flag are cleared by its own finish handler
                previous.reject()

        from omacad.ui.numeric_slider import add_numeric_sliders
        add_numeric_sliders(dlg)

        self.current_tool_dlg = dlg
        dlg._embedded = False
        dlg._is_docked = True
        dlg.setParent(self.tool_container)
        dlg.setWindowFlags(Qt.WindowType.Widget)
        dlg.setMinimumWidth(0)
        dlg.setFixedWidth(358)
        dlg.unsetCursor()

        self.tool_layout.addWidget(dlg)
        self.tool_container.show()
        self.lbl_title.setText(dlg.windowTitle().upper() if theme.palette().studio else f"🛠️ {dlg.windowTitle().upper()}")
        dlg.show()

        # Hide background info when tool is active for clean focused UI
        self.info_container.hide()

        def on_finished(*_):
            dlg._tool_done = True
            self.undock_tool(dlg)
            if nested and previous is not None and self.current_tool_dlg is None \
                    and not getattr(previous, "_tool_done", False):
                self.dock_tool(previous)            # back to the tool the prompt was asked from

        if not getattr(dlg, "_tool_finish_hooked", False):
            dlg._tool_finish_hooked = True
            dlg.finished.connect(on_finished)

    def undock_tool(self, dlg=None):
        if dlg is None:
            dlg = self.current_tool_dlg
        if dlg is not None and self.current_tool_dlg is dlg:
            self.tool_layout.removeWidget(dlg)
            dlg.hide()
            self.current_tool_dlg = None
            self.tool_container.hide()
            self.lbl_title.setText("INSPECTOR")
            self.info_container.show()
            self.refresh_info()

    def _make_card(self, title: str, layout) -> QFrame:
        card = QFrame()
        style(card, "QFrame { background-color: rgba(30, 33, 38, 0.88); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; }",
              "QFrame { background-color: @surface; border: none; border-radius: 0; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(6)

        icon_name, title = theme.studio_symbol(title)   # Studio icons: the heading's emoji becomes a line icon
        lbl_header = QLabel(title if theme.palette().studio else title.upper())   # Studio: calm sentence-case headings
        style(lbl_header, "font-size: 11px; font-weight: bold; color: #E26D28; letter-spacing: 0.5px; border: none; background: transparent;",
              "QLabel { color: @text; font-size: 16px; font-weight: 500; letter-spacing: 0; }")
        if icon_name:
            row = QHBoxLayout()
            row.setSpacing(8)
            pic = QLabel()
            pic.setPixmap(theme.tool_icon(icon_name, 20).pixmap(20, 20))
            style(pic, "border: none; background: transparent;")
            row.addWidget(pic)
            row.addWidget(lbl_header, 1)
            card_layout.addLayout(row)
        else:
            card_layout.addWidget(lbl_header)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        style(div, "background-color: #2D323B; height: 1px; border: none;", "QFrame { background-color: @border; }")
        card_layout.addWidget(div)

        card_layout.addLayout(layout)
        return card

    def show_hover(self, info) -> None:
        """Measures of the hovered element as (title, [(label, text)]); None clears the card."""
        while self.hover_layout.count():
            item = self.hover_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if info:
            title, rows = info
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)
            for label, text in rows:
                value = QLabel(text)
                style(value, "color: #FFC83B; font-weight: bold; border: none; background: transparent;")
                form.addRow(f"{label}:", value)
            self.hover_layout.addWidget(self._make_card(f"👆 {title}", form))

    def refresh_info(self, selected_entities=None, measure_info=None):
        """Updates the context info based on document, selection, or sketch state."""
        # Clear existing info widgets
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # A. Measure active?
        if measure_info:
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)
            for line in measure_info:
                lbl = QLabel(line)
                style(lbl, "color: #FFC83B; font-weight: bold; font-size: 13px; border: none; background: transparent;")
                form.addRow(lbl)
            self.info_layout.addWidget(self._make_card("📏 Measurement", form))
            return

        # B. Sketch mode active?
        sk = self.doc.active_sketch
        if sk is not None:
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)

            plane_name = sk.plane.name if hasattr(sk.plane, "name") else "Sketch Plane"
            form.addRow("Plane:", QLabel(plane_name))

            status_str = self.doc.sketch_status(sk)
            lbl_status = QLabel(status_str or "Under defined")
            if "Fully" in status_str:
                style(lbl_status, "color: #66BB6A; font-weight: bold; border: none; background: transparent;",
                      "QLabel { color: @ok; font-weight: bold; }")   # the theme's own green: light green was unreadable on white
            else:
                style(lbl_status, "color: #FFA726; border: none; background: transparent;")
            form.addRow("Status:", lbl_status)

            form.addRow("Elements:", QLabel(f"{len(sk.entities)}"))
            form.addRow("Constraints:", QLabel(f"{len(sk.constraints)}"))
            form.addRow("Dimensions:", QLabel(f"{len(sk.dimensions)}"))
            form.addRow("Profiles:", QLabel(f"{len(sk.profiles)}"))

            if selected_entities:
                n_sel = len(selected_entities)
                lbl_sel = QLabel(f"{n_sel} element(s) selected")
                style(lbl_sel, "color: #42A5F5; font-weight: bold; border: none; background: transparent;",
                      "QLabel { color: @accent; font-weight: bold; }")
                form.addRow("Selection:", lbl_sel)

            self.info_layout.addWidget(self._make_card(f"✏️ Sketch: {sk.name}", form))
            return

        # C. Body selected?
        selected_bodies = [self.doc.bodies[bid] for bid in self.doc.selected_body_ids if bid in self.doc.bodies]
        if selected_bodies:
            body = selected_bodies[0]
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            form.setSpacing(6)

            vol = body.manifold.volume()
            area = body.manifold.surface_area()
            bbox = body.manifold.bounding_box()
            dx = bbox[3] - bbox[0]
            dy = bbox[4] - bbox[1]
            dz = bbox[5] - bbox[2]

            lbl_vol = QLabel(f"{vol:,.1f} mm³".replace(",", " "))
            style(lbl_vol, "color: #E0E0E0; font-weight: bold; border: none; background: transparent;")
            form.addRow("Volume:", lbl_vol)

            lbl_area = QLabel(f"{area:,.1f} mm²".replace(",", " "))
            form.addRow("Area:", lbl_area)

            form.addRow("Size:", QLabel(f"{dx:.1f} × {dy:.1f} × {dz:.1f} mm"))
            form.addRow("Flat faces:", QLabel(f"{len(body.faces)}"))
            form.addRow("Edges:", QLabel(f"{len(body.edges)}"))

            self.info_layout.addWidget(self._make_card(f"📦 Body: {body.name}", form))
            return

        # D. Document Overview (Nothing specifically selected)
        form_doc = QFormLayout()
        form_doc.setContentsMargins(0, 4, 0, 0)
        form_doc.setSpacing(6)
        form_doc.addRow("Document:", QLabel(self.doc.name))
        form_doc.addRow("Bodies:", QLabel(f"{len(self.doc.bodies)}"))
        form_doc.addRow("Sketches:", QLabel(f"{len(self.doc.sketches)}"))
        form_doc.addRow("Features:", QLabel(f"{len(self.doc.timeline.features)}"))
        form_doc.addRow("Offset planes:", QLabel(f"{len(self.doc.construction_planes)}"))
        if hasattr(self.doc, "canvases"):
            form_doc.addRow("Canvases:", QLabel(f"{len(self.doc.canvases)}"))
        self.info_layout.addWidget(self._make_card("📋 Design overview", form_doc))

        # Quick tips
        v_tips = QVBoxLayout()
        v_tips.setContentsMargins(0, 4, 0, 0)
        v_tips.setSpacing(4)
        tips = [
            "E - Extrude profile",
            "F - Fit View / Center",
            "I - Measure tool",
            "Ctrl+P - Parameters",
            "Right-click face - Sketch / Extrude",
            "Right-click plane - Split body / Sketch",
        ]
        for tip in tips:
            lbl = QLabel(tip)
            style(lbl, "color: #8E95A0; font-size: 11px; border: none; background: transparent;")
            v_tips.addWidget(lbl)
        self.info_layout.addWidget(self._make_card("⚡ Shortcuts", v_tips))

