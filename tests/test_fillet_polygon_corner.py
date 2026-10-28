"""Fillet/chamfer on a polygon prism's corner (report 20261024-084617): the tool's cross-section reached out of the
body with points square to face 1, so at any corner other than 90 degrees (a hexagon's 120) it cut a notch into
face 2. The removed area must be exactly the corner region at every angle."""
import math
from pathlib import Path

import manifold3d as m3d
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.fillet import FilletFeature

DOC = Path(__file__).parent / "data" / "fillet_hexagon_corner.omacad"
H = 30.0


def _corner_edge(body):
    edges = [e for e in body.edges if getattr(e, "kind", "") == "line" and e.convex and abs(e.p1[2] - e.p0[2]) > H - 1]
    return max(edges, key=lambda e: (round(float(e.p0[0]), 3), round(float(e.p0[1]), 3)))


@pytest.mark.parametrize("sides", [3, 4, 6, 8])
@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_corner_of_any_angle_loses_exactly_the_corner_region(sides, kind):
    doc = Document()
    body = doc.add_prism(40.0, H, sides=sides)
    before = body.manifold.volume()
    edge = _corner_edge(body)
    doc.add_fillet([(tuple(edge.p0), tuple(edge.p1))], 2.0, kind)
    after = next(iter(doc.bodies.values())).manifold.volume()
    theta = math.pi - 2 * math.pi / sides                     # interior angle of the polygon
    if kind == "fillet":
        area = 4.0 * (1 / math.tan(theta / 2) - (math.pi - theta) / 2)
    else:
        area = 0.5 * 4.0 * math.sin(theta)
    assert abs((before - after) - area * H) / (area * H) < 0.01


def test_hexagon_corner_from_the_report_has_no_notch():
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    edge = next(e for e in body.edges if getattr(e, "kind", "") == "line" and e.convex
                and e.p0[0] > 80 and e.p0[1] < 0 and abs(e.p1[2] - e.p0[2]) > 30)
    region = m3d.Manifold.cube((20, 20, 60)).translate((70, -57, -10))
    before = body.manifold ^ region
    f = FilletFeature("f", "F", [(tuple(edge.p0), tuple(edge.p1))], 4.0)
    f.execute(doc)
    after = next(iter(doc.bodies.values())).manifold ^ region
    exact = 16.0 * (1 / math.sqrt(3) - math.pi / 6)            # 120 degree corner, r = 4
    for z in (1.0, 20.0, 39.9):
        lost = before.slice(z).area() - after.slice(z).area()
        assert abs(lost - exact) / exact < 0.01
