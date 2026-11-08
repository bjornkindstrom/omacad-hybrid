"""Rendering script models to illustration images for script explanations and menus."""
from pathlib import Path
from typing import List, Optional

from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.scripting.folder import default_folder, is_own, list_scripts
from omacad.scripting.loader import read_info
from omacad.scripting.runner import run_script
from omacad.ui.media_export import cropped_to_model, model_image


def render_script_image(viewport, script_path, out_path: Optional[Path] = None) -> Optional[Path]:
    """Runs `script_path` with its default values and captures a clean rendered image cropped to the model.
    Saves to `out_path` or `<stem>.png` next to the script."""
    script_path = Path(script_path)
    info = read_info(script_path)
    if info.error:
        return None
    target = Path(out_path) if out_path else script_path.with_suffix(".png")

    old_doc = getattr(viewport, "doc", None)
    cam = None
    if hasattr(viewport, "target") and viewport.target is not None:
        cam = (viewport.target.copy(),
               getattr(viewport, "distance", 200.0),
               getattr(viewport, "azimuth", 35.0),
               getattr(viewport, "elevation", 28.0))

    temp_doc = Document()
    try:
        try:
            run_script(temp_doc, script_path)
        except Exception as e:
            from omacad import applog
            applog.log("scripts", f"render_script_image failed for {script_path.name}: {e}")
            return None
        viewport.set_document(temp_doc)
        viewport.zoom_fit()
        viewport.update()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        if temp_doc.bodies:
            img = model_image(viewport)
            cropped = cropped_to_model(img)
        else:
            cropped = viewport.grabFramebuffer()

        if cropped is not None and not cropped.isNull():
            target.parent.mkdir(parents=True, exist_ok=True)
            if cropped.save(str(target), "PNG"):
                return target
    finally:
        if old_doc is not None:
            viewport.set_document(old_doc)
            if cam is not None and cam[0] is not None:
                viewport.target, viewport.distance, viewport.azimuth, viewport.elevation = cam
            viewport.update()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
    return None


def render_script_images(viewport, folder: Optional[Path] = None, only_own: bool = False,
                         overwrite: bool = False, specific: Optional[Path] = None) -> List[Path]:
    """Renders pictures for scripts in `folder` (default: user scripts folder).
    Returns list of created/updated image paths."""
    if specific:
        out = render_script_image(viewport, specific)
        return [out] if out else []

    folder = Path(folder) if folder else default_folder()
    infos = list_scripts(folder)
    made = []
    for info in infos:
        if info.error:
            continue
        if only_own and not is_own(info.path):
            continue
        png = info.path.with_suffix(".png")
        if png.exists() and not overwrite:
            continue
        res = render_script_image(viewport, info.path, png)
        if res:
            made.append(res)
    return made
