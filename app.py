#!/usr/bin/env python3
"""
Omacad - Native CAD for Omarchy
Entrypoint script.
"""

import sys
import os

# Ensure current directory is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QSurfaceFormat, QIcon
from PySide6.QtCore import Qt

from omacad.ui.main_window import MainWindow


def selftest(out_file=None) -> int:
    """`Omacad.exe --selftest`: import everything the frozen app needs and check the bundled files, without a window.
    The release build runs this on Windows so a broken package is caught before anyone downloads it."""
    import importlib
    import pathlib
    def report(text: str) -> None:
        if out_file:      # the windowed Windows exe has no console, so the result goes to a file
            pathlib.Path(out_file).write_text(text, encoding="utf-8")
        else:
            print(text)

    try:
        _selftest_checks(importlib, pathlib)
    except Exception:
        import traceback
        report("selftest FAILED\n" + traceback.format_exc())
        return 1
    report("selftest ok")
    return 0


def _selftest_checks(importlib, pathlib) -> None:
    for mod in ("numpy", "manifold3d", "trimesh", "shapely", "python_solvespace", "PySide6.QtWidgets", "OpenGL.GL",
                "urllib.request", "ssl", "http.client", "email.message", "tomllib",
                "omacad.model.document", "omacad.io.exporter", "omacad.ui.theme", "omacad.rfc"):
        importlib.import_module(mod)
    from omacad.ui import theme
    assert len(theme.available_themes()) >= 10, "bundled themes are missing"
    assert (pathlib.Path(theme.THEMES_DIR).parent / "icon.svg").exists(), "assets are missing"


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
    # Set default OpenGL surface format with 4x MSAA anti-aliasing
    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    from omacad import applog
    applog.install()   # what the app prints and any error end up in problem reports

    # Initialize Qt Application
    app = QApplication(sys.argv)
    from omacad.ui.theme import BigIconStyle
    app.setStyle(BigIconStyle("Fusion"))  # larger menu/tree/tool icons
    app.setApplicationName("Omacad")
    app.setOrganizationName("Omarchy")
    app.setDesktopFileName("omacad")

    from omacad.ui import theme as _theme
    _theme.apply_saved_choice()   # a theme picked by hand in Settings, before any widget is styled

    # Create & Show Main Window
    window = MainWindow()
    
    window.show()
    from omacad import session
    if session.RESUME_FLAG in sys.argv:
        window.restore_session()
    window.start_restart_watch()
    import threading
    from omacad import rfc
    from PySide6.QtCore import QTimer
    QTimer.singleShot(8000, lambda: threading.Thread(target=rfc.send_pending, daemon=True).start())   # requests saved while offline

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
