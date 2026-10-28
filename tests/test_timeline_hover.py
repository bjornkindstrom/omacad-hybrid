"""Timeline: only the last step shows its name, the others are icon-only and grow when hovered; while the mouse is on a
step the model shows what that step added (green) or removed (red), or lights up its sketch; leaving restores."""
import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui.timeline_bar import FeatureNodeWidget, TimelineBar


@pytest.fixture
def bar():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(20, 20, 10)
    doc.add_cylinder(4.0, 6.0)
    doc.add_cylinder(2.0, 3.0)
    b = TimelineBar(doc)
    b.show()
    return b


def _chips(bar):
    return bar.findChildren(FeatureNodeWidget)


def _enter(chip):
    chip.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))


def _leave(chip):
    chip.leaveEvent(QEvent(QEvent.Type.Leave))


def test_only_the_last_chip_shows_its_name_and_hover_expands_the_others(bar):
    chips = sorted(_chips(bar), key=lambda c: c.index)
    assert [c.lbl_name.isVisible() for c in chips] == [False, False, True]
    narrow = chips[0].sizeHint().width()
    _enter(chips[0])
    assert chips[0].lbl_name.isVisible() and chips[0].sizeHint().width() > narrow
    _leave(chips[0])
    assert not chips[0].lbl_name.isVisible()


def test_hover_shows_what_the_step_added_and_leaving_restores(bar):
    seen = []
    bar.highlight_changed.connect(lambda a, r: seen.append((a is not None, r is not None)))
    chips = sorted(_chips(bar), key=lambda c: c.index)
    _enter(chips[1])
    assert seen == []                               # a quick sweep does not compute anything yet
    QTest.qWait(200)
    assert seen[-1] == (True, False)                # the cylinder added material
    _leave(chips[1])
    assert seen[-1] == (False, False)               # nothing was clicked: cleared
    bar.on_node_clicked(1)                          # click colours step 1 ...
    _enter(chips[2])
    QTest.qWait(200)
    _leave(chips[2])
    assert seen[-1] == (True, False)                # ... and leaving a hovered chip brings that back


def test_a_quick_pass_over_a_chip_does_nothing(bar):
    seen = []
    bar.highlight_changed.connect(lambda a, r: seen.append(1))
    chip = sorted(_chips(bar), key=lambda c: c.index)[0]
    _enter(chip)
    _leave(chip)
    QTest.qWait(200)
    assert seen == []


def test_hovering_a_sketch_step_lights_the_sketch_up():
    QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 5)
    from omacad.model.sketch import SketchPlane
    sk = doc.start_sketch_on_plane(SketchPlane.create_named("XY"))
    sk.add_circle((0.0, 0.0), 3.0)
    doc.finish_sketch()
    b = TimelineBar(doc)
    b.show()
    flashes = []
    b.flash_sketch_requested.connect(flashes.append)
    chip = [c for c in _chips(b) if c.feature.feature_type == "sketch"][0]
    _enter(chip)
    QTest.qWait(200)
    assert flashes[-1] == sk.sketch_id
    _leave(chip)
    assert flashes[-1] is None
