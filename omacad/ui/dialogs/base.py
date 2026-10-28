"""Base modal dialog and docking runner for Omacad feature dialogs."""

from typing import Optional
from PySide6.QtCore import Qt, QEventLoop
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QDoubleSpinBox, QSpinBox
)
from omacad.ui.theme import style
from omacad.ui.theme_styles import _STUDIO_CSS

# The main window's right-hand panel; every tool dialog is docked there so none covers the model.
SIDE_HOST = None


def run_docked(dlg) -> int:
    """Like dlg.exec(), but the dialog sits cleanly in the right-hand side panel."""
    if SIDE_HOST is None:
        return QDialog.exec(dlg)
    SIDE_HOST.dock(dlg)
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    loop.exec()
    return dlg.result()


# Studio tool panels (Chamfer in the design proposal): a heading, labels in muted text above their fields,
# grouped buttons at the bottom; the same rules for every tool built on this class.
_STUDIO_PANEL = _STUDIO_CSS + """
    QDialog { background-color: @surface; border: none; border-radius: 8px; }
    QLabel { color: @muted; font-size: 12px; }
    QLabel#StudioHeading { color: @text; font-size: 18px; font-weight: 500; }
    QCheckBox, QRadioButton { color: @text; }
    QFrame[frameShape="4"] { color: @border; }
"""


def studio_layout(dlg) -> None:
    """With a Studio theme: the panel gets its title as a heading and every form puts its labels above the fields.
    Only the layout changes; the fields, their order and their bindings stay as each tool built them."""
    from PySide6.QtWidgets import QFormLayout, QLabel
    from omacad.ui import theme
    if not theme.palette().studio:
        return
    for form in dlg.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(6)
    layout = dlg.layout()
    title = dlg.windowTitle().strip()
    if layout is not None and title and not dlg.findChild(QLabel, "StudioHeading"):
        heading = QLabel(title)
        heading.setObjectName("StudioHeading")
        layout.insertWidget(0, heading)


class BaseFeatureDialog(QDialog):
    """Base modal dialog with Fusion 360 styling, docked in the right side panel."""

    def __init__(self, title: str, parent=None, embedded: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._embedded = embedded
        self.setFixedWidth(358)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        style(self, """
            QDialog {
                background-color: #25282C;
                border: 1px solid #3E444D;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #33373E;
                color: #E0E3E7;
                border: 1px solid #4D535E;
                border-bottom: 2px solid #25282D;
                border-radius: 5px;
                padding: 7px 18px;
                font-weight: 600;
                font-size: 13px;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #3E434C;
                border-color: #5C6370;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #E26D28;
                border: 1px solid #E26D28;
                border-top: 2px solid #B85317;
                color: #FFFFFF;
                padding-top: 8px;
            }
            QPushButton#PrimaryButton, QPushButton:default {
                background-color: #E26D28;
                border: 1px solid #FF7E36;
                border-bottom: 2px solid #B85317;
                color: #FFFFFF;
                font-weight: bold;
                padding: 7px 22px;
            }
            QPushButton#PrimaryButton:hover, QPushButton:default:hover {
                background-color: #FF7E36;
                border-color: #FFA566;
                color: #FFFFFF;
            }
            QPushButton#PrimaryButton:pressed, QPushButton:default:pressed {
                background-color: #C45B1C;
                border: 1px solid #B85317;
                border-top: 2px solid #8C3A0A;
                color: #FFFFFF;
                padding-top: 8px;
            }
        """, studio=_STUDIO_PANEL)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(12)

    def exec(self):
        return run_docked(self)

    def showEvent(self, event):
        if not getattr(self, "_studio_done", False):
            self._studio_done = True
            studio_layout(self)
        super().showEvent(event)

    def place(self, parent_size=None, left: bool = False):
        """Docks the dialog in the right-hand side panel."""
        if SIDE_HOST is not None:
            SIDE_HOST.dock(self)

    def primary_field(self):
        """The number field that typing in the 3D view goes to: the distance/size field, else the first
        visible, editable number field."""
        named = [getattr(self, n, None) for n in ("spn_dist", "spn_size")]
        for field in [f for f in named if f is not None] + self.findChildren(QDoubleSpinBox) + self.findChildren(QSpinBox):
            if field.isVisibleTo(self) and field.isEnabled() and not field.isReadOnly():
                return field
        return None

    def number_fields(self) -> list:
        """The visible, editable number fields in the order Tab visits them."""
        out = []
        w = self.nextInFocusChain()
        while w is not None and w is not self:
            if (isinstance(w, (QDoubleSpinBox, QSpinBox)) and w.isVisibleTo(self) and w.isEnabled()
                    and not w.isReadOnly() and w not in out):
                out.append(w)
            w = w.nextInFocusChain()
        return out

    def focusNextPrevChild(self, forward: bool) -> bool:
        """Tab / Shift+Tab move between the number fields only (as in Fusion), wrapping round, with the value
        selected so typing replaces it (Björn #47). Panels without number fields keep Qt's own order."""
        fields = self.number_fields()
        if not fields:
            return super().focusNextPrevChild(forward)
        cur = self.focusWidget()
        idx = next((i for i, f in enumerate(fields) if f is cur or f.isAncestorOf(cur)), None) if cur else None
        nxt = fields[0] if idx is None else fields[(idx + (1 if forward else -1)) % len(fields)]
        nxt.setFocus(Qt.FocusReason.TabFocusReason)
        nxt.lineEdit().selectAll()
        return True

    def focus_primary(self) -> bool:
        """Put the cursor in the primary field with its text selected, so the first digit replaces it."""
        field = self.primary_field()
        if field is None:
            return False
        field.setFocus(Qt.FocusReason.OtherFocusReason)
        field.lineEdit().setFocus(Qt.FocusReason.OtherFocusReason)
        field.lineEdit().selectAll()
        return True

    def add_buttons(self):
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setObjectName("PrimaryButton")
        self.btn_ok.setDefault(True)  # Enter confirms, as in Fusion
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)

        self.main_layout.addLayout(btn_layout)
