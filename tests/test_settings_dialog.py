"""Test that SettingsDialog content is scrollable and stays accessible on smaller displays (e.g. Windows laptops)."""

from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea
from omacad.ui.settings_dialog import SettingsDialog


def test_settings_dialog_fits_and_scrolls_on_small_screens():
    QApplication.instance() or QApplication([])
    dlg = SettingsDialog()
    # Check that tabs are embedded in QScrollArea
    assert isinstance(dlg.tabs.widget(0), QScrollArea)
    assert isinstance(dlg.tabs.widget(2), QScrollArea)

    # Simulate opening on a display with constrained vertical height (e.g. 500px)
    dlg.resize(550, 480)
    dlg.show()

    assert dlg.height() <= 480

    # Ensure Save and Cancel buttons are within dialog bounds and visible
    save_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Save")
    cancel_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Cancel")

    assert save_btn.isVisible()
    assert cancel_btn.isVisible()

    save_y = save_btn.mapTo(dlg, save_btn.rect().topLeft()).y()
    assert 0 < save_y < dlg.height()
    dlg.close()


def test_primitive_precision_save_reload_and_reset(monkeypatch):
    from omacad.ui import theme
    from omacad.ui.settings import get_settings, SettingsManager

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)
    dlg = SettingsDialog()
    assert dlg.cmb_primitive_decimals.currentData() == 0
    dlg.cmb_primitive_decimals.setCurrentIndex(2)
    dlg.save_and_close()
    assert SettingsManager(get_settings().config_file).get("primitive_drag_decimals") == 2

    dlg = SettingsDialog()
    assert dlg.cmb_primitive_decimals.currentData() == 2
    dlg.reset_all()
    assert dlg.cmb_primitive_decimals.currentData() == 0
    dlg.close()


def test_category_navigation_and_camera_controls():
    QApplication.instance() or QApplication([])
    dlg = SettingsDialog()
    for index in range(dlg.navigation.count()):
        dlg.navigation.setCurrentRow(index)
        assert dlg.tabs.currentIndex() == index
    dlg.cmb_projection.setCurrentIndex(dlg.cmb_projection.findData("orthographic"))
    assert not dlg.spn_fov.isEnabled()
    dlg.cmb_projection.setCurrentIndex(dlg.cmb_projection.findData("perspective"))
    assert dlg.spn_fov.isEnabled()
    dlg.close()
