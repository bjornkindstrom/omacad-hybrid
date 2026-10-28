"""Report 20261025-125922: chamfering a curved outline drew stripes down the wall.

Topology and the outline tool must retain the solid's double precision. Rounding
outline coordinates through float32 before the boolean leaves thin wall slivers.
"""
from pathlib import Path

import numpy as np
import pytest

from omacad.io.exporter import Exporter

DOC = str(Path(__file__).parent / "data" / "chamfer_fragmented_walls.omacad")


@pytest.mark.parametrize("whole_selection", [False, True])
def test_chamfer_keeps_curved_walls_free_of_false_creases(whole_selection):
    doc = Exporter.load_project(DOC)
    if not whole_selection:
        # The loop alone must also work; the report selected two arcs on it too.
        feature = doc.timeline.features[-1]
        feature.edges = feature.edges[:1]
        doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    assert body.manifold.status().name == "NoError"
    assert body.manifold.volume() == pytest.approx(632680.238, abs=0.03)
    segments = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
    # Only the three horizontal rims are sharp: bottom, wall/bevel, bevel/top.
    assert np.allclose(segments[:, 0, 2], segments[:, 1, 2], atol=1e-4)
    assert np.allclose(np.unique(segments[..., 2]), [0.0, 45.292, 50.0])
    tangents = body.render_mesh.tangent_lines().reshape(-1, 2, 3)
    # Six straight-wall/arc transitions, at most one wall and one bevel seam each.
    assert 6 <= len(tangents) <= 12
    vertical = tangents[np.abs(tangents[:, 1, 2] - tangents[:, 0, 2]) > 40]
    assert len(vertical) == 6
    assert np.allclose(vertical[:, 0, :2], vertical[:, 1, :2], atol=1e-4)


def test_all_three_rims_are_closed_and_each_surface_is_whole():
    """Follow-up 20261025-130556: missing bevel seams and many tiny hover patches.

    That report's document is byte-identical to this fixture. The four sketch
    arcs become four wall surfaces and four bevel surfaces, with three flat
    walls, three flat bevel bands, a top and a bottom.
    """
    from collections import Counter
    import trimesh
    from omacad.model.faces_surfaces import curved_surface_ids

    doc = Exporter.load_project(DOC)
    feature = doc.timeline.features[-1]
    body = next(iter(doc.bodies.values()))
    assert len(body.faces) == 8
    v, f, _ = body.render_mesh.source
    tm = trimesh.Trimesh(v, f, process=False)
    surface_ids = curved_surface_ids(v, f, tm, 20.0)
    curves = set(surface_ids) - {-1}
    assert len(curves) == 8
    assert all(tm.area_faces[surface_ids == sid].sum() > 100 for sid in curves)
    tangents = body.render_mesh.tangent_lines().reshape(-1, 2, 3)
    assert len(tangents) == 12  # all six wall/arc seams continue across the bevel
    assert np.count_nonzero(np.isclose(np.abs(tangents[:, 1, 2] - tangents[:, 0, 2]), feature.size)) == 6

    segments = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
    bottom = segments[np.isclose(segments[:, 0, 2], 0)]
    # The bottom is unchanged; its convex outline's inward mitre offset is the top rim.
    from shapely.ops import polygonize
    outline = next(iter(polygonize([s[:, :2] for s in bottom])))
    expected = outline.buffer(-feature.size, join_style='mitre').length
    for z, perimeter in ((0., feature.edges[0][3]), (50. - feature.size, feature.edges[0][3]), (50., expected)):
        rim = segments[np.isclose(segments[:, 0, 2], z)]
        degrees = Counter(map(tuple, np.round(rim.reshape(-1, 3), 4)))
        assert set(degrees.values()) == {2}  # no gaps or spurs along any of the rims
        assert np.linalg.norm(rim[:, 1] - rim[:, 0], axis=1).sum() == pytest.approx(perimeter, abs=1e-3)


@pytest.mark.parametrize('kind', ['chamfer', 'fillet'])
def test_selecting_arcs_already_in_a_loop_does_not_cut_the_surface_twice(kind):
    doc = Exporter.load_project(DOC)
    feature = doc.timeline.features[-1]
    feature.kind = kind
    # Selection order must not matter: the containing loop comes last here.
    feature.edges.reverse()
    doc.timeline.recompute(doc)
    actual = next(iter(doc.bodies.values())).manifold
    feature.edges = feature.edges[-1:]
    doc.timeline.recompute(doc)
    expected = next(iter(doc.bodies.values())).manifold
    assert actual.num_tri() == expected.num_tri()
    assert actual.volume() == pytest.approx(expected.volume(), abs=1e-8)
    assert (actual - expected).is_empty() and (expected - actual).is_empty()


def test_loop_covers_only_arcs_whose_whole_span_is_on_its_chords():
    from dataclasses import replace
    from omacad.model.faces_types import CircularEdge, LoopEdge

    arc = CircularEdge(np.zeros(3), np.array([0., 0., 1.]), 10., -1., -1., True, nseg=96, a0=6., sweep=1.)
    circle = replace(arc, a0=0., sweep=2 * np.pi)
    loop = LoopEdge(circle.polyline(96)[:-1], circle.axis)
    assert loop.contains_arc(arc)  # crosses the angle wrap at 2 pi
    assert loop.contains_arc(circle)
    assert not loop.contains_arc(replace(arc, radius=10.001))
    assert not loop.contains_arc(replace(arc, center=np.array([0., 0., 0.001])))
    assert not loop.contains_arc(replace(arc, convex=False))
    half = LoopEdge(loop.pts[:49], loop.n)  # remaining half is a straight chord, not the missing semicircle
    assert not half.contains_arc(circle)
    assert not half.contains_arc(arc)
    assert half.contains_arc(replace(arc, a0=0.2, sweep=1.))
