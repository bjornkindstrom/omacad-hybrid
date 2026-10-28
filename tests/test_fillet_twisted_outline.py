"""Rapport 20261025-111509: after an Extrude with Twist the whole top outline can be filleted or chamfered.
The walls lean against the top face, so the outline was never offered as one loop (loops needed square walls)."""
import math
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DATA = Path(__file__).parent / "data" / "fillet_twisted_extrude_top.omacad"


def _report_doc():
    return Exporter.load_project(str(DATA))


def _hexagon_doc():
    doc = Document()
    sk = doc.start_sketch("XY")
    pts = [(10 * math.cos(math.radians(60 * k)), 10 * math.sin(math.radians(60 * k))) for k in range(6)]
    for k in range(6):
        sk.add_line(pts[k], pts[(k + 1) % 6])
    sk.solve_profiles()
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 20.0, "new_body", twist=40.0)
    return doc


def _top_loop(doc):
    body = next(iter(doc.bodies.values()))
    loops = [e for e in body.edges if e.kind == "loop" and e.n[2] > 0.99]
    assert len(loops) == 1
    return loops[0]


def _section_depth(manifold, p, t, n, d):
    """How far material reaches along the corner's bisector, in the plane through p across the edge
    (t = edge direction, n = top normal, d = down the wall): 0 for a sharp corner."""
    a = np.cross(n, t)                                    # into the face
    basis = np.column_stack([a, n, t])                    # section coordinates (a, h), t becomes z
    m = manifold.translate(tuple(-p)).transform(np.column_stack([basis.T, np.zeros(3)]))
    sec = Polygon(max(m.slice(0.0).to_polygons(), key=lambda q: Polygon(q).area))
    d2 = np.array([d @ a, d @ n])
    b = np.array([1.0, 0.0]) + d2 / np.linalg.norm(d2)
    b /= np.linalg.norm(b)
    hit = sec.exterior.intersection(LineString([(0.0, 0.0), tuple(5.0 * b)]))
    pts = [hit] if hit.geom_type == "Point" else list(getattr(hit, "geoms", []))
    return min(math.hypot(q.x, q.y) for q in pts), d2 / np.linalg.norm(d2)


@pytest.mark.parametrize("make", [_report_doc, _hexagon_doc])
@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_whole_top_outline_of_a_twisted_extrude_rounds_like_the_corner_it_meets(make, kind):
    doc = make()
    loop = _top_loop(doc)
    assert loop.walls is not None and float(np.abs(loop.walls @ loop.n).max()) > 0.1   # the walls lean
    # a point in the middle of the longest straight run of the outline, where the section is well defined
    P = loop.pts
    seg = np.linalg.norm(np.roll(P, -1, axis=0) - P, axis=1)
    i = int(np.argmax(seg))
    p, t = (P[i] + P[(i + 1) % len(P)]) / 2.0, (P[(i + 1) % len(P)] - P[i]) / seg[i]
    d = np.cross(loop.walls[i], t)
    d = -d if d @ loop.n > 0 else d                       # down the wall
    d /= np.linalg.norm(d)
    r = 1.5
    v0 = next(iter(doc.bodies.values())).manifold.volume()
    doc.add_fillet([loop.ref()], r, kind=kind)
    body = next(iter(doc.bodies.values()))
    assert body.manifold.genus() == 0 and body.manifold.volume() < v0 - 0.5 * r * r
    depth, d2 = _section_depth(body.manifold, p, t, loop.n, d)
    half = 0.5 * math.acos(float(np.clip(d2[0], -1.0, 1.0)))    # half the angle between top and wall
    if kind == "fillet":   # the ball of radius r touching both: its surface lies r/sin(half) - r from the corner
        want = r / math.sin(half) - r
    else:                  # the bevel through the points r along the top and r down the wall
        want = r * math.cos(half)
    assert abs(depth - want) < 0.03 * r
