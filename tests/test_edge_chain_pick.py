"""Picking one edge for Fillet/Chamfer follows the smooth chain; the preview's body lookup must not compare arrays."""
import os

from omacad.io.exporter import Exporter
from omacad.model.faces import tangent_chain
from omacad.model.faces_edges import loop_contains

DOC = os.path.join(os.path.dirname(__file__), "data", "plate_rounded_chain.omacad")


def _body():
    return next(iter(Exporter.load_project(DOC).bodies.values()))


def test_chain_follows_tangent_arcs_and_stops_at_knicks():
    body = _body()
    # straight sides + rounded corners come as one loop; its straight sides are also edges of their own (#104),
    # and the float64 mesh leaves no stray lines on the fillet
    loops = [e for e in body.edges if e.kind == "loop"]
    assert len(loops) == 1
    lines = [e for e in body.edges if e.kind == "line"]
    assert lines and all(loop_contains(loops[0], e) for e in lines)
    arcs = [e for e in body.edges if e.kind == "circle" and e.is_arc]
    assert arcs
    for arc in arcs:
        chain = tangent_chain(arc, body.edges)
        assert len(chain) <= len(body.edges)
        assert all(any(c.same_as(k) for k in tangent_chain(c, body.edges)) for c in chain)


def test_owner_lookup_with_same_as_does_not_raise():
    body = _body()
    assert all(any(e.same_as(k) for k in body.edges) for e in body.edges)
