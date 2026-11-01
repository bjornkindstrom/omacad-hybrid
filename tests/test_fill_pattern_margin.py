"""Fill pattern respects the requested clearance even beyond the source's clearance."""
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


def test_margin_wider_than_the_original_clips_its_row():
    feat, rem = _fill(10.0)
    assert feat.margin_used == pytest.approx(10.0)
    assert feat.copies == 2
    whole = [p for p in rem.decompose() if p.volume() == pytest.approx(HEX_AREA * WALL, rel=1e-3)]
    assert len(whole) == 0
    for p in rem.decompose():
        bb = p.bounding_box()
        assert bb[2] == pytest.approx(10.0, abs=1e-3) and bb[5] == pytest.approx(12.0, abs=1e-3)


def test_increasing_margin_cannot_add_material():
    _, narrow = _fill(3.0)
    _, wide = _fill(10.0)
    assert wide.volume() < narrow.volume()


def test_margin_inside_the_original_clearance_is_kept():
    feat, rem = _fill(5.0)
    assert feat.margin_used == pytest.approx(5.0)
    assert rem.volume() == pytest.approx(4 * HEX_AREA * WALL, rel=1e-3)
