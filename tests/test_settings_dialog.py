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


def test_settings_are_grouped_where_they_belong_and_the_token_survives_save(monkeypatch):
    """Lip joint, fan menu, scripts and B-rep sit in their own sections; moving them keeps every value."""
    from PySide6.QtWidgets import QFrame, QLabel
    from omacad.ui import theme
    from omacad.ui.settings import get_settings, SettingsManager

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)
    get_settings().set("rfc_token", "ghp_secret_token_value")
    get_settings().save()
    dlg = SettingsDialog()
    names = [dlg.navigation.item(i).text() for i in range(dlg.navigation.count())]
    assert names == ["Appearance", "Interface", "Modelling", "3D View", "General"]
    assert dlg.tabs.count() == len(names)

    def section(widget):
        card = widget.parentWidget()
        while card is not None and not (isinstance(card, QFrame) and card.objectName() == "SettingsCard"):
            card = card.parentWidget()
        title = next(lbl for lbl in card.findChildren(QLabel) if lbl.objectName() == "SettingsSection")
        page = next(i for i in range(dlg.tabs.count()) if dlg.tabs.widget(i).isAncestorOf(card))
        return names[page], title.text()

    assert section(dlg.chk_split_lip) == ("Modelling", "Primitives & Split Body")
    assert section(dlg.chk_brep) == ("Modelling", "Geometry & quality")
    assert section(dlg.cmb_fan_style) == ("Interface", "Fan menu")
    assert section(dlg.chk_share_scripts) == ("General", "Scripts")
    assert section(dlg.spn_autosave) == ("General", "Saving & updates")
    assert section(dlg.spn_arrow_size) == ("Appearance", "Extrude arrow")
    assert section(dlg.spn_guide_gap) == ("Appearance", "Sketch lines")
    assert section(dlg.chk_tangent_edges) == ("3D View", "Display")
    assert section(dlg.spn_fov) == ("3D View", "Camera")
    assert section(dlg.edt_rfc_token) == ("General", "Change requests & problem reports")

    assert dlg.edt_rfc_token.text() == "ghp_secret_token_value"
    dlg.save_and_close()
    assert SettingsManager(get_settings().config_file).get("rfc_token") == "ghp_secret_token_value"
