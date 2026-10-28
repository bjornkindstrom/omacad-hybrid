"""Fill pattern: a margin wider than the original's own distance to the edge is held to that distance,
so the original's row still fits (F9 report: 10 mm margin on a 22 mm tall box wall gave two slivers)."""
from pathlib import Path

import math
import pytest

from omacad.io.exporter import Exporter

DATA = Path(__file__).parent / "data"
HEX_AREA = 3 * math.sqrt(3) / 2 * 3.0 ** 2   # regular hexagon, circumradius 3 mm
WALL = 2.0


def _fill(margin):
    doc = Exporter.load_project(str(DATA / "fill_pattern_thin_wall.omacad"))
    feat = doc.add_pattern(["feat_sketch_2", "extrude_7"], "fill", spacing1=5.0, spacing2=margin, count1=25.0, mirror_mode="grid")
    body = next(iter(doc.bodies.values()))
    rem, _ = feat.compute(doc, body.body_id)
    return feat, rem


def test_margin_wider_than_the_original_keeps_its_row():
    feat, rem = _fill(10.0)
    assert feat.margin_used == pytest.approx(8.0, abs=1e-2)   # hexagon spans z 8..14 on the 0..22 wall
    assert feat.copies == 4
    whole = [p for p in rem.decompose() if p.volume() == pytest.approx(HEX_AREA * WALL, rel=1e-3)]
    assert len(whole) == 2                                     # the outer two are clipped by the side margins
    for p in rem.decompose():
        bb = p.bounding_box()
        assert bb[2] == pytest.approx(8.0, abs=1e-3) and bb[5] == pytest.approx(14.0, abs=1e-3)


def test_margin_inside_the_original_clearance_is_kept():
    feat, rem = _fill(5.0)
    assert feat.margin_used == pytest.approx(5.0)
    assert rem.volume() == pytest.approx(4 * HEX_AREA * WALL, rel=1e-3)
