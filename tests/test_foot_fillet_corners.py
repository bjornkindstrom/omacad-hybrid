"""Foot fillets on the straight edges of a polygon wall flow into each other at the corners."""
import math

import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.sketch import SketchPlane


def octagon_on_plate(radius=10.0):
    d = Document()
    d.add_box(60, 60, 5)
    d.auto_include_edges = False                      # the sketch holds the octagon only
    sk = d.start_sketch_on_plane(SketchPlane.from_face(np.array([0., 0, 1]), np.array([0., 0, 5])))
    sk.add_polygon((30, 30), (30 + radius, 30), 8)
    d.finish_sketch()
    d.extrude_profile(list(d.sketches)[-1], 0, 15, "join")
    d.timeline.recompute(d)
    return d


def test_corners_are_filled_not_notched():
    d = octagon_on_plate()
    body = next(iter(d.bodies.values()))
    foot = [e for e in body.edges if getattr(e, "kind", "") == "line" and not e.convex
            and abs(e.p0[2] - 5) < 1e-6 and abs(e.p1[2] - 5) < 1e-6 and np.linalg.norm(e.p0[:2] - 30) < 12]
    assert len(foot) == 8
    r = 2.0
    d.add_fillet([(tuple(e.p0), tuple(e.p1)) for e in foot], r)
    m = next(iter(d.bodies.values())).manifold
    h = 0.5                                              # height above the plate
    reach = r - math.sqrt(r * r - (r - h) ** 2)          # how far the rounding sticks out from the wall at that height
    apothem = 10.0 * math.cos(math.pi / 8)
    for k in range(8):                                   # every wall corner: a point just inside the rounding, which
        a = math.radians(45 * k)                         # rolls round the corner edge (as far out as along the walls)
        corner_r = 10.0
        d_out = 0.95 * reach
        p = (30 + (corner_r + d_out) * math.cos(a), 30 + (corner_r + d_out) * math.sin(a), 5 + h)
        probe = __import__("manifold3d").Manifold.cube((0.02, 0.02, 0.02), True).translate(p)
        assert not (probe ^ m).is_empty(), f"corner {k} is notched"
    # and nothing sticks out beyond the rounding
    far = (30 + 10.0 * math.cos(0) + 1.4 * r, 30.0, 5.2)
    probe = __import__("manifold3d").Manifold.cube((0.02, 0.02, 0.02), True).translate(far)
    assert (probe ^ m).is_empty()
