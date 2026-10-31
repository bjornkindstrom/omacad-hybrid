"""Pictures and videos of the model as it is shown: Export > Screenshot, Copy Image, Rotating Video.

Every capture draws only the bodies and a section's cut face (`Viewport3D.capture_model_only`: no grid, axes,
sketches, handles, ViewCube or text) with the camera and colours of the view, without the selection colour. A
picture is cropped to the model (`cropped_to_model`); the video keeps the whole view, as the model swings round the
camera's centre. The video turns the camera
once around the vertical axis (Near / Medium / Far: centred on the model at that distance; As shown: from where it
stands) and puts it back; frames go straight into ffmpeg."""
import math
import shutil
import subprocess
from contextlib import contextmanager, suppress
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage

MARGIN = 0.06                 # background kept around the model in a screenshot / copied picture
TURN_SECONDS = 6.0
# How close the video camera is: share of the view's shorter side the model's bounding sphere fills; None = as shown
DISTANCES = {"Medium": 0.7, "Near": 0.95, "Far": 0.45, "As shown": None}
FPS = {".mp4": 30, ".webm": 30, ".gif": 15}        # a GIF at 30 fps is large and most viewers slow it down anyway
VIDEO_FILTERS = {"MP4 video (*.mp4)": ".mp4", "WebM video (*.webm)": ".webm", "Animated GIF (*.gif)": ".gif"}
IMAGE_FILTERS = {"PNG image (*.png)": ".png", "JPEG image (*.jpg)": ".jpg"}


@contextmanager
def model_only(viewport):
    """While capturing: the bodies alone, none of them coloured as selected; everything is put back afterwards."""
    bodies = list(viewport.doc.bodies.values())
    selected = [b.selected for b in bodies]
    viewport.capture_model_only = True
    for body in bodies:
        body.selected = False
    try:
        yield
    finally:
        viewport.capture_model_only = False
        for body, was in zip(bodies, selected):
            body.selected = was
        viewport.update()


def model_image(viewport) -> QImage:
    with model_only(viewport):
        return viewport.grabFramebuffer()


def cropped_to_model(image: QImage, margin: float = MARGIN) -> QImage:
    """The part of a capture that holds the model, plus `margin` (of its larger side) of background around it.
    The background is the plain colour in the corners (a capture has nothing else but the bodies)."""
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    rows = np.frombuffer(rgba.constBits(), np.uint8).reshape(rgba.height(), rgba.bytesPerLine())
    pixels = rows[:, :rgba.width() * 4].reshape(rgba.height(), rgba.width(), 4)
    ys, xs = np.nonzero(np.any(pixels != pixels[0, 0], axis=2))
    if not len(xs):
        return image
    pad = int(round(margin * max(xs.max() - xs.min(), ys.max() - ys.min())))
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(image.width() - 1, xs.max() + pad), min(image.height() - 1, ys.max() + pad)
    return image.copy(int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1))


def frame_for_turn(viewport, fill: float) -> None:
    """Aim at the middle of the visible bodies and zoom so their bounding sphere fills `fill` of the view's shorter
    side: the model then turns in place and stays whole in the picture all the way round (same zoom calibration
    as `frame_face`)."""
    boxes = [b.manifold.bounding_box() for b in viewport.doc.bodies.values() if b.visible and not b.manifold.is_empty()]
    if not boxes:
        return
    lo = np.min([box[:3] for box in boxes], axis=0)
    hi = np.max([box[3:] for box in boxes], axis=0)
    radius = max(float(np.linalg.norm(hi - lo)) / 2.0, 1e-3)
    viewport.target = ((lo + hi) / 2.0).astype(np.float32)
    aspect = min(1.0, viewport.width() / max(1, viewport.height()))
    viewport.distance = 2.0 * radius / (fill * aspect * 2.0 * math.tan(math.radians(viewport.fovy) / 2.0))


def turntable_frames(viewport, count: int, fill=None):
    """`count` images of one full turn around the vertical axis from the current view; with `fill` (DISTANCES)
    framed round the model first. The camera is put back afterwards."""
    start = viewport.azimuth, np.array(viewport.target, copy=True), viewport.distance
    with model_only(viewport):
        try:
            if fill:
                frame_for_turn(viewport, fill)
            for i in range(count):
                viewport.azimuth = (start[0] + 360.0 * i / count) % 360.0
                yield viewport.grabFramebuffer()
        finally:
            viewport.azimuth, viewport.target, viewport.distance = start


def ffmpeg_command(path: str, width: int, height: int, fps: int) -> list:
    """Raw RGBA frames on stdin -> `path`; the format follows the file extension."""
    source = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
              "-s", f"{width}x{height}", "-r", str(fps), "-i", "-"]
    even = "pad=ceil(iw/2)*2:ceil(ih/2)*2"          # yuv420p needs even sides
    suffix = Path(path).suffix.lower()
    if suffix == ".gif":
        return source + ["-vf", "split[a][b];[a]palettegen[p];[b][p]paletteuse", "-loop", "0", path]
    if suffix == ".webm":
        return source + ["-vf", even, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-pix_fmt", "yuv420p", path]
    return source + ["-vf", even, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                     path]


def write_turntable(viewport, path: str, progress=None, fill=None) -> bool:
    """Record one turn to `path` (.mp4, .webm or .gif), framed by `fill` (see DISTANCES; None = the view as it is).
    `progress(done, total)` may return False to cancel; the
    unfinished file is then removed and False returned. RuntimeError when ffmpeg is missing or fails."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg was not found. Install it (for example: sudo pacman -S ffmpeg) to export videos.")
    fps = FPS.get(Path(path).suffix.lower(), 30)
    count = int(round(TURN_SECONDS * fps))
    frames = turntable_frames(viewport, count, fill)
    proc, cancelled = None, False
    try:
        for done, image in enumerate(frames, 1):
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            if proc is None:
                proc = subprocess.Popen(ffmpeg_command(path, image.width(), image.height(), fps),
                                        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.stdin.write(bytes(image.constBits())[:image.sizeInBytes()])
            if progress is not None and progress(done, count) is False:
                cancelled = True
                break
    except BrokenPipeError:
        pass                                    # ffmpeg stopped; its own message is reported below
    finally:
        frames.close()                          # puts the camera back
    if proc is None:
        return False
    if cancelled:
        proc.kill()
        with suppress(BrokenPipeError):
            proc.stdin.close()
        proc.wait()
        proc.stderr.close()
        Path(path).unlink(missing_ok=True)
        return False
    with suppress(BrokenPipeError):
        proc.stdin.close()
    error = proc.stderr.read().decode(errors="replace").strip()
    proc.stderr.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg could not write the video: {error or 'exit code ' + str(proc.returncode)}")
    return True


def _save_path(window, title: str, filters: dict, default_name: str):
    """File name from a save dialog, with the chosen type's extension added when it was left out."""
    from PySide6.QtWidgets import QFileDialog
    path, chosen = QFileDialog.getSaveFileName(window, title, default_name, ";;".join(filters))
    if not path:
        return None
    if Path(path).suffix.lower() not in filters.values():
        path += filters.get(chosen, next(iter(filters.values())))
    return path


def _ask_distance(window):
    """Near / Medium / Far / As shown for the video, the last choice first; None when cancelled."""
    from PySide6.QtWidgets import QInputDialog
    from omacad.ui.settings import get_settings
    settings = get_settings()
    names = list(DISTANCES)
    last = settings.get("turntable_distance", names[0])
    choice, ok = QInputDialog.getItem(window, "Rotating Video", "Camera distance:", names,
                                      names.index(last) if last in names else 0, False)
    if not ok:
        return None
    settings.set("turntable_distance", choice)
    return choice


def _base_name(window) -> str:
    name = (window.doc.name or "").removeprefix("Omacad - ").strip()
    return Path(getattr(window, "current_path", None) or name or "Untitled").stem


def run(window, kind: str):
    """Export > Screenshot ("screenshot"), Copy Image ("copy") or Rotating Video ("video")."""
    from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
    from PySide6.QtCore import Qt
    viewport = window.viewport
    if not any(b.visible for b in window.doc.bodies.values()):
        window.status_label.setText("Export: there is no visible body to show.")
        return
    if kind == "copy":
        QApplication.clipboard().setImage(cropped_to_model(model_image(viewport)))
        window.status_label.setText("Picture of the model copied: paste it into another app (Ctrl+V).")
        return
    if kind == "screenshot":
        path = _save_path(window, "Save Screenshot", IMAGE_FILTERS, _base_name(window) + ".png")
        if path:
            if cropped_to_model(model_image(viewport)).save(path):
                window.status_label.setText(f"Screenshot saved to {path}")
            else:
                QMessageBox.warning(window, "Screenshot", f"Could not save the picture to:\n{path}")
        return
    distance = _ask_distance(window)
    if distance is None:
        return
    path = _save_path(window, "Save Rotating Video", VIDEO_FILTERS, _base_name(window) + ".mp4")
    if not path:
        return
    dialog = QProgressDialog("Recording the model turning…", "Cancel", 0, 100, window)
    dialog.setWindowTitle("Rotating Video")
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)

    def progress(done, total):
        dialog.setMaximum(total)
        dialog.setValue(done)
        QApplication.processEvents()
        return not dialog.wasCanceled()

    try:
        finished = write_turntable(viewport, path, progress, DISTANCES[distance])
    except RuntimeError as e:
        dialog.close()
        QMessageBox.warning(window, "Rotating Video", str(e))
        return
    dialog.close()
    window.status_label.setText(f"Rotating video saved to {path}" if finished else "Rotating video cancelled.")
