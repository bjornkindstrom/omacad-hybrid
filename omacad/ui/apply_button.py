"""A green check button floating in the viewport that applies the open tool panel or sketch selection (Björn #160)."""
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QToolButton, QWidget, QHBoxLayout, QLabel
from omacad.ui.expr_spin import ExprDoubleSpinBox


class _ApplyValue(ExprDoubleSpinBox):
    """A viewport field shares its tool's Enter/Esc behavior and parameter completion."""

    def __init__(self, dialog, parent):
        super().__init__(parent)
        self.dialog = dialog

    def keyPressEvent(self, event):
        if self.suggestion_key(event):
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.interpretText()
            self.editingFinished.emit()
            self.dialog.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.dialog.reject()
            return
        super().keyPressEvent(event)

BUTTON_STYLE = (
    "QToolButton { background: #2E9F4F; color: white; border: 2px solid #BFF0CC; "
    "border-radius: 18px; font-size: 20px; font-weight: bold; }"
    "QToolButton:hover { background: #3CC264; }"
)


def _make_button(viewport) -> QToolButton:
    btn = QToolButton(viewport)
    btn.setText("✓")
    btn.setToolTip("Apply (Enter)")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedSize(36, 36)
    btn.setStyleSheet(BUTTON_STYLE)
    btn.hide()
    return btn


def _place_button(btn: QToolButton, viewport, pos, avoid_widget=None) -> None:
    if pos is None:
        btn.hide()
        return
    x = int(min(max(pos[0] + 28, 4), max(4, viewport.width() - btn.width() - 4)))
    y = int(min(max(pos[1] - 44, 4), max(4, viewport.height() - btn.height() - 4)))
    if avoid_widget is not None and avoid_widget.parent() is viewport and avoid_widget.isVisible():
        rect = avoid_widget.geometry().adjusted(-8, -8, 8, 8)
        if rect.contains(x, y):
            alt_x = int(min(max(pos[0] - btn.width() - 28, 4), max(4, viewport.width() - btn.width() - 4)))
            if not rect.contains(alt_x, y):
                x = alt_x
            else:
                y = int(min(max(rect.bottom() + 12, 4), max(4, viewport.height() - btn.height() - 4)))
    btn.move(x, y)
    btn.show()
    btn.raise_()


def arrow_anchor(viewport):
    """Screen position of the active 3D extrude/fillet/offset-plane arrow tip, or None."""
    h = getattr(viewport, "extrude_handle", None)
    if not h:
        return None
    return viewport.world_to_screen(
        np.asarray(h["origin"], dtype=float) + np.asarray(h["axis"], dtype=float) * float(h["dist"])
    )


def mesh_anchor(viewport, mesh):
    """Upper-right screen position of a render mesh's bounding box, or None."""
    if mesh is None or getattr(mesh, "vertices", None) is None or len(mesh.vertices) == 0:
        return None
    lo = np.asarray(mesh.bounds_min, dtype=float)
    hi = np.asarray(mesh.bounds_max, dtype=float)
    corners = [
        np.array([x, y, z], dtype=float)
        for x in (lo[0], hi[0])
        for y in (lo[1], hi[1])
        for z in (lo[2], hi[2])
    ]
    pts = [viewport.world_to_screen(c) for c in corners]
    pts = [p for p in pts if p is not None]
    if not pts:
        return None
    best = max(pts, key=lambda p: float(p[0]) - float(p[1]))
    return float(best[0]), float(best[1])


def preview_anchor(viewport):
    """Screen position of the current preview mesh, display override, or move gizmo."""
    if getattr(viewport, "extrude_handle", None):
        pos = arrow_anchor(viewport)
        if pos is not None:
            return pos
    if getattr(viewport, "move_gizmo", None):
        pos = viewport.world_to_screen(np.asarray(viewport.move_gizmo["origin"], dtype=float))
        if pos is not None:
            return float(pos[0]), float(pos[1])
    if getattr(viewport, "preview_mesh", None) is not None:
        return mesh_anchor(viewport, viewport.preview_mesh)
    override = getattr(viewport, "display_override", None)
    if override:
        for m in override.values():
            pos = mesh_anchor(viewport, m)
            if pos is not None:
                return pos
    return None


def face_ref_anchor(viewport, faces_fn):
    """Screen position of the last picked face reference (or preview fallback)."""
    faces = faces_fn()
    if faces:
        last = faces[-1]
        pt = last.get("point") or last.get("origin")
        if pt is not None:
            scr = viewport.world_to_screen(np.asarray(pt, dtype=float))
            if scr is not None:
                return float(scr[0]), float(scr[1])
    return preview_anchor(viewport) if faces else None


def profile_anchor(viewport, doc):
    """Screen position of the selected sketch profile (or preview fallback)."""
    pos = preview_anchor(viewport)
    if pos is not None:
        return pos
    key = doc.selected_extra[-1] if getattr(doc, "selected_extra", None) else getattr(doc, "selected_profile", None)
    if not key:
        return None
    sk = doc.sketches.get(key[0])
    if sk is None or key[1] >= len(sk.profiles):
        return None
    pts = sk.profiles[key[1]].exterior_pts
    if not len(pts):
        return None
    mid = np.mean(pts, axis=0)
    scr = viewport.world_to_screen(sk.plane.uv_to_world(float(mid[0]), float(mid[1])))
    return (float(scr[0]), float(scr[1])) if scr is not None else None


def add_apply_button(viewport, dialog, anchor, interval_ms: int = 60, fields=()) -> QToolButton:
    """Show a green ✓ next to `anchor()` (a viewport pixel (x, y), or None to hide it) while `dialog` is open;
    clicking it accepts the dialog, so the mouse never has to travel to OK. It follows the anchor when the camera
    moves and is removed when the dialog finishes."""
    btn = _make_button(viewport)
    host = btn
    field_rows = []
    if fields:
        host = QWidget(viewport)
        host.setObjectName("viewport_apply_controls")
        from omacad.ui.theme import style
        style(host, "QWidget#viewport_apply_controls { background: @surface; border: 1px solid @border; border-radius: 5px; }")
        layout = QHBoxLayout(host)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        def copy_value(source, target):
            blocked = target.blockSignals(True)
            target.set_expression(source.expression() or str(source.value()))
            target.blockSignals(blocked)

        for title, source in fields:
            label = QLabel(host)
            editor = _ApplyValue(dialog, host)
            editor.source_field = source
            editor.setRange(source.minimum(), source.maximum())
            editor.setDecimals(source.decimals())
            editor.setSingleStep(source.singleStep())
            editor.setSuffix(source.suffix())
            editor.setFixedWidth(120)
            copy_value(source, editor)
            source.valueChanged.connect(lambda _v, s=source, e=editor: copy_value(s, e))
            editor.valueChanged.connect(lambda _v, s=source, e=editor: s.set_expression(e.expression() or str(e.value())))
            editor.editingFinished.connect(lambda s=source, e=editor: s.set_expression(e.expression() or str(e.value())))
            layout.addWidget(label)
            layout.addWidget(editor)
            field_rows.append((title, source, label, editor))
        layout.addWidget(btn)
        btn.show()
        host.hide()
    btn.clicked.connect(dialog.accept)

    def place():
        try:
            ok_btn = getattr(dialog, "btn_ok", None)
            if ok_btn is not None and not ok_btn.isEnabled():
                host.hide()
                return
            for title, source, label, editor in field_rows:
                label.setText(title() if callable(title) else title)
                visible = not source.isHidden()
                label.setVisible(visible)
                editor.setVisible(visible)
            if field_rows:
                host.adjustSize()
            _place_button(host, viewport, anchor(), avoid_widget=dialog)
        except RuntimeError:        # the button or viewport is already gone
            pass

    timer = QTimer(dialog)
    timer.setInterval(interval_ms)
    timer.timeout.connect(place)
    timer.start()
    if hasattr(dialog, "changed"):
        try:
            dialog.changed.connect(place)
        except Exception:
            pass
    QTimer.singleShot(0, place)

    def done(*_):
        timer.stop()
        try:
            host.hide()
            host.deleteLater()
        except RuntimeError:
            pass

    dialog.finished.connect(done)
    dialog.destroyed.connect(done)
    return btn


def _sketch_entities_screen_pos(viewport, sk, entity_ids):
    pts = []
    for eid in entity_ids:
        ent = sk.get_entity(eid)
        if ent is None:
            continue
        for a, b in ent.to_lines():
            for uv in (a, b):
                scr = viewport.world_to_screen(sk.plane.uv_to_world(float(uv[0]), float(uv[1])))
                if scr is not None:
                    pts.append((float(scr[0]), float(scr[1])))
    if not pts:
        return None
    return max(pts, key=lambda p: p[0] - p[1])


def _sketch_pending_state(viewport):
    """Returns (anchor_xy, callback) when a sketch tool is waiting for Enter after selection, else (None, None)."""
    sk = getattr(viewport.doc, "active_sketch", None)
    if sk is None:
        return None, None
    tool = getattr(viewport, "sketch_tool", "NONE")
    if tool == "FILLET" and getattr(viewport, "fillet_picked", None):
        uv = viewport.fillet_picked[-1][0]
        scr = viewport.world_to_screen(sk.plane.uv_to_world(float(uv[0]), float(uv[1])))
        return ((float(scr[0]), float(scr[1])) if scr is not None else None), viewport._fillet_apply_picked
    if tool == "OFFSET" and getattr(viewport, "selected_entities", None) and getattr(viewport, "offset_preview", None) is None:
        return _sketch_entities_screen_pos(viewport, sk, viewport.selected_entities), viewport._offset_go
    if tool == "MOVE" and getattr(viewport, "_move_phase", "") == "pick" and getattr(viewport, "selected_entities", None):
        return _sketch_entities_screen_pos(viewport, sk, viewport.selected_entities), viewport._move_next
    if tool == "MIRROR" and getattr(viewport, "_mirror_phase", "") == "pick" and getattr(viewport, "selected_entities", None):
        return _sketch_entities_screen_pos(viewport, sk, viewport.selected_entities), viewport._mirror_next
    if tool in ("SPLINE", "CONTROL_SPLINE") and len(getattr(viewport, "_spline_points", ())) >= 2:
        uv = viewport._spline_points[-1]
        scr = viewport.world_to_screen(sk.plane.uv_to_world(float(uv[0]), float(uv[1])))
        return ((float(scr[0]), float(scr[1])) if scr is not None else None), viewport._finish_spline
    if tool == "ROTATE" and getattr(viewport, "_move", None) and viewport.rotation_panel.ok.isEnabled():
        uv = viewport._move["pivot"]
        scr = viewport.world_to_screen(sk.plane.uv_to_world(float(uv[0]), float(uv[1])))
        return ((float(scr[0]), float(scr[1])) if scr is not None else None), lambda: viewport._rotate_finish(True)
    if tool == "SCALE" and getattr(viewport, "_move", None) and viewport.scale_panel.ok.isEnabled():
        uv = viewport._move["pivot"]
        scr = viewport.world_to_screen(sk.plane.uv_to_world(float(uv[0]), float(uv[1])))
        return ((float(scr[0]), float(scr[1])) if scr is not None else None), lambda: viewport._scale_finish(True)
    if tool == "PATTERN" and getattr(viewport, "_pattern", None):
        return _sketch_entities_screen_pos(viewport, sk, viewport._pattern.get("ids", ())), lambda: viewport._pattern_finish(True)
    return None, None


def attach_sketch_apply_button(viewport, interval_ms: int = 60) -> QToolButton:
    """Floating green ✓ in the viewport for sketch tools that wait for Enter after picking (Fillet, Offset, Move,
    Mirror, Spline, Rotate, Scale, Pattern)."""
    btn = _make_button(viewport)
    action = [None]

    def on_click():
        fn = action[0]
        if fn is not None:
            btn.hide()
            fn()

    btn.clicked.connect(on_click)

    def place():
        try:
            pos, fn = _sketch_pending_state(viewport)
            action[0] = fn
            _place_button(btn, viewport, pos if fn is not None else None)
        except RuntimeError:
            pass

    timer = QTimer(viewport)
    timer.setInterval(interval_ms)
    timer.timeout.connect(place)
    timer.start()
    for sig_name in ("selection_changed", "sketch_tool_changed"):
        sig = getattr(viewport, sig_name, None)
        if sig is not None:
            try:
                sig.connect(lambda *_: place())
            except Exception:
                pass
    viewport._sketch_apply_btn = btn
    viewport._sketch_apply_place = place
    return btn

