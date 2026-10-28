"""Sliders paired with existing tool fields; the spinbox remains the source of truth."""
from PySide6.QtCore import Qt, QEvent, QSignalBlocker
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSlider, QDoubleSpinBox, QSpinBox


class NumericSlider(QWidget):
    def __init__(self, field):
        super().__init__(field.parentWidget())
        self.field = field
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setObjectName("ToolNumericSlider")
        self.slider.setRange(0, 1000)
        self.slider.setAccessibleName(field.accessibleName() or field.suffix().strip() or "Value")
        self._low = self._high = 0.
        self._updating = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self.slider.valueChanged.connect(self._slide)
        self.slider.sliderReleased.connect(lambda: self.sync(rescale=True))

    def attach(self):
        hidden = self.field.isHidden()
        self._layout.addWidget(self.field)
        self._layout.addWidget(self.slider)
        self.field.installEventFilter(self)
        self.field.valueChanged.connect(self.sync)
        self.setVisible(not hidden)
        self.sync(rescale=True)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.ShowToParent, QEvent.Type.HideToParent):
            self.setVisible(not self.field.isHidden())
        elif event.type() == QEvent.Type.EnabledChange:
            self.slider.setEnabled(self.field.isEnabled() and not self.field.isReadOnly())
        return super().eventFilter(obj, event)

    def sync(self, *_, rescale=False):
        value = self.field.value()
        if self._updating:
            return
        if "°" in self.field.suffix():   # angles: the field's own range, at most one turn each way
            self._low = max(float(self.field.minimum()), -360.)
            self._high = min(float(self.field.maximum()), 360.)
        elif rescale or value < self._low or value > self._high or self._low == self._high:
            # A local range keeps small dimensions usable even if the field allows
            # kilometres. Typed values retain the field's complete numeric range.
            span = max(10., 2 * abs(value), 20 * self.field.singleStep())
            self._low = max(float(self.field.minimum()), -span if self.field.minimum() < 0 else 0.)
            self._high = min(float(self.field.maximum()), span)
        self._low = max(self._low, float(self.field.minimum()))
        self._high = min(self._high, float(self.field.maximum()))
        self.slider.setEnabled(self.field.isEnabled() and not self.field.isReadOnly() and self._high > self._low)
        self.slider.setToolTip(f"Drag to adjust ({self._low:g} to {self._high:g}). Type any exact value in the field.")
        with QSignalBlocker(self.slider):
            fraction = (value-self._low)/(self._high-self._low) if self._high > self._low else 0.
            self.slider.setValue(round(1000*fraction))

    def _slide(self, position):
        if self.field.isReadOnly() or not self.field.isEnabled():
            return
        value = self._low + (self._high-self._low) * position/1000
        decimals = self.field.decimals() if isinstance(self.field, QDoubleSpinBox) else 0
        value = round(value, decimals)
        self._updating = True
        try:
            if self.field.property("primitive_dimension"):
                from omacad.ui.primitive_handles import primitive_drag_value
                self.field.set_expression(primitive_drag_value(self.field, value))
            elif hasattr(self.field, "set_expression"):
                self.field.set_expression(str(value))
            else:
                self.field.setValue(value)
        finally:
            self._updating = False
        if not self.slider.isSliderDown():
            self.sync()


def add_numeric_sliders(widget):
    """Pair every number field under `widget` with a slider, once, wherever it sits (also in group boxes):
    the field moves into a NumericSlider in the layout it came from and stays the source of truth."""
    fields = widget.findChildren(QDoubleSpinBox) + widget.findChildren(QSpinBox)
    for field in fields:
        if field.property("has_tool_slider") or isinstance(field.parentWidget(), NumericSlider):
            continue
        owner = field.parentWidget()
        layout = owner.layout() if owner is not None else None
        if layout is None:
            continue
        wrapper = NumericSlider(field)
        item = layout.replaceWidget(field, wrapper)
        if item is None:
            wrapper.deleteLater()
            continue
        del item
        wrapper.attach()
