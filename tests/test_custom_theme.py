"""Custom themes: every colour set by hand in the theme editor, saved under a name, shown live."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from omacad.ui import theme  # noqa: E402


@pytest.fixture(autouse=True)
def reset(tmp_path, monkeypatch):
    monkeypatch.setattr(theme, "CUSTOM_DIR", tmp_path / "themes")
    yield
    theme.FIXED_THEME = None
    theme.PREVIEW = None
    theme._palette = theme.load_palette()


def test_save_load_and_use_a_custom_theme():
    key = theme.save_custom_theme("Night shift", {
        "mode": "dark", "background": "#101820", "darker_background": "#080C10", "foreground": "#DDEEFF",
        "muted": "#667788", "accent": "#FF00AA", "highlight": "#00FF88", "canvas": "#010203", "grid": "#304050",
        "tool_measure": "#123456"})
    assert key == "user:Night shift" and theme.custom_themes() == ["Night shift"]
    theme.set_fixed_theme(key)
    p = theme.palette()
    assert p.canvas_rgb01() == pytest.approx((1 / 255, 2 / 255, 3 / 255))
    assert p.grid_rgb01() == pytest.approx((0x30 / 255, 0x40 / 255, 0x50 / 255))
    assert p.highlight01() == pytest.approx((0, 1, 136 / 255))
    assert theme.load_theme_data(key)["tool_measure"] == "#123456"


def test_preview_overrides_and_is_cleared():
    theme.set_fixed_theme("nord")
    theme.set_preview({"background": "#FFFFFF", "canvas": "#0A0B0C"})
    assert theme.palette().canvas_rgb01() == pytest.approx((10 / 255, 11 / 255, 12 / 255))
    theme.set_preview(None)
    assert theme.palette().canvas_rgb01() != pytest.approx((10 / 255, 11 / 255, 12 / 255))


def test_delete_and_unsafe_names():
    assert theme.safe_theme_name("../a/b*") == "ab"
    key = theme.save_custom_theme("x", {"background": "#000000"})
    theme.delete_custom_theme("x")
    assert theme.custom_themes() == []
    with pytest.raises(ValueError):
        theme.save_custom_theme("///", {})


def test_editor_tab_collects_every_role_and_saves():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.theme_editor import ThemeEditorTab, THEME_ROLES
    tab = ThemeEditorTab()
    d = tab.collect()
    for key, _l, _t in THEME_ROLES:
        assert d[key].startswith("#")
    tab.rows["canvas"].current_hex = "#112233"
    tab.edt_name.setText("Mine")
    got = []
    tab.saved.connect(got.append)
    tab._save()
    assert got == ["user:Mine"]
    assert theme.load_theme_data("user:Mine")["canvas"] == "#112233"


def test_editor_preview_keeps_a_role_theme_look():
    """Opening the editor previews the current colours; with Studio/Graphite/Atelier that preview must keep the
    panels, fields, font and corners (it used to drop them, and the whole app fell back to the old look)."""
    from PySide6.QtWidgets import QApplication
    from omacad.ui import theme
    from omacad.ui.theme_editor import ThemeEditorTab
    QApplication.instance() or QApplication([])
    theme.set_fixed_theme("graphite")
    try:
        tab = ThemeEditorTab()
        tab._load_base()
        assert theme.PREVIEW is not None and theme.palette().studio
        assert theme.palette().radius == 3 and theme.current_font() == "Noto Sans"
        tab.rows["background"].current_hex = "#223344"           # Background = the panels
        tab._preview()
        assert theme.palette().map_hex("#25282C") == "#223344"
    finally:
        theme.set_preview(None)
        theme.set_fixed_theme(None)
