"""Björn #74: sketch line and selected line thickness (and selected colour) are settings, thinner by default."""
from PySide6.QtWidgets import QApplication

from omacad.ui.settings import get_settings, sketch_line_widths
from omacad.ui.settings_dialog import SettingsDialog


def test_defaults_are_thinner_and_settings_are_used():
    assert sketch_line_widths() == (1.6, 2.4)
    get_settings().set("sketch_line_width", 1.0)
    get_settings().set("selected_line_width", 99)
    assert sketch_line_widths() == (1.0, 12.0)      # held to a sane range


def test_settings_dialog_saves_and_resets_them():
    QApplication.instance() or QApplication([])
    dlg = SettingsDialog()
    dlg.spn_sketch_w.setValue(1.2)
    dlg.spn_selected_w.setValue(3.0)
    dlg.save_and_close()
    assert sketch_line_widths() == (1.2, 3.0)
    dlg = SettingsDialog()
    dlg.reset_all()
    assert (dlg.spn_sketch_w.value(), dlg.spn_selected_w.value()) == (1.6, 2.4)
