"""
Tests for Smart Joints (#231):
- Revolute (hinge) & Slider joint creation, limits clamping, and Rodrigues rotation
- Smart edge / cylinder inference
- Project file round-trip serialization
- Articulation of real assembly from Request #231 (box with hinged lid)
"""

from pathlib import Path
import math
import tempfile
import os
import numpy as np
import pytest

from omacad.model.document import Document
from omacad.model.features.joint import JointFeature, infer_joint_from_edge, axis_angle_matrix, slider_matrix
from omacad.io.exporter import Exporter

DATA = Path(__file__).parent / "data"


def test_axis_angle_matrix_rotation():
    # 90 degrees around Y axis through origin
    m = axis_angle_matrix([0, 1, 0], 90.0, pivot=[0, 0, 0])
    pt = np.array([10.0, 0.0, 0.0, 1.0])
    res = m @ pt
    assert np.allclose(res[:3], [0.0, 0.0, -10.0], atol=1e-5)

    # 90 degrees around Y axis through pivot (5, 0, 0)
    m = axis_angle_matrix([0, 1, 0], 90.0, pivot=[5, 0, 0])
    pt = np.array([10.0, 0.0, 0.0, 1.0])
    res = m @ pt
    assert np.allclose(res[:3], [5.0, 0.0, -5.0], atol=1e-5)


def test_slider_matrix():
    m = slider_matrix([0, 0, 1], 25.0)
    pt = np.array([1.0, 2.0, 3.0, 1.0])
    res = m @ pt
    assert np.allclose(res[:3], [1.0, 2.0, 28.0], atol=1e-5)


def test_joint_limits_clamping():
    jf = JointFeature(
        "j1", "Hinge 1", "body_1",
        joint_type="revolute",
        origin=(0, 0, 0), axis=(0, 0, 1),
        value=45.0,
        limits_enabled=True,
        min_limit=0.0, max_limit=90.0,
    )
    assert jf.value == 45.0

    # Setting value within limits
    jf.set_value(60.0)
    assert jf.value == 60.0

    # Setting value below min
    jf.set_value(-30.0)
    assert jf.value == 0.0

    # Setting value above max
    jf.set_value(150.0)
    assert jf.value == 90.0


def test_document_add_joint_and_recompute():
    doc = Document()
    doc.add_box(20.0, 20.0, 20.0)
    bid = list(doc.bodies.keys())[0]

    # Add a revolute joint around top edge (0, 0, 20) with Y axis
    jf = doc.add_joint(
        bid, joint_type="revolute",
        origin=(0.0, 0.0, 20.0), axis=(0.0, 1.0, 0.0),
        value=45.0, min_limit=0.0, max_limit=120.0
    )
    assert jf is not None
    assert len(doc.joints) == 1

    # Live update joint value via doc
    doc.set_joint_value(jf.feature_id, 90.0)
    assert jf.value == 90.0
    b = doc.bodies[bid]
    bb = b.manifold.bounding_box()
    # At 90 deg rotation around (0,0,20) with Y axis, the box swings from X=[0..20] to Z=[0..20]
    assert bb[2] <= 20.0 + 1e-4


def test_joint_project_serialization():
    doc = Document()
    doc.add_cylinder(10.0, 30.0)
    bid = list(doc.bodies.keys())[0]

    doc.add_joint(
        bid, joint_type="slider",
        origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0),
        value=15.0, min_limit=-10.0, max_limit=50.0
    )

    with tempfile.NamedTemporaryFile(suffix=".omacad", delete=False) as tf:
        path = tf.name

    try:
        Exporter.save_project(doc, path)
        loaded = Exporter.load_project(path)
        assert len(loaded.joints) == 1
        j = loaded.joints[0]
        assert j.joint_type == "slider"
        assert j.value == 15.0
        assert j.min_limit == -10.0
        assert j.max_limit == 50.0
        assert np.allclose(j.axis, [0.0, 0.0, 1.0])
    finally:
        os.remove(path)


def test_smart_joint_on_request_231_assembly():
    """Verify smart joint articulation on Björn's model from Request #231."""
    doc = Exporter.load_project(str(DATA / "request_231_smart_joints.omacad"))
    lid = doc.bodies["body_extrude_2"]
    box = doc.bodies["body_extrude_17"]

    # In Request #231, Move Extrude 1 (9) rotated Extrude 1 to 66° around [199.6593, 599.6594, 0.0] with ry.
    # Now we create a smart Joint on the lid along the hinge axis [0, 1, 0] at [199.6593, 0.0, 0.0]
    jf = doc.add_joint(
        "body_extrude_2",
        ref_body_id="body_extrude_17",
        joint_type="revolute",
        origin=[199.6593, 0.0, 0.0],
        axis=[0.0, 1.0, 0.0],
        value=0.0,
        limits_enabled=True,
        min_limit=0.0,
        max_limit=115.0,
    )
    assert jf is not None

    # Articulate lid closed (0 deg)
    doc.set_joint_value(jf.feature_id, 0.0)
    assert jf.value == 0.0

    # Articulate lid to 66 deg (as user wanted)
    doc.set_joint_value(jf.feature_id, 66.0)
    assert jf.value == 66.0

    # Articulate lid fully open (115 deg)
    doc.set_joint_value(jf.feature_id, 115.0)
    assert jf.value == 115.0

    # Check bounds at 115 deg: lid is upright / tilted back
    mesh = lid.manifold.to_mesh()
    assert len(mesh.vert_properties) > 0
    assert mesh.vert_properties[:, 2].max() > 200.0


def test_joint_dialog_headless():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from omacad.ui.dialogs.joint_dlg import JointDialog
    doc = Document()
    doc.add_box(10.0, 10.0, 10.0)
    bid = list(doc.bodies.keys())[0]

    dlg = JointDialog(doc, preselected_body_id=bid)
    assert dlg.target_body_id() == bid
    assert dlg.joint_type() == "revolute"

    # Test limits
    dlg.spn_min.setValue(10.0)
    dlg.spn_max.setValue(100.0)
    limits_en, mn, mx = dlg.limits()
    assert limits_en is True
    assert mn == 10.0
    assert mx == 100.0

    # Test scrubber slider updates current value
    dlg.slider.setValue(500) # midpoint -> 55.0 deg
    assert abs(dlg.current_value() - 55.0) < 1.0


def test_infer_joint_from_edge():
    # Straight line edge
    class DummyLineEdge:
        kind = "line"
        p0 = [10.0, 20.0, 0.0]
        p1 = [10.0, 50.0, 0.0]

    jtype, orig, axis = infer_joint_from_edge(DummyLineEdge())
    assert jtype == "revolute"
    assert np.allclose(orig, [10.0, 20.0, 0.0])
    assert np.allclose(axis, [0.0, 1.0, 0.0])

    # Circular edge
    class DummyCircleEdge:
        kind = "circle"
        center = [0.0, 0.0, 15.0]
        axis = [0.0, 0.0, 1.0]

    jtype, orig, axis = infer_joint_from_edge(DummyCircleEdge())
    assert jtype == "revolute"
    assert np.allclose(orig, [0.0, 0.0, 15.0])
    assert np.allclose(axis, [0.0, 0.0, 1.0])


def test_joint_gizmo_methods():
    from omacad.ui.viewport.gizmo_mixin import GizmoMixin

    class DummyViewport(GizmoMixin):
        def __init__(self):
            self.distance = 100.0
            self.joint_gizmo = None

        def update(self):
            pass

        def world_to_screen(self, pt):
            # Simple mock projection
            return [pt[0] + 100.0, pt[1] + 100.0]

        def get_matrices(self):
            return np.eye(4), np.eye(4), np.eye(4)

        def width(self):
            return 800

        def height(self):
            return 600

    vp = DummyViewport()
    vp.set_joint_gizmo(
        origin=[0.0, 0.0, 0.0],
        axis=[0.0, 0.0, 1.0],
        joint_type="revolute",
        value=30.0,
        min_limit=0.0,
        max_limit=90.0
    )
    assert vp.joint_gizmo is not None
    assert vp.joint_gizmo["value"] == 30.0

    # Test hit near origin screen spot (100, 100)
    assert vp._joint_gizmo_hit(105, 105) is True
    assert vp._joint_gizmo_hit(500, 500) is False

    vp.clear_joint_gizmo()
    assert vp.joint_gizmo is None

