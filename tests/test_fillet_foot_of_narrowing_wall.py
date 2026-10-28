"""Fillet at the foot of a triangular rib (report 20261023-210908): the band must stop at the rib's sloping sides
instead of filling air beside them."""
import math
from pathlib import Path

import manifold3d as m3d

from omacad.io.exporter import Exporter

DOC = Path(__file__).parent / "data" / "fillet_foot_of_rib.omacad"


def test_fillet_stays_inside_the_sloping_sides_of_the_rib():
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    assert doc.timeline.features[-1].skipped == 0
    # The fillet region: in front of the rib (y < -5) and above the box top (z > 25).
    region = m3d.Manifold.cube((200, 200, 200), True).translate((0, -105, 125))
    left = body.manifold ^ region.trim_by_plane((-1, 0, 0.4), 10.0)  # left of x = 0.4 (z - 25)
    right = body.manifold ^ region.trim_by_plane((1, 0, 10 / 37.5), 25 + 25 * 10 / 37.5)  # right of x = 25 - (z-25)*4/15
    assert left.volume() < 1e-6 and right.volume() < 1e-6
    # 49.5 is limited to 0.99 * the 20 mm floor in front of the rib; the rib is 25 - 2/3 h wide at height h.
    r = 19.8
    exact = 25 * r * r * (1 - math.pi / 4) - 2 / 3 * r ** 3 * (5 / 6 - math.pi / 4)
    fill = (body.manifold ^ region).volume()
    assert abs(fill - exact) / exact < 0.005
