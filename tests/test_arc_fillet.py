"""Fillet and chamfer on an open arc (a flat face meeting part of a cylinder), not only on full circles."""
import os

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.timeline import FilletFeature

DOC = os.path.join(os.path.dirname(__file__), "data", "block_with_arc_cut.omacad")


def _load():
    d = Exporter.load_project(DOC)
    return d, next(iter(d.bodies.values()))


def _big_arcs(body):
    return [e for e in body.edges if e.kind == "circle" and e.is_arc and e.radius > 20]


def test_open_arcs_are_edges():
    _, body = _load()
    arcs = _big_arcs(body)
    assert len(arcs) == 2
    for a in arcs:
        assert a.convex and a.s1 > 0                      # the flat face lies outside the concave cut
        assert 1.5 < a.sweep < 1.8
        pts = a.polyline(48)
        assert np.allclose(np.linalg.norm(pts[:, 1:] - a.center[1:], axis=1), a.radius, atol=1e-6)


def test_rounded_plate_corners_have_the_right_side():
    _, body = _load()
    corners = [e for e in body.edges if e.kind == "circle" and e.is_arc and e.radius < 10]
    assert corners and all(e.s1 < 0 for e in corners)     # the plate lies inside the corner circle


@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_arc_fillet_removes_material_and_stays_solid(kind):
    doc, body = _load()
    v0 = body.manifold.volume()
    f = FilletFeature("f_arc", "Fillet", [e.ref() for e in _big_arcs(body)], 2.0, kind)
    doc.timeline.add_feature(f)
    doc.timeline.recompute(doc)
    nb = next(iter(doc.bodies.values()))
    assert f.skipped == 0
    removed = v0 - nb.manifold.volume()
    # cross-section area x arc length at the centroid radius
    area = (1 - np.pi / 4) * 4.0 if kind == "fillet" else 2.0
    expected = 2 * area * 1.661 * 63.7
    assert 0.9 * expected < removed < 1.15 * expected
    assert len(nb.manifold.decompose()) == 1 and nb.manifold.genus() == 0


def test_arc_ref_survives_a_save_round_trip():
    doc, body = _load()
    refs = [e.ref() for e in _big_arcs(body)]
    f = FilletFeature("f_arc", "Fillet", refs, 2.0)
    assert f.edges[0][0] == "arc" and len(f.edges[0]) == 6
    from omacad.model.faces import edge_from_ref
    assert all(edge_from_ref(r, body.edges) is not None for r in f.edges)
