"""Shell feature modeling and geometry regression tests."""
import json
import math
from pathlib import Path

import pytest
import manifold3d as m3d

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.shell import ShellFeature
from omacad.model.kernel import CadKernel
from omacad.model import quality
from omacad.model.sketch import Sketch, SketchPlane

DATA_DIR = Path(__file__).parent / "data"


# ==============================================================================
# Shell Cylinder & Cavity Tests
# ==============================================================================

def _cylinder():
    return Document().add_cylinder(20, 40).manifold


def _area(r):
    n = quality.circle_segments()
    return n / 2 * math.sin(2 * math.pi / n) * r ** 2


def _offset(t):
    return 20 + t / math.cos(math.pi / quality.circle_segments())


@pytest.mark.parametrize("open_top", [False, True])
def test_inside_shell_of_cylinder_keeps_its_side_wall(open_top):
    faces = [{"normal": [0, 0, 1], "origin": [0, 0, 40]}] if open_top else None
    shelled = ShellFeature.compute_shell(_cylinder(), 2.0, "inside", open_faces=faces)
    cavity = _area(_offset(-2)) * (38 if open_top else 36)
    assert shelled.volume() == pytest.approx(_area(20) * 40 - cavity, rel=1e-6)


def test_outside_shell_of_cylinder_stays_round():
    shelled = ShellFeature.compute_shell(_cylinder(), 2.0, "outside")
    assert shelled.bounding_box()[3] == pytest.approx(_offset(2), rel=1e-6)
    assert shelled.volume() == pytest.approx(_area(_offset(2)) * 44 - _area(20) * 40, rel=1e-6)


def test_shell_of_cylinder_with_embossed_ribs_uses_the_plain_cylinder():
    doc_path = str(DATA_DIR / "circular_pattern_wrapped_emboss.omacad")
    doc = Exporter.load_project(doc_path)
    bid = "body_cylinder_1"
    body = doc.bodies[bid].manifold
    cylinder = doc.step_states[1][bid]
    ribs = body.volume() - cylinder.volume()
    upto = len(doc.timeline.features)
    for faces, cavity_h in ((None, 58), ([{"normal": [0, 0, 1], "origin": [0, 0, 62]}], 60)):
        shelled = ShellFeature.shell_body(doc, bid, upto, body, 2.0, "inside", open_faces=faces)
        wall = _area(20) * 62 - _area(_offset(-2)) * cavity_h
        assert shelled.volume() == pytest.approx(wall + ribs, rel=1e-6)


def test_drop_slivers_keeps_a_closed_inner_void():
    hollow = m3d.Manifold.cube((10, 10, 10), True) - m3d.Manifold.cube((6, 6, 6), True)
    flake = m3d.Manifold.cube((1, 1, 1)).scale((1, 1, 1e-9)).translate((20, 0, 0))
    assert CadKernel.drop_slivers(hollow + flake).volume() == pytest.approx(1000 - 216)


def test_shell_of_stacked_cylinders_follows_the_step():
    doc_path = str(DATA_DIR / "shell_stacked_cylinders.omacad")
    doc = Exporter.load_project(doc_path)
    body = doc.bodies["body_cylinder_1"].manifold
    n = quality.circle_segments()
    inner = lambda r: _area(r - 2 / math.cos(math.pi / n))
    assert len(body.decompose()) == 1
    assert body.slice(1).area() == pytest.approx(_area(20), rel=1e-6)
    assert body.slice(20).area() == pytest.approx(_area(20) - inner(20), rel=1e-6)
    assert body.slice(39).area() == pytest.approx(_area(20) - inner(16), rel=1e-6)
    for z in (41, 43, 45.5):
        assert body.slice(z).area() == pytest.approx(_area(16) - inner(16), rel=1e-6)


# ==============================================================================
# Shell Replay Recompute
# ==============================================================================

UP = dict(plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0])


def test_shell_of_a_stacked_cylinder_survives_a_rebuild():
    doc = Document()
    jar = doc.add_cylinder(20, 40)
    neck = doc.add_cylinder(16, 10, plane_origin=[0, 0, 40], **UP)
    doc.combine_bodies(jar.body_id, neck.body_id, "join")
    doc.add_shell(jar.body_id, 2.0, open_faces=[{"normal": [0, 0, 1], "origin": [0, 0, 50], "body_id": jar.body_id}])
    added = doc.bodies[jar.body_id].manifold.volume()
    doc.timeline.recompute(doc)
    assert doc.bodies[jar.body_id].manifold.volume() == pytest.approx(added, rel=1e-9)


# ==============================================================================
# Shell Feature & Sketch Hiding
# ==============================================================================

def test_shell_feature_compute_shell_and_hide_sketches():
    doc = Document()
    sk = doc.start_sketch("XY")
    sk.add_circle((0, 0), 10)
    doc.finish_sketch()
    doc.extrude_profile(sk.sketch_id, 0, 10.0)
    assert len(doc.bodies) == 1
    body_id = list(doc.bodies.keys())[0]
    body = doc.bodies[body_id]

    sk.visible = True
    orig_vol = body.manifold.volume()
    assert orig_vol > 0

    shelled = ShellFeature.compute_shell(body.manifold, thickness=1.0, direction="inside", thickness2=0.0, open_faces=[])
    assert shelled is not None
    assert 0 < shelled.volume() < orig_vol

    open_faces = [{"normal": [0, 0, 1], "origin": [0, 0, 10]}]
    shelled_open = ShellFeature.compute_shell(body.manifold, thickness=1.0, direction="inside", thickness2=0.0, open_faces=open_faces)
    assert shelled_open is not None
    assert 0 < shelled_open.volume() < orig_vol

    doc.add_shell(body_id, thickness=1.0, open_faces=open_faces)
    assert sk.visible is False


def test_face_sketch_parent_body_and_tree_grouping():
    doc = Document()
    sk1 = doc.start_sketch("XY")
    sk1.add_circle((0, 0), 10)
    doc.finish_sketch()
    doc.extrude_profile(sk1.sketch_id, 0, 10.0)
    body_id = list(doc.bodies.keys())[0]
    body = doc.bodies[body_id]

    face = body.faces[0]
    face_plane = SketchPlane.from_face(face.normal, face.origin)
    face_plane.face = face

    sk2 = doc.start_sketch_on_plane(face_plane)
    assert sk2.parent_body_id == body_id

    sk3 = doc.start_sketch("XZ")
    assert sk3.parent_body_id is None

    d = sk2.to_dict()
    assert d.get("parent_body_id") == body_id
    sk2_restored = Sketch.from_dict(d)
    assert sk2_restored.parent_body_id == body_id


# ==============================================================================
# Sketch Projection on Shelled Rim (#103)
# ==============================================================================

def test_project_takes_the_whole_rim_face():
    doc_path = str(DATA_DIR / "project_shelled_rim.omacad")
    doc = Exporter.load_project(doc_path)
    sk = doc.sketches["sketch_3"]
    rim = next(f for f in next(iter(doc.bodies.values())).faces
               if f.normal[2] > 0.999 and abs(f.origin[2] - 25.0) < 1e-3)
    sk.entities = [e for e in sk.entities if not getattr(e, "projected", False)]
    doc.refresh_sketch_references(sk)
    new = sk.include_reference_edges()
    sk.solve_profiles()
    assert sum(e.entity_type == "circle" for e in new) == 4
    areas = sorted(p.area for p in sk.profiles)
    assert len(areas) == 6
    assert areas[-1] > 3000.0
    assert areas[-2] == pytest.approx(rim.area, rel=2e-3)


# ==============================================================================
# Sphere Shell & Arbitrary Cut / Split Tests
# ==============================================================================

def test_shell_sphere_inside_outside_both_and_split():
    doc = Document()
    s = doc.add_sphere(25.0)
    v25 = CadKernel.create_sphere(25.0).volume()
    v23 = CadKernel.create_sphere(23.0).volume()
    v26 = CadKernel.create_sphere(26.0).volume()
    v27 = CadKernel.create_sphere(27.0).volume()

    out = ShellFeature.compute_shell(s.manifold, 2.0, "outside")
    assert out.volume() == pytest.approx(v27 - v25, rel=1e-5)
    both = ShellFeature.compute_shell(s.manifold, 2.0, "both", thickness2=1.0)
    assert both.volume() == pytest.approx(v26 - v23, rel=1e-5)

    doc.add_shell(s.body_id, 2.0, direction="inside")
    assert doc.bodies[s.body_id].manifold.volume() == pytest.approx(v25 - v23, rel=1e-5)

    # Split at an arbitrary angled plane
    cp_id = doc.add_construction_plane(doc.origin_planes["XY"], 5.0, name="Angled", angle=30.0)
    feat = doc.split_body(s.body_id, cp_id)
    assert feat is not None
    assert len(doc.bodies) == 2
    total_vol = sum(b.manifold.volume() for b in doc.bodies.values())
    assert total_vol == pytest.approx(v25 - v23, rel=1e-4)

    # Split the remaining half again with XY + lip joint
    half_id = s.body_id
    feat2 = doc.split_body(
        half_id, "XY",
        lip={"style": "inner", "height": 3.0, "width": 0.0, "clearance": 0.2, "lip_on": "back", "snap_fit": False},
    )
    assert feat2 is not None
    assert all(b.manifold.volume() > 100.0 for b in doc.bodies.values())


def test_split_sphere_then_shell_with_open_face():
    doc = Document()
    s = doc.add_sphere(25.0)
    doc.split_body(s.body_id, "XY")
    top_id = next(bid for bid, b in doc.bodies.items() if b.manifold.bounding_box()[2] >= -1e-4)
    doc.add_shell(top_id, 2.0, open_faces=[{"normal": [0, 0, -1], "origin": [0, 0, 0]}])
    bowl = doc.bodies[top_id].manifold
    assert bowl.volume() > 1000.0
    assert bowl.slice(1.0).area() < CadKernel.create_sphere(25.0).slice(1.0).area()
