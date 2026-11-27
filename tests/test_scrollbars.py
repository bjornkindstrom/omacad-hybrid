"""Every scroll bar in the app uses the one app-wide style: wide, visible, accent on hover."""
import pathlib

from PySide6.QtWidgets import QApplication, QListWidget, QScrollArea, QWidget

from omacad.ui import theme

ROOT = pathlib.Path(__file__).resolve().parents[1] / "omacad"


def test_no_widget_sheet_overrides_the_app_scroll_bars():
    owners = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.py")
              if "QScrollBar" in p.read_text(encoding="utf-8")]
    assert owners == ["ui/theme.py"]


def test_scroll_bars_are_wide_in_every_theme(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(theme, "COLORS_FILE", tmp_path / "colors.toml")
    try:
        for name in ("studio_glass", "studio", "graphite", None):
            theme.set_fixed_theme(name)
            css = theme.scrollbar_stylesheet()
            assert f"width: {theme.SCROLLBAR_PX}px" in css and theme._hex(theme.palette().accent) in css
            assert css in app.styleSheet()
            host = QWidget()
            theme.style(host, theme._BASE_CSS, theme._STUDIO_CSS)    # a themed window, like the main window
            area = QScrollArea(host)
            area.setWidget(QListWidget())
            area.resize(200, 100)
            area.widget().setMinimumSize(400, 400)
            host.resize(220, 120)
            host.show()
            app.processEvents()
            assert area.verticalScrollBar().width() == theme.SCROLLBAR_PX
            assert area.horizontalScrollBar().height() == theme.SCROLLBAR_PX
            host.close()
    finally:
        theme.set_fixed_theme(None)


def test_scroll_bar_track_and_handle_are_round_at_both_ends(tmp_path, monkeypatch):
    """Qt draws square corners when a radius is more than half the side: the handle (10 px) had radius 6."""
    import re
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollBar
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(theme, "COLORS_FILE", tmp_path / "colors.toml")
    try:
        theme.set_fixed_theme("studio")
        css = theme.scrollbar_stylesheet()
        handle = re.search(r"::handle:vertical \{[^}]*border-radius: (\d+)px", css)
        track = re.search(r"QScrollBar:vertical \{[^}]*border-radius: (\d+)px", css)
        assert int(handle.group(1)) * 2 == theme.scrollbar_handle_px()
        assert int(track.group(1)) * 2 == theme.SCROLLBAR_PX
        bar = QScrollBar(Qt.Vertical)
        bar.setRange(0, 100)
        bar.setPageStep(20)
        bar.setValue(0)
        bar.resize(theme.SCROLLBAR_PX, 200)
        bar.show()
        app.processEvents()
        img = bar.grab().toImage()
        m = 1 + theme.SCROLLBAR_HANDLE_MARGIN          # first handle pixel row/column
        corner = img.pixelColor(m, m)
        middle = img.pixelColor(theme.SCROLLBAR_PX // 2, m + 8)
        handle = (theme._hex(theme.palette().muted).lower(), theme._hex(theme.palette().accent).lower())   # accent if hovered
        assert middle.name().lower() in handle
        assert corner.name().lower() not in handle      # the handle's top corner is cut round
        bar.close()
    finally:
        theme.set_fixed_theme(None)
