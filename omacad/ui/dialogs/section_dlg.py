"""Dialog for interactive section view plane slicing."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel, QSlider, QFormLayout, QCheckBox, QHBoxLayout, QPushButton
)
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class SectionDialog(BaseFeatureDialog):
    """Section view: slide the cutting plane through the model until you see what you want."""
    changed = Signal()

    def __init__(self, base_name: str, extent: float, parent=None):
        super().__init__("Section View", parent)
        info = QLabel(f"Cutting along: {base_name}. Drag the slider or the blue arrow in the view, or type an offset.")
        info.setWordWrap(True)
        self.main_layout.addWidget(info)
        self.extent = max(float(extent), 1.0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-1000, 1000)
        self.slider.setValue(0)
        self.main_layout.addWidget(self.slider)
        form = QFormLayout()
        self.spn_offset = ExprDoubleSpinBox()
        self.spn_offset.setProperty("has_tool_slider", True)
        self.spn_offset.setRange(-100000.0, 100000.0)
        self.spn_offset.setDecimals(2)
        self.spn_offset.setSuffix(" mm")
        form.addRow("Offset:", self.spn_offset)
        self.chk_flip = QCheckBox("Look from the other side")
        form.addRow("", self.chk_flip)
        self.main_layout.addLayout(form)
        self._busy = False
        self.slider.valueChanged.connect(self._from_slider)
        self.spn_offset.valueChanged.connect(self._from_spin)
        self.chk_flip.toggled.connect(lambda *_: self.changed.emit())
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        done = QPushButton("Save")
        done.setObjectName("PrimaryButton")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        row.addWidget(done)
        self.main_layout.addLayout(row)

    def _from_slider(self, v):
        if self._busy:
            return
        self._busy = True
        self.spn_offset.setValue(round(v / 1000.0 * self.extent, 2))
        self._busy = False
        self.changed.emit()

    def _from_spin(self, val):
        if not self._busy:
            self._busy = True
            self.slider.setValue(int(max(-1000, min(1000, val / self.extent * 1000.0))))
            self._busy = False
        self.changed.emit()

    def set_offset(self, val: float):
        self.spn_offset.setValue(round(val, 2))

    def offset(self) -> float:
        return self.spn_offset.value()

    def flip(self) -> bool:
        return self.chk_flip.isChecked()
