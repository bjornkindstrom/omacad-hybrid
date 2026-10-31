"""A body made from a sketch is called "Body N" and its object row shows a picture of it, drawn in idle time
(problem report 20261031-125610)."""
import itertools

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.ui import body_thumbnails
from omacad.ui.body_thumbnails import render_thumbnail
from omacad.ui.browser import BrowserTree

DATA = "tests/data/hexagon_body_from_sketch.omacad"


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def object_row(browser, oid):
    return next(item for item, _ in browser._walk() if item.data(0, Qt.ItemDataRole.UserRole) == ("object", oid))


def sketch_body(doc, x):
    sk = doc.start_sketch("XY")
    sk.add_rect((x, 0), (x + 10, 10))
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 5)


def test_the_report_document_names_its_object_body_1():
    doc = Exporter.load_project(DATA)
    (obj,) = doc.object_history.objects.values()
    assert obj.name == "Body 1"
    assert doc.object_history.names[obj.object_id] == "Body 1"      # saved with the document


def test_numbers_count_up_survive_undo_and_a_rename_by_the_user_wins():
    doc = Document()
    sketch_body(doc, 0)
    sketch_body(doc, 20)
    first, second = doc.object_history.objects
    assert [o.name for o in doc.object_history.objects.values()] == ["Body 1", "Body 2"]
    doc.undo()                                  # extrude of the second
    assert doc.object_history.objects[second].name != "Body 2"     # just a sketch again
    doc.redo()
    assert doc.object_history.objects[second].name == "Body 2"
    doc.rename_object(first, "Bracket")
    sketch_body(doc, 40)
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
    outline = 100 * np.abs(eye).sum()           # area of a cube's shadow along a unit direction
    expected = outline * (0.9 / extent) ** 2    # share of the picture after fitting it to 90 %
    assert (alpha > 127).mean() == pytest.approx(expected, rel=0.03)
    assert alpha[0, 0] == 0                     # the background stays transparent


def test_row_gets_the_picture_only_in_idle_time_and_redraws_only_after_a_change(monkeypatch):
    doc = Exporter.load_project(DATA)
    browser = BrowserTree(doc)
    (oid,) = doc.object_history.objects
    row = object_row(browser, oid)
    assert row.text(0) == "Body 1"
    assert row.icon(0).isNull()                 # not drawn while the tree is built
    assert browser.thumbnails.timer.isActive()
    drawn = []
    real = body_thumbnails.render_thumbnail
    monkeypatch.setattr(body_thumbnails, "render_thumbnail", lambda solids, *a: drawn.append(1) or real(solids, *a))
    browser.thumbnails.finish()
    assert len(drawn) == 1 and not object_row(browser, oid).icon(0).isNull()
    doc.notify_changed()                        # nothing about the body changed
    browser.thumbnails.finish()
    assert len(drawn) == 1
    assert not object_row(browser, oid).icon(0).isNull()           # the rebuilt row keeps the picture
    extrude = next(f for f in doc.timeline.features if f.feature_type == "extrude")
    doc.edit_feature_dimension(extrude.feature_id, "distance", "40")
    browser.thumbnails.finish()
    assert len(drawn) == 2
    index = browser.tree.indexFromItem(object_row(browser, oid))
    assert browser.tree.sizeHintForIndex(index).height() >= body_thumbnails.SIZE


def test_resting_the_mouse_on_the_row_shows_a_big_picture_drawn_once_until_the_body_changes(monkeypatch):
    from PySide6.QtCore import QEvent, QPoint
    from PySide6.QtGui import QHelpEvent
    from PySide6.QtWidgets import QToolTip
    doc = Exporter.load_project(DATA)
    browser = BrowserTree(doc)
    browser.resize(320, 600)
    browser.show()
    (oid,) = doc.object_history.objects
    assert browser.thumbnails.large_picture(oid) == ""          # nothing until the small picture exists
    browser.thumbnails.finish()
    drawn = []
    real = body_thumbnails.render_thumbnail
    monkeypatch.setattr(body_thumbnails, "render_thumbnail", lambda solids, *a: drawn.append(a) or real(solids, *a))
    rect = browser.tree.visualItemRect(object_row(browser, oid))
    viewport = browser.tree.viewport()
    QApplication.sendEvent(viewport, QHelpEvent(QEvent.Type.ToolTip, rect.center(), viewport.mapToGlobal(rect.center())))
    assert "data:image/png;base64," in QToolTip.text() and "object" in QToolTip.text()
    assert drawn == [(body_thumbnails.LARGE, 1.0)]
    browser.thumbnails.large_picture(oid)
    assert len(drawn) == 1                                      # cached while the body is the same
    extrude = next(f for f in doc.timeline.features if f.feature_type == "extrude")
    doc.edit_feature_dimension(extrude.feature_id, "distance", "40")
    browser.thumbnails.finish()
    browser.thumbnails.large_picture(oid)
    assert drawn[-1] == (body_thumbnails.LARGE, 1.0) and len(drawn) == 3   # small + big drawn again
    QToolTip.hideText()
    browser.close()


def test_big_picture_is_drawn_in_idle_time_after_the_small_ones(monkeypatch):
    doc = Exporter.load_project(DATA)
    browser = BrowserTree(doc)
    (oid,) = doc.object_history.objects
    drawn = []
    real = body_thumbnails.render_thumbnail
    monkeypatch.setattr(body_thumbnails, "render_thumbnail", lambda solids, *a: drawn.append(a) or real(solids, *a))
    browser.thumbnails.work()                   # first idle turn: the small picture
    assert drawn == [()] and browser.thumbnails.timer.isActive()
    browser.thumbnails.work()                   # next turn: the big one
    assert drawn[-1] == (body_thumbnails.LARGE, 1.0)
    browser.thumbnails.large_picture(oid)       # the hover finds it ready
    assert len(drawn) == 2
    assert not browser.thumbnails.pending and not browser.thumbnails.pending_large      # nothing left to do
