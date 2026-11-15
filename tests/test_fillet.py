"""Fillet geometry, modeling, and edge rounding regression tests."""
import math
import os
from pathlib import Path
from types import SimpleNamespace

import manifold3d as m3d
import numpy as np
import pytest
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.faces import edge_from_ref
from omacad.model.features.base import Body
from omacad.model.features.fillet import FilletFeature
from omacad.model.kernel import CadKernel
from omacad.model.sketch import SketchPlane
from omacad.model.wrapped_edges import WrappedLoopEdge, wrapped_round_tool

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Open Arcs Fillet & Chamfer
# ==============================================================================

DOC_ARC = DATA_DIR / "block_with_arc_cut.omacad"


def _load_arc():
    d = Exporter.load_project(str(DOC_ARC))
    return d, next(iter(d.bodies.values()))


def _big_arcs(body):
    return [e for e in body.edges if e.kind == "circle" and e.is_arc and e.radius > 20]


def test_open_arcs_are_edges():
    _, body = _load_arc()
    arcs = _big_arcs(body)
    assert len(arcs) == 2
    for a in arcs:
        assert a.convex and a.s1 > 0
        assert 1.5 < a.sweep < 1.8
        pts = a.polyline(48)
        assert np.allclose(np.linalg.norm(pts[:, 1:] - a.center[1:], axis=1), a.radius, atol=1e-6)


def test_rounded_plate_corners_have_the_right_side():
    _, body = _load_arc()
    corners = [e for e in body.edges if e.kind == "circle" and e.is_arc and e.radius < 10]
    assert corners and all(e.s1 < 0 for e in corners)


@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_arc_fillet_removes_material_and_stays_solid(kind):
    doc, body = _load_arc()
    v0 = body.manifold.volume()
    f = FilletFeature("f_arc", "Fillet", [e.ref() for e in _big_arcs(body)], 2.0, kind)
    doc.timeline.add_feature(f)
    doc.timeline.recompute(doc)
    nb = next(iter(doc.bodies.values()))
    assert f.skipped == 0
    removed = v0 - nb.manifold.volume()
    area = (1 - np.pi / 4) * 4.0 if kind == "fillet" else 2.0
    expected = 2 * area * 1.661 * 63.7
    assert 0.9 * expected < removed < 1.15 * expected
    assert len(nb.manifold.decompose()) == 1 and nb.manifold.genus() == 0


def test_arc_ref_survives_a_save_round_trip():
    doc, body = _load_arc()
    refs = [e.ref() for e in _big_arcs(body)]
    f = FilletFeature("f_arc", "Fillet", refs, 2.0)
    assert f.edges[0][0] == "arc" and len(f.edges[0]) == 6
    assert all(edge_from_ref(r, body.edges) is not None for r in f.edges)


# ==============================================================================
# Fillet clearance limit
# ==============================================================================

def test_fillet_overrun_capped_to_adjacent_clearance():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_clearance.omacad"))
    fillet = doc.timeline.features[-1]
    assert isinstance(fillet, FilletFeature)
    fillet.size = 20.0
    doc.timeline.recompute(doc)
    body = list(doc.bodies.values())[0]
    assert not body.manifold.is_empty()
    assert body.manifold.volume() > 8800.0


# ==============================================================================
# Fusion-like Fillet/Chamfer box corners & multi-distance types
# ==============================================================================

BOX_A, BOX_B, BOX_C, BOX_R = 30.0, 20.0, 10.0, 3.0


def _box_round(kind, **kw):
    doc = Document()
    body = doc.add_box(BOX_A, BOX_B, BOX_C)
    edges = [e.ref() for e in body.edges if getattr(e, "kind", "line") == "line"]
    assert len(edges) == 12
    feat = doc.add_fillet(edges, BOX_R, kind, **kw)
    assert feat.skipped == 0
    return doc, next(iter(doc.bodies.values())).manifold


def _planes_box(planes):
    m = m3d.Manifold.cube((BOX_A, BOX_B, BOX_C))
    for n, off in planes:
        k = math.sqrt(sum(c * c for c in n))
        m = m.trim_by_plane(tuple(c / k for c in n), off / k)
    return m


def _box_frame(doc):
    bb = next(iter(doc.bodies.values())).manifold.bounding_box()
    return bb[:3]


def test_all_box_edges_fillet_meet_in_a_ball():
    _doc, m = _box_round("fillet")
    a, b, c = BOX_A - 2 * BOX_R, BOX_B - 2 * BOX_R, BOX_C - 2 * BOX_R
    exact = a * b * c + 2 * BOX_R * (a * b + b * c + a * c) + math.pi * BOX_R * BOX_R * (a + b + c) + 4 / 3 * math.pi * BOX_R ** 3
    bumps = 8 * ((2 - math.sqrt(2)) - math.pi / 6) * BOX_R ** 3
    assert m.genus() == 0
    assert abs(m.volume() - exact) < 0.1 * bumps


def test_equal_chamfer_corners_get_a_triangle():
    doc, m = _box_round("chamfer")
    x0, y0, z0 = _box_frame(doc)
    planes = []
    for sx in (0, 1):
        for sy in (0, 1):
            for sz in (0, 1):
                corner = (sx * BOX_A, sy * BOX_B, sz * BOX_C)
                n = (1 - 2 * sx, 1 - 2 * sy, 1 - 2 * sz)
                dot = sum(a * b for a, b in zip(n, corner))
                planes.append((n, 2 * BOX_R + dot))
                for k in range(3):
                    ne = tuple(0 if i == k else n[i] for i in range(3))
                    planes.append((ne, BOX_R + sum(a * b for a, b in zip(ne, corner))))
    ref = _planes_box(planes).translate((x0, y0, z0))
    assert abs(m.volume() - ref.volume()) < 1e-6
    assert (m - ref).volume() < 1e-6 and (ref - m).volume() < 1e-6


def test_two_distance_chamfer_puts_the_first_distance_on_the_top_face():
    doc = Document()
    body = doc.add_box(BOX_A, BOX_B, BOX_C)
    zmax = body.manifold.bounding_box()[5]
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - zmax) < 1e-6 and abs(e.p1[2] - zmax) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    doc.add_fillet([edge.ref()], 4.0, "chamfer", chamfer_type="two", size2=1.5)
    m = next(iter(doc.bodies.values())).manifold
    assert abs(m.volume() - (BOX_A * BOX_B * BOX_C - 0.5 * 4.0 * 1.5 * BOX_A)) < 1e-6
    top = m.slice(zmax - 1e-4)
    width = top.bounds()[3] - top.bounds()[1]
    assert abs(width - (BOX_B - 4.0)) < 1e-2
    feat = doc.timeline.features[-1]
    doc.edit_feature(len(doc.timeline.features) - 1, flip=True)
    m = next(iter(doc.bodies.values())).manifold
    top = m.slice(zmax - 1e-4)
    assert abs(top.bounds()[3] - top.bounds()[1] - (BOX_B - 1.5)) < 1e-2
    assert feat.flip


def test_distance_and_angle_chamfer_and_save_roundtrip(tmp_path):
    doc = Document()
    body = doc.add_box(BOX_A, BOX_B, BOX_C)
    zmax = body.manifold.bounding_box()[5]
    edge = next(e for e in body.edges if getattr(e, "kind", "line") == "line"
                and abs(e.p0[2] - zmax) < 1e-6 and abs(e.p1[2] - zmax) < 1e-6 and abs(e.p0[0] - e.p1[0]) > 1)
    doc.add_fillet([edge.ref()], 2.0, "chamfer", chamfer_type="angle", angle=60.0)
    vol = BOX_A * BOX_B * BOX_C - 0.5 * 2.0 * 2.0 * math.tan(math.radians(60.0)) * BOX_A
    assert abs(next(iter(doc.bodies.values())).manifold.volume() - vol) < 1e-6
    path = tmp_path / "c.omacad"
    Exporter.save_project(doc, str(path))
    again = Exporter.load_project(str(path))
    feat = again.timeline.features[-1]
    assert (feat.chamfer_type, feat.angle) == ("angle", 60.0)
    assert abs(next(iter(again.bodies.values())).manifold.volume() - vol) < 1e-6


# ==============================================================================
# Filleted straight side length in sketch solver (Report 20261024-064212)
# ==============================================================================

def test_side_between_fillets_takes_the_new_length():
    doc = Exporter.load_project(str(DATA_DIR / "filleted_rect_side_length.omacad"))
    sk = doc.sketches["sketch_1"]
    assert doc.update_dimension("sketch_1", "d2", 40.0)
    right, top, left = (sk.get_entity(i) for i in ("line_2", "line_3", "line_4"))
    assert math.isclose(abs(right.p2[1] - right.p1[1]), 40.0, abs_tol=1e-6)
    assert math.isclose(top.p1[1], 58.0, abs_tol=1e-6) and math.isclose(top.p2[1], 58.0, abs_tol=1e-6)
    assert math.isclose(abs(left.p1[1] - left.p2[1]), 33.0, abs_tol=1e-6)
    radii = {d.dim_id: d.value for d in sk.dimensions if d.dim_type == "RADIUS"}
    for arc_id, dim_id in (("arc_5", "d3"), ("arc_6", "d4"), ("arc_7", "d5"), ("arc_8", "d6")):
        assert math.isclose(sk.get_entity(arc_id).get_circle_params()[1], radii[dim_id], abs_tol=1e-6)
    assert math.isclose(next(d.value for d in sk.dimensions if d.dim_id == "d2"), 40.0, abs_tol=1e-6)
    assert len(sk.solve_profiles()) == 1
    doc.undo()
    right = doc.sketches["sketch_1"].get_entity("line_2")
    assert math.isclose(abs(right.p2[1] - right.p1[1]), 22.0, abs_tol=1e-6)


# ==============================================================================
# Fillet foot of rib & narrowing wall (Report 20261023-210908)
# ==============================================================================

def test_fillet_stays_inside_the_sloping_sides_of_the_rib():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_foot_of_rib.omacad"))
    body = next(iter(doc.bodies.values()))
    assert doc.timeline.features[-1].skipped == 0
    region = m3d.Manifold.cube((200, 200, 200), True).translate((0, -105, 125))
    left = body.manifold ^ region.trim_by_plane((-1, 0, 0.4), 10.0)
    right = body.manifold ^ region.trim_by_plane((1, 0, 10 / 37.5), 25 + 25 * 10 / 37.5)
    assert left.volume() < 1e-6 and right.volume() < 1e-6
    r = 19.8
    exact = 25 * r * r * (1 - math.pi / 4) - 2 / 3 * r ** 3 * (5 / 6 - math.pi / 4)
    fill = (body.manifold ^ region).volume()
    assert abs(fill - exact) / exact < 0.005


# ==============================================================================
# Fillet loop concave arcs (Björn #78)
# ==============================================================================

def _slice_poly(m, z):
    return [Polygon(p) for p in m.slice(z).to_polygons()]


def test_fillet_round_concave_arcs_is_smooth():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_loop_concave_arcs.omacad"))
    ids = [f.feature_id for f in doc.timeline.features]
    bid = next(iter(doc.bodies))
    before = doc.step_states[ids.index("fillet_3")][bid]
    body = doc.bodies[bid].manifold
    assert len(body.decompose()) == 1 and body.genus() == 0
    outline = unary_union(_slice_poly(before, 5.0))
    for z in (9.9, 9.5, 8.5):
        loops = _slice_poly(body, z)
        assert len(loops) == 1, z
        inset = 2.0 - math.sqrt(4.0 - (z - 8.0) ** 2)
        ideal = outline.buffer(-inset, join_style=1)
        assert loops[0].difference(ideal).area < 0.01, z
        assert ideal.difference(loops[0]).area < 1.0, z


# ==============================================================================
# Polygon corner fillet/chamfer (Report 20261024-084617)
# ==============================================================================

PRISM_H = 30.0


def _corner_edge(body):
    edges = [e for e in body.edges if getattr(e, "kind", "") == "line" and e.convex and abs(e.p1[2] - e.p0[2]) > PRISM_H - 1]
    return max(edges, key=lambda e: (round(float(e.p0[0]), 3), round(float(e.p0[1]), 3)))


@pytest.mark.parametrize("sides", [3, 4, 6, 8])
@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_corner_of_any_angle_loses_exactly_the_corner_region(sides, kind):
    doc = Document()
    body = doc.add_prism(40.0, PRISM_H, sides=sides)
    before = body.manifold.volume()
    edge = _corner_edge(body)
    doc.add_fillet([(tuple(edge.p0), tuple(edge.p1))], 2.0, kind)
    after = next(iter(doc.bodies.values())).manifold.volume()
    theta = math.pi - 2 * math.pi / sides
    if kind == "fillet":
        area = 4.0 * (1 / math.tan(theta / 2) - (math.pi - theta) / 2)
    else:
        area = 0.5 * 4.0 * math.sin(theta)
    assert abs((before - after) - area * PRISM_H) / (area * PRISM_H) < 0.01


def test_hexagon_corner_from_the_report_has_no_notch():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_hexagon_corner.omacad"))
    body = next(iter(doc.bodies.values()))
    edge = next(e for e in body.edges if getattr(e, "kind", "") == "line" and e.convex
                and e.p0[0] > 80 and e.p0[1] < 0 and abs(e.p1[2] - e.p0[2]) > 30)
    region = m3d.Manifold.cube((20, 20, 60)).translate((70, -57, -10))
    before = body.manifold ^ region
    f = FilletFeature("f", "F", [(tuple(edge.p0), tuple(edge.p1))], 4.0)
    f.execute(doc)
    after = next(iter(doc.bodies.values())).manifold ^ region
    exact = 16.0 * (1 / math.sqrt(3) - math.pi / 6)
    for z in (1.0, 20.0, 39.9):
        lost = before.slice(z).area() - after.slice(z).area()
        assert abs(lost - exact) / exact < 0.01


# ==============================================================================
# Sharp inside corners & honeycomb margin (Report 20261024-081206)
# ==============================================================================

NOTCH_R, NOTCH_TOP = 1.0, 5.0
NOTCH_APEX = np.array([20.0, 20.0])
NOTCH_SIDES = [np.array([-math.sin(math.radians(30)), -math.cos(math.radians(30))]),
               np.array([math.sin(math.radians(30)), -math.cos(math.radians(30))])]


def _notched_plate():
    plate = m3d.Manifold.cube((40.0, 40.0, NOTCH_TOP))
    far = [NOTCH_APEX + 30.0 * s for s in NOTCH_SIDES]
    notch = m3d.Manifold.extrude(m3d.CrossSection([[tuple(NOTCH_APEX), tuple(far[0]), tuple(far[1])]]), NOTCH_TOP + 2).translate((0, 0, -1))
    return plate - notch


def test_rim_of_a_sharp_notch_is_two_rounded_half_planes():
    body = Body("b", "plate", _notched_plate())
    body.update_render_mesh()
    rims = [e for e in body.edges if getattr(e, "kind", "") == "line" and abs(e.p0[2] - NOTCH_TOP) < 1e-6
            and abs(e.p1[2] - NOTCH_TOP) < 1e-6 and min(np.linalg.norm(e.p0[:2] - NOTCH_APEX), np.linalg.norm(e.p1[:2] - NOTCH_APEX)) < 1e-6]
    assert len(rims) == 2
    feat = FilletFeature("f", "Fillet", [e.ref() for e in rims], NOTCH_R)
    feat.execute(SimpleNamespace(bodies={"b": body}))
    assert feat.skipped == 0

    plate = m3d.Manifold.cube((40.0, 40.0, NOTCH_TOP))
    rod = m3d.Manifold.cylinder(200.0, NOTCH_R, circular_segments=2048, center=True)
    halves = []
    for k, s in enumerate(NOTCH_SIDES):
        wall = np.array([-s[1], s[0]]) * (1 if k == 0 else -1)
        n3 = (float(-wall[0]), float(-wall[1]), 0.0)
        half = plate.trim_by_plane(n3, float(-wall @ NOTCH_APEX))
        line = np.array([s[0], s[1], 0.0])
        inward = np.array([-wall[0], -wall[1], 0.0])
        if np.linalg.det(np.column_stack((inward, (0, 0, 1), line))) < 0:
            line = -line
        frame = np.column_stack((inward, (0.0, 0.0, 1.0), line, (NOTCH_APEX[0], NOTCH_APEX[1], NOTCH_TOP))).astype(float)
        slab = m3d.Manifold.cube((NOTCH_R + 1.0, NOTCH_R + 1.0, 400.0)).translate((-1.0, -NOTCH_R, -200.0))
        band = (slab - rod.translate((NOTCH_R, -NOTCH_R, 0.0))).transform(frame)
        halves.append(half - band)
    exact = (halves[0] + halves[1]).volume()
    assert body.manifold.genus() == 0
    assert body.manifold.volume() == pytest.approx(exact, abs=0.04)


def test_honeycomb_margin_corners_have_no_ridge():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_honeycomb_margin.omacad"))
    m = doc.bodies["body_box_1"].manifold
    for x, z, depth in ((24.8, 13.0, 0.4), (39.2, 13.0, 0.4), (24.8, 19.5, 0.4), (39.2, 19.5, 0.4)):
        probe = m3d.Manifold.cube((0.02, 2.0, 0.02)).translate((x - 0.01, 23.0, z - 0.01))
        top = 23.0 + (m ^ probe).volume() / 0.02 ** 2
        assert 25.0 - top == pytest.approx(depth, abs=0.08)


# ==============================================================================
# Surface follow on cylindrical neighbour
# ==============================================================================

def test_inside_fillet_follows_the_adjacent_cylinder_for_the_full_edge():
    path = DATA_DIR / "fillet_surface_follow.omacad"
    doc = Exporter.load_project(str(path))
    doc.timeline.marker_index = 2
    doc.timeline.clear_cache()
    doc.timeline.recompute(doc)

    feature = doc.timeline.features[-1]
    assert isinstance(feature, FilletFeature)
    body = next(iter(doc.bodies.values()))
    edge = edge_from_ref(feature.edges[0], body.edges)
    assert edge is not None and edge.kind == "line" and not edge.convex

    circle = next(e for e in body.edges if e.kind == "circle" and abs(float(e.axis @ [0, 0, 1])) > 0.999)
    tool = feature._circular_neighbor_tool(body, edge, feature.size)
    assert tool is not None

    cx, cy = circle.center[:2]
    for z in (1.0, 7.5, 14.0):
        polygons = tool.slice(z).to_polygons()
        assert len(polygons) == 1
        points = np.asarray(polygons[0])
        radial_error = np.abs(np.linalg.norm(points - [cx, cy], axis=1) - circle.radius)
        assert np.count_nonzero(radial_error < 0.03) >= 90

    expected_added_volume = tool.volume()
    feature.execute(doc)
    assert body.manifold.status().name == "NoError"
    assert math.isclose(body.manifold.volume(), 11986.372361773334 + expected_added_volume,
                        rel_tol=1e-7, abs_tol=1e-5)
    assert feature.skipped == 0


# ==============================================================================
# Twisted Extrude top outline fillet/chamfer (Report 20261025-111509)
# ==============================================================================

def _report_twisted_doc():
    return Exporter.load_project(str(DATA_DIR / "fillet_twisted_extrude_top.omacad"))


def _hexagon_twisted_doc():
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
    a = np.cross(n, t)
    basis = np.column_stack([a, n, t])
    m = manifold.translate(tuple(-p)).transform(np.column_stack([basis.T, np.zeros(3)]))
    sec = Polygon(max(m.slice(0.0).to_polygons(), key=lambda q: Polygon(q).area))
    d2 = np.array([d @ a, d @ n])
    b = np.array([1.0, 0.0]) + d2 / np.linalg.norm(d2)
    b /= np.linalg.norm(b)
    hit = sec.exterior.intersection(LineString([(0.0, 0.0), tuple(5.0 * b)]))
    pts = [hit] if hit.geom_type == "Point" else list(getattr(hit, "geoms", []))
    return min(math.hypot(q.x, q.y) for q in pts), d2 / np.linalg.norm(d2)


@pytest.mark.parametrize("make", [_report_twisted_doc, _hexagon_twisted_doc])
@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_whole_top_outline_of_a_twisted_extrude_rounds_like_the_corner_it_meets(make, kind):
    doc = make()
    loop = _top_loop(doc)
    assert loop.walls is not None and float(np.abs(loop.walls @ loop.n).max()) > 0.1
    P = loop.pts
    seg = np.linalg.norm(np.roll(P, -1, axis=0) - P, axis=1)
    i = int(np.argmax(seg))
    p, t = (P[i] + P[(i + 1) % len(P)]) / 2.0, (P[(i + 1) % len(P)] - P[i]) / seg[i]
    d = np.cross(loop.walls[i], t)
    d = -d if d @ loop.n > 0 else d
    d /= np.linalg.norm(d)
    r = 1.5
    v0 = next(iter(doc.bodies.values())).manifold.volume()
    doc.add_fillet([loop.ref()], r, kind=kind)
    body = next(iter(doc.bodies.values()))
    assert body.manifold.genus() == 0 and body.manifold.volume() < v0 - 0.5 * r * r
    depth, d2 = _section_depth(body.manifold, p, t, loop.n, d)
    half = 0.5 * math.acos(float(np.clip(d2[0], -1.0, 1.0)))
    if kind == "fillet":
        want = r / math.sin(half) - r
    else:
        want = r * math.cos(half)
    assert abs(depth - want) < 0.03 * r


# ==============================================================================
# Wall outside corner rolling ball (Report 20261023-211810, 20261023-214720)
# ==============================================================================

def _feet_at(body, v):
    return [(tuple(e.p0), tuple(e.p1)) for e in body.edges if e.kind == "line" and not e.convex
            and min(np.linalg.norm(e.p0 - v), np.linalg.norm(e.p1 - v)) < 1e-2]


def test_square_block_corner_is_a_revolved_fillet():
    doc = Document()
    base = doc.add_box(50, 50, 10, center="bottom_center")
    block = doc.add_box(20, 20, 20, center="bottom_center", translation=(-15, -15, 10))
    doc.combine_bodies(base.body_id, block.body_id)
    body = next(iter(doc.bodies.values()))
    v = np.array([-5.0, -5.0, 10.0])
    feet = _feet_at(body, v)
    assert len(feet) == 2
    before = body.manifold.volume()
    r = 6.0
    doc.add_fillet(feet, r)
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    area = r * r * (1 - math.pi / 4)
    exact = 2 * 20 * area + math.pi / 2 * r ** 3 * (5 / 6 - math.pi / 4)
    added = result.volume() - before
    assert abs(added - exact) / exact < 0.005


def test_rib_end_and_side_fillets_flow_round_the_corner():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_rib_outside_corner.omacad"))
    body = next(iter(doc.bodies.values()))
    v = np.array([-8.347, -4.5, 25.0])
    feet = _feet_at(body, v)
    assert len(feet) == 2
    r = 14.5
    doc.add_fillet(feet, r)
    result = next(iter(doc.bodies.values())).manifold
    assert doc.timeline.features[-1].skipped == 0 and result.genus() == 0
    h = 0.5
    reach = r - math.sqrt(r * r - (r - h) ** 2)
    pts = np.vstack(result.slice(25.0 + h).to_polygons())
    beyond = pts[(pts[:, 0] > v[0] + 1e-3) & (pts[:, 1] > v[1] + 1e-3)]
    assert len(beyond) > 10
    assert np.linalg.norm(beyond - v[:2], axis=1).max() < reach + 0.1


def test_band_beside_a_leaning_corner_edge_stops_at_the_ball():
    doc = Exporter.load_project(str(DATA_DIR / "fillet_leaning_rib_corner.omacad"))
    feat = doc.timeline.features[-1]
    result = next(iter(doc.bodies.values())).manifold
    assert feat.skipped == 0 and result.genus() == 0
    for z in (25.001, 25.01):
        assert len(result.slice(z).decompose()) == 1
    mesh = result.to_mesh()
    tri = np.asarray(mesh.vert_properties)[:, :3][np.asarray(mesh.tri_verts)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    c = tri.mean(axis=1)
    step = (np.abs(c[:, 0] - 10.0) < 0.02) & (c[:, 1] > -8) & (c[:, 1] < 1) & (n[:, 0] > 0.99 * np.linalg.norm(n, axis=1))
    assert np.linalg.norm(n[step], axis=1).sum() / 2 < 0.05


# ==============================================================================
# Foot fillet over rim fillet & polygon corners (Report 20261011-222411)
# ==============================================================================

def test_foot_fillet_runs_out_into_the_rim_fillet():
    doc = Exporter.load_project(str(DATA_DIR / "foot_fillet_over_rim_fillet.omacad"))
    doc.timeline.recompute(doc)
    m = next(iter(doc.bodies.values())).manifold
    assert m.status().name == "NoError" and len(m.decompose()) == 1
    xs = np.concatenate([p[:, 0] for p in m.slice(9.95).to_polygons()])
    assert xs.min() > -13.8
    fillet2 = next(f for f in doc.timeline.features if f.name == "Fillet 2")
    fillet2.suppressed = True
    doc.timeline.recompute(doc)
    without = next(iter(doc.bodies.values())).manifold.volume()
    assert 0 < m.volume() - without < 144


def _octagon_on_plate(radius=10.0):
    d = Document()
    d.add_box(60, 60, 5)
    d.auto_include_edges = False
    sk = d.start_sketch_on_plane(SketchPlane.from_face(np.array([0., 0, 1]), np.array([0., 0, 5])))
    sk.add_polygon((30, 30), (30 + radius, 30), 8)
    d.finish_sketch()
    d.extrude_profile(list(d.sketches)[-1], 0, 15, "join")
    d.timeline.recompute(d)
    return d


def test_corners_are_filled_not_notched():
    d = _octagon_on_plate()
    body = next(iter(d.bodies.values()))
    foot = [e for e in body.edges if getattr(e, "kind", "") == "line" and not e.convex
            and abs(e.p0[2] - 5) < 1e-6 and abs(e.p1[2] - 5) < 1e-6 and np.linalg.norm(e.p0[:2] - 30) < 12]
    assert len(foot) == 8
    r = 2.0
    d.add_fillet([(tuple(e.p0), tuple(e.p1)) for e in foot], r)
    m = next(iter(d.bodies.values())).manifold
    h = 0.5
    reach = r - math.sqrt(r * r - (r - h) ** 2)
    for k in range(8):
        a = math.radians(45 * k)
        corner_r = 10.0
        d_out = 0.95 * reach
        p = (30 + (corner_r + d_out) * math.cos(a), 30 + (corner_r + d_out) * math.sin(a), 5 + h)
        probe = m3d.Manifold.cube((0.02, 0.02, 0.02), True).translate(p)
        assert not (probe ^ m).is_empty(), f"corner {k} is notched"
    far = (30 + 10.0 * math.cos(0) + 1.4 * r, 30.0, 5.2)
    probe = m3d.Manifold.cube((0.02, 0.02, 0.02), True).translate(far)
    assert (probe ^ m).is_empty()


# ==============================================================================
# Negative fillet cove (Lennart #79, Report 20261020-193759)
# ==============================================================================

def test_negative_fillet_on_a_rim_cuts_a_cove_inward():
    doc = Exporter.load_project(str(DATA_DIR / "negative_fillet_rim.omacad"))
    body = next(iter(doc.bodies.values()))
    bb = body.manifold.bounding_box()
    assert bb[3] < 20.0 + 1e-6 and bb[5] < 25.0 + 1e-6
    r, R = 10.0, 15.0
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


# ==============================================================================
# Slot fillet smooth transitions (Report 20261031-160743)
# ==============================================================================

def test_slot_fillet_transitions_are_smooth():
    project_path = DATA_DIR / "slot_fillet_transitions.omacad"
    doc = Exporter.load_project(str(project_path))
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    assert body is not None and body.manifold is not None
    sl = body.render_mesh.sharp_lines
    slot_fillet_pts = [p for p in sl if 2.9 <= p[2] <= 5.1 and 19 <= p[0] <= 46 and 34 <= p[1] <= 41]
    assert len(slot_fillet_pts) == 0, f"Expected clean loop transition without facet seam lines, got {len(slot_fillet_pts)} points"


# ==============================================================================
# Wall foot fillet leaning wall (Fusion 360 look)
# ==============================================================================

DOC_WALL = str(DATA_DIR / "wall_foot_fillet.omacad")
WALL_LEN = 26.0
WALL_ANGLE = math.pi - math.atan2(62.9908 - 25.0, 1.3183 - (-14.7304))


def _filleted_wall(r):
    doc = Exporter.load_project(DOC_WALL)
    doc.timeline.features = doc.timeline.features[:3]
    doc.timeline.recompute(doc)
    body = next(iter(doc.bodies.values()))
    v0 = body.manifold.volume()
    foot = next(e for e in body.edges if e.kind == "line" and not e.convex and abs(e.p0[0] + 14.7304) < 1e-2 and abs(e.p1[0] + 14.7304) < 1e-2)
    doc.timeline.features.append(FilletFeature("t", "F", [foot.ref()], r, kind="fillet"))
    doc.timeline.recompute(doc)
    new = next(iter(doc.bodies.values()))
    return new.manifold.volume() - v0, new.manifold.bounding_box()


def _wall_area(r):
    return r * r * (1 / math.tan(WALL_ANGLE / 2) - (math.pi - WALL_ANGLE) / 2) * WALL_LEN


def test_foot_fillet_that_fits_has_exact_volume():
    dv, _ = _filleted_wall(10.0)
    assert abs(dv - _wall_area(10.0)) / _wall_area(10.0) < 0.01


def test_oversized_foot_fillet_stays_on_the_floor():
    dv, bb = _filleted_wall(30.0)
    r_max = 10.2696 * 0.99 * math.tan(WALL_ANGLE / 2)
    assert dv < _wall_area(r_max) * 1.01
    assert bb[0] >= -25.0 - 1e-3


# ==============================================================================
# Wrapped Deboss / Emboss Fillet & Chamfer (Request #63)
# ==============================================================================

DOC_WRAPPED = DATA_DIR / "wrapped_deboss_fillet.omacad"


def _load_wrapped():
    return Exporter.load_project(str(DOC_WRAPPED))


def test_report_has_both_pickable_wrapped_rims():
    doc = _load_wrapped()
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "wrapped"]
    assert len(edges) == 2
    assert {e.convex for e in edges} == {True, False}
    assert sorted(e.radius for e in edges) == pytest.approx([19, 20], abs=.01)
    for e in edges:
        assert edge_from_ref(e.ref(), body.edges) is e
        size = FilletFeature._safe_edge_size(body, e, 2)
        assert .48 < size < .50


@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
@pytest.mark.parametrize("convex", [True, False])
def test_report_rounding_survives_save_rebuild_and_undo(kind, convex):
    doc = _load_wrapped()
    body = next(iter(doc.bodies.values()))
    before = body.manifold.volume()
    edge = next(e for e in body.edges if e.kind == "wrapped" and e.convex == convex)
    feature = doc.add_fillet([edge.ref()], .25, kind=kind)
    assert feature.skipped == 0
    after = next(iter(doc.bodies.values())).manifold.volume()
    assert .1 < abs(after - before) < 4
    assert (after < before) == convex
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert restored.timeline.features[-1].skipped == 0
    assert next(iter(restored.bodies.values())).manifold.volume() == pytest.approx(after, abs=1e-6)
    doc.undo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(before, abs=1e-6)
    doc.redo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(after, abs=1e-6)


def test_wrapped_chamfer_volume_matches_cylindrical_integral():
    r, radius, w, h = .25, 20., 10., 15.
    corners = np.array([[-w / 2, 0], [w / 2, 0], [w / 2, h], [-w / 2, h]])
    uv = []
    for a, b in zip(corners, np.roll(corners, -1, axis=0)):
        for t in np.linspace(0, 1, math.ceil(np.linalg.norm(b - a) / .2), endpoint=False):
            uv.append(a + (b - a) * t)
    uv = np.asarray(uv)

    def wrap(p):
        theta = p[:, 0] / radius
        return np.column_stack(((radius + p[:, 2]) * np.sin(theta),
                                -(radius + p[:, 2]) * np.cos(theta), p[:, 1]))

    pts = wrap(np.column_stack((uv, np.zeros(len(uv)))))
    edge = WrappedLoopEdge(pts, np.array([0., 0., 1.]), np.zeros(3), radius,
                           np.array([0., -1., 0.]), np.array([1., 0., 0.]), True, ())
    base = m3d.Manifold.cube((w, h, 2)).translate((-w / 2, 0, -2)).refine_to_length(.2).warp_batch(wrap)
    tool = wrapped_round_tool(edge, r, "chamfer")
    removed = (base ^ tool).volume()
    expected = (w + h) * r * r - 4 * r ** 3 / 3 - (w + h) * r ** 3 / (3 * radius) + r ** 4 / (3 * radius)
    assert removed == pytest.approx(expected, rel=.02)


def test_report_at_original_high_curve_quality():
    from omacad.model import quality
    quality.set_circle_segments(360)
    doc = _load_wrapped()
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "wrapped"]
    assert len(edges) == 2
    assert sorted(e.radius for e in edges) == pytest.approx([19, 20], abs=.01)
    feature = doc.add_fillet([e.ref() for e in edges], .25)
    assert feature.skipped == 0
    assert next(iter(doc.bodies.values())).manifold.status() == m3d.Error.NoError


def test_wrapped_rounding_is_invariant_under_body_rotation():
    body = next(iter(_load_wrapped().bodies.values()))
    edge = next(e for e in body.edges if e.kind == "wrapped" and e.convex)
    delta = body.manifold.volume() - (body.manifold - CadKernel.round_tool(edge, .25, "fillet")).volume()
    body.manifold = body.manifold.rotate([20, 35, 10])
    body.update_render_mesh()
    edge = next(e for e in body.edges if e.kind == "wrapped" and e.convex)
    rotated_delta = body.manifold.volume() - (body.manifold - CadKernel.round_tool(edge, .25, "fillet")).volume()
    assert rotated_delta == pytest.approx(delta, rel=.02)


def test_raised_wrapped_emboss_has_both_roundable_rims():
    doc = _load_wrapped()
    assert doc.edit_feature(3, depth=1.)
    body = next(iter(doc.bodies.values()))
    edges = [e for e in body.edges if e.kind == "wrapped"]
    assert len(edges) == 2
    assert sorted(e.radius for e in edges) == pytest.approx([20, 21], abs=.01)
    feature = doc.add_fillet([e.ref() for e in edges], .25)
    assert feature.skipped == 0
    assert next(iter(doc.bodies.values())).manifold.status() == m3d.Error.NoError

