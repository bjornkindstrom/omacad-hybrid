"""Soft fan menu looks (design/fan-menu-proposals 1, 3, 4): Soft Ring, Glass Donut, Tiles next to Classic."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from omacad.ui import fan_menu_soft, theme  # noqa: E402
from omacad.ui.fan_menu import FanItem  # noqa: E402
from omacad.ui.settings import get_settings  # noqa: E402


@pytest.fixture
def win():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    w = MainWindow()
    w.viewport.resize(800, 600)
    yield w
    theme.set_fixed_theme(None)
    w.close()
    w.deleteLater()


def _open(win, **hub):
    menu = win.viewport._ensure_fan_menu()
    menu.popup(center=QPointF(400, 300), categories=win.viewport._build_workspace_fan_categories(sketch=False),
               default_category_idx=0, **hub)
    return menu


def _hover_outer(menu, idx):
    sec = menu.outer_sectors[idx]
    a = math.radians(sec.start_angle + sec.span_angle / 2)
    r = (sec.r_inner + sec.r_outer) / 2
    menu.handle_mouse_move(menu.center_pos.x() + r * math.cos(a), menu.center_pos.y() - r * math.sin(a))


def _render(menu) -> QImage:
    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    img.fill(QColor("#EEF1F5"))
    p = QPainter(img)
    try:
        menu.draw(p, 800, 600)
    finally:
        p.end()
    return img


def test_auto_follows_the_theme_and_an_explicit_choice_wins():
    QApplication.instance() or QApplication([])
    try:
        theme.set_fixed_theme("studio_glass")
        assert fan_menu_soft.resolve_style("auto") == "glass"
        theme.set_fixed_theme("studio_soft")
        assert fan_menu_soft.resolve_style("auto") == "soft"
        assert fan_menu_soft.resolve_style("nonsense") == "soft"
        assert [fan_menu_soft.resolve_style(s) for s in ("soft", "glass", "tiles", "classic")] == [
            "soft", "glass", "tiles", "classic"]
        assert get_settings().get("fan_menu_style") == "auto"            # the default
    finally:
        theme.set_fixed_theme(None)


@pytest.mark.parametrize("theme_key", ["studio_soft", "studio_glass", "graphite", None])
def test_every_look_paints_rings_sub_sectors_and_both_hubs(win, theme_key):
    """Each look paints in every kind of theme, with an open sub ring and the split Finish/Cancel hub, and differs
    from the classic picture; the hit areas stay the same (geometry is shared)."""
    theme.set_fixed_theme(theme_key)
    get_settings().set("fan_menu_animation", False)
    menu = _open(win, hub_ok=FanItem(id="ok", label="Finish"), hub_cancel=FanItem(id="no", label="Cancel"))
    prim = next(i for i, s in enumerate(menu.outer_sectors) if s.item.id == "primitives")
    _hover_outer(menu, prim)
    assert menu.hovered_outer_idx == prim and menu.sub_sectors
    pictures = {}
    for style in ("classic", "soft", "glass", "tiles"):
        get_settings().set("fan_menu_style", style)
        pictures[style] = _render(menu)
        assert menu.hovered_outer_idx == prim                           # painting does not touch hover state
    assert len({img.cacheKey() for img in pictures.values()}) == 4
    assert all(pictures[s] != pictures["classic"] for s in ("soft", "glass", "tiles"))


def test_the_hovered_tool_is_filled_with_the_accent_in_soft_and_marked_by_an_arc_in_glass(win):
    theme.set_fixed_theme("studio_soft")
    get_settings().set("fan_menu_animation", False)
    menu = _open(win)
    _hover_outer(menu, 1)
    sec = menu.outer_sectors[1]
    a = math.radians(sec.start_angle + sec.span_angle * 0.15)
    rim = (menu.center_pos.x() + (sec.r_outer - 12) * math.cos(a), menu.center_pos.y() - (sec.r_outer - 12) * math.sin(a))
    accent = QColor(*(round(v) for v in theme.palette().accent))
    get_settings().set("fan_menu_style", "soft")
    px = QColor(_render(menu).pixel(int(rim[0]), int(rim[1])))
    assert abs(px.red() - accent.red()) + abs(px.green() - accent.green()) + abs(px.blue() - accent.blue()) < 30
    get_settings().set("fan_menu_style", "glass")                       # glass: a tint, not a full accent fill
    px = QColor(_render(menu).pixel(int(rim[0]), int(rim[1])))
    assert abs(px.red() - accent.red()) > 60


def test_opening_fades_in_unless_turned_off_or_classic(win):
    theme.set_fixed_theme("studio_soft")
    get_settings().set("fan_menu_style", "soft")
    menu = _open(win)
    assert fan_menu_soft.open_progress(menu) < 1.0
    _render(menu)                                                       # a frame mid-animation paints fine
    get_settings().set("fan_menu_animation", False)
    assert fan_menu_soft.open_progress(_open(win)) == 1.0
    get_settings().set("fan_menu_animation", True)
    get_settings().set("fan_menu_style", "classic")
    assert fan_menu_soft.open_progress(_open(win)) == 1.0


def test_long_names_shrink_then_are_cut_or_left_to_the_tooltip():
    QApplication.instance() or QApplication([])
    f, fits = fan_menu_soft._label_font("Loft", 40, False, 10.5)
    assert fits and f.pixelSize() == round(10.5)
    f, fits = fan_menu_soft._label_font("Primitives", 50, False, 10.5)   # a little smaller font is enough
    assert fits and f.pixelSize() < 10
    f, fits = fan_menu_soft._label_font("Canvas (Image)", 40, False, 10.5)
    assert not fits and f.pixelSize() >= fan_menu_soft.MIN_LABEL_PX - 0.5


def _at(menu, r, deg):
    a = math.radians(deg)
    return menu.center_pos.x() + r * math.cos(a), menu.center_pos.y() - r * math.sin(a)


def test_sliding_sideways_past_a_tool_with_a_sub_ring_moves_on_but_heading_out_keeps_it(win):
    """Björn: hovering past Primitives stopped there; its sub ring's corridor held the hover over most of the ring.
    Now only a move heading outward (or the rim) keeps the sub ring; sliding along the ring reaches the next tool."""
    menu = _open(win)
    prim = next(i for i, s in enumerate(menu.outer_sectors) if s.item.id == "primitives")
    nxt = prim + 1
    sec, other = menu.outer_sectors[prim], menu.outer_sectors[nxt]
    mid = (sec.r_inner + sec.r_outer) / 2
    p_mid, o_mid = sec.start_angle + sec.span_angle / 2, other.start_angle + other.span_angle / 2
    menu.handle_mouse_move(*_at(menu, mid, p_mid))
    assert menu.hovered_outer_idx == prim and menu.sub_sectors
    for t in (0.25, 0.5, 0.75, 1.0):                       # slide along the middle of the ring
        menu.handle_mouse_move(*_at(menu, mid, p_mid + (o_mid - p_mid) * t))
    assert menu.hovered_outer_idx == nxt and menu.outer_sectors[nxt].item.id != "primitives"

    menu.handle_mouse_move(*_at(menu, mid, p_mid))          # back on Primitives, then diagonally out to a sub item
    assert menu.hovered_outer_idx == prim
    target = menu.sub_sectors[-1]
    t_mid = target.start_angle + target.span_angle / 2
    turn = (t_mid - p_mid + 180) % 360 - 180                 # the short way round
    for t in (0.2, 0.4, 0.6, 0.8, 1.0):
        r = mid + ((target.r_inner + target.r_outer) / 2 - mid) * t
        menu.handle_mouse_move(*_at(menu, r, p_mid + turn * t))
        if t < 1.0:
            assert menu.hovered_outer_idx == prim, t      # the corridor holds while heading out
    assert menu.hovered_sub_idx == len(menu.sub_sectors) - 1
