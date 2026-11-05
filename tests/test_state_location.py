"""Settings must survive a restart of the one-file Windows exe (requests #173, #174, #175, #177)."""
from pathlib import Path

from omacad.hybrid_paths import state_dir
from omacad.ui.settings import DEFAULT_SETTINGS, SettingsManager, default_settings


def test_the_windows_exe_keeps_its_state_in_appdata_not_in_its_temporary_folder():
    path = state_dir(env={"APPDATA": r"C:\Users\x\AppData\Roaming"}, frozen=True, platform="win32",
                     source_root=Path(r"C:\Users\x\AppData\Local\Temp\_MEI123"))
    assert path == Path(r"C:\Users\x\AppData\Roaming") / "Omacad Hybrid"


def test_without_appdata_the_exe_still_stays_in_the_users_profile():
    home = Path("/users/x")
    path = state_dir(env={}, frozen=True, platform="win32", source_root=Path("/temp/_MEI123"), home=home)
    assert path == home / "AppData" / "Roaming" / "Omacad Hybrid"


def test_a_frozen_linux_app_uses_the_users_state_folder():
    home = Path("/home/x")
    assert state_dir(env={}, frozen=True, platform="linux", home=home) == home / ".local/state/omacad-hybrid"
    assert state_dir(env={"XDG_STATE_HOME": "/s"}, frozen=True, platform="linux", home=home) == Path("/s/omacad-hybrid")


def test_a_checkout_keeps_its_own_state_and_the_override_wins():
    assert state_dir(env={}, frozen=False, source_root=Path("/repo")) == Path("/repo/.state")
    assert state_dir(env={"OMACAD_HYBRID_STATE_DIR": "/x"}, frozen=True, platform="win32") == Path("/x")


def test_saved_choices_are_there_after_a_restart_and_no_temporary_file_is_left(tmp_path):
    path = tmp_path / "config" / "settings.json"
    SettingsManager(path).update({"rfc_token": "abc", "theme_mode": "fixed", "theme_name": "graphite",
                                  "show_button_labels": True})
    again = SettingsManager(path)
    assert again.get("rfc_token") == "abc"
    assert (again.get("theme_mode"), again.get("theme_name")) == ("fixed", "graphite")
    assert again.get("show_button_labels") is True
    assert [p.name for p in path.parent.iterdir()] == ["settings.json"]


def test_windows_starts_in_studio_with_its_icons_and_linux_defaults_stay():
    windows = default_settings("win32")
    assert (windows["theme_mode"], windows["theme_name"], windows["icon_theme"]) == ("fixed", "studio", "studio")
    assert default_settings("linux") == DEFAULT_SETTINGS


def test_a_saved_choice_wins_over_the_windows_default(tmp_path, monkeypatch):
    monkeypatch.setattr("omacad.ui.settings.sys.platform", "win32")
    path = tmp_path / "settings.json"
    assert SettingsManager(path).get("icon_theme") == "studio"
    SettingsManager(path).set("icon_theme", "solid")
    assert SettingsManager(path).get("icon_theme") == "solid"
