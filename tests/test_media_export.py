"""Export > Screenshot, Copy Image and Rotating Video: the model alone, as it is shown; the video turns once around."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage, QSurfaceFormat
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui import commands, media_export


def _app():
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)
    return QApplication.instance() or QApplication([])


def _rgb(image):
    img = image.convertToFormat(QImage.Format.Format_RGB888)
    rows = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
    return rows[:, :img.width() * 3].reshape(img.height(), img.width(), 3).copy()


class FakeView:
    """Stands in for the viewport: each grab is a flat image whose colour says the camera angle and records what
    capture state it was taken in."""
    def __init__(self, doc, size=(64, 48)):
        self.doc, self.size, self.azimuth, self.capture_model_only, self.grabs = doc, size, 30.0, False, []
        self.target, self.distance, self.fovy = np.array([1.0, 2.0, 3.0], np.float32), 300.0, 45.0

    def width(self):
        return self.size[0]

    def height(self):
        return self.size[1]

    def grabFramebuffer(self):
        self.grabs.append((self.azimuth, self.capture_model_only, [b.selected for b in self.doc.bodies.values()]))
        image = QImage(*self.size, QImage.Format.Format_RGB32)
        image.fill(QColor(int(self.azimuth / 360 * 255), 80, 160))
        return image

    def update(self):
        pass


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,nb_read_frames,codec_name", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def test_export_button_holds_screenshot_copy_and_video():
    title, items = commands.SOLID_GROUPS[-1]
    assert title == "EXPORT" and items == [commands.EXPORT]
    assert commands.EXPORT[4] == ["screenshot", "copy_image", "turntable"]
    assert [commands.get(c).arg for c in commands.EXPORT[4]] == ["screenshot", "copy", "video"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
@pytest.mark.parametrize("suffix, codec, fps", [(".mp4", "h264", 30), (".webm", "vp9", 30), (".gif", "gif", 15)])
def test_one_full_turn_from_the_current_view_and_the_camera_is_put_back(tmp_path, suffix, codec, fps):
    _app()
    doc = Document()
    body = doc.add_box(10, 10, 10)
    body.selected = True
    view = FakeView(doc, (63, 47))                     # odd sides: the encoder needs even ones
    path = tmp_path / f"turn{suffix}"
    seen = []
    assert media_export.write_turntable(view, str(path), lambda done, total: seen.append((done, total)))
    count = int(media_export.TURN_SECONDS * fps)
    assert seen[-1] == (count, count) and len(view.grabs) == count
    angles = [a for a, _, _ in view.grabs]
    assert angles[0] == 30.0 and np.allclose(np.diff(np.unwrap(np.radians(angles))), np.radians(360 / count))
    assert all(only and selected == [False] for _, only, selected in view.grabs)      # the model alone, unselected
    assert view.azimuth == 30.0 and not view.capture_model_only and body.selected   # all put back
    info = _probe(path)
    assert info["codec_name"] == codec and int(info["nb_read_frames"]) == count
    assert (info["width"], info["height"]) == ((63, 47) if codec == "gif" else (64, 48))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_cancel_removes_the_unfinished_file_and_restores_the_camera(tmp_path):
    _app()
    doc = Document()
    doc.add_box(10, 10, 10)
    view = FakeView(doc)
    path = tmp_path / "turn.mp4"
    assert media_export.write_turntable(view, str(path), lambda done, total: done < 10) is False
    assert not path.exists() and len(view.grabs) == 10 and view.azimuth == 30.0


def test_missing_ffmpeg_says_how_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setattr(media_export.shutil, "which", lambda name: None)
    view = FakeView(Document())
    with pytest.raises(RuntimeError, match="ffmpeg was not found"):
        media_export.write_turntable(view, str(tmp_path / "x.mp4"))
    assert view.grabs == []


def test_the_typed_name_gets_the_chosen_types_extension(monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    _app()
    answer = ("/tmp/model", "Animated GIF (*.gif)")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a: answer))
    assert media_export._save_path(None, "t", media_export.VIDEO_FILTERS, "x.mp4") == "/tmp/model.gif"
    answer = ("/tmp/model.webm", "MP4 video (*.mp4)")
    assert media_export._save_path(None, "t", media_export.VIDEO_FILTERS, "x.mp4") == "/tmp/model.webm"


def test_real_view_capture_is_the_body_on_a_plain_background_and_copy_puts_it_on_the_clipboard():
    from PySide6.QtTest import QTest
    from omacad.ui.main_window import MainWindow
    app = _app()
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    win = MainWindow()
    win.show()
    try:
        body = win.doc.add_box(20, 15, 10)
        body.selected = True
        QTest.qWait(1500)
        view = win.viewport
        assert view.show_grid
        shot = _rgb(media_export.model_image(view))
        body.visible = False
        empty = _rgb(media_export.model_image(view))
        body.visible = True
        assert len(np.unique(empty.reshape(-1, 3), axis=0)) == 1     # no grid, axes, ViewCube or text
        assert np.any(shot != empty, axis=2).sum() > 500                # the body is there
        normal = _rgb(view.grabFramebuffer())
        assert len(np.unique(normal[~np.any(shot != empty, axis=2)], axis=0)) > 1   # the live view still has them
        assert body.selected and not view.capture_model_only
        media_export.run(win, "copy")
        copied = _rgb(QApplication.clipboard().image())
        ys, xs = np.nonzero(np.any(shot != empty, axis=2))
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        pad = round(media_export.MARGIN * (max(h, w) - 1))
        assert copied.shape == (h + 2 * pad, w + 2 * pad, 3)          # the model and a margin, not the whole view
        assert np.array_equal(copied, shot[ys.min() - pad:ys.max() + pad + 1, xs.min() - pad:xs.max() + pad + 1])
    finally:
        win.close()


def test_crop_keeps_the_model_and_a_margin_and_stops_at_the_edges():
    _app()
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor(240, 240, 240))
    for x in range(50, 101):                    # model: 51 x 21 px at (50..100, 30..50)
        for y in range(30, 51):
            image.setPixelColor(x, y, QColor(90, 100, 120))
    out = media_export.cropped_to_model(image, 0.1)
    assert (out.width(), out.height()) == (51 + 10, 21 + 10)
    assert out.pixelColor(5, 5) == QColor(90, 100, 120) and out.pixelColor(4, 4) == QColor(240, 240, 240)
    edge = media_export.cropped_to_model(image, 2.0)            # the margin cannot reach past the picture
    assert (edge.width(), edge.height()) == (200, 100)
    blank = QImage(20, 10, QImage.Format.Format_RGB32)
    blank.fill(QColor(240, 240, 240))
    assert media_export.cropped_to_model(blank).size() == blank.size()


def test_near_medium_far_centre_the_turn_on_the_model_and_the_camera_is_put_back():
    import math
    doc = Document()
    doc.add_box(30, 20, 10, translation=(100, 0, 0))
    view = FakeView(doc, (200, 100))
    seen = []
    for name, fill in media_export.DISTANCES.items():
        frames = media_export.turntable_frames(view, 2, fill)
        next(frames)
        seen.append((name, view.target.copy(), view.distance))
        frames.close()
        assert np.allclose(view.target, [1, 2, 3]) and view.distance == 300.0     # put back
    by = {name: (target, distance) for name, target, distance in seen}
    radius = math.sqrt(30 ** 2 + 20 ** 2 + 10 ** 2) / 2
    for name in ("Near", "Medium", "Far"):
        target, distance = by[name]
        assert np.allclose(target, [115, 10, 5])
        # the sphere's diameter fills `fill` of the shorter side (height 100 of 200 here: aspect 1)
        assert 2 * radius / (2 * distance * math.tan(math.radians(45) / 2)) == pytest.approx(media_export.DISTANCES[name])
    assert by["Near"][1] < by["Medium"][1] < by["Far"][1]
    assert np.allclose(by["As shown"][0], [1, 2, 3]) and by["As shown"][1] == 300.0


def test_real_view_near_turn_keeps_the_whole_model_in_the_picture():
    from PySide6.QtTest import QTest
    from omacad.ui.viewport.viewport import Viewport3D
    app = _app()
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    doc = Document()
    doc.add_box(60, 10, 25, translation=(200, 50, 0))     # long and far from the origin: it would swing out
    view = Viewport3D(doc)
    view.resize(500, 300)
    view.show()
    try:
        QTest.qWait(1500)
        heights = {}
        for name in ("Near", "Medium", "Far"):
            frames = list(media_export.turntable_frames(view, 8, media_export.DISTANCES[name]))
            for image in frames:
                rgb = _rgb(image)
                model = np.any(rgb != rgb[0, 0], axis=2)
                assert model.sum() > 100
                assert not (model[0].any() or model[-1].any() or model[:, 0].any() or model[:, -1].any())
            heights[name] = np.ptp(np.nonzero(np.any(model, axis=1))[0])
        assert heights["Near"] > heights["Medium"] > heights["Far"]
    finally:
        view.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_video_button_asks_distance_then_file_and_remembers_the_distance(tmp_path, monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog, QInputDialog
    from omacad.ui.main_window import MainWindow
    from omacad.ui.settings import get_settings
    app = _app()
    if app.platformName() in ("offscreen", "minimal"):
        pytest.skip("needs the real display (GL)")
    asked = []
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda w, t, l, items, i, e: asked.append(items[i]) or ("Far", True)))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a: (str(tmp_path / "turn"), "Animated GIF (*.gif)")))
    monkeypatch.setattr(media_export, "TURN_SECONDS", 0.4)
    old = get_settings().get("turntable_distance", "Medium")
    win = MainWindow()
    win.show()
    try:
        win.doc.add_box(20, 15, 10)
        QTest.qWait(1500)
        win.ribbon.export_media_clicked.emit("video")
        assert (tmp_path / "turn.gif").exists() and int(_probe(tmp_path / "turn.gif")["nb_read_frames"]) == 6
        assert "Rotating video saved" in win.status_label.text()
        win.ribbon.export_media_clicked.emit("video")
        assert asked == [old, "Far"]                     # the last choice is offered first
    finally:
        get_settings().set("turntable_distance", old)
        win.close()
