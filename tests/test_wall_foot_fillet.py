"""Fillet at the straight foot of a leaning wall (Fusion 360 look): exact volume while it fits on the floor,
and a radius too big for the floor is limited so no material hangs over the box edge."""
import math
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.features.fillet import FilletFeature

DOC = str(Path(__file__).parent / "data" / "wall_foot_fillet.omacad")
WALL_LEN = 26.0                                 # wall runs from y=-1 to y=25
ANGLE = math.pi - math.atan2(62.9908 - 25.0, 1.3183 - (-14.7304))   # air wedge between floor and wall


def _filleted(r):
    doc = Exporter.load_project(DOC)
    doc.timeline.features = doc.timeline.features[:3]
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    v0 = body.manifold.volume()
    foot = next(e for e in body.edges if e.kind == "line" and not e.convex and abs(e.p0[0] + 14.7304) < 1e-2 and abs(e.p1[0] + 14.7304) < 1e-2)
    doc.timeline.features.append(FilletFeature("t", "F", [foot.ref()], r, kind="fillet"))
    doc.timeline.recompute(doc)
    new = next(iter(doc.bodies.values()))
    return new.manifold.volume() - v0, new.manifold.bounding_box()


def _area(r):
    return r * r * (1 / math.tan(ANGLE / 2) - (math.pi - ANGLE) / 2) * WALL_LEN


def test_foot_fillet_that_fits_has_exact_volume():
    dv, _ = _filleted(10.0)
    assert abs(dv - _area(10.0)) / _area(10.0) < 0.01


def test_oversized_foot_fillet_stays_on_the_floor():
    dv, bb = _filleted(30.0)
    r_max = 10.2696 * 0.99 * math.tan(ANGLE / 2)    # floor is 10.27 wide between the foot and the box edge
    assert dv < _area(r_max) * 1.01
    assert bb[0] >= -25.0 - 1e-3                    # nothing sticks out past the box
