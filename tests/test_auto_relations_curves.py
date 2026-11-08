"""SolidWorks-style automatic relations: a line drawn onto a circle or arc stays on it; Ctrl turns them off."""
import math
from types import SimpleNamespace

import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchArc
from omacad.ui.viewport.sketch_tools_mixin import SketchToolsMixin


def _auto(doc, sk, line):
    SketchToolsMixin._auto_constrain_line(SimpleNamespace(doc=doc), sk, line)
    return [(c.ctype, c.pts) for c in sk.constraints]


def test_line_drawn_from_a_circle_edge_stays_on_it():
    doc = Document()
    sk = doc.start_sketch()
    circle = sk.add_circle((0.0, 0.0), 10.0)
    p = (10.0 * math.cos(0.3) * 0.995, 10.0 * math.sin(0.3) * 0.995)   # on the drawn polygon, not the true circle
    line = sk.add_line(p, (30.0, 25.0))
    assert _auto(doc, sk, line) == [("POINT_ON_CIRCLE", ["p1"])]
    line = sk.get_entity(line.entity_id)
    assert math.dist(line.p1, sk.get_entity(circle.entity_id).center) == pytest.approx(10.0, abs=1e-6)


def test_line_from_the_centre_joins_it():
    doc = Document()
    sk = doc.start_sketch()
    sk.add_circle((5.0, 5.0), 10.0)
    line = sk.add_line((5.0, 5.0), (30.0, 25.0))
    assert _auto(doc, sk, line) == [("COINCIDENT", ["p1", "center"])]


def test_line_from_an_arc_end_joins_it():
    doc = Document()
    sk = doc.start_sketch()
    arc = SketchArc(sk._new_entity_id("arc"), (10.0, 0.0), (0.0, 10.0), (-10.0, 0.0))
    sk.entities.append(arc)
    line = sk.add_line((25.0, -30.0), (10.0, 0.0))
    assert _auto(doc, sk, line) == [("ARC_END", ["p2", "p_start"])]


def test_ctrl_held_blocks_snaps_and_relations(monkeypatch):
    from omacad.ui.viewport import pointer_mixin
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.ControlModifier))
    assert pointer_mixin._ctrl_held()
    monkeypatch.setattr(QApplication, "keyboardModifiers", staticmethod(lambda: Qt.KeyboardModifier.NoModifier))
    assert not pointer_mixin._ctrl_held()
