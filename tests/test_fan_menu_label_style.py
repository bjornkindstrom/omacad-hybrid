"""Fan menu label layouts are selectable and persist in Hybrid settings."""
import hashlib

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from omacad.ui import settings as settings_module, theme
from omacad.ui.fan_menu import FanItem, FanMenu
from omacad.ui.settings import SettingsManager
from omacad.ui.settings_dialog import SettingsDialog


def test_fan_menu_label_choice_saves_and_resets(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "_instance", SettingsManager(path))
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)

    dlg = SettingsDialog()
    assert dlg.cmb_fan_labels.currentData() == "curved"
    dlg.cmb_fan_labels.setCurrentIndex(dlg.cmb_fan_labels.findData("readable_curved"))
    dlg.save_and_close()
    assert SettingsManager(path).get("fan_menu_label_style") == "readable_curved"

    dlg = SettingsDialog()
    assert dlg.cmb_fan_labels.currentData() == "readable_curved"
    dlg.cmb_fan_labels.setCurrentIndex(dlg.cmb_fan_labels.findData("horizontal"))
    dlg.reset_all()
    assert dlg.cmb_fan_labels.currentData() == "curved"
    dlg.close()


def test_all_three_label_styles_render_differently(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    manager = SettingsManager(tmp_path / "settings.json")
    monkeypatch.setattr(settings_module, "_instance", manager)
    viewport = QWidget()
    viewport.resize(800, 700)
    menu = FanMenu(viewport)
    categories = [FanItem(f"cat_{i}", name, children=[FanItem("tool", "Extrude")])
                  for i, name in enumerate(("Create", "Modify", "Inspect", "View", "History"))]
    menu.popup(QPoint(400, 350), categories)
    rendered = {}
    for style in ("curved", "readable_curved", "horizontal"):
        manager.set("fan_menu_label_style", style)
        image = QImage(800, 700, QImage.Format.Format_RGB32)
        image.fill(QColor("#17202a"))
        painter = QPainter(image)
        menu.draw(painter, image.width(), image.height())
        painter.end()
        rendered[style] = hashlib.sha256(image.bits()).hexdigest()
    assert len(set(rendered.values())) == 3
