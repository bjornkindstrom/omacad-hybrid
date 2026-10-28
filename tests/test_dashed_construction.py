import numpy as np
from omacad.ui.viewport.render_mixin import dash_lines


def _px(p):
    return (float(p[0]), float(p[1]))


def test_straight_line_is_cut_into_dashes():
    out = np.array(dash_lines([0, 0, 0, 150, 0, 0], _px)).reshape(-1, 2, 3)
    assert len(out) == 10                       # 150 px / (9+6)
    assert np.allclose(out[0], [[0, 0, 0], [9, 0, 0]])
    assert np.allclose(out[1][0], [15, 0, 0])


def test_phase_carries_over_short_segments():
    flat = []
    for i in range(30):                         # 30 pieces of 5 px = same line as 150 px
        flat += [i * 5, 0, 0, i * 5 + 5, 0, 0]
    out = np.array(dash_lines(flat, _px)).reshape(-1, 2, 3)
    total = sum(np.linalg.norm(b - a) for a, b in out)
    assert abs(total - 90.0) < 1e-6             # 10 dashes of 9 px


def test_render_uses_saved_guide_gap():
    from types import SimpleNamespace
    from omacad.ui import settings
    from omacad.ui.viewport.render_mixin import RenderGLMixin

    manager = settings.get_settings()
    line = [0, 0, 0, 150, 0, 0]
    view = SimpleNamespace(world_to_screen=_px)
    for gap in (1.0, 6.0, 18.5, 50.0):
        manager.set("guide_line_gap", gap)
        reloaded = settings.SettingsManager(manager.config_file)
        assert reloaded.get("guide_line_gap") == gap
        out = np.array(RenderGLMixin.dash_segments(view, line)).reshape(-1, 2, 3)
        assert np.isclose(out[1, 0, 0] - out[0, 1, 0], gap)
        assert np.isclose(out[0, 1, 0] - out[0, 0, 0], 9.0)


def test_guide_gap_dialog_saves_reopens_and_resets(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from omacad.ui import settings, theme
    from omacad.ui.settings_dialog import SettingsDialog

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(theme, "set_fixed_theme", lambda *_: None)
    dlg = SettingsDialog()
    assert dlg.spn_guide_gap.value() == 6.0
    dlg.spn_guide_gap.setValue(18.5)
    dlg.save_and_close()
    assert settings.get_settings().get("guide_line_gap") == 18.5
    reopened = SettingsDialog()
    assert reopened.spn_guide_gap.value() == 18.5
    reopened.reset_all()
    assert reopened.spn_guide_gap.value() == 6.0
    reopened.save_and_close()
    assert settings.get_settings().get("guide_line_gap") == 6.0
    dlg.deleteLater()
    reopened.deleteLater()
    app.processEvents()


def test_fractional_gaps_keep_exact_spacing_on_long_lines():
    for gap in (1.1, 6.1, 18.5, 49.9):
        out = np.array(dash_lines([0, 0, 0, 1500, 0, 0], _px, gap_px=gap)).reshape(-1, 2, 3)
        assert np.allclose(out[1:, 0, 0] - out[:-1, 1, 0], gap)
        assert np.allclose(out[:-1, 1, 0] - out[:-1, 0, 0], 9.0)
