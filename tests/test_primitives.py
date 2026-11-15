"""Primitive solid tests: Box, Cylinder, Sphere, Prism/Hexagon geometry, placement, and features."""
import math
import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.features.primitives import BoxFeature, CylinderFeature, PrismFeature
from omacad.model.sketch import SketchPlane
from omacad.model import quality


# =========================================================================
# 1. Box, Cylinder, Sphere placement and bounds
# =========================================================================

def test_box_bottom_center():
    doc = Document()
    b = doc.add_box(40, 20, 10, center="bottom_center")
    mesh = b.render_mesh
    assert abs(mesh.bounds_min[2] - 0.0) < 1e-4
    assert abs(mesh.bounds_max[2] - 10.0) < 1e-4
    assert abs(mesh.bounds_min[0] - (-20.0)) < 1e-4
    assert abs(mesh.bounds_max[0] - 20.0) < 1e-4
    assert abs(mesh.bounds_min[1] - (-10.0)) < 1e-4
    assert abs(mesh.bounds_max[1] - 10.0) < 1e-4


def test_cylinder_bottom_center():
    doc = Document()
    c = doc.add_cylinder(15, 30, center="bottom_center")
    mesh = c.render_mesh
    assert abs(mesh.bounds_min[2] - 0.0) < 1e-4
    assert abs(mesh.bounds_max[2] - 30.0) < 1e-4
    assert abs(mesh.bounds_min[0] - (-15.0)) < 1e-4
    assert abs(mesh.bounds_max[0] - 15.0) < 1e-4


def test_box_on_horizontal_face():
    doc = Document()
    base = doc.add_box(100, 100, 20, center="bottom_center")
    top_plane = SketchPlane(
        name="Top Face",
        origin=np.array([0.0, 0.0, 20.0], dtype=np.float32),
        u_axis=np.array([1.0, 0.0, 0.0], dtype=np.float32),
        v_axis=np.array([0.0, 1.0, 0.0], dtype=np.float32),
        normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
    )
    b2 = doc.add_box(30, 30, 15, center="bottom_center",
                     plane_origin=top_plane.origin, plane_normal=top_plane.normal,
                     plane_u=top_plane.u_axis, plane_v=top_plane.v_axis)
    mesh = b2.render_mesh
    assert abs(mesh.bounds_min[2] - 20.0) < 1e-4
    assert abs(mesh.bounds_max[2] - 35.0) < 1e-4


def test_cylinder_on_vertical_face():
    doc = Document()
    base = doc.add_box(100, 100, 40, center="bottom_center")
    side_plane = SketchPlane(
        name="Side Face",
        origin=np.array([50.0, 0.0, 20.0], dtype=np.float32),
        u_axis=np.array([0.0, 1.0, 0.0], dtype=np.float32),
        v_axis=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        normal=np.array([1.0, 0.0, 0.0], dtype=np.float32),
    )
    cyl = doc.add_cylinder(10, 25, center="bottom_center",
                           plane_origin=side_plane.origin, plane_normal=side_plane.normal,
                           plane_u=side_plane.u_axis, plane_v=side_plane.v_axis)
    mesh = cyl.render_mesh
    assert abs(mesh.bounds_min[0] - 50.0) < 1e-4
    assert abs(mesh.bounds_max[0] - 75.0) < 1e-4


def test_primitive_translation_is_saved_with_the_primitive_step():
    doc = Document()
    box = doc.add_box(10, 8, 6, translation=[12, -4, 3])
    assert box.manifold.bounding_box() == pytest.approx((12, -4, 3, 22, 4, 9), abs=1e-5)
    cylinder = doc.add_cylinder(3, 8, translation=[-10, 5, 2])
    assert cylinder.manifold.bounding_box() == pytest.approx((-13, 2, 2, -7, 8, 10), abs=1e-5)
    prism = doc.add_prism(8, 5, translation=[0, 14, -2])
    assert prism.manifold.bounding_box()[1:6:4] == pytest.approx((9.3811978465, 3), abs=1e-4)
    sphere = doc.add_sphere(4, translation=[20, 0, 5])
    assert sphere.manifold.bounding_box() == pytest.approx((16, -4, 1, 24, 4, 9), abs=1e-5)

    loaded = Document()
    Exporter.apply_dict(loaded, Exporter.document_to_dict(doc))
    for bid, body in doc.bodies.items():
        assert loaded.bodies[bid].manifold.volume() == pytest.approx(body.manifold.volume())
        assert loaded.bodies[bid].manifold.bounding_box() == pytest.approx(body.manifold.bounding_box(), abs=1e-5)


def test_primitive_translation_accepts_numpy_offset_used_by_drag_handles():
    offset = np.array([12.0, -4.0, 3.0])
    doc = Document()
    box = doc.add_box(10, 8, 6, translation=offset)
    assert box.manifold.bounding_box() == pytest.approx((12, -4, 3, 22, 4, 9), abs=1e-5)
    cylinder = doc.add_cylinder(3, 8, translation=offset)
    assert cylinder.manifold.bounding_box() == pytest.approx((9, -7, 3, 15, -1, 11), abs=1e-5)
    sphere = doc.add_sphere(4, translation=offset)
    assert sphere.manifold.bounding_box() == pytest.approx((8, -8, -1, 16, 0, 7), abs=1e-5)


# =========================================================================
# 2. Taper angles, walls & volumes
# =========================================================================

def _box_taper_volume(l, w, h, k):
    return l * w * h - (l + w) * k * h * h + 4 * k * k * h**3 / 3


def _cylinder_taper_volume(r, h, k):
    n = quality.circle_segments()
    return n / 2 * math.sin(2 * math.pi / n) * (r * r * h - r * k * h * h + k * k * h**3 / 3)


@pytest.mark.parametrize("angle", [-12, 0, 12])
@pytest.mark.parametrize("kind", ["box", "cylinder"])
@pytest.mark.parametrize("wall", [0.0, 2.0])
def test_tapered_volume_and_constant_normal_shell(kind, angle, wall):
    doc = Document()
    k = math.tan(math.radians(angle))
    h = 20.0
    if kind == "box":
        body = doc.add_box(50, 40, h, taper_angle=angle, wall_thickness=wall, center="bottom_center")
        expected = _box_taper_volume(50, 40, h, k)
    else:
        body = doc.add_cylinder(25, h, taper_angle=angle, wall_thickness=wall)
        expected = _cylinder_taper_volume(25, h, k)
    if wall:
        offset = wall / math.cos(math.radians(angle))
        if kind == "box":
            expected -= _box_taper_volume(50 - 2 * k * wall - 2 * offset, 40 - 2 * k * wall - 2 * offset, h - wall, k)
        else:
            expected -= _cylinder_taper_volume(25 - k * wall - offset, h - wall, k)
    assert body.manifold.volume() == pytest.approx(expected, rel=1e-6)
    saved = Exporter.document_to_dict(doc)
    copy = Document()
    Exporter.apply_dict(copy, saved)
    assert copy.timeline.features[0].taper_angle == angle
    assert next(iter(copy.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)
    doc.undo()
    assert not doc.bodies
    doc.redo()
    assert next(iter(doc.bodies.values())).manifold.volume() == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("cls,args", [(BoxFeature, (50, 40, 20)), (CylinderFeature, (25, 20))])
def test_taper_rounding_and_placement(cls, args):
    feature = cls("a", "A", *args, taper_angle=8, wall_thickness=2,
                  outer_round=1, inner_round=0.5, center=True,
                  plane_origin=[10, 20, 30], plane_normal=[0, -1, 0],
                  plane_u=[1, 0, 0], plane_v=[0, 0, 1])
    solid = feature.build_solid()
    assert not solid.is_empty()
    assert solid.status().name == "NoError"
    assert 0 < solid.volume() < cls("b", "B", *args).build_solid().volume()


@pytest.mark.parametrize("kind,args", [("box", (10, 10, 50)), ("cylinder", (5, 50))])
def test_invalid_taper_leaves_document_unchanged(kind, args):
    doc = Document()
    before = doc.snapshot()
    with pytest.raises(ValueError, match="closes the top"):
        getattr(doc, "add_" + kind)(*args, taper_angle=45)
    assert doc.snapshot() == before


# =========================================================================
# 3. Prism / Regular polygon primitives
# =========================================================================

def _prism_area(apothem, sides=6):
    return sides * apothem**2 * math.tan(math.pi / sides)


def test_hexagon_is_sized_across_flats_with_a_flat_facing_x():
    solid = PrismFeature("p", "p", 20.0, 10.0).build_solid()
    assert solid.volume() == pytest.approx(_prism_area(10) * 10, rel=1e-9)
    x0, y0, z0, x1, y1, z1 = solid.bounding_box()
    assert (x0, x1) == pytest.approx((-10, 10))
    assert y1 == pytest.approx(10 / math.cos(math.pi / 6))
    assert (z0, z1) == pytest.approx((0, 10))


@pytest.mark.parametrize("sides", [3, 5, 8])
def test_other_side_counts(sides):
    solid = PrismFeature("p", "p", 30.0, 4.0, sides=sides).build_solid()
    assert solid.volume() == pytest.approx(_prism_area(15, sides) * 4, rel=1e-9)
    assert solid.bounding_box()[3] == pytest.approx(15)


def test_prism_shell_wall_is_square_to_the_flats():
    solid = PrismFeature("p", "p", 20.0, 10.0, wall_thickness=2.0).build_solid()
    assert solid.volume() == pytest.approx(_prism_area(10) * 10 - _prism_area(8) * 8, rel=1e-9)


def test_prism_chamfer_runs_along_every_flat():
    a, h, c = 10.0, 10.0, 1.0
    solid = PrismFeature("p", "p", 2 * a, h, outer_round=c, outer_round_kind="chamfer").build_solid()
    k = _prism_area(1.0)
    expected = k * a**2 * (h - 2 * c) + 2 * k * (a**3 - (a - c)**3) / 3
    assert solid.volume() == pytest.approx(expected, rel=1e-9)


def test_prism_taper_narrows_the_flats():
    a, h, angle = 10.0, 10.0, 10.0
    solid = PrismFeature("p", "p", 2 * a, h, taper_angle=angle).build_solid()
    top = a - h * math.tan(math.radians(angle))
    a0, a1 = _prism_area(a), _prism_area(top)
    assert solid.volume() == pytest.approx(h / 3 * (a0 + a1 + math.sqrt(a0 * a1)), rel=1e-6)


def test_tapered_shelled_rounded_hexagon_builds():
    solid = PrismFeature("p", "p", 30.0, 20.0, taper_angle=5.0, wall_thickness=2.0, outer_round=2.0,
                         inner_round=1.0).build_solid()
    assert solid.genus() == 0 and 0 < solid.volume() < _prism_area(15) * 20


def test_prism_document_add_edit_save_load_and_undo(tmp_path):
    doc = Document()
    body = doc.add_prism(20.0, 10.0, wall_thickness=1.0)
    feat = doc.timeline.features[-1]
    assert body.name == "Hexagon 1" and feat.feature_type == "prism"
    assert doc.edit_feature(0, across_flats=30.0, sides=8)
    assert doc.bodies[body.body_id].manifold.volume() == pytest.approx(_prism_area(15, 8) * 10 - _prism_area(14, 8) * 9, rel=1e-9)
    path = tmp_path / "hex.omacad"
    Exporter.save_project(doc, str(path))
    loaded = Exporter.load_project(str(path))
    again = loaded.timeline.features[0]
    assert (again.feature_type, again.sides, again.across_flats, again.wall_thickness) == ("prism", 8, 30.0, 1.0)
    doc.undo()
    assert doc.timeline.features[0].across_flats == 20.0 and doc.timeline.features[0].sides == 6
