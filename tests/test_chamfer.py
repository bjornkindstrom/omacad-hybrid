"""Chamfer modeling and edge selection regression tests."""
from collections import Counter, defaultdict
from dataclasses import replace
import math
from pathlib import Path

import manifold3d as m3d
import numpy as np
import pytest
import trimesh
from shapely.ops import polygonize

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces_edges import loop_contains
from omacad.model.faces_surfaces import curved_surface_ids
from omacad.model.faces_types import CircularEdge, LoopEdge

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Chamfer moving hole edge-cache tests (Björn #105)
# ==============================================================================

def _solid_at(body, x, y, z):
    probe = m3d.Manifold.cube([0.05, 0.05, 0.05]).translate([x, y, z])
    return (body.manifold ^ probe).volume() > 1e-6


@pytest.mark.parametrize("dist, x", [(45.0, -10.0), (15.0, -40.0)])
def test_chamfer_moves_with_the_hole(dist, x):
    doc_path = str(DATA_DIR / "chamfer_follows_moved_hole.omacad")
    doc = Exporter.load_project(doc_path)
    volume = doc.bodies["body_extrude_2"].manifold.volume()
    assert doc.update_dimension("sketch_1", "d10", dist)
    body = doc.bodies["body_extrude_2"]
    assert not _solid_at(body, x + 6.0, 35, 9.8)        # the bevel is at the hole's new place
    assert _solid_at(body, x + 6.0, 35, 7.0)            # below the 2 mm bevel the plate is solid
    assert _solid_at(body, -25 + 6.0, 35, 9.8)          # nothing left where the hole was
    assert doc.timeline.features[-1].skipped == 0
    assert body.manifold.volume() == pytest.approx(volume, rel=1e-6)


# ==============================================================================
# Chamfer fragmented walls and double precision tests (Report 20261025-125922)
# ==============================================================================

DOC_FRAGMENTED = str(DATA_DIR / "chamfer_fragmented_walls.omacad")


@pytest.mark.parametrize("whole_selection", [False, True])
def test_chamfer_keeps_curved_walls_free_of_false_creases(whole_selection):
    doc = Exporter.load_project(DOC_FRAGMENTED)
    if not whole_selection:
        feature = doc.timeline.features[-1]
        feature.edges = feature.edges[:1]
        doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    assert body.manifold.status().name == "NoError"
    assert body.manifold.volume() == pytest.approx(632680.238, abs=0.03)
    segments = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
    assert np.allclose(segments[:, 0, 2], segments[:, 1, 2], atol=1e-4)
    assert np.allclose(np.unique(segments[..., 2]), [0.0, 45.292, 50.0])
    tangents = body.render_mesh.tangent_lines().reshape(-1, 2, 3)
    assert 6 <= len(tangents) <= 12
    vertical = tangents[np.abs(tangents[:, 1, 2] - tangents[:, 0, 2]) > 40]
    assert len(vertical) == 6
    assert np.allclose(vertical[:, 0, :2], vertical[:, 1, :2], atol=1e-4)


def test_all_three_rims_are_closed_and_each_surface_is_whole():
    doc = Exporter.load_project(DOC_FRAGMENTED)
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
    assert len(tangents) == 12
    assert np.count_nonzero(np.isclose(np.abs(tangents[:, 1, 2] - tangents[:, 0, 2]), feature.size)) == 6

    segments = body.render_mesh.sharp_lines.reshape(-1, 2, 3)
    bottom = segments[np.isclose(segments[:, 0, 2], 0)]
    outline = next(iter(polygonize([s[:, :2] for s in bottom])))
    expected = outline.buffer(-feature.size, join_style='mitre').length
    for z, perimeter in ((0., feature.edges[0][3]), (50. - feature.size, feature.edges[0][3]), (50., expected)):
        rim = segments[np.isclose(segments[:, 0, 2], z)]
        degrees = Counter(map(tuple, np.round(rim.reshape(-1, 3), 4)))
        assert set(degrees.values()) == {2}
        assert np.linalg.norm(rim[:, 1] - rim[:, 0], axis=1).sum() == pytest.approx(perimeter, abs=1e-3)


@pytest.mark.parametrize('kind', ['chamfer', 'fillet'])
def test_selecting_arcs_already_in_a_loop_does_not_cut_the_surface_twice(kind):
    doc = Exporter.load_project(DOC_FRAGMENTED)
    feature = doc.timeline.features[-1]
    feature.kind = kind
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
    arc = CircularEdge(np.zeros(3), np.array([0., 0., 1.]), 10., -1., -1., True, nseg=96, a0=6., sweep=1.)
    circle = replace(arc, a0=0., sweep=2 * np.pi)
    loop = LoopEdge(circle.polyline(96)[:-1], circle.axis)
    assert loop.contains_arc(arc)
    assert loop.contains_arc(circle)
    assert not loop.contains_arc(replace(arc, radius=10.001))
    assert not loop.contains_arc(replace(arc, center=np.array([0., 0., 0.001])))
    assert not loop.contains_arc(replace(arc, convex=False))
    half = LoopEdge(loop.pts[:49], loop.n)
    assert not half.contains_arc(circle)
    assert not half.contains_arc(arc)
    assert half.contains_arc(replace(arc, a0=0.2, sweep=1.))


# ==============================================================================
# Chamfered hole fins test (Request 20261013-211700)
# ==============================================================================

def fin_edges(m):
    mesh = m.to_mesh()
    V, T = np.array(mesh.vert_properties)[:, :3], np.array(mesh.tri_verts)
    N = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    L = np.linalg.norm(N, axis=1)
    N = N / np.maximum(L[:, None], 1e-12)
    edges = defaultdict(list)
    for i, t in enumerate(T):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((t[a], t[b])))].append(i)
    return sum(1 for ts in edges.values()
               if len(ts) == 2 and L[ts[0]] > 1e-3 and L[ts[1]] > 1e-3 and N[ts[0]] @ N[ts[1]] < -0.9)


def test_chamfered_hole_has_no_fins():
    doc = Exporter.load_project(str(DATA_DIR / "chamfer_hole_fins.omacad"))
    doc.timeline.recompute(doc)
    m = next(iter(doc.bodies.values())).manifold
    assert fin_edges(m) == 0
    assert len(m.decompose()) == 1


# ==============================================================================
# Outline piece selection tests (#104)
# ==============================================================================

DOC_PIECE = str(DATA_DIR / "chamfer_single_outline_piece.omacad")


def _top_piece():
    doc = Exporter.load_project(DOC_PIECE)
    body = next(iter(doc.bodies.values()))
    loop = next(e for e in body.edges if e.kind == "loop" and e.n[2] > 0.5)
    pieces = [e for e in body.edges if e.kind in ("line", "circle") and loop_contains(loop, e)]
    return doc, body, loop, pieces


def test_outline_pieces_are_edges_of_their_own():
    _, body, loop, pieces = _top_piece()
    lines = [e for e in pieces if e.kind == "line"]
    assert any(e.kind == "circle" for e in pieces)
    total = sum(e.length for e in lines) + sum(float(e.radius) * float(e.sweep) for e in pieces if e.kind == "circle")
    assert total == pytest.approx(loop.perimeter, rel=1e-3)


def test_double_click_on_a_piece_takes_the_whole_outline():
    from omacad.ui.viewport.picker_mixin import PickerMixin
    _, body, loop, pieces = _top_piece()

    class Stub:
        def _visible_edges(self):
            return body.edges
    for piece in pieces:
        assert [e.kind for e in PickerMixin._edge_loop(Stub(), piece)] == ["loop"]


def test_chamfer_one_piece_leaves_the_rest_sharp():
    doc, body, loop, pieces = _top_piece()
    v0 = body.manifold.volume()
    line = max((e for e in pieces if e.kind == "line"), key=lambda e: e.length)
    others = [e for e in pieces if e.kind == "line" and e is not line and e.length > 5.0]
    doc.add_fillet([line.ref()], 2.0, kind="chamfer")
    after = next(iter(doc.bodies.values()))
    removed = v0 - after.manifold.volume()
    assert 0.97 * 2.0 * line.length < removed <= 1.0 * 2.0 * line.length
    lengths = [e.length for e in after.edges if e.kind == "line"]
    for o in others:
        assert any(abs(o.length - L) < 1e-3 for L in lengths), o.length
    doc2, body2, loop2, pieces2 = _top_piece()
    doc2.add_fillet([loop2.ref(), *[p.ref() for p in pieces2]], 2.0, kind="chamfer")
    doc3, body3, loop3, _ = _top_piece()
    doc3.add_fillet([loop3.ref()], 2.0, kind="chamfer")
    vol = lambda d: next(iter(d.bodies.values())).manifold.volume()
    assert vol(doc2) == pytest.approx(vol(doc3), rel=1e-6)


# ==============================================================================
# Wall outside corner tests (Report 20261023-213524, 20261023-213915)
# ==============================================================================

def _feet_at(body, v):
    return [(tuple(e.p0), tuple(e.p1)) for e in body.edges if e.kind == "line" and not e.convex
            and min(np.linalg.norm(e.p0 - v), np.linalg.norm(e.p1 - v)) < 1e-2]


def test_square_block_corner_is_a_quarter_cone():
    doc = Document()
    base = doc.add_box(50, 50, 10, center="bottom_center")
    block = doc.add_box(20, 20, 20, center="bottom_center", translation=(-15, -15, 10))
    doc.combine_bodies(base.body_id, block.body_id)
    body = next(iter(doc.bodies.values()))
    feet = _feet_at(body, np.array([-5.0, -5.0, 10.0]))
    assert len(feet) == 2
    before = body.manifold.volume()
    d = 6.0
    doc.add_fillet(feet, d, kind="chamfer")
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    exact = 2 * 20 * d * d / 2 + math.pi * d ** 3 / 12
    added = result.volume() - before
    assert abs(added - exact) / exact < 0.005


def test_rib_end_and_side_chamfers_swing_round_the_corner():
    doc = Exporter.load_project(str(DATA_DIR / "chamfer_rib_outside_corner.omacad"))
    body = next(iter(doc.bodies.values()))
    v = np.array([10.0, -7.269, 25.0])
    feet = _feet_at(body, v)
    assert len(feet) == 2
    d = 7.0
    doc.add_fillet(feet, d, kind="chamfer")
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    pts = np.vstack(result.slice(25.5).to_polygons())
    beyond = pts[(pts[:, 0] < v[0] - 1e-3) & (pts[:, 1] > v[1] + 1e-3)]
    assert len(beyond) > 10
    assert np.linalg.norm(beyond - v[:2], axis=1).max() < d - 0.5 + 0.05


def test_bands_on_differently_leaning_walls_meet_at_one_point():
    doc = Exporter.load_project(str(DATA_DIR / "chamfer_leaning_rib_corner.omacad"))
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    v = np.array([10.0, -7.269, 25.0])
    cd = np.array([0.0, -7.731, 12.5]) / np.linalg.norm([0.0, -7.731, 12.5])
    pts = np.asarray(result.to_mesh().vert_properties)[:, :3]
    d = pts - v
    t = d @ cd
    on_edge = t[(np.linalg.norm(d - t[:, None] * cd, axis=1) < 1e-3) & (t > 0.5) & (t < 14.0)]
    assert len(on_edge) and np.allclose(on_edge, 7.0, atol=1e-3)
    end_top = pts[(abs(pts[:, 0] - 10.0) < 1e-3) & (abs(pts[:, 2] - 32.0) < 1e-3)]
    corner_y = v[1] - 7.0 * 7.731 / 12.5
    assert abs(end_top[:, 1].max() - (corner_y - 7.0)) < 1e-2
