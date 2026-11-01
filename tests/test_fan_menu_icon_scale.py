"""The fan menu icon scale is saved and changes rendered icon size."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from omacad.ui import settings as settings_module, theme
from omacad.ui.fan_menu import FanItem, FanMenu, SectorGeom
from omacad.ui.settings import SettingsManager
from omacad.ui.settings_dialog import SettingsDialog


def test_icon_scale_is_saved_and_reset(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "_instance", SettingsManager(path))
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)

    dialog = SettingsDialog()
    assert dialog.spn_fan_icon_scale.value() == 100
    dialog.spn_fan_icon_scale.setValue(150)
    dialog.save_and_close()
    assert SettingsManager(path).get("fan_menu_icon_scale") == 1.5

    dialog = SettingsDialog()
    assert dialog.spn_fan_icon_scale.value() == 150
    dialog.reset_all()
    assert dialog.spn_fan_icon_scale.value() == 100
    dialog.close()


def test_icon_scale_changes_the_actual_fan_menu_icon(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    manager = SettingsManager(tmp_path / "settings.json")
    monkeypatch.setattr(settings_module, "_instance", manager)
    viewport = QWidget()
    menu = FanMenu(viewport)
    menu.center_pos = QPointF(200, 200)
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#ff0000"))
    sector = SectorGeom(FanItem("tool", "", icon=QIcon(pixmap)), 45, 70, 100, 200, QPainterPath())

    counts = []
    for scale in (0.5, 1.5):
        manager.set("fan_menu_icon_scale", scale)
        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("#000000"))
        painter = QPainter(image)
        menu._draw_sector_content(painter, sector, QColor("#ffffff"), QColor("#ffffff"))
        painter.end()
        counts.append(sum(image.pixelColor(x, y) == QColor("#ff0000")
                          for y in range(400) for x in range(400)))
    assert counts[1] > counts[0] * 2
