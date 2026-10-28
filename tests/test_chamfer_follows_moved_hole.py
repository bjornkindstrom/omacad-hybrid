"""Björn #105: moving a hole (its sketch dimension) takes its Chamfer along. The edge cache was keyed by counts,
volume and outer box, which stay the same when a hole moves inside a plate, so the Chamfer got the old hole's edges
and cut a cone where the hole used to be."""
import manifold3d as m3d
import pytest

from omacad.io.exporter import Exporter

DOC = "tests/data/chamfer_follows_moved_hole.omacad"


def _solid_at(body, x, y, z):
    probe = m3d.Manifold.cube([0.05, 0.05, 0.05]).translate([x, y, z])
    return (body.manifold ^ probe).volume() > 1e-6


@pytest.mark.parametrize("dist, x", [(45.0, -10.0), (15.0, -40.0)])
def test_chamfer_moves_with_the_hole(dist, x):
    doc = Exporter.load_project(DOC)
    volume = doc.bodies["body_extrude_2"].manifold.volume()
    assert doc.update_dimension("sketch_1", "d10", dist)
    body = doc.bodies["body_extrude_2"]
    assert not _solid_at(body, x + 6.0, 35, 9.8)        # the bevel is at the hole's new place
    assert _solid_at(body, x + 6.0, 35, 7.0)            # below the 2 mm bevel the plate is solid
    assert _solid_at(body, -25 + 6.0, 35, 9.8)          # nothing left where the hole was
    assert doc.timeline.features[-1].skipped == 0
    assert body.manifold.volume() == pytest.approx(volume, rel=1e-6)
