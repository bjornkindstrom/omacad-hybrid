"""Fill pattern: the edge margin applies to the outer edge of the face; holes and bosses in it only get the gap."""
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter


def test_obstacles_get_the_gap_not_the_edge_margin():
    doc = Exporter.load_project(str(Path(__file__).parent / "data" / "fill_pattern_clearance.omacad"))
    doc.timeline.recompute(doc)
    ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([ext.feature_id], kind="fill", spacing1=1.0, spacing2=3.0, count1=5.0, mirror_mode="triangular")
    feat = doc.timeline.features[-1]
    feat.compute(doc, next(iter(doc.bodies.values())).body_id)
    room = feat._fill_clip[0]
    holes = sorted((Polygon(r) for r in room.interiors), key=lambda p: p.area)
    assert len(holes) == 2
    # bosses of radius 2.5 and 5 mm: the room is cut round them by radius + gap (1 mm), not + margin (3 mm)
    for hole, r in zip(holes, (3.5, 6.0)):
        assert hole.bounds[2] - hole.bounds[0] == pytest.approx(2 * r, abs=0.1)
