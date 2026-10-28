"""A negative fillet cuts a concave cove centred on the sharp edge (Lennart #79, report 20261020-193759)."""
import math
from pathlib import Path

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DOC = Path(__file__).parent / "data" / "negative_fillet_rim.omacad"


def test_negative_fillet_on_a_rim_cuts_a_cove_inward():
    # r20 x 15 base with a r15 x 10 step on top; Fillet -10 on the step's top rim
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    bb = body.manifold.bounding_box()
    assert bb[3] < 20.0 + 1e-6 and bb[5] < 25.0 + 1e-6       # nothing sticks out above or beside the part
    r, R = 10.0, 15.0
    # Pappus: the quarter disc centred on the rim, its centroid 4r/3pi inside the corner
    cove = 2 * math.pi * (R - 4 * r / (3 * math.pi)) * math.pi * r * r / 4
    full = math.pi * (20.0 ** 2 * 15.0 + R ** 2 * 10.0)
    assert abs(body.manifold.volume() - (full - cove)) / cove < 0.01


def test_negative_fillet_on_a_box_edge_cuts_a_cove():
    doc = Document("cove")
    doc.add_box(20.0, 20.0, 20.0)
    doc.add_fillet([((20.0, 0.0, 20.0), (20.0, 20.0, 20.0))], -5.0)
    body = next(iter(doc.bodies.values()))
    assert doc.timeline.features[-1].skipped == 0
    assert abs(body.manifold.volume() - (8000.0 - math.pi * 25.0 / 4 * 20.0)) < 0.5
