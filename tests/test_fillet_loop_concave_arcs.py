"""Björn #78: a 2 mm fillet round a dog-bone outline (two circles joined by two inward arcs) left a row of teeth along
the arcs. A tiny real fold where an arc meets a circle sent the tool down the piece-by-piece path, whose straight
pieces left an uncut wedge at every right turn and touched end to end (zero-thickness flaps)."""
import math

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from omacad.io.exporter import Exporter


def _slice(m, z):
    return [Polygon(p) for p in m.slice(z).to_polygons()]


def test_fillet_round_concave_arcs_is_smooth():
    doc = Exporter.load_project("tests/data/fillet_loop_concave_arcs.omacad")
    ids = [f.feature_id for f in doc.timeline.features]
    bid = next(iter(doc.bodies))
    before = doc.step_states[ids.index("fillet_3")][bid]
    body = doc.bodies[bid].manifold
    assert len(body.decompose()) == 1 and body.genus() == 0
    outline = unary_union(_slice(before, 5.0))
    for z in (9.9, 9.5, 8.5):
        loops = _slice(body, z)
        assert len(loops) == 1, z                          # no teeth or flaps beside the outline
        inset = 2.0 - math.sqrt(4.0 - (z - 8.0) ** 2)      # r 2 fillet from z 8 to the top at 10
        ideal = outline.buffer(-inset, join_style=1)
        assert loops[0].difference(ideal).area < 0.01, z   # nothing left standing outside the rounding
        assert ideal.difference(loops[0]).area < 1.0, z    # and not cut deeper than the facets need
