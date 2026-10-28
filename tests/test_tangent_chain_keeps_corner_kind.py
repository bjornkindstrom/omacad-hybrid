"""Chamfer on the foot of a rib next to a fillet (report 20261023-211415): the concave foot edge runs straight on into
the convex end edge of the fillet band. "Joined edges follow" took both, so the chamfer filled one and cut the other."""
import math
from pathlib import Path

import numpy as np

from omacad.io.exporter import Exporter
from omacad.model.faces import tangent_chain

DOC = Path(__file__).parent / "data" / "chamfer_rib_foot_next_to_fillet.omacad"


def test_chain_stops_where_an_inside_corner_becomes_an_outside_corner():
    doc = Exporter.load_project(str(DOC))
    body = next(iter(doc.bodies.values()))
    foot = next(e for e in body.edges if e.kind == "line" and not e.convex
                and np.allclose(e.p0[[0, 2]], (-8.347, 25), atol=1e-2) and np.allclose(e.p1[[0, 2]], (-8.347, 25), atol=1e-2))
    chain = tangent_chain(foot, body.edges)
    assert len(chain) == 1

    before = body.manifold.volume()
    doc.add_fillet([(tuple(foot.p0), tuple(foot.p1))], 2.0, kind="chamfer")
    added = next(iter(doc.bodies.values())).manifold.volume() - before
    # equal 2 mm chamfer in the 110.8 deg air wedge between the top face and the rib's sloping side, along the whole foot
    wedge = math.atan2(17.5, -(15 - 8.347))
    exact = 0.5 * 2.0 * 2.0 * math.sin(wedge) * float(np.linalg.norm(np.asarray(foot.p1) - np.asarray(foot.p0)))
    assert abs(added - exact) / exact < 0.01
