"""Settings for a fitted slip-over lid."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QComboBox, QDoubleSpinBox, QLabel
from omacad.ui.dialogs.base import BaseFeatureDialog
from omacad.model.features.lid import LidFeature


class LidDialog(BaseFeatureDialog):
    changed = Signal()

    def __init__(self, doc, parent=None):
        super().__init__("Make a lid", parent)
        form = QFormLayout()
        self.body = QComboBox()
        for bid, body in doc.bodies.items():
            self.body.addItem(body.name, bid)
        if doc.selected_body_ids:
            self.select_body(doc.selected_body_ids[0])
        form.addRow("Body", self.body)
        self.direction = QComboBox()
        self.direction.addItems(list(LidFeature.DIRECTIONS))
        form.addRow("Opening direction", self.direction)
        self.edge_kind = QComboBox()
        for label, value in (("None", "none"), ("Chamfer", "chamfer"), ("Fillet", "fillet")):
            self.edge_kind.addItem(label, value)
        form.addRow("Top outer edge", self.edge_kind)
        self.fields = {}
        for key, label, value, minimum in (("clearance", "Fit clearance", .25, 0),
                                         ("thickness", "Lid / wall thickness", 2, .05),
                                         ("overlap", "Overlap", 5, .05),
                                         ("edge_size", "Chamfer size / fillet radius", .5, .01)):
            spin = QDoubleSpinBox()
            spin.setRange(minimum, 10000)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            spin.setValue(value)
            spin.valueChanged.connect(self.changed)
            self.fields[key] = spin
            form.addRow(label, spin)
        self.message = QLabel("A separate slip-over lid. Choose the opening direction; the source stays intact.")
        self.message.setWordWrap(True)
        form.addRow(self.message)
        self.main_layout.addLayout(form)
        self.add_buttons()
        self.body.currentIndexChanged.connect(self.changed)
        self.direction.currentIndexChanged.connect(self.changed)
        self.edge_kind.currentIndexChanged.connect(self.changed)
        self.edge_kind.currentIndexChanged.connect(lambda: self.fields["edge_size"].setEnabled(self.edge_kind.currentData() != "none"))
        self.fields["edge_size"].setEnabled(False)

    def select_body(self, bid):
        index = self.body.findData(bid)
        if index >= 0:
            self.body.setCurrentIndex(index)

    def values(self):
        return self.body.currentData(), dict(direction=self.direction.currentText(), edge_kind=self.edge_kind.currentData(),
                                            **{k: w.value() for k, w in self.fields.items()})
