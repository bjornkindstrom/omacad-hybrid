"""Tests for Box and Cylinder origin placement and on-face positioning."""

import numpy as np
import pytest
from omacad.model.document import Document
from omacad.model.features.primitives import BoxFeature, CylinderFeature
from omacad.model.sketch import SketchPlane


def test_box_bottom_center():
    doc = Document()
    b = doc.add_box(40, 20, 10, center="bottom_center")
    mesh = b.render_mesh
    # Bottom should be at Z=0, top at Z=10
    assert abs(mesh.bounds_min[2] - 0.0) < 1e-4
    assert abs(mesh.bounds_max[2] - 10.0) < 1e-4
    # Centered on XY around 0
    assert abs(mesh.bounds_min[0] - (-20.0)) < 1e-4
    assert abs(mesh.bounds_max[0] - 20.0) < 1e-4
    assert abs(mesh.bounds_min[1] - (-10.0)) < 1e-4
    assert abs(mesh.bounds_max[1] - 10.0) < 1e-4


def test_cylinder_bottom_center():
    doc = Document()
    c = doc.add_cylinder(15, 30, center="bottom_center")
    mesh = c.render_mesh
    # Bottom should be at Z=0, top at Z=30
    assert abs(mesh.bounds_min[2] - 0.0) < 1e-4
    assert abs(mesh.bounds_max[2] - 30.0) < 1e-4
    # Centered on XY around 0
    assert abs(mesh.bounds_min[0] - (-15.0)) < 1e-4
    assert abs(mesh.bounds_max[0] - 15.0) < 1e-4


def test_box_on_horizontal_face():
    doc = Document()
    # Create base box
    base = doc.add_box(100, 100, 20, center="bottom_center")
    
    # Place a smaller box on top face (Z=20)
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
    # Create base box
    base = doc.add_box(100, 100, 40, center="bottom_center")
    
    # Vertical side face at X=50 pointing +X
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
    # Normal is +X, so bottom of cylinder starts at X=50, top reaches X=75
    assert abs(mesh.bounds_min[0] - 50.0) < 1e-4
    assert abs(mesh.bounds_max[0] - 75.0) < 1e-4


def test_primitive_translation_is_saved_with_the_primitive_step():
    from omacad.io.exporter import Exporter

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
