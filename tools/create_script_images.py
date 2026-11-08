#!/usr/bin/env python3
"""Create illustration screenshots for Omacad scripts."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.scripting.folder import default_folder
from omacad.scripting.images import render_script_images
from omacad.ui import theme
from omacad.ui.main_window import MainWindow


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create illustration pictures for Omacad scripts")
    parser.add_argument("--folder", type=Path, default=None, help="Folder containing scripts (default: Omacad user scripts folder)")
    parser.add_argument("--script", type=Path, default=None, help="A specific script to create an image for")
    parser.add_argument("--all", action="store_true", help="Regenerate all images even if they already exist")
    parser.add_argument("--own-only", action="store_true", help="Only process the user's own scripts (skip bundled examples)")
    args = parser.parse_args(argv)

    fmt = QSurfaceFormat()
    fmt.setSamples(4)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle(theme.BigIconStyle("Fusion"))
    theme.apply_saved_choice()

    window = MainWindow()
    window.resize(900, 600)
    window.show()
    app.processEvents()

    target_folder = args.folder or default_folder()
    print(f"Omacad: generating script images in {target_folder}...")
    made = render_script_images(window.viewport, folder=target_folder, only_own=args.own_only,
                                overwrite=args.all, specific=args.script)
    if made:
        for p in made:
            print(f"  ✓ {p.name}")
        print(f"Done: {len(made)} script image(s) created.")
    else:
        print("No script images needed to be created (use --all to regenerate existing images).")

    window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
