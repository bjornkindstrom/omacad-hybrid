"""Small UI motion (plan A10): a docked tool panel fades and glides in, ribbon buttons fade their hover look.

Both are off when the setting `ui_animations` is (tests turn it off, so they see the final state at once). Every
animation ends exactly in the state the widget has without it: the opacity effect is removed and the margin is
put back, so nothing stays half drawn or costs anything once it has run.
"""

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStyle, QStyleOptionToolButton, QStylePainter

PANEL_MS = 170          # a tool panel fading in
PANEL_GLIDE_PX = 10     # how far below its place it starts
HOVER_IN_MS = 110       # a button lighting up under the mouse
HOVER_OUT_MS = 200      # and fading back (slower, so a quick pass over the ribbon leaves a soft trail)


def enabled() -> bool:
    try:
        from omacad.ui.settings import get_settings
        return bool(get_settings().get("ui_animations", True))
    except Exception:
        return False


def glide_in(widget, layout) -> None:
    """Fade `widget` in while the top margin of the `layout` it sits in shrinks to its own value."""
    if not enabled():
        return
    old = getattr(widget, "_ui_glide", None)
    if old is not None:
        old.stop()
    m = layout.contentsMargins()
    top = m.top()
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QVariantAnimation(widget)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(PANEL_MS)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def step(t):
        try:
            effect.setOpacity(float(t))
            layout.setContentsMargins(m.left(), top + int(round(PANEL_GLIDE_PX * (1.0 - float(t)))), m.right(), m.bottom())
        except RuntimeError:                # the widget went away mid-way
            anim.stop()

    def done():
        try:
            widget.setGraphicsEffect(None)
            layout.setContentsMargins(m.left(), top, m.right(), m.bottom())
        except RuntimeError:
            pass
        widget._ui_glide = None

    anim.valueChanged.connect(step)
    anim.finished.connect(done)
    widget._ui_glide = anim
    step(0.0)
    anim.start()


class HoverFade:
    """Mixin for a QToolButton styled by a style sheet: its :hover look fades in and out instead of switching.

    paintEvent draws the button as it looks without the mouse, then the hover look on top at the fade's opacity."""

    def _hover_init(self):
        self._hover_t = 0.0
        self._hover_anim = None

    def _hover_to(self, target: float, ms: int):
        if not enabled():
            self._hover_t = target
            return
        anim = getattr(self, "_hover_anim", None)
        if anim is None:
            anim = self._hover_anim = QVariantAnimation(self)
            anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            anim.valueChanged.connect(self._hover_step)
        anim.stop()
        anim.setStartValue(float(self._hover_t))
        anim.setEndValue(float(target))
        anim.setDuration(max(1, int(ms * abs(target - self._hover_t))))
        anim.start()

    def _hover_step(self, t):
        self._hover_t = float(t)
        self.update()

    def enterEvent(self, event):
        self._hover_to(1.0, HOVER_IN_MS)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_to(0.0, HOVER_OUT_MS)
        super().leaveEvent(event)

    def paintEvent(self, event):
        t = getattr(self, "_hover_t", 0.0)
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        hovered = bool(opt.state & QStyle.StateFlag.State_MouseOver)
        if not enabled() or t >= 1.0 or (t <= 0.0 and not hovered) or self.isDown() or self.isChecked():
            super().paintEvent(event)
            return
        p = QStylePainter(self)
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        p.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, opt)
        if t > 0.0:
            p.setOpacity(t)
            opt.state |= QStyle.StateFlag.State_MouseOver
            p.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, opt)
        p.end()
