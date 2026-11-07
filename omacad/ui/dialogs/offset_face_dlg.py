"""Dialog for Offset Face: pick faces in the viewport, type how far they move."""

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QFormLayout, QLabel, QListWidget, QPushButton
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog

HINT = ("Click flat faces, holes, pins or curved surfaces such as threads in the viewport (click again to deselect). "
        "Plus moves the face out of the body (adds material, a hole gets smaller), minus moves it in.\n\n"
        "Fit of a thread: click the thread flank on the part you want to change. Minus removes material there "
        "(looser fit), plus adds material (tighter fit). The Thread step is adjusted, so the thread stays clean.")


class FacePickMixin:
    """Faces of one body picked in the viewport: `self.faces` (refs) and `self.body_id`; needs `changed` and
    `_update_count`."""

    @staticmethod
    def _same(a, b) -> bool:
        import numpy as np
        if a["kind"] != b["kind"]:
            return False
        if a["kind"] == "surface":    # the same patch: clicks close to each other
            return bool(np.linalg.norm(np.asarray(a["point"]) - np.asarray(b["point"])) < 0.5)
        keys = ("normal", "origin") if a["kind"] == "plane" else ("origin", "axis")
        same = all(np.allclose(a[k], b[k], atol=1e-3) for k in keys)
        if a["kind"] == "cylinder":
            same = same and np.isclose(a["radius"], b["radius"], atol=1e-3) and a.get("internal") == b.get("internal")
        return bool(same)

    def toggle(self, ref: dict, body_id: str) -> bool:
        """Adds the face (or removes it when already picked). False when it belongs to another body."""
        if self.faces and body_id != self.body_id:
            return False
        for i, f in enumerate(self.faces):
            if self._same(f, ref):
                self.faces.pop(i)
                break
        else:
            self.faces.append(ref)
        self.body_id = body_id if self.faces else ""
        self._update_count()
        self.changed.emit()
        return True

    def clear(self):
        self.faces, self.body_id = [], ""
        self._update_count()
        self.changed.emit()


class OffsetFaceDialog(FacePickMixin, BaseFeatureDialog):
    """Offset Face: the faces are picked in the viewport, the distance is typed here."""

    changed = Signal()

    def __init__(self, parent=None, distance: float = 0.2, editing: bool = False, embedded: bool = False):
        super().__init__("Offset Face", parent, embedded)
        self.faces = []          # face references, see offset_face.plane_face_ref / cylinder_face_ref
        self.body_id = ""        # the body the faces belong to
        form = QFormLayout()
        self.spn_dist = ExprDoubleSpinBox()
        self.spn_dist.setRange(-1000.0, 1000.0)
        self.spn_dist.setDecimals(3)
        self.spn_dist.setSingleStep(0.05)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.setValue(distance)
        self.spn_dist.setToolTip("Distance in mm. Formulas and parameter names work. Negative moves the face into the body.")
        form.addRow("Distance:", self.spn_dist)
        self.lbl_count = QLabel("" if editing else HINT)
        self.lbl_count.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_count)
        self.lbl_note = QLabel("")       # what OK will do with the current selection (set by the tool prompt)
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet("font-weight: bold;")      # the theme's own text colour: always readable
        self.lbl_note.hide()
        self.main_layout.addWidget(self.lbl_note)
        self.main_layout.addLayout(form)
        self.lst_faces = QListWidget()
        self.lst_faces.setMaximumHeight(130)
        self.lst_faces.setToolTip("Selected faces stay highlighted in the viewport. Orbit the model and click more faces to add them.")
        self.main_layout.addWidget(self.lst_faces)
        self.btn_remove = QPushButton("Remove selected face")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.main_layout.addWidget(self.btn_remove)
        btn = QPushButton("Clear selection")
        btn.clicked.connect(self.clear)
        self.main_layout.addWidget(btn)
        self.add_buttons()
        self._update_count()
        self.spn_dist.valueChanged.connect(lambda *_: self.changed.emit())
        QTimer.singleShot(0, self, lambda: (self.spn_dist.setFocus(), self.spn_dist.selectAll()))

    def _update_count(self):
        n = len(self.faces)
        self.lbl_count.setText(f"{n} face{'s' if n != 1 else ''} selected. Orbit the model and click more faces to add them; click again to remove." if n else HINT)
        self.lst_faces.clear()
        for i, ref in enumerate(self.faces, 1):
            kind = ref["kind"]
            label = {"plane": "Flat face", "cylinder": "Cylindrical face", "surface": "Curved face", "thread": "Thread"}.get(kind, kind)
            if kind == "plane":
                normal = ref["normal"]
                axis = max(range(3), key=lambda k: abs(normal[k]))
                label += " · " + (("+" if normal[axis] > 0 else "−") + "XYZ"[axis] if abs(normal[axis]) > 0.9999 else "sloped")
            elif kind == "cylinder":
                label += f" · radius {ref['radius']:g} mm"
            self.lst_faces.addItem(f"{i}. {label}")
        self.btn_remove.setEnabled(bool(n))
        self.btn_ok.setEnabled(bool(n))

    def _remove_selected(self):
        row = self.lst_faces.currentRow()
        if row < 0:
            return
        self.faces.pop(row)
        if not self.faces:
            self.body_id = ""
        self._update_count()
        self.changed.emit()

    def highlights(self, body):
        """Resolve the selected references on the unchanged body, independently of the offset preview."""
        import numpy as np
        from omacad.model.faces import smooth_patch_vertices
        from omacad.model.features.offset_face import _frame
        highlighted = []
        mesh = body.render_mesh
        triangles = np.asarray(mesh.vertices).reshape(-1, 3, 3) if mesh is not None else np.empty((0, 3, 3))
        for ref in self.faces:
            if ref["kind"] == "plane":
                for face in body.faces:
                    if np.dot(face.normal, ref["normal"]) > 0.9999 and abs(np.dot(face.normal, np.asarray(ref["origin"]) - face.origin)) < 0.01:
                        highlighted.append(face)
            elif len(triangles) and ref["kind"] == "surface":
                normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
                normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
                dist = np.linalg.norm(triangles.mean(axis=1) - ref["point"], axis=1) + 10. * (normals @ ref["normal"] < 0.5)
                highlighted.append({"tris": smooth_patch_vertices(mesh, int(dist.argmin())).reshape(-1, 3, 3)})
            elif len(triangles) and ref["kind"] == "cylinder":
                M = np.linalg.inv(_frame(ref["origin"], ref["axis"]))
                local = triangles @ M[:3, :3].T + M[:3, 3]
                radius = np.linalg.norm(local[:, :, :2], axis=2)
                side = np.ptp(local[:, :, 2], axis=1) > 1e-5
                mask = side & (np.abs(radius - ref["radius"]).max(axis=1) < max(0.02, ref["radius"] * 1e-3))
                highlighted.append({"tris": triangles[mask]})
        return highlighted

    def set_note(self, text: str) -> None:
        self.lbl_note.setText(text)
        self.lbl_note.setVisible(bool(text))

    def distance(self) -> float:
        return self.spn_dist.value()

    def get_expressions(self) -> dict:
        e = self.spn_dist.expression()
        return {"distance": e} if e else {}
