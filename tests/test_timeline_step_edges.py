"""Timeline: clicking a Fillet/Chamfer step outlines exactly the edges that step rounds (request #67: with several
chamfers you could not tell which one you were about to edit); other steps and a second click clear it."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from omacad.model.document import Document
from omacad.ui.timeline_bar import TimelineBar


@pytest.fixture
def doc():
    QApplication.instance() or QApplication([])
    d = Document()
    d.add_box(20, 20, 10)
    body = next(iter(d.bodies.values()))
    tops = [e for e in body.edges if e.kind == "line" and abs(e.p0[2] - e.p1[2]) < 1e-6 and e.p0[2] > 5]
    d.add_fillet([tops[0].ref()], 1.0, "chamfer")
    d.add_fillet([tops[1].ref()], 1.0, "chamfer")
    d.tops = tops[:2]
    return d


def test_click_on_a_chamfer_outlines_its_own_edge(doc):
    bar = TimelineBar(doc)
    seen = []
    bar.step_edges_changed.connect(seen.append)
    for step, want in ((2, doc.tops[0]), (3, doc.tops[1])):
        bar.on_node_clicked(step)
        assert len(seen[-1]) == 1
        got = seen[-1][0]                       # the earlier chamfer may have shortened it: same line, not same ends
        d = (want.p1 - want.p0) / np.linalg.norm(want.p1 - want.p0)
        for p in (got.p0, got.p1):
            off = (p - want.p0) - ((p - want.p0) @ d) * d
            assert np.linalg.norm(off) < 1e-6
    bar.on_node_clicked(3)
    assert seen[-1] == []                       # second click on the same step clears
    bar.on_node_clicked(1)
    assert seen[-1] == []                       # the box step rounds nothing
