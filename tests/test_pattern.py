"""Pattern features (Linear, Circular, Fill): lattices, margins, clearances, obstacles, orientation, and thread cutting."""
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.pattern import PatternFeature
from omacad.model.sketch import SketchPlane
from omacad.model.timeline import _best_pattern

DATA_DIR = Path(__file__).parent / "data"


# =========================================================================
# 1. Linear Pattern
# =========================================================================

def test_linear_pattern_copies_the_finished_hollow_body():
    doc = Exporter.load_project(str(DATA_DIR / "linear_pattern_hollow_body.json"))
    ids = [f.feature_id for f in doc.timeline.features]
    bid, body = next(iter(doc.bodies.items()))
    original = body.manifold
    expected_copies = original.translate((0, 0, 20)) + original.translate((0, 0, 40))
    params = dict(axis1="z", count1=3, spacing1=20)
    preview = PatternFeature("preview", "Preview", ids, "linear", **params)
    removed, added = preview.compute(doc, bid)
    assert removed is None and added is not None
    assert (added - expected_copies).volume() == pytest.approx(0, abs=1e-6)
    assert (expected_copies - added).volume() == pytest.approx(0, abs=1e-6)

    feature = doc.add_pattern(ids, "linear", **params)
    assert feature.copies == 2
    result = doc.bodies[bid].manifold
    assert result.volume() == pytest.approx(3 * original.volume(), rel=1e-8)
    assert len(result.decompose()) == 3
    assert (result - original - expected_copies).volume() == pytest.approx(0, abs=1e-6)
    doc.timeline.recompute(doc)
    assert doc.bodies[bid].manifold.volume() == pytest.approx(3 * original.volume(), rel=1e-8)
    doc.undo()
    assert doc.bodies[bid].manifold.volume() == pytest.approx(original.volume())
    doc.redo()
    assert doc.bodies[bid].manifold.volume() == pytest.approx(3 * original.volume(), rel=1e-8)


# =========================================================================
# 2. Fill Pattern: Margins, Clearances, Obstacles & Room
# =========================================================================

def test_obstacles_get_the_gap_not_the_edge_margin():
    doc = Exporter.load_project(str(DATA_DIR / "fill_pattern_clearance.omacad"))
    doc.timeline.recompute(doc)
    ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([ext.feature_id], kind="fill", spacing1=1.0, spacing2=3.0, count1=5.0, mirror_mode="triangular")
    feat = doc.timeline.features[-1]
    feat.compute(doc, next(iter(doc.bodies.values())).body_id)
    room = feat._fill_clip[0]
    holes = sorted((Polygon(r) for r in room.interiors), key=lambda p: p.area)
    assert len(holes) == 2
    for hole, r in zip(holes, (3.5, 6.0)):
        assert hole.bounds[2] - hole.bounds[0] == pytest.approx(2 * r, abs=0.1)


def test_no_partial_triangles_beside_the_holes():
    doc = Exporter.load_project(str(DATA_DIR / "fill_pattern_around_holes.omacad"))
    doc.timeline.recompute(doc)
    ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([ext.feature_id], kind="fill", spacing1=3.0, spacing2=1.0, count1=5.0, mirror_mode="triangular")
    feat = doc.timeline.features[-1]
    body = next(iter(doc.bodies.values()))
    res = feat.compute(doc, body.body_id)
    rem, _ = res
    pieces = rem.decompose()
    assert max(p.volume() for p in pieces) > 0


def test_fill_margin_wider_than_original_clips_row():
    doc = Exporter.load_project(str(DATA_DIR / "fill_pattern_thin_wall.omacad"))
    feat = doc.add_pattern(["feat_sketch_2", "extrude_7"], "fill", spacing1=5.0, spacing2=10.0, count1=25.0, mirror_mode="grid")
    body = next(iter(doc.bodies.values()))
    rem, _ = feat.compute(doc, body.body_id)
    assert feat.margin_used == pytest.approx(10.0)
    assert feat.copies == 2


def test_no_channel_along_the_triangle_edges_of_the_face():
    doc = Exporter.load_project(str(DATA_DIR / "fill_pattern_hairline_cracks.omacad"))
    doc.timeline.recompute(doc)
    ext = [f for f in doc.timeline.features if f.feature_type == "extrude"][-1]
    doc.add_pattern([ext.feature_id], kind="fill", spacing1=3.0, spacing2=3.0, count1=25.0, mirror_mode="grid")
    feat = doc.timeline.features[-1]
    body = next(iter(doc.bodies.values()))
    rem, _ = feat.compute(doc, body.body_id)
    assert rem is not None


def test_hexagon_holes_fill_the_floor_around_the_posts():
    doc = Exporter.load_project(str(DATA_DIR / "fill_box_floor_with_lid.omacad"))
    box_id = "body_extrude_2"
    before = doc.bodies[box_id].manifold.volume()
    hole_vol = 83.1384
    pat = doc.add_pattern(["extrude_15"], kind="fill", count1=0.0, spacing1=3.0, spacing2=3.0, mirror_mode="stagger")
    assert pat.copies >= 20
    assert abs((before - doc.bodies[box_id].manifold.volume()) - hole_vol * pat.copies) < 0.05 * hole_vol


def test_fill_preview_of_unsaved_pattern_computes():
    doc = Exporter.load_project(str(DATA_DIR / "request_223_fill_pattern.json"))
    doc.timeline.recompute(doc)
    ids = [f.feature_id for f in doc.timeline.features if f.name in ("Sketch 2", "Extrude 2")]
    feat = PatternFeature("tmp", "tmp", ids, "fill", spacing1=4.0, spacing2=8.0)
    results = [feat.compute(doc, bid) for bid in list(doc.bodies)]
    assert any(r is not None for r in results)
    assert feat.copies > 1


# =========================================================================
# 3. Polygon Lattices & Spacing Calculations
# =========================================================================

def _regular_polygon(n, r=10.0, rot=0.0):
    return Polygon([(r * math.cos(rot + 2 * math.pi * k / n), r * math.sin(rot + 2 * math.pi * k / n)) for k in range(n)])


def _cell_area_per_copy(foot, gap):
    members, v1, v2 = _best_pattern(foot, gap)
    return abs(v1[0] * v2[1] - v1[1] * v2[0]) / len(members), members, v1, v2


@pytest.mark.parametrize("n", [3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize("rot", [0.0, 0.3])
def test_lattice_keeps_gap_and_does_not_overlap(n, rot):
    foot, gap = _regular_polygon(n, rot=rot), 2.0
    _, members, v1, v2 = _cell_area_per_copy(foot, gap)
    c = foot.centroid
    inv = affinity.rotate(foot, 180, origin=(c.x, c.y))
    shapes = []
    for i in range(-2, 3):
        for j in range(-2, 3):
            for turned, off in members:
                shapes.append(affinity.translate(inv if turned else foot, i * v1[0] + j * v2[0] + off[0], i * v1[1] + j * v2[1] + off[1]))
    for a in range(len(shapes)):
        for b in range(a + 1, len(shapes)):
            assert shapes[a].distance(shapes[b]) >= 2.0 - 1e-4


def test_square_is_a_square_grid_and_hexagon_a_honeycomb():
    gap = 2.0
    sq = _regular_polygon(4, rot=math.pi / 4)
    side = sq.bounds[2] - sq.bounds[0]
    area, *_ = _cell_area_per_copy(sq, gap)
    assert area == pytest.approx((side + gap)**2, rel=5e-3)
    hx = _regular_polygon(6)
    apothem = 10.0 * math.cos(math.pi / 6)
    area, *_ = _cell_area_per_copy(hx, gap)
    assert area == pytest.approx((2 * apothem + gap)**2 * math.sqrt(3) / 2, rel=5e-3)


@pytest.mark.parametrize("n", [3, 5])
def test_odd_polygons_pair_up_with_a_turned_copy(n):
    area, members, *_ = _cell_area_per_copy(_regular_polygon(n), 1.0)
    assert len(members) == 2


# =========================================================================
# 4. Plane Tracking & Thread Pattern Quality
# =========================================================================

def test_source_plane_follows_body_half_turn():
    plane = SketchPlane.create_named("XY")
    source = SimpleNamespace(feature_id="sketch", sketch=SimpleNamespace(plane=plane))
    turn = np.diag([1.0, -1.0, -1.0, 1.0])
    turn[:3, 3] = (0, 0, 12)
    pattern = PatternFeature("pattern", "Fill", ["sketch"], kind="fill")
    move_before = SimpleNamespace(feature_id="move_before", feature_type="move", copy_body=False,
                                  suppressed=False, error=None, applied=turn)
    move_after = SimpleNamespace(feature_id="move_after", feature_type="move", copy_body=False,
                                 suppressed=False, error=None, applied=turn)
    doc = SimpleNamespace(timeline=SimpleNamespace(features=[source, move_before, pattern, move_after]),
                          sketches={}, object_history=SimpleNamespace(owners={
                              "sketch": "body", "move_before": "body", "move_after": "body"}))

    moved = pattern._source_plane(doc)
    np.testing.assert_allclose(moved.origin, (0, 0, 12))
    np.testing.assert_allclose(moved.normal, (0, 0, -1))
    np.testing.assert_allclose(moved.v_axis, (0, -1, 0))
    np.testing.assert_allclose(plane.normal, (0, 0, 1))


def test_pattern_thread_no_ugly_vertical_facet_lines():
    doc_path = DATA_DIR / "pattern_thread_ugly_facet_lines.omacad"
    doc = Exporter.load_project(str(doc_path))
    doc.timeline.recompute(doc)
    body = doc.bodies["body_split_5"]
    mesh = body.render_mesh
    lines = np.asarray(mesh.sharp_lines).reshape(-1, 2, 3)

    holes = [
        ("original (-15, -15)", -15, -15),
        ("mirror X (15, -15)", 15, -15),
        ("mirror Y (-15, 15)", -15, 15),
        ("mirror XY (15, 15)", 15, 15),
    ]

    for name, x, y in holes:
        mid = 0.5 * (lines[:, 0, :] + lines[:, 1, :])
        dist = np.hypot(mid[:, 0] - x, mid[:, 1] - y)
        hl = lines[dist < 5.0]
        dz = np.abs(hl[:, 1, 2] - hl[:, 0, 2])
        vertical_count = int(np.sum(dz > 0.05))
        assert vertical_count == 0, f"{name} had {vertical_count} vertical facet lines"


# =========================================================================
# 5. Linked Pattern Holes & Wall Clearances (#216 follow-up)
# =========================================================================

def _plate(doc):
    sk = doc.start_sketch("XY")
    lines = sk.add_rect((-50., -30.), (50., 30.))
    assert doc.add_constraints(sk.sketch_id, [("FIX", [l.entity_id], []) for l in lines])
    return sk, lines


def _wall(lines, x=None, y=None):
    for l in lines:
        if x is not None and l.p1[0] == pytest.approx(x) and l.p2[0] == pytest.approx(x):
            return l
        if y is not None and l.p1[1] == pytest.approx(y) and l.p2[1] == pytest.approx(y):
            return l


def _clearances(sk, holes):
    return [v for h in holes for v in (50. - abs(h.center[0]) - h.radius, 30. - abs(h.center[1]) - h.radius)]


def _dim(doc, sk, hole, wall, value):
    assert doc.add_dimension_constraint(sk.sketch_id, "PT_LINE_DIST", hole.entity_id, value,
                                        refs=[wall.entity_id], pts=["edge_near"],
                                        moving_entity_id=hole.entity_id)
    return sk.dimensions[-1]


@pytest.mark.parametrize("dims_first", [True, False])
def test_corner_holes_follow_the_master_wall_distance(dims_first, tmp_path):
    from omacad.model.sketch_pattern import corner_copies
    from omacad.model.sketch_linked_clearance import link_clearances
    doc = Document()
    sk, lines = _plate(doc)
    master = sk.add_circle((-40., 20.), 4.)
    if dims_first:
        left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
        top = _dim(doc, sk, master, _wall(lines, y=30.), 6.)
    copies = corner_copies(sk, [master], (-50., -30., 50., 30.))
    link_clearances(sk)
    if not dims_first:
        left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
        top = _dim(doc, sk, master, _wall(lines, y=30.), 6.)
    holes = [master, *copies]
    assert _clearances(sk, holes) == pytest.approx([6., 6.] * 4)
    assert doc.update_dimension(sk.sketch_id, left.dim_id, 12.)
    assert doc.update_dimension(sk.sketch_id, top.dim_id, 3.)
    assert _clearances(sk, holes) == pytest.approx([12., 3.] * 4)
    diameter = next(d for d in sk.dimensions if d.target_entity_id == master.entity_id and d.dim_type == "DIAMETER")
    assert doc.update_dimension(sk.sketch_id, diameter.dim_id, 10.)
    assert all(h.radius == pytest.approx(5.) for h in holes)
    assert _clearances(sk, holes) == pytest.approx([12., 3.] * 4)
    ids = [h.entity_id for h in holes]
    doc.undo()
    doc.undo()
    sk = doc.sketches[sk.sketch_id]
    holes = [sk.get_entity(i) for i in ids]
    assert all(h.radius == pytest.approx(4.) for h in holes)
    assert _clearances(sk, holes) == pytest.approx([12., 6.] * 4)
    doc.redo()
    path = tmp_path / "plate.omacad"
    doc.finish_sketch()
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    assert loaded.update_dimension(sk.sketch_id, left.dim_id, 8.)
    restored = loaded.sketches[sk.sketch_id]
    assert _clearances(restored, [restored.get_entity(h.entity_id) for h in holes]) == pytest.approx([8., 3.] * 4)


def test_editing_a_copy_clearance_unlinks_only_that_hole():
    from omacad.model.sketch_pattern import corner_copies
    doc = Document()
    sk, lines = _plate(doc)
    master = sk.add_circle((-40., 20.), 4.)
    copies = corner_copies(sk, [master], (-50., -30., 50., 30.))
    left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
    right = next(d for d in sk.dimensions if d.follows == left.dim_id
                 and sk.get_entity(d.target_entity_id).center[0] > 0 and sk.get_entity(d.target_entity_id).center[1] > 0)
    assert doc.update_dimension(sk.sketch_id, right.dim_id, 15.)
    assert right.follows is None
    assert doc.update_dimension(sk.sketch_id, left.dim_id, 9.)
    rims = {h.entity_id: 50. - abs(h.center[0]) - h.radius for h in [master, *copies]}
    assert rims.pop(right.target_entity_id) == pytest.approx(15.)
    assert list(rims.values()) == pytest.approx([9.] * 3)
    doc.remove_dimension(sk.sketch_id, left.dim_id)
    assert not any(d.follows for d in sk.dimensions)


def test_unlinked_or_middle_copies_are_left_alone():
    from omacad.model.sketch_pattern import rectangular_copies
    doc = Document()
    sk, lines = _plate(doc)
    master = sk.add_circle((-40., 20.), 4.)
    linked = rectangular_copies(sk, [master], 3, 40.)
    free, = rectangular_copies(sk, [master], 1, 0., 2, -40., linked=False)
    left = _dim(doc, sk, master, _wall(lines, x=-50.), 6.)
    assert not any(d.target_entity_id in [free.entity_id, linked[0].entity_id] for d in sk.dimensions)
