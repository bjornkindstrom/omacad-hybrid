"""Studio theme (design/appearance-proposals proposal 1): white panels on a grey-blue window, blue accent, Noto Sans.
Selectable and saved in Settings; its extra rules never leak into the other themes."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFormLayout, QLabel, QWidget  # noqa: E402

from omacad.ui import theme  # noqa: E402


@pytest.fixture(autouse=True)
def reset():
    QApplication.instance() or QApplication([])
    yield
    theme.set_fixed_theme(None)


def test_studio_surfaces_by_role():
    theme.set_fixed_theme("studio")
    p = theme.palette()
    assert p.studio
    assert p.map_hex("#25282C") == "#FFFFFF"      # panels and menus: white
    assert p.map_hex("#1A1C1E") == "#F2F5F9"      # fields
    assert p.map_hex("#1E2022") == "#E9EDF2"      # window
    assert p.map_hex("#E0E3E7") == "#253247"      # text
    assert p.map_hex("#E26D28") == "#2863D9"      # the accent family becomes the blue
    assert [round(v * 255) for v in p.canvas_rgb01()] == [0xF2, 0xF4, 0xF8]
    assert theme.current_font() == "Noto Sans"


def test_see_through_dark_panels_become_solid_cards_but_hover_tints_stay_light():
    theme.set_fixed_theme("studio")
    assert "0.85" not in theme.themeify("background-color: rgba(32, 34, 37, 0.85);")
    assert "0.4)" in theme.themeify("background-color: rgba(60, 68, 79, 0.4);")


def test_other_themes_are_unchanged():
    theme.set_fixed_theme("tokyo-night")
    p = theme.palette()
    assert not p.studio
    expected = theme._hex(theme._mix(p.darker, p.foreground, (theme._lum(theme._rgb("#25282C")) - 0.10) / 0.80))
    assert p.map_hex("#25282C") == expected
    assert "0.85" in theme.themeify("background-color: rgba(32, 34, 37, 0.85);")


def test_studio_rules_follow_the_theme_switch():
    w = QWidget()
    theme.set_fixed_theme("tokyo-night")
    theme.style(w, "QWidget { color: #E0E3E7; }", "QWidget { background: @surface; border: 1px solid @border; }")
    assert "#D7DFEA" not in w.styleSheet()
    theme.set_fixed_theme("studio")
    assert "#D7DFEA" in w.styleSheet() and "#FFFFFF" in w.styleSheet()
    theme.set_fixed_theme("nord")
    assert "#D7DFEA" not in w.styleSheet()


def test_bare_declarations_are_replaced_by_the_studio_rules():
    w = QLabel()
    theme.set_fixed_theme("studio")
    theme.style(w, "color: #8E95A0; background: transparent;", "QLabel { color: @muted; }")
    assert w.styleSheet() == "QLabel { color: #64748B; }"


def test_tool_panel_gets_a_heading_and_labels_above_fields_only_in_studio():
    from omacad.ui.dialogs.base import BaseFeatureDialog
    from PySide6.QtWidgets import QDoubleSpinBox

    def panel():
        d = BaseFeatureDialog("Chamfer")
        form = QFormLayout()
        form.addRow("Distance:", QDoubleSpinBox())
        d.main_layout.addLayout(form)
        d.show()
        return d, form

    theme.set_fixed_theme("studio")
    d, form = panel()
    assert form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows
    assert d.findChild(QLabel, "StudioHeading").text() == "Chamfer"
    d.close()
    theme.set_fixed_theme("tokyo-night")
    d, form = panel()
    assert form.rowWrapPolicy() != QFormLayout.RowWrapPolicy.WrapAllRows
    assert d.findChild(QLabel, "StudioHeading") is None
    d.close()


def test_studio_is_chosen_saved_and_shown_again(monkeypatch):
    from omacad.ui.settings import SettingsManager, get_settings
    from omacad.ui.settings_dialog import SettingsDialog
    picked = []
    monkeypatch.setattr(theme, "set_fixed_theme", picked.append)
    dlg = SettingsDialog()
    dlg.cmb_theme_mode.setCurrentIndex(dlg.cmb_theme_mode.findData("studio"))
    dlg.save_and_close()
    saved = SettingsManager(get_settings().config_file)
    assert (saved.get("theme_mode"), saved.get("theme_name")) == ("fixed", "studio")
    assert picked == ["studio"]
    dlg = SettingsDialog()
    assert dlg.cmb_theme_mode.currentData() == "studio"
    dlg.close()
    theme.apply_saved_choice()
    assert theme.FIXED_THEME == "studio" and theme.palette().studio


def test_studio_icons_are_one_colour_and_blue_when_active():
    from PySide6.QtGui import QIcon
    from omacad.ui import theme_icons
    from omacad.ui.settings import get_settings
    get_settings().set("icon_theme", "studio")
    theme.set_fixed_theme("studio")
    theme_icons.clear_icon_cache()

    def colours(mode_state):
        img = icon.pixmap(48, 48, QIcon.Mode.Normal, mode_state).toImage()
        return {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())
                if img.pixelColor(x, y).alpha() == 255}

    for name in ("〰️", "🏺", "fillet", "chamfer"):     # the drawn Sweep/Loft and recoloured Blueprint icons
        icon = theme_icons.tool_icon(name, 24)
        assert colours(QIcon.State.Off) == {"#253247"}
        assert colours(QIcon.State.On) == {"#2863d9"}


def test_icons_only_drawn_for_studio_keep_their_emoji_in_other_sets():
    from omacad.ui import theme_icons
    from omacad.ui.settings import get_settings
    get_settings().set("icon_theme", "solid")
    assert not (theme_icons.ICONS_DIR / "solid" / "sweep.svg").exists()
    assert not theme_icons.tool_icon("〰️", 24).isNull()


def test_choosing_the_studio_theme_suggests_studio_icons(monkeypatch):
    from omacad.ui.settings_dialog import SettingsDialog
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)
    dlg = SettingsDialog()
    i = dlg.cmb_theme_mode.findData("studio")
    dlg.cmb_theme_mode.setCurrentIndex(i)
    dlg.cmb_theme_mode.activated.emit(i)
    assert dlg.cmb_icon_theme.currentData() == "studio"
    dlg.close()


def test_every_command_step_and_constraint_has_its_own_studio_icon():
    """No function falls back to an emoji in the Studio set, and commands only share an icon when they do the same
    thing in the other workspace (Mirror/Move in a sketch and on bodies)."""
    from collections import defaultdict
    from omacad.ui import commands, theme_icons
    from omacad.ui.ribbon import Ribbon
    from omacad.ui.timeline_bar import FeatureNodeWidget
    studio = theme_icons.ICONS_DIR / theme_icons.STUDIO_ICONS
    has = lambda name: (studio / f"{name}.svg").exists()
    users = defaultdict(set)
    cmds = commands.COMMANDS.values() if isinstance(commands.COMMANDS, dict) else commands.COMMANDS
    for c in cmds:
        name = theme_icons.COMMAND_ICONS.get(c.cid) or theme_icons.EMOJI_TO_TOOL.get(c.icon, c.icon)
        assert has(name), c.cid
        users[name].add(c.label)
    assert {n: u for n, u in users.items() if len(u) > 1} == {}
    for ftype, emoji in FeatureNodeWidget.FEATURE_ICONS.items():
        assert has(theme_icons.EMOJI_TO_TOOL.get(emoji, "")), ftype
    for ctype, _label, symbol, _tip in Ribbon.CONSTRAINTS:
        assert has(theme_icons.EMOJI_TO_TOOL.get(symbol, "")), ctype


def test_emoji_icons_become_studio_icons_only_with_the_studio_set():
    from omacad.ui import theme_icons
    from omacad.ui.settings import get_settings
    get_settings().set("icon_theme", "studio")
    theme_icons.clear_icon_cache()
    img = theme_icons.emoji_icon("💾", 24).pixmap(48, 48).toImage()
    seen = {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())
            if img.pixelColor(x, y).alpha() == 255}
    assert seen and seen <= {"#253247", "#1d2939", "#e0e3e7"}       # a one-colour line icon, not the coloured emoji
    get_settings().set("icon_theme", "solid")
    assert theme_icons.studio_symbol("💾 Save") == (None, "💾 Save")


def test_tree_steps_get_studio_icons_by_type_and_kind():
    from types import SimpleNamespace as NS
    from omacad.ui import object_browser
    from omacad.ui.settings import get_settings
    icon = lambda ftype, kind="": object_browser._feature_studio_icon(NS(feature_type=ftype, kind=kind))
    get_settings().set("icon_theme", "studio")
    assert (icon("fillet", "fillet"), icon("fillet", "chamfer")) == ("fillet", "chamfer")
    assert [icon("pattern", k) for k in ("linear", "circular", "fill", "mirror")] == [
        "pattern_linear", "pattern_circular", "pattern_fill", "mirror"]
    assert (icon("move"), icon("extrude"), icon("hole")) == ("move", "extrude", "hole")
    get_settings().set("icon_theme", "solid")
    assert icon("fillet", "chamfer") == ""          # other sets keep their emoji


@pytest.mark.parametrize("name, window, surface, accent, radius", [
    ("graphite", "#12171F", "#1D2531", "#F2B35E", 3),
    ("atelier", "#E7E4DC", "#FAF9F5", "#39735D", 14),
])
def test_graphite_and_atelier_use_the_same_role_rules_with_their_own_colours(name, window, surface, accent, radius):
    theme.set_fixed_theme(name)
    p = theme.palette()
    assert p.studio
    assert (p.map_hex("#1E2022"), p.map_hex("#25282C"), p.map_hex("#E26D28")) == (window, surface, accent)
    sheet = theme.studio_sheet("QFrame { border-radius: 8px; background: @accent; color: @on_accent; }")
    assert f"border-radius: {radius}px" in sheet and accent in sheet


def test_text_on_the_accent_stays_readable():
    theme.set_fixed_theme("graphite")                          # light amber: dark text on the primary button
    assert theme.studio_sheet("@on_accent") == "#1A1408"
    theme.set_fixed_theme("atelier")                           # dark green: white text
    assert theme.studio_sheet("@on_accent") == "#FFFFFF"


@pytest.mark.parametrize("key", ["graphite", "atelier"])
def test_graphite_and_atelier_are_chosen_and_saved(monkeypatch, key):
    from omacad.ui.settings import SettingsManager, get_settings
    from omacad.ui.settings_dialog import SettingsDialog
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)
    dlg = SettingsDialog()
    i = dlg.cmb_theme_mode.findData(key)
    dlg.cmb_theme_mode.setCurrentIndex(i)
    dlg.cmb_theme_mode.activated.emit(i)
    assert dlg.cmb_icon_theme.currentData() == "studio"        # the line icons come with every proposal theme
    dlg.save_and_close()
    saved = SettingsManager(get_settings().config_file)
    assert (saved.get("theme_mode"), saved.get("theme_name")) == ("fixed", key)
    assert SettingsDialog().cmb_theme_mode.currentData() == key


@pytest.mark.parametrize("icon_set", ["solid", "blueprint", "semantic", "studio"])
def test_each_rectangle_kind_has_its_own_icon_and_the_button_shows_the_default(icon_set):
    from omacad.model.document import Document
    from omacad.ui import theme_icons
    from omacad.ui.ribbon import Ribbon
    from omacad.ui.settings import get_settings
    from omacad.ui.sketch_tools import RECT_TOOLS
    get_settings().set("icon_theme", icon_set)
    theme_icons.clear_icon_cache()
    images = {}
    for tool in RECT_TOOLS:
        assert (theme_icons.ICONS_DIR / icon_set / f"{tool.lower()}.svg").exists()
        images[tool] = theme_icons.tool_icon(tool.lower(), 30).pixmap(30, 30).toImage()
    kinds = list(images.values())
    assert all(a != b for i, a in enumerate(kinds) for b in kinds[i + 1:])     # four different pictures
    ribbon = Ribbon(Document("t"))
    ribbon.set_rect_default("CENTER_ROUNDED_RECT", save=False)
    ribbon.btn_rect.apply_scale()                                                # restyling keeps it
    assert ribbon.btn_rect.icon().pixmap(30, 30).toImage() == images["CENTER_ROUNDED_RECT"]


@pytest.mark.parametrize("name", ["studio", "graphite", "atelier"])
def test_coloured_status_text_reads_on_the_panels(name):
    """Björn #89: text in panels must be readable. Status colours come from the theme and keep a contrast of at
    least 3:1 to the panels (WCAG for bold text); a fixed light green/yellow on white did not."""
    theme.set_fixed_theme(name)
    p = theme.palette()

    def lum(c):          # WCAG relative luminance (linear sRGB)
        lin = [v / 255 / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def contrast(a, b):
        la, lb = sorted((lum(a), lum(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)
    surface = p.surfaces["surface"]
    for colour in (p.ok, p.accent, p.muted, p.foreground):
        assert contrast(colour, surface) >= 3.0, theme._hex(colour)


def test_finished_sketches_are_grey_unless_a_colour_is_chosen():
    """Björn #90: a finished sketch read as heavy black lines (orange core in a 3.5 px dark rim); now a theme grey."""
    from omacad.ui.settings import finished_sketch_grey, get_settings
    theme.set_fixed_theme("atelier")
    light_view = finished_sketch_grey()
    theme.set_fixed_theme("graphite")
    dark_view = finished_sketch_grey()
    assert max(light_view) - min(light_view) < 0.1 and max(dark_view) - min(dark_view) < 0.1     # grey
    assert sum(dark_view) > sum(light_view)                                    # lighter grey on a dark view
    assert get_settings().sketch_finished_color_rgb01() == dark_view
    get_settings().set("sketch_finished_color", "#FF0000")
    assert get_settings().sketch_finished_color_rgb01() == (1.0, 0.0, 0.0)
