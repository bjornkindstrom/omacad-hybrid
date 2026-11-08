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
from PySide6.QtCore import Qt, QTimer

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
    from omacad.scripting import folder as script_folder
    assert script_folder.GUIDE.exists(), "the scripting guide (New Script with AI) is missing"
    assert list(script_folder.EXAMPLES.glob("*.py")), "the example scripts are missing"
    from omacad.hybrid_paths import STATE_DIR
    unpacked = getattr(sys, "_MEIPASS", None)
    assert not unpacked or pathlib.Path(unpacked) not in STATE_DIR.parents, "settings would be lost when the app closes"


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
    if "--check-script" in sys.argv:      # test-run a user script without a window (Scripts; the AI uses it too)
        from omacad.scripting.runner import check_script
        i = sys.argv.index("--check-script")
        out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv[:-1] else None
        sys.exit(check_script(sys.argv[i + 1], out) if len(sys.argv) > i + 1 else 2)
    if "--create-script-images" in sys.argv:
        from tools.create_script_images import main as create_images_main
        sys.exit(create_images_main([arg for arg in sys.argv[1:] if arg != "--create-script-images"]))
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
    app.setApplicationName("Omacad Hybrid")
    app.setOrganizationName("Omacad Hybrid")
    app.setDesktopFileName("omacad-hybrid")

    from omacad.ui import theme as _theme
    _theme.apply_saved_choice()   # a theme picked by hand in Settings, before any widget is styled

    # Create & Show Main Window
    window = MainWindow()
    
    window.show()
    from omacad import session
    from omacad.ui import busy_dialog
    busy_dialog.install(window)     # here, not in MainWindow: tests call the model on the main thread
    window.start_autosave()
    if session.RESUME_FLAG in sys.argv:
        window.restore_session()
    else:
        QTimer.singleShot(0, window.offer_autosave_resume)   # after a crash: get the unsaved work back
    from PySide6.QtWidgets import QLabel
    from omacad.viewport_accel import backend_name
    window.statusBar().addPermanentWidget(QLabel(f"Viewport picking: {backend_name().upper()}"))
    QTimer.singleShot(0, window.retry_requests)  # resume requests left by an interrupted upload
    request_retry_timer = QTimer(window)
    request_retry_timer.setInterval(5 * 60 * 1000)
    request_retry_timer.timeout.connect(window.retry_requests)
    request_retry_timer.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
