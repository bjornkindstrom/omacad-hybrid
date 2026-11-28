"""Selection colours in the 3D view follow the theme (A9)."""
import pytest

from omacad.ui import theme


def test_blue_or_missing_highlight_keeps_the_solidcraft_blues():
    for data in (None, {"highlight": "#1D4ED8"}):
        pal = theme.Palette(data)
        assert pal.selection_edge01() == pytest.approx((0.0, 0.48, 1.0))
        assert pal.selection_face01() == pytest.approx((0.40, 0.61, 0.84))
        assert pal.selected_body01() == pytest.approx((0.43, 0.67, 0.92))


def test_another_highlight_colours_the_selection():
    pal = theme.Palette({"highlight": "#F2B35E"})            # Graphite's amber
    assert pal.selection_edge01() == pytest.approx((0xF2 / 255, 0xB3 / 255, 0x5E / 255))
    r, g, b = pal.selected_body01()
    assert r > g > b                                          # warm, lightened towards white
    assert all(c >= e for c, e in zip(pal.selection_face01(), pal.selection_edge01()))


def test_the_sketch_tint_is_stronger_on_a_dark_canvas(monkeypatch):
    from omacad.ui.viewport.render_mixin import RenderGLMixin
    mix = RenderGLMixin()
    monkeypatch.setattr(theme, "_palette", theme.Palette({"canvas": "#F2F4F8"}))
    assert mix.live_fill_alpha() == RenderGLMixin.LIVE_FILL_ALPHA
    monkeypatch.setattr(theme, "_palette", theme.Palette({"canvas": "#1E2022"}))
    assert mix.live_fill_alpha() == RenderGLMixin.LIVE_FILL_ALPHA_DARK
