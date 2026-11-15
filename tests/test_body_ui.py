"""Body UI, viewport dimension overlays, browser tree rows and thumbnails tests."""
import itertools
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui import body_thumbnails
from omacad.ui.body_thumbnails import render_thumbnail
from omacad.ui.browser import BrowserTree
from omacad.ui.object_browser import ROLE
from omacad.ui.viewport.body_dims import box_corners, dimension_edges, draw_body_dimensions

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Viewport Body Dimensions
# ==============================================================================

class _Recorder(QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.texts = []

    def drawText(self, *args):
        self.texts.append(args[-1])
        return super().drawText(*args)


def _view(doc):
    def project(pts):
        p = np.asarray(pts, float)
        x = 200 + (p[:, 0] + p[:, 1]) * 2.0
        y = 300 + (p[:, 0] - p[:, 1]) * 1.0 - p[:, 2] * 2.0
        return np.c_[x, y], np.ones(len(p), bool)
    return SimpleNamespace(doc=doc, project_points=project)


def test_edges_are_the_front_floor_edges_and_one_upright():
    lo, hi = (0, 0, 0), (43, 47, 20)
    screen, _ = _view(None).project_points(box_corners(lo, hi))
    edges = dimension_edges(screen, lo, hi)
    assert sorted(round(v, 6) for _a, _b, v in edges) == [20, 43, 47]
    front = edges[0][0]
    assert tuple(box_corners(lo, hi)[front]) == (43, 0, 0)
    upright = edges[2]
    assert box_corners(lo, hi)[upright[1]][2] == 20 and box_corners(lo, hi)[upright[0]][2] == 0


def test_selected_body_draws_its_three_sizes_and_nothing_without_selection():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(43, 47, 20)
    image = QImage(800, 600, QImage.Format.Format_ARGB32)
    painter = _Recorder(image)
    draw_body_dimensions(_view(doc), painter)
    assert painter.texts == []
    doc.selected_body_ids = list(doc.bodies)
    draw_body_dimensions(_view(doc), painter)
    painter.end()
    assert sorted(painter.texts) == ["20.00", "43.00", "47.00"]


# ==============================================================================
# Browser Tree Body Rows & Construction Bodies
# ==============================================================================

DOC_BODY = DATA_DIR / "body_of_body.omacad"
OID = "object_feat_sketch_2"
BID = "body_extrude_4"


def _rows(browser):
    return [item.text(0).replace("🧊 ", "") for item, _ in browser._walk()]


def test_body_row_is_named_after_its_object():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(str(DOC_BODY))
    browser = BrowserTree(doc)
    assert "Body of Body 2" in _rows(browser)
    doc.rename_object(OID, "Bänk")
    browser.refresh_tree()
    assert "Body of Bänk" in _rows(browser)
    doc.rename_item("body", BID, "Lock")
    browser.refresh_tree()
    assert "Lock" in _rows(browser)


def test_construction_body_is_saved_and_never_picked(tmp_path):
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(str(DOC_BODY))
    body = doc.bodies[BID]
    assert body.pickable
    doc.set_body_construction(BID, True)
    assert doc.bodies[BID].construction and not doc.bodies[BID].pickable
    path = str(tmp_path / "c.omacad")
    Exporter.save_project(doc, path)
    again = Exporter.load_project(path)
    assert again.bodies[BID].construction
    doc.undo()
    assert not doc.bodies[BID].construction
    doc.redo()
    assert doc.bodies[BID].construction


def test_click_on_object_row_selects_its_bodies():
    QApplication.instance() or QApplication([])
    doc = Exporter.load_project(str(DOC_BODY))
    browser = BrowserTree(doc)
    item = next(i for i, _ in browser._walk() if i.data(0, ROLE) == ("object", OID))
    browser.on_item_clicked(item, 0)
    assert doc.bodies[BID].selected
    assert doc.selected_body_ids == [BID]


# ==============================================================================
# Body Thumbnails in Object Tree (Report 20261031-125610)
# ==============================================================================

DATA_THUMB = DATA_DIR / "hexagon_body_from_sketch.omacad"


def _object_row(browser, oid):
    return next(item for item, _ in browser._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ("object", oid))


def _sketch_body(doc, x):
    sk = doc.start_sketch("XY")
    sk.add_rect((x, 0), (x + 10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5)


def test_the_report_document_names_its_object_body_1():
    doc = Exporter.load_project(str(DATA_THUMB))
    (obj,) = doc.object_history.objects.values()
    assert obj.name == "Body 1"
    assert doc.object_history.names[obj.object_id] == "Body 1"


def test_numbers_count_up_survive_undo_and_a_rename_by_the_user_wins():
    doc = Document()
    _sketch_body(doc, 0)
    _sketch_body(doc, 20)
    first, second = doc.object_history.objects
    assert [o.name for o in doc.object_history.objects.values()] == ["Body 1", "Body 2"]
    doc.undo()
    assert doc.object_history.objects[second].name != "Body 2"
    doc.redo()
    assert doc.object_history.objects[second].name == "Body 2"
    doc.rename_object(first, "Bracket")
    _sketch_body(doc, 40)
    names = [o.name for o in doc.object_history.objects.values()]
    assert names == ["Bracket", "Body 2", "Body 3"]
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert [o.name for o in restored.object_history.objects.values()] == names


def test_a_primitive_keeps_its_own_name():
    doc = Document()
    doc.add_box(10, 10, 10)
    assert [o.name for o in doc.object_history.objects.values()] == ["Box 1"]


def test_cube_picture_covers_exactly_its_projected_outline():
    doc = Document()
    body = doc.add_box(10, 10, 10)
    image = render_thumbnail([(body.manifold, (0.7, 0.75, 0.8))], size=64, scale=2.0)
    px = image.width()
    alpha = np.array([[image.pixelColor(x, y).alpha() for x in range(px)] for y in range(px)])
    eye, right, up = body_thumbnails._EYE, body_thumbnails._RIGHT, body_thumbnails._UP
    corners = np.array(list(itertools.product((0, 10), repeat=3)), dtype=float)
    extent = max(np.ptp(corners @ right), np.ptp(corners @ up))
    outline = 100 * np.abs(eye).sum()
    expected = outline * (0.9 / extent) ** 2
    assert (alpha > 127).mean() == pytest.approx(expected, rel=0.03)
    assert alpha[0, 0] == 0


def test_row_gets_the_picture_only_in_idle_time_and_redraws_only_after_a_change(monkeypatch):
    doc = Exporter.load_project(str(DATA_THUMB))
    browser = BrowserTree(doc)
    (oid,) = doc.object_history.objects
    row = _object_row(browser, oid)
    assert row.text(0) == "Body 1"
    assert row.icon(0).isNull()
    assert browser.thumbnails.timer.isActive()
    drawn = []
    real = body_thumbnails.render_thumbnail
    monkeypatch.setattr(body_thumbnails, "render_thumbnail", lambda solids, *a: drawn.append(1) or real(solids, *a))
    browser.thumbnails.finish()
    assert len(drawn) == 1 and not _object_row(browser, oid).icon(0).isNull()
    doc.notify_changed()
    browser.thumbnails.finish()
    assert len(drawn) == 1
    assert not _object_row(browser, oid).icon(0).isNull()
    extrude = next(f for f in doc.timeline.features if f.feature_type == "extrude")
    doc.edit_feature_dimension(extrude.feature_id, "distance", "40")
    browser.thumbnails.finish()
    assert len(drawn) == 2
