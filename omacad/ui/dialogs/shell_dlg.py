"""Dialog for Shell feature: hollowing out 3D solid bodies."""

from typing import Optional, List, Dict, Any
import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QLabel, QPushButton
)
from omacad.model.document import Document
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog


class ShellDialog(BaseFeatureDialog):
    """Dialog to hollow out a 3D solid body with specified wall thickness and optional open faces."""

    changed = Signal()

    def __init__(self, doc: Document, parent=None, preselected_body_id: Optional[str] = None):
        super().__init__("Shell", parent)
        self.doc = doc
        form = QFormLayout()

        # Target Body
        self.body_ids = list(doc.bodies.keys())
        body_names = [doc.bodies[bid].name for bid in self.body_ids]
        self.cmb_target = QComboBox()
        self.cmb_target.addItems(body_names)
        if preselected_body_id and preselected_body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(preselected_body_id))
        elif doc.selected_body_ids and doc.selected_body_ids[0] in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(doc.selected_body_ids[0]))
        form.addRow("Target Body:", self.cmb_target)

        # Direction of the wall (as in Fusion): inside, outside, or both with a thickness each
        self.cmb_dir = QComboBox()
        for label, tip in (("Inside", "The wall grows inward"), ("Outside", "The wall grows outward"),
                           ("Both", "Inside and outside")):
            self.cmb_dir.addItem(label)
            self.cmb_dir.setItemData(self.cmb_dir.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
        form.addRow("Direction:", self.cmb_dir)

        # Wall Thickness
        self.spn_thickness = ExprDoubleSpinBox()
        self.spn_thickness.setRange(0.05, 500.0)
        self.spn_thickness.setDecimals(2)
        self.spn_thickness.setSuffix(" mm")
        self.spn_thickness.setValue(2.0)
        self.lbl_thick = QLabel("Wall Thickness:")
        form.addRow(self.lbl_thick, self.spn_thickness)
        self.spn_thickness2 = ExprDoubleSpinBox()
        self.spn_thickness2.setRange(0.05, 500.0)
        self.spn_thickness2.setDecimals(2)
        self.spn_thickness2.setSuffix(" mm")
        self.spn_thickness2.setValue(2.0)
        self.lbl_thick2 = QLabel("Outside Thickness:")
        form.addRow(self.lbl_thick2, self.spn_thickness2)

        # Open Faces
        self.open_faces = []
        self.lbl_faces = QLabel("0 open face(s) selected.\n(Click faces in viewport to leave them open, e.g. top of box)")
        self.lbl_faces.setWordWrap(True)
        form.addRow("Open Faces:", self.lbl_faces)

        self.btn_clear_faces = QPushButton("Clear Open Faces")
        self.btn_clear_faces.clicked.connect(self.clear_faces)
        form.addRow("", self.btn_clear_faces)

        self.main_layout.addLayout(form)
        self.add_buttons()

        self.spn_thickness.valueChanged.connect(lambda *_: self.changed.emit())
        self.spn_thickness2.valueChanged.connect(lambda *_: self.changed.emit())
        self.cmb_target.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self.cmb_dir.currentIndexChanged.connect(lambda *_: (self._dir_changed(), self.changed.emit()))
        self._dir_changed()

    DIRS = ["inside", "outside", "both"]

    def direction(self) -> str:
        return self.DIRS[self.cmb_dir.currentIndex()]

    def _dir_changed(self):
        d = self.direction()
        self.lbl_thick.setText({"inside": "Wall Thickness:", "outside": "Wall Thickness:", "both": "Inside Thickness:"}[d])
        self.lbl_thick2.setVisible(d == "both")
        self.spn_thickness2.setVisible(d == "both")

    def toggle_face(self, face):
        """Add or remove an open face by user viewport pick."""
        # Check if already in list
        fn = [float(x) for x in face.normal]
        fo = [float(x) for x in face.origin]
        found_idx = -1
        for i, f in enumerate(self.open_faces):
            if np.allclose(f["normal"], fn, atol=1e-3) and np.allclose(f["origin"], fo, atol=1e-3):
                found_idx = i
                break
        if found_idx >= 0:
            self.open_faces.pop(found_idx)
        else:
            self.open_faces.append({"normal": fn, "origin": fo, "body_id": getattr(face, "body_id", ""), "_face": face})

        count = len(self.open_faces)
        self.lbl_faces.setText(f"{count} open face{'s' if count != 1 else ''} selected.\n(Click again to deselect)")
        parent = self.parent()
        vp = getattr(parent, "viewport", None)
        if vp is not None:
            vp.highlighted_faces = [f["_face"] for f in self.open_faces if "_face" in f]
            vp.update()
        self.changed.emit()

    def clear_faces(self):
        self.open_faces = []
        self.lbl_faces.setText("0 open face(s) selected.\n(Click faces in viewport to leave them open)")
        parent = self.parent()
        vp = getattr(parent, "viewport", None)
        if vp is not None:
            vp.highlighted_faces = []
            vp.update()
        self.changed.emit()

    def select_body(self, body_id: str):
        if body_id in self.body_ids:
            self.cmb_target.setCurrentIndex(self.body_ids.index(body_id))
            self.changed.emit()

    def get_expressions(self) -> dict:
        out = {"thickness": self.spn_thickness.expression()}
        if self.direction() == "both":
            out["thickness2"] = self.spn_thickness2.expression()
        return {k: v for k, v in out.items() if v}

    def get_values(self):
        b_idx = self.cmb_target.currentIndex()
        if b_idx < 0 or b_idx >= len(self.body_ids):
            return None, 2.0, []
        return self.body_ids[b_idx], self.spn_thickness.value(), list(self.open_faces)
