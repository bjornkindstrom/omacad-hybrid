"""
Omacad - Parametric Timeline Bar
Horizontal history timeline at the bottom with playback controls and feature nodes.
"""

from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QScrollArea, QFrame, QLabel, QSizePolicy, QMenu, QInputDialog
)
from omacad.ui import theme
from omacad.ui.theme import style
from omacad.ui import feature_edit
from omacad.model.document import Document
from omacad.model.timeline import Feature


class FeatureNodeWidget(QFrame):
    """A single feature node chip in the parametric timeline."""

    clicked = Signal(int)
    double_clicked = Signal(int)
    context_requested = Signal(int, object)  # step index, global position
    hovered = Signal(int)                    # the mouse came over / left the chip (step number)
    unhovered = Signal(int)

    FEATURE_ICONS = {
        "box": "📦",
        "cylinder": "🥫",
        "prism": "⬢",
        "cone": "🔺",
        "sweep": "〰️",
        "loft": "🏺",
        "pipe": "🧪",
        "sphere": "⚽",
        "sketch": "✏️",
        "extrude": "⬆️",
        "emboss": "🔖",
        "revolve": "🔄",
        "hole": "🕳️",
        "delete_body": "🗑️",
        "combine": "🔗",
        "fillet": "🔘",
        "pattern": "🔁",
        "thread": "🔩",
        "offset_face": "↔️",
        "honeycomb": "🐝",
        "shell": "🐚",
        "split_body": "🪚",
        "move": "🧭",
        "import_mesh": "📥",
    }

    def __init__(self, index: int, feature: Feature, is_active: bool, parent: Optional[QWidget] = None,
                 show_label: bool = True):
        super().__init__(parent)
        self.index = index
        self.feature = feature
        self.is_active = is_active
        self.show_label = show_label       # only the last step shows its name; the others grow when hovered

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(4)

        icon_str = self.FEATURE_ICONS.get(feature.feature_type, "⚙️")
        lbl_icon = QLabel()
        lbl_icon.setPixmap(theme.emoji_icon(icon_str, 24).pixmap(24, 24))
        layout.addWidget(lbl_icon)

        lbl_name = QLabel(feature.name)
        failed = bool(getattr(feature, "error", "")) and not feature.suppressed
        if feature.suppressed:
            style(lbl_name, "font-size: 11px; font-weight: bold; color: #6B7280; text-decoration: line-through;")
        elif failed:
            style(lbl_name, "font-size: 11px; font-weight: bold; color: #F87171;")
        else:
            style(lbl_name, "font-size: 11px; font-weight: bold;")
        problem = f"Failed: {feature.error}\n\n" if failed else ""
        formulas = getattr(feature, "exprs", None) or {}
        if formulas:                        # values that follow parameters: ƒx on the chip, the formulas in the tooltip
            lbl_name.setText(f"{feature.name} ƒx")
        driven = ("\nƒx " + ", ".join(f"{k} = {v}" for k, v in formulas.items())) if formulas else ""
        self.setToolTip(problem + self._describe(feature) + driven + "\n\nDouble-click to edit, right-click for more.")
        layout.addWidget(lbl_name)
        self.lbl_name = lbl_name
        lbl_name.setVisible(show_label)

        self.setObjectName("TimelineChip")
        if failed:
            style(self, """
                QFrame#TimelineChip {
                    background-color: #3A2326;
                    border: 1px solid #F87171;
                    border-radius: 4px;
                }
            """)
        elif is_active:
            style(self, """
                QFrame#TimelineChip {
                    background-color: #2D333B;
                    border: 1px solid #E26D28;
                    border-radius: 4px;
                }
                QFrame#TimelineChip:hover {
                    background-color: #353D47;
                }
            """)
        else:
            style(self, """
                QFrame#TimelineChip {
                    background-color: #212428;
                    border: 1px solid #333842;
                    border-radius: 4px;
                }
                QFrame#TimelineChip:hover {
                    background-color: #282C32;
                }
            """)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _describe(f) -> str:
        t = f.feature_type
        if t == "extrude":
            return f"{f.name}\nDistance {f.distance:g} mm, {f.direction.replace('_', ' ')}, {f.operation.replace('_', ' ')}"
        if t == "emboss":
            return f"{f.name}\n{f.effect.title()} {abs(f.depth):g} mm" + (", flipped" if f.flip else "")
        if t == "revolve":
            return f"{f.name}\nAngle {f.angle:g}°, {f.operation.replace('_', ' ')}"
        if t == "box":
            return f"{f.name}\n{f.length:g} x {f.width:g} x {f.height:g} mm"
        if t == "cylinder":
            return f"{f.name}\nRadius {f.radius:g}, height {f.height:g} mm"
        if t == "prism":
            return f"{f.name}\n{f.sides} sides, {f.across_flats:g} across flats, height {f.height:g} mm"
        if t == "cone":
            return f"{f.name}\nRadius {f.radius:g} to {f.top_radius:g}, height {f.height:g} mm"
        if t == "pipe":
            return f"{f.name}\nDiameter {f.diameter:g} mm" + (f", wall {f.thickness:g} mm" if f.thickness else "")
        if t in ("sweep", "loft"):
            return f"{f.name}\n{f.operation.replace('_', ' ')}"
        if t == "sphere":
            return f"{f.name}\nRadius {f.radius:g} mm"
        if t == "pattern":
            return f"{f.name}\n{f.kind} of {len(f.source_ids)} step(s), {f.copies} copies"
        if t == "fillet":
            return f"{f.name}\n{f.kind.title()} {f.size:g} mm on {len(f.edges)} edge(s)"
        if t == "shell":
            return f"{f.name}\nThickness {f.thickness:g} mm ({len(getattr(f, 'open_faces', ()) or ())} open face(s))"
        if t == "offset_face":
            return f"{f.name}\nOffset {f.distance:g} mm on {len(getattr(f, 'faces', ()) or ())} face(s)"
        if t == "honeycomb":
            depth = "through" if f.through else f"{f.depth:g} mm deep"
            return f"{f.name}\n{f.cells} {f.shape} cells, {f.size:g} mm, wall {f.wall:g} mm, {depth}"
        if t == "thread":
            return f"{f.name}\nØ{f.diameter:g} × {f.pitch:g} mm, L={f.length:g} mm"
        if t == "split_body":
            return f"{f.name}\nPlane {f.plane_id}"
        if t == "move":
            return f"{f.name}\nΔ({f.dx:g}, {f.dy:g}, {f.dz:g}) mm, ∠({f.rx:g}°, {f.ry:g}°, {f.rz:g}°)"
        return f.name + ("  (suppressed)" if f.suppressed else "")


    def enterEvent(self, event):
        self.lbl_name.setVisible(True)
        self.hovered.emit(self.index)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.lbl_name.setVisible(self.show_label)
        self.unhovered.emit(self.index)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)

    def contextMenuEvent(self, event):
        self.context_requested.emit(self.index, event.globalPos())


STEP_CHANGE_MIN_THICKNESS = 0.01   # mm: thinner added/removed material is a re-split surface, not a change


class TimelineBar(QWidget):
    """Bottom Parametric Timeline bar with history playback."""

    edit_sketch_requested = Signal(str)
    highlight_changed = Signal(object, object)  # (material the step added, material it removed), or (None, None)
    flash_sketch_requested = Signal(object)     # sketch id to show highlighted for a moment, or None
    step_edges_changed = Signal(object)         # edges a Fillet/Chamfer step rounds, to outline in the view ([] = none)
    status_message = Signal(str)

    def __init__(self, document: Document, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.feature_pick_handler = None
        self.busy_reason = lambda: None     # set by the main window: why the history must not change now (open tool)
        self.doc = document
        self._highlighted: Optional[int] = None   # step number whose changes are coloured in the view
        self._hovering: Optional[int] = None      # step number under the mouse (its changes are shown while it is there)
        self._hover_step: Optional[int] = None
        self._changes_cache: dict = {}
        self._edges_cache: dict = {}
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(90)           # a quick sweep over the chips does not compute every step
        self._hover_timer.timeout.connect(self._apply_hover)
        self.doc.add_change_listener(self.refresh_timeline)

        self.setFixedHeight(48)
        self.setObjectName("TimelineBar")
        style(self, """
            QWidget#TimelineBar {
                background-color: #1A1C1E;
                border-top: 1px solid #2B2E33;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Timeline Label
        lbl_title = QLabel("TIMELINE")
        style(lbl_title, "font-weight: bold; font-size: 10px; color: #7B818C; letter-spacing: 0.5px;")
        layout.addWidget(lbl_title)

        # Playback Controls
        self.btn_rewind = QPushButton()
        self.btn_rewind.setToolTip("Rewind to Beginning")
        self.btn_rewind.setFixedSize(28, 28)
        self.btn_rewind.setIcon(theme.tool_icon("timeline_rewind", 16))
        self.btn_rewind.setIconSize(QSize(16, 16))
        self.btn_rewind.clicked.connect(self.on_rewind)
        layout.addWidget(self.btn_rewind)

        self.btn_prev = QPushButton()
        self.btn_prev.setToolTip("Step Backward")
        self.btn_prev.setFixedSize(28, 28)
        self.btn_prev.setIcon(theme.tool_icon("timeline_back", 16))
        self.btn_prev.setIconSize(QSize(16, 16))
        self.btn_prev.clicked.connect(self.on_step_back)
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton()
        self.btn_next.setToolTip("Step Forward")
        self.btn_next.setFixedSize(28, 28)
        self.btn_next.setIcon(theme.tool_icon("timeline_forward", 16))
        self.btn_next.setIconSize(QSize(16, 16))
        self.btn_next.clicked.connect(self.on_step_forward)
        layout.addWidget(self.btn_next)

        self.btn_ff = QPushButton()
        self.btn_ff.setToolTip("Fast Forward to End")
        self.btn_ff.setFixedSize(28, 28)
        self.btn_ff.setIcon(theme.tool_icon("timeline_end", 16))
        self.btn_ff.setIconSize(QSize(16, 16))
        self.btn_ff.clicked.connect(self.on_fast_forward)
        layout.addWidget(self.btn_ff)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        style(div, "color: #333842;")
        layout.addWidget(div)

        # Scroll Area for Feature Chips
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        style(self.scroll_area, "QScrollArea { border: none; background: transparent; }")

        self.nodes_container = QWidget()
        self.nodes_layout = QHBoxLayout(self.nodes_container)
        self.nodes_layout.setContentsMargins(4, 0, 4, 0)
        self.nodes_layout.setSpacing(6)
        self.nodes_layout.addStretch()

        self.scroll_area.setWidget(self.nodes_container)
        layout.addWidget(self.scroll_area)

        self.refresh_timeline()

    def refresh_timeline(self):
        """Re-renders feature nodes according to timeline state."""
        if self._highlighted is not None or self._hovering is not None:
            self._highlighted = self._hovering = None
            self._show(None)
            self.flash_sketch_requested.emit(None)
        self._hover_timer.stop()
        self._changes_cache.clear()
        self._edges_cache.clear()
        # Clear existing nodes
        while self.nodes_layout.count() > 1:
            item = self.nodes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        features = self.doc.timeline.features
        marker = self.doc.timeline.marker_index

        for idx, feat in enumerate(features):
            is_active = (idx < marker)
            chip = FeatureNodeWidget(idx + 1, feat, is_active, show_label=(idx == len(features) - 1))
            chip.hovered.connect(self.on_node_hovered)
            chip.unhovered.connect(self.on_node_unhovered)
            chip.clicked.connect(self.on_node_clicked)
            chip.double_clicked.connect(self.on_node_edit)
            chip.context_requested.connect(self.on_node_menu)
            self.nodes_layout.insertWidget(idx, chip)

    def update_icons(self):
        """The playback icons follow the theme (called when it changes)."""
        for btn, name in ((self.btn_rewind, "timeline_rewind"), (self.btn_prev, "timeline_back"),
                          (self.btn_next, "timeline_forward"), (self.btn_ff, "timeline_end")):
            btn.setIcon(theme.tool_icon(name, 16))

    def find_step(self, index: int):
        """Find in Timeline: scroll to that step and colour what it changed."""
        item = self.nodes_layout.itemAt(index)
        if item is None or item.widget() is None:
            return
        self.scroll_area.ensureWidgetVisible(item.widget())
        if self._highlighted != index + 1:
            self.on_node_clicked(index + 1)

    def _blocked(self) -> bool:
        """True (and says why) while a tool is open: rebuilding would swap the bodies it works on."""
        reason = self.busy_reason()
        if reason:
            self.status_message.emit(reason)
        return bool(reason)

    def _changes(self, step_index: int):
        """(added, removed) material of a step, remembered until the timeline is rebuilt."""
        if step_index not in self._changes_cache:
            if (step_index - 1) not in self.doc.step_states or step_index not in self.doc.step_states:
                if self.busy_reason():
                    return None, None                       # no rebuild under an open tool
                self.doc.timeline.recompute(self.doc)       # steps just added have no recorded states yet
            changes = self.doc.step_changes(step_index - 1)
            placed = self.doc.placement_after(self.doc.timeline.features[step_index - 1].feature_id)
            if placed is not None:          # the object was moved since: show it where the body is now
                changes = tuple(m.transform(placed[:3, :].tolist()) if m is not None else None for m in changes)
            self._changes_cache[step_index] = changes
        return self._changes_cache[step_index]

    def _edges(self, step_index: int) -> list:
        """The edges a Fillet/Chamfer step rounds, as they were before it (other steps: none)."""
        if step_index not in self._edges_cache:
            feat = self.doc.timeline.features[step_index - 1]
            before = self.doc.step_states.get(step_index - 1)
            edges = feat.edges_in(before) if feat.feature_type == "fillet" and before else []
            placed = self.doc.placement_after(feat.feature_id) if edges else None
            self._edges_cache[step_index] = [PlacedEdge(e, placed) for e in edges] if placed is not None else edges
        return self._edges_cache[step_index]

    def _show(self, step_index: Optional[int]):
        """Colours what a step changed in the model and outlines the edges it rounds; None clears both."""
        if step_index is None:
            self.highlight_changed.emit(None, None)
            self.step_edges_changed.emit([])
            return
        self.highlight_changed.emit(*self._changes(step_index))
        self.step_edges_changed.emit(self._edges(step_index))

    def on_node_hovered(self, step_index: int):
        self._hover_step = step_index
        self._hover_timer.start()

    def on_node_unhovered(self, step_index: int):
        if self._hover_step == step_index:
            self._hover_step = None
            self._hover_timer.stop()
        if self._hovering == step_index:       # back to what a click had coloured (or nothing)
            self._hovering = None
            self.flash_sketch_requested.emit(None)
            self._show(self._highlighted)

    def _apply_hover(self):
        """Mouse rested on a chip: colour what that step added (green) / removed (red) in the model, or show its sketch."""
        step = self._hover_step
        if step is None or not (1 <= step <= len(self.doc.timeline.features)):
            return
        feat = self.doc.timeline.features[step - 1]
        self._hovering = step
        if feat.feature_type == "sketch":
            self.flash_sketch_requested.emit(feat.sketch.sketch_id)
            self._show(None)
        else:
            self.flash_sketch_requested.emit(None)
            self._show(step)

    def on_node_clicked(self, step_index: int):
        """A click colours what that step changed in the model (green = added, red = removed); a second click
        on the same step clears it. Rolling back is done with the arrows or the right-click menu."""
        if self.feature_pick_handler is not None:
            self.feature_pick_handler(self.doc.timeline.features[step_index-1].feature_id)
            return
        if self._highlighted == step_index:
            self._highlighted = None
            self._show(None)
            return
        self._highlighted = step_index
        self._show(step_index)

    def on_node_edit(self, step_index: int):
        """Double-click: edit that step (a sketch opens in sketch mode)."""
        idx = step_index - 1
        feat = self.doc.timeline.features[idx]
        if self.feature_pick_handler is not None:
            self.feature_pick_handler(feat.feature_id)
            return
        if self._blocked():
            return
        if feat.feature_type == "sketch":
            self.edit_sketch_requested.emit(feat.sketch.sketch_id)
        elif feature_edit.can_edit(feat):
            feature_edit.edit_feature(self.window(), self.doc, idx)

    def on_node_menu(self, step_index: int, pos):
        idx = step_index - 1
        feat = self.doc.timeline.features[idx]
        menu = QMenu(self)
        theme.style_menu(menu)
        a_edit = theme.action_with_icon(menu, "✏️ Edit…") if feature_edit.can_edit(feat) else None
        a_rename = theme.action_with_icon(menu, "🏷️ Rename…")
        a_supp = theme.action_with_icon(menu, "▶️ Unsuppress" if feat.suppressed else "⏸️ Suppress")
        menu.addSeparator()
        a_back = theme.action_with_icon(menu, "⏮️ Roll back to here")
        a_end = theme.action_with_icon(menu, "⏭️ Roll forward to the end")
        menu.addSeparator()
        a_del = theme.action_with_icon(menu, "🗑️ Delete…")
        chosen = menu.exec(pos)
        if chosen is None or (chosen is not a_rename and self._blocked()):
            return
        if chosen is a_edit:
            self.on_node_edit(step_index)
        elif chosen is a_rename:
            name, ok = QInputDialog.getText(self.window(), "Rename step", "Name:", text=feat.name)
            if ok:
                self.doc.rename_feature(idx, name)
        elif chosen is a_supp:
            self.doc.toggle_suppress(idx)
        elif chosen is a_back:
            self.doc.timeline.step_to(step_index, self.doc)
            self.doc.notify_changed()
        elif chosen is a_end:
            self.on_fast_forward()
        elif chosen is a_del and feature_edit.confirm_delete(self.window(), self.doc, idx):
            self.doc.delete_feature(idx)

    def on_rewind(self):
        if self._blocked():
            return
        self.doc.timeline.rewind(self.doc)
        self.doc.notify_changed()

    def on_step_back(self):
        if self._blocked():
            return
        self.doc.timeline.step_backward(self.doc)
        self.doc.notify_changed()

    def on_step_forward(self):
        if self._blocked():
            return
        self.doc.timeline.step_forward(self.doc)
        self.doc.notify_changed()

    def on_fast_forward(self):
        if self._blocked():
            return
        self.doc.timeline.fast_forward(self.doc)
        self.doc.notify_changed()


class PlacedEdge:
    """An edge shown where its object has been moved to since (only its polyline is drawn)."""
    def __init__(self, edge, m):
        self.edge, self.m = edge, m

    def polyline(self, *args):
        pts = np.asarray(self.edge.polyline(*args), dtype=float)
        return pts @ self.m[:3, :3].T + self.m[:3, 3]
