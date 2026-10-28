"""The rectangle ribbon button: one button with a dropdown, and a remembered default."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")        # CI installs only the modelling dependencies

from omacad.model.document import Document  # noqa: E402
from omacad.ui import settings as settings_mod  # noqa: E402
from omacad.ui.ribbon import RECT_TOOLS  # noqa: E402


@pytest.fixture
def ribbon(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_mod, "_instance", settings_mod.SettingsManager(tmp_path / "s.json"))
    from omacad.ui.ribbon import Ribbon
    return Ribbon(Document())


def test_default_is_remembered_and_drives_the_button(ribbon):
    chosen = []
    ribbon.sketch_tool_selected.connect(chosen.append)
    ribbon.set_rect_default("ROUNDED_RECT")
    ribbon.btn_rect.click()
    assert chosen == ["ROUNDED_RECT"]
    assert settings_mod.get_settings().get("rect_default_tool") == "ROUNDED_RECT"
    assert ribbon.btn_rect.text() == RECT_TOOLS["ROUNDED_RECT"][0]


def test_dropdown_lists_every_kind(ribbon):
    labels = [a.text() for a in ribbon.btn_rect.menu().actions() if a.text()]
    assert all(t.replace("\n", " ") in labels for t, _ in RECT_TOOLS.values())


def test_palette_shows_sides_and_corner_radius_only_for_their_tools():
    from PySide6.QtWidgets import QApplication
    from omacad.model.document import Document
    from omacad.ui.viewport import Viewport3D
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.start_sketch()
    vp = Viewport3D(doc)
    pal = vp.sketch_palette
    for tool, sides, radius in (("NONE", False, False), ("POLYGON", True, False), ("ROUNDED_RECT", False, True),
                                ("CENTER_ROUNDED_RECT", False, True), ("LINE", False, False), ("RECT", False, False)):
        vp.set_sketch_tool(tool)
        # the tool panel shows them now (with sliders); the palette rows only keep the defaults (#76)
        assert pal.sides_row.isHidden() and pal.radius_row.isHidden(), tool
        assert ("Sides" in vp.tool_panel.spins, "Radius" in vp.tool_panel.spins) == (sides, radius), tool
    vp.close()
    vp.deleteLater()
    app.processEvents()
