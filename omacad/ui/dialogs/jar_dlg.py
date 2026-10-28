"""Dialog for Jar with Lid: the sizes of a threaded jar and its screw lid; every field has a slider when docked."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton
from omacad.model.jar import PROFILES, JarSpec
from omacad.ui.expr_spin import ExprDoubleSpinBox
from omacad.ui.dialogs.base import BaseFeatureDialog

PROFILE_NAMES = ("Trapezoid 45°", "Round", "ISO 60°")      # Trapezoid 45° prints without support


class JarDialog(BaseFeatureDialog):
    """Jar with Lid: OK adds the jar and the lid as ordinary, editable history steps (one undo step)."""

    changed = Signal()
    FIELDS = (  # attribute, label, low, high, tip
        ("diameter", "Diameter:", 5.0, 1000.0, "Outside diameter of the jar and the lid."),
        ("height", "Height:", 2.0, 1000.0, "The jar up to its shoulder; the neck comes on top."),
        ("wall", "Wall:", 0.4, 50.0, "Wall and bottom of the jar."),
        ("inside_chamfer", "Inside chamfer:", 0.0, 50.0, "Chamfer inside the jar, at the bottom and under the shoulder "
                                                       "(at most the shoulder's width, which makes it 45° and printable "
                                                       "without support). 0 = none."),
        ("neck_diameter", "Neck diameter:", 2.0, 1000.0, "The neck the thread sits on (without the thread)."),
        ("neck_height", "Neck / thread height:", 1.0, 500.0, "Height of the neck, which is also the thread's length."),
        ("pitch", "Pitch:", 0.5, 50.0, "Rise of the thread per turn."),
        ("tolerance", "Thread tolerance:", -1.0, 1.0, "Offset Face on the lid's thread. Minus gives more room (looser), "
                                                      "plus less (tighter). -0.2 suits most FDM printers."),
        ("thread_chamfer", "Thread chamfer:", 0.0, 10.0, "45° lead-in on the jar's top thread and in the lid's mouth, "
                                                         "so the lid finds the thread. 0 = none."),
        ("lid_top", "Lid top:", 0.4, 50.0, "Thickness of the lid's top."),
    )

    def __init__(self, parent=None, spec: JarSpec = None, embedded: bool = False):
        super().__init__("Jar with Lid", parent, embedded)
        spec = spec or JarSpec()
        form = QFormLayout()
        self.spins = {}
        for key, label, lo, hi, tip in self.FIELDS:
            s = ExprDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(2)
            s.setSingleStep(0.05 if key == "tolerance" else 0.5)
            s.setSuffix(" mm")
            s.setValue(getattr(spec, key))
            s.setToolTip(tip)
            s.valueChanged.connect(lambda *_: self.changed.emit())
            form.addRow(label, s)
            self.spins[key] = s
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItems(PROFILE_NAMES)
        self.cmb_profile.setCurrentIndex(PROFILES.index(spec.profile) if spec.profile in PROFILES else 0)
        self.cmb_profile.currentIndexChanged.connect(lambda *_: self.changed.emit())
        form.insertRow(7, "Thread profile:", self.cmb_profile)
        self.chk_beside = QCheckBox("Beside the jar")
        self.chk_beside.setToolTip("The lid lies upside down beside the jar, ready to print. Off: screwed on.")
        self.chk_beside.setChecked(spec.lid_beside)
        self.chk_beside.toggled.connect(lambda *_: self.changed.emit())
        form.addRow("Lid:", self.chk_beside)
        self.main_layout.addLayout(form)
        reset_row = QHBoxLayout()
        reset_row.addStretch()
        self.btn_reset = QPushButton("Reset to defaults")
        self.btn_reset.setAutoDefault(False)
        self.btn_reset.clicked.connect(self.reset_defaults)
        reset_row.addWidget(self.btn_reset)
        self.main_layout.addLayout(reset_row)
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        self.main_layout.addWidget(self.lbl_info)
        self.add_buttons()

    def reset_defaults(self):
        """Restore the original Jar with Lid values, regardless of saved previous settings."""
        spec = JarSpec()
        for key, spin in self.spins.items():
            spin.set_expression(str(getattr(spec, key)))
        self.cmb_profile.setCurrentIndex(PROFILES.index(spec.profile))
        self.chk_beside.setChecked(spec.lid_beside)
        self.changed.emit()

    def spec(self) -> JarSpec:
        return JarSpec(**{k: s.value() for k, s in self.spins.items()},
                       profile=PROFILES[self.cmb_profile.currentIndex()], lid_beside=self.chk_beside.isChecked())

    def set_problems(self, lid_wall: float, problems) -> None:
        """Shows what OK would make; with problems, OK is off until they are fixed."""
        ok = getattr(self, "btn_ok", None)
        if ok is not None:
            ok.setEnabled(not problems)
        self.lbl_info.setText("\n".join(problems) if problems else
                              f"Lid wall outside the thread: {lid_wall:.2f} mm. OK adds the steps to the timeline; "
                              "each one can be edited there afterwards.")
