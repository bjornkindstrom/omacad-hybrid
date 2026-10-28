"""A circle measured from a rounded rectangle's wall follows the wall when the size changes (#100)."""
from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchLine
from omacad.model.sketch_solver import solve_sketch


def _ent(sk, eid):
    return next(e for e in sk.entities if e.entity_id == eid)


def test_guide_lines_map_to_their_walls():
    doc = Document()
    sk = doc.start_sketch("XY")
    walls = sk.add_rounded_rect((0, 0), (40, 30), 5.0)
    guides = sk.corner_guide_walls()
    assert len(guides) == 8
    wall_ids = {w.entity_id for w in walls}
    for gid, wid in guides.items():
        g, w = _ent(sk, gid), _ent(sk, wid)
        assert isinstance(g, SketchLine) and g.is_construction and wid in wall_ids
        # the guide lies on its wall's line
        (x1, y1), (x2, y2) = w.p1, w.p2
        for p in (g.p1, g.p2):
            assert (p[0] - x1) * (y2 - y1) - (p[1] - y1) * (x2 - x1) == pytest.approx(0.0, abs=1e-6)


def test_circle_measured_from_corner_guide_follows_the_wall():
    # Björn's file: the 5 mm from the top was stored against the top-left corner's guide line (line_15)
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "smart_circle_corner_guide.omacad"))
    sk = next(iter(doc.sketches.values()))
    assert solve_sketch(sk).ok
    top, left, circle = _ent(sk, "line_3"), _ent(sk, "line_4"), _ent(sk, "circle_17")
    d11 = next(d for d in sk.dimensions if d.dim_id == "d11")
    assert d11.refs == ["line_3"]
    assert top.p1[1] - circle.center[1] == pytest.approx(5.0, abs=1e-4)
    assert circle.center[0] - left.p1[0] == pytest.approx(5.0, abs=1e-4)
    for dim, value in (("d7", 80.0), ("d8", 90.0)):      # width, then height
        assert doc.update_dimension(sk.sketch_id, dim, value)
        top, left, bottom, circle = _ent(sk, "line_3"), _ent(sk, "line_4"), _ent(sk, "line_1"), _ent(sk, "circle_17")
        assert top.p1[1] - circle.center[1] == pytest.approx(5.0, abs=1e-4)
        assert circle.center[0] - left.p1[0] == pytest.approx(5.0, abs=1e-4)
    assert top.p1[1] - bottom.p1[1] == pytest.approx(90.0, abs=1e-4)
