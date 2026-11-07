"""Shell thickness controls stay visible when docked (report 20261107-084755)."""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.ui.dialogs.shell_dlg import ShellDialog
from omacad.ui.main_window import MainWindow
from omacad.ui.numeric_slider import NumericSlider


@pytest.mark.parametrize("initial_direction", [0, 1, 2])
def test_docked_shell_keeps_thickness_controls(initial_direction):
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    doc = Exporter.load_project(str(Path(__file__).parent / "data/shell_panel.omacad"))
    dlg = ShellDialog(doc, win)
    dlg.cmb_dir.setCurrentIndex(initial_direction)
    try:
        win.dock(dlg)
        app.processEvents()
        for direction in [initial_direction, 2, 0, 1, 2]:
            dlg.cmb_dir.setCurrentIndex(direction)
            app.processEvents()
            for field, label, visible in (
                (dlg.spn_thickness, dlg.lbl_thick, True),
                (dlg.spn_thickness2, dlg.lbl_thick2, direction == 2),
            ):
                wrapper = field.parentWidget()
                assert isinstance(wrapper, NumericSlider)
                assert field.isVisibleTo(dlg) == visible
                assert label.isVisibleTo(dlg) == visible
                assert wrapper.isVisibleTo(dlg) == visible
                assert wrapper.slider.isVisibleTo(dlg) == visible
        dlg.spn_thickness.setValue(3.5)
        assert dlg.get_values()[1] == 3.5
        dlg.spn_thickness.parentWidget().slider.setValue(1000)
        assert dlg.get_values()[1] == dlg.spn_thickness.value() > 3.5
    finally:
        dlg.reject()
        win.close()
