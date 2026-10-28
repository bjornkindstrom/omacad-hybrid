"""Exact-volume checks of the modelling features against closed-form or shapely results."""
import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane
from omacad.model.sketch_trim import apply_trim, trim_plan


def body(d):
    return list(d.bodies.values())[0]


def vol(d):
    return body(d).manifold.volume()


def extruded(poly, height):
    d = Document()
    sk = d.start_sketch("XY")
    sk.add_loop(poly, closed=True)
    d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, height, "new_body")
    return d


def top_edges(d, z):
    return [e.ref() for e in body(d).edges if e.kind == "line" and abs(e.p0[2] - z) < 1e-6 and abs(e.p1[2] - z) < 1e-6]


# ---- fillet / chamfer on extruded outlines ---------------------------------------------------------
H = 15.0
SHAPES = {
    "irregular convex": [(0, 0), (40, 5), (55, 30), (25, 45), (-5, 25)],
    "L shape": [(0, 0), (50, 0), (50, 15), (20, 15), (20, 40), (0, 40)],
    "sharp and obtuse": [(0, 0), (60, 0), (45, 12), (30, 40), (10, 20)],
}


def chamfer_volume(poly, s):
    P = Polygon(poly)
    zs = np.linspace(0, s, 400)
    area = [P.buffer(-z, join_style=2, mitre_limit=1e9).area for z in zs]
    return P.area * (H - s) + np.trapezoid(area, zs)


def fillet_volume(poly, r):
    P = Polygon(poly)
    zs = np.linspace(0, r, 1500)
    area = [P.buffer(-(r - math.sqrt(max(r * r - (r - z) ** 2, 0))), join_style=2, mitre_limit=1e9).area for z in zs]
    return P.area * (H - r) + np.trapezoid(area, zs)


@pytest.mark.parametrize("name", SHAPES)
@pytest.mark.parametrize("s", [2.0, 4.0])
def test_chamfer_top_of_irregular_extrusion_is_exact(name, s):
    d = extruded(SHAPES[name], H)
    assert len(body(d).edges) >= len(SHAPES[name]) * 3        # a mild bend must not hide the walls
    d.add_fillet(top_edges(d, H), s, "chamfer")
    assert vol(d) == pytest.approx(chamfer_volume(SHAPES[name], s), rel=2e-4)
    assert len(body(d).manifold.decompose()) == 1


@pytest.mark.parametrize("name", SHAPES)
def test_fillet_top_of_irregular_extrusion(name):
    d = extruded(SHAPES[name], H)
    d.add_fillet(top_edges(d, H), 3.0, "fillet")
    assert vol(d) == pytest.approx(fillet_volume(SHAPES[name], 3.0), rel=1e-3)


def test_chamfer_of_circle_edges_has_no_slivers_and_exact_profile():
    R, Hh, s = 12.0, 20.0, 2.5
    d = Document()
    d.add_cylinder(R, Hh)
    d.add_fillet([e.ref() for e in body(d).edges if e.kind == "circle"], s, "chamfer")
    mesh = body(d).manifold.to_mesh()
    v = np.asarray(mesh.vert_properties[:, :3], float)
    r, z = np.hypot(v[:, 0], v[:, 1]), v[:, 2]
    prof = np.array([(0, 0), (R - s, 0), (R, s), (R, Hh - s), (R - s, Hh), (0, Hh)])
    for ri, zi in zip(r, z):
        dmin = 1e9
        for p, q in zip(prof[:-1], prof[1:]):
            t = np.clip(np.dot((ri, zi) - p, q - p) / np.dot(q - p, q - p), 0, 1)
            dmin = min(dmin, np.linalg.norm(p + t * (q - p) - (ri, zi)))
        assert dmin < 1e-6
    from omacad.model import quality
    assert len(v) < 8 * quality.circle_segments()             # the tool uses the wall's own segment count


def test_fillet_follows_an_edited_history():
    d = Document()
    d.add_box(40, 30, 20)
    d.add_fillet(top_edges(d, 20), 3.0, "chamfer")
    d.edit_feature(0, length=60)
    P = Polygon([(0, 0), (60, 0), (60, 30), (0, 30)])
    zs = np.linspace(0, 3, 400)
    exact = P.area * 17 + np.trapezoid([P.buffer(-z, join_style=2, mitre_limit=1e9).area for z in zs], zs)
    assert vol(d) == pytest.approx(exact, rel=1e-4)
    assert d.timeline.features[-1].skipped == 0


def test_fillet_of_a_circle_after_the_radius_changed():
    d = Document()
    d.add_cylinder(15, 20)
    d.add_fillet([e.ref() for e in body(d).edges if e.kind == "circle" and abs(e.center[2] - 20) < 1e-6], 2.0, "fillet")
    d.edit_feature(0, radius=25)
    assert d.timeline.features[-1].skipped == 0
    from omacad.model import quality
    n = quality.circle_segments()
    polygon = 0.5 * n * 25 ** 2 * math.sin(2 * math.pi / n) * 20
    removed = 2 * math.pi * (25 - 0.2232 * 2) * 4 * (1 - math.pi / 4)
    assert vol(d) == pytest.approx(polygon - removed, rel=2e-3)


def test_foot_of_a_rounded_block_is_one_outline():
    d = Document()
    sk = d.start_sketch("XY"); sk.add_rect((-20, -20), (20, 20)); d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 10, "new_body")
    sk2 = d.start_sketch_on_plane(SketchPlane.from_face(np.array([0, 0, 1.0]), np.array([0, 0, 10.0]), name="FACE"))
    sk2.add_rect((-10, -10), (10, 10)); d.finish_sketch()
    idx = [i for i, p in enumerate(sk2.profiles) if abs(p.area - 400) < 1][0]
    d.extrude_profile(sk2.sketch_id, idx, 15, "join")
    corners = [e.ref() for e in body(d).edges if e.kind == "line" and abs(e.p0[0] - e.p1[0]) < 1e-6 and abs(e.p0[1] - e.p1[1]) < 1e-6
               and abs(abs(e.p0[0]) - 10) < 1e-6 and abs(abs(e.p0[1]) - 10) < 1e-6]
    d.add_fillet(corners, 4.0, "fillet")
    foot = [e for e in body(d).edges if e.kind == "loop" and not e.convex]
    assert len(foot) == 1
    v0 = vol(d)
    d.add_fillet([foot[0].ref()], 2.0, "chamfer")
    pappus = 0.5 * 4 * (foot[0].perimeter + 2 * math.pi * (2.0 / 3.0))
    assert vol(d) - v0 == pytest.approx(pappus, rel=2e-3)


# ---- shell, revolve, hole, mirror ------------------------------------------------------------------
def shelled(direction, faces, t=3.0, t2=2.0):
    d = Document()
    d.add_box(40, 40, 60)
    d.add_shell(body(d).body_id, t, faces, direction=direction, thickness2=t2)
    return vol(d)


TOP = [{"normal": [0, 0, 1], "origin": [20, 20, 60]}]


def test_shell_directions():
    assert shelled("inside", []) == pytest.approx(96000 - 34 * 34 * 54, rel=1e-6)
    assert shelled("inside", TOP) == pytest.approx(96000 - 34 * 34 * 57, rel=1e-6)
    assert shelled("outside", []) == pytest.approx(46 * 46 * 66 - 96000, rel=1e-6)
    assert shelled("outside", TOP) == pytest.approx(46 * 46 * 63 - 96000, rel=1e-6)
    assert shelled("both", [], 3, 2) == pytest.approx(44 * 44 * 64 - 34 * 34 * 54, rel=1e-6)
    assert shelled("both", TOP, 3, 2) == pytest.approx(44 * 44 * 62 - 34 * 34 * 57, rel=1e-6)


def revolved(profile, **kw):
    d = Document()
    sk = d.start_sketch("XY")
    profile(sk)
    d.finish_sketch()
    d.add_revolve(sk.sketch_id, 0, **kw)
    return d


def test_revolve_angles_and_axes():
    rect = lambda sk: sk.add_rect((10, 0), (20, 30))
    full = math.pi * (20 ** 2 - 10 ** 2) * 30
    assert vol(revolved(rect, axis=("v",))) == pytest.approx(full, rel=2e-3)
    assert vol(revolved(rect, axis=("v",), angle=90)) == pytest.approx(full / 4, rel=2e-3)
    assert vol(revolved(rect, axis=("v",), angle=90, direction="symmetric")) == pytest.approx(full / 4, rel=2e-3)
    assert vol(revolved(rect, axis=("v",), angle=90, direction="two_sides", angle2=45)) == pytest.approx(full * 135 / 360, rel=2e-3)
    assert vol(revolved(lambda sk: sk.add_rect((0, 5), (30, 12)), axis=("u",))) == pytest.approx(math.pi * (12 ** 2 - 5 ** 2) * 30, rel=2e-3)
    assert vol(revolved(lambda sk: sk.add_circle((30, 10), 5), axis=("v",))) == pytest.approx(2 * math.pi ** 2 * 30 * 25, rel=6e-3)


def test_revolve_profile_crossing_the_axis_fails_cleanly():
    d = Document()
    sk = d.start_sketch("XY"); sk.add_rect((-5, 0), (10, 30)); d.finish_sketch()
    feat = d.add_revolve(sk.sketch_id, 0, axis=("v",))
    assert not d.bodies and "cross" in feat.problem


@pytest.mark.parametrize("kw,expected", [
    (dict(hole_type="simple", diameter=6, depth=6), math.pi * 9 * 6),
    (dict(hole_type="simple", diameter=6, through=True), math.pi * 9 * 10),
    (dict(hole_type="counterbore", diameter=6, depth=8, cb_diameter=12, cb_depth=3), math.pi * 36 * 3 + math.pi * 9 * 5),
    (dict(hole_type="countersink", diameter=6, depth=8, cs_diameter=12, cs_angle=90), math.pi * 3 / 3 * (36 + 18 + 9) + math.pi * 9 * 5),
    (dict(hole_type="simple", diameter=6, depth=6, tip="angle"), math.pi * 9 * 6 + math.pi * 9 * 3 / math.tan(math.radians(59)) / 3),
])
def test_hole_volumes(kw, expected):
    d = Document()
    d.add_box(40, 30, 10)
    v0 = vol(d)
    d.add_hole([{"origin": [20, 15, 10], "normal": [0, 0, 1]}], **kw)
    assert v0 - vol(d) == pytest.approx(expected, rel=6e-3)


def test_hole_optional_chamfer_adds_a_conical_entrance():
    d = Document()
    d.add_box(40, 30, 10)
    before = vol(d)
    d.add_hole([{"origin": [20, 15, 10], "normal": [0, 0, 1]}],
               diameter=6, depth=10, through=True, chamfer_depth=1, chamfer_angle=45)
    removed = before - vol(d)
    expected_cylinder = math.pi * 9 * 9
    expected_frustum = math.pi * (4 ** 2 + 4 * 3 + 3 ** 2) / 3
    assert removed == pytest.approx(expected_cylinder + expected_frustum, rel=6e-3)


def test_hole_chamfer_width_limits_a_larger_max_depth():
    def removed_volume(max_depth):
        d = Document()
        d.add_box(40, 30, 10)
        before = vol(d)
        d.add_hole([{"origin": [20, 15, 10], "normal": [0, 0, 1]}],
                   diameter=6, depth=10, through=True, chamfer=2,
                   chamfer_depth=max_depth, chamfer_angle=45)
        return before - vol(d)
    assert removed_volume(10) == pytest.approx(removed_volume(2), rel=6e-3)


def test_mirror_across_a_plane():
    d = Document()
    d.add_box(40, 30, 10)
    sk = d.start_sketch("XY"); sk.add_circle((30, 15), 4); d.finish_sketch()
    d.extrude_profile(sk.sketch_id, 0, 10, "cut")
    one = vol(d)
    d.construction_planes["cp"] = {"name": "P", "origin": [20, 0, 0], "normal": [1, 0, 0], "visible": True}
    d.add_pattern([d.timeline.features[-2].feature_id, d.timeline.features[-1].feature_id], "mirror", mirror_mode="plane:cp")
    assert 40 * 30 * 10 - vol(d) == pytest.approx(2 * (40 * 30 * 10 - one), rel=1e-4)


# ---- sketch tools ----------------------------------------------------------------------------------
def make_sketch():
    d = Document()
    return d.start_sketch("XY")


def test_trim_removes_a_dangling_stub_and_a_middle_piece():
    from omacad.model.sketch import SketchLine
    sk = make_sketch()
    sk.entities = [SketchLine("a", (0, 0), (20, 0)), SketchLine("b", (10, -5), (10, 10)), SketchLine("c", (5, 0), (5, 8))]
    plan = trim_plan(sk, 2, 0, 0.5)                      # the stub of a left of c
    assert plan[2] == [("line", (5.0, 0.0), (20.0, 0.0))]
    apply_trim(sk, plan)
    assert {e.entity_id for e in sk.entities} >= {"b", "c"} and len(sk.entities) == 3
    plan = trim_plan(sk, 10, 8, 0.5)                     # top of b above a: removed up to the crossing
    assert plan[2] == [("line", (10.0, -5.0), (10.0, 0.0))]


def test_trim_circle_becomes_an_arc():
    from omacad.model.sketch import SketchCircle, SketchLine
    sk = make_sketch()
    sk.entities = [SketchCircle("k", (0, 0), 5), SketchLine("l", (-10, 0), (10, 0)), SketchLine("m", (-10, 2), (10, 2))]
    apply_trim(sk, trim_plan(sk, 0, 5, 0.3))
    assert [e.entity_type for e in sk.entities].count("arc") == 1


def test_sketch_mirror_and_offset():
    sk = make_sketch()
    sk.add_line((10, 0), (30, 10))
    sk.add_circle((20, -10), 4)
    new = sk.mirror_entities([e.entity_id for e in sk.entities], (0, 0), (0, 1))
    assert len(new) == 2 and new[0].p1 == (-10.0, 0.0) and new[1].center == (-20.0, -10.0)
    sk2 = make_sketch()
    sk2.add_rect((0, 0), (20, 10))
    out = sk2.offset_entities([e.entity_id for e in sk2.entities], -2)
    assert len(out) == 4
    assert any(abs(p.area - 16 * 6) < 1e-6 for p in sk2.profiles)


def test_face_outline_becomes_sketch_lines():
    d = Document()
    d.add_box(40, 30, 10)
    sk0 = d.start_sketch("XY"); sk0.add_circle((20, 15), 5); d.finish_sketch()
    d.extrude_profile(sk0.sketch_id, 0, 10, "cut")
    sk = d.start_sketch_on_plane(SketchPlane.from_face(np.array([0, 0, 1.0]), np.array([0, 0, 10.0]), name="FACE"))
    kinds = sorted(e.entity_type for e in sk.entities)
    assert kinds == ["circle", "line", "line", "line", "line"] and all(getattr(e, "projected", False) for e in sk.entities)
    assert sk.include_reference_edges() == []            # no duplicates
    lines = [e.entity_id for e in sk.entities if e.entity_type == "line"]
    assert len(sk.offset_entities(lines, -3)) == 4
    from omacad.model.sketch import Sketch
    assert sum(1 for e in Sketch.from_dict(sk.to_dict()).entities if getattr(e, "projected", False)) == 5


# ---- files -----------------------------------------------------------------------------------------
def test_all_feature_types_survive_save_and_load(tmp_path):
    d = Document()
    d.add_box(40, 30, 10)
    d.add_hole([{"origin": [20, 15, 10], "normal": [0, 0, 1]}], hole_type="counterbore", diameter=4, depth=6, cb_diameter=8, cb_depth=2)
    d.add_shell(body(d).body_id, 1.5, TOP[:0], direction="both", thickness2=1.0)
    sk = d.start_sketch("XY"); sk.add_rect((10, 0), (15, 5)); d.finish_sketch()
    d.add_revolve(sk.sketch_id, 0, axis=("v",), angle=90, direction="symmetric")
    d.delete_body(list(d.bodies)[-1])
    path = tmp_path / "all.omacad"
    Exporter.save_project(d, str(path))
    d2 = Exporter.load_project(str(path))
    assert sorted(round(b.manifold.volume(), 3) for b in d2.bodies.values()) == sorted(round(b.manifold.volume(), 3) for b in d.bodies.values())
    assert [f.feature_type for f in d2.timeline.features] == [f.feature_type for f in d.timeline.features]
